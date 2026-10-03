"""Score a downloaded session-brief glance-test receipt against grades.jsonl.

State is exact. Waiting-on and topic use a deliberately conservative,
deterministic content-term match: blank/nonblank must agree; answers for short
truth strings must contain every content term; longer answers need at least
50% truth-term recall and 25% answer-term precision. Confidence is reported as
answered-only because the oracle has no confidence truth field.

Usage::

    python evals/session_brief/glance_score.py /path/to/glance-test.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable, NoReturn


STATES = {"done", "waiting_on_user", "running", "abandoned"}
STOP_WORDS = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "for", "from", "in", "into", "is", "it", "of", "on", "or", "that", "the", "their", "this",
    "to", "was", "what", "when", "with", "you", "your",
}


def _fail(message: str) -> NoReturn:
    raise SystemExit(f"glance score failed: {message}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"could not read JSON {path}: {exc}")
    if not isinstance(payload, dict):
        _fail(f"receipt must be a JSON object: {path}")
    return payload


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _fail(f"could not read {path}: {exc}")
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail(f"invalid JSON in {path}:{line_number}: {exc}")
        if not isinstance(row, dict):
            _fail(f"expected an object in {path}:{line_number}")
        yield row


def _find_grades(receipt: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            _fail(f"grades file does not exist: {path}")
        return path
    current = receipt.resolve().parent
    candidates: list[Path] = []
    for _ in range(6):
        candidates.append(current / "grades.jsonl")
        if current.parent == current:
            break
        current = current.parent
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    _fail(f"could not find grades.jsonl; searched {searched}; pass --grades explicitly")


def _key(fixture_id: str, message_count: int) -> str:
    return f"{fixture_id}-{message_count}"


def _load_truth(path: Path, variant: str) -> dict[str, dict[str, str | int]]:
    truth: dict[str, dict[str, str | int]] = {}
    for row in _iter_jsonl(path):
        if row.get("variant") != variant:
            continue
        fixture_id = row.get("fixture_id")
        message_count = row.get("message_count")
        grade = row.get("grade")
        raw = grade.get("truth") if isinstance(grade, dict) else None
        if not isinstance(fixture_id, str) or not isinstance(message_count, int) or not isinstance(raw, dict):
            _fail(f"invalid truth row in {path}")
        state = raw.get("state")
        waiting_on = raw.get("waiting_on", "")
        topic = raw.get("topic", "")
        if state not in STATES or not isinstance(waiting_on, str) or not isinstance(topic, str):
            continue
        key = _key(fixture_id, message_count)
        if key in truth:
            _fail(f"duplicate truth row for {key}")
        truth[key] = {
            "fixture_id": fixture_id,
            "message_count": message_count,
            "state": state,
            "waiting_on": waiting_on,
            "topic": topic,
        }
    if not truth:
        _fail(f"no usable {variant!r} truth rows found in {path}")
    return truth


def _terms(value: Any) -> set[str]:
    if not isinstance(value, str):
        return set()
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return {
        token
        for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
        if token not in STOP_WORDS and len(token) > 1
    }


def _text_match(answer: Any, expected: str) -> tuple[bool, str]:
    answer_terms = _terms(answer)
    expected_terms = _terms(expected)
    if not expected_terms:
        ok = not answer_terms
        return ok, "blank matches" if ok else "expected blank"
    if not answer_terms:
        return False, "answer is blank"
    overlap = answer_terms & expected_terms
    if len(expected_terms) <= 3:
        ok = overlap == expected_terms
        return ok, f"{len(overlap)}/{len(expected_terms)} content terms"
    recall = len(overlap) / len(expected_terms)
    precision = len(overlap) / len(answer_terms)
    ok = recall >= 0.5 and precision >= 0.25
    return ok, f"{len(overlap)}/{len(expected_terms)} recall, {len(overlap)}/{len(answer_terms)} precision"


def _state(value: Any) -> str:
    if value == "waiting":
        return "waiting_on_user"
    return value if isinstance(value, str) else ""


def _validate_answers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schema_version") != 1:
        _fail("receipt schema_version must be 1")
    answers = payload.get("answers")
    if not isinstance(answers, list):
        _fail("receipt answers must be a list")
    if len(answers) != 10:
        _fail(f"receipt must contain exactly 10 answers, got {len(answers)}")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, answer in enumerate(answers):
        if not isinstance(answer, dict):
            _fail(f"answer {index} must be an object")
        fixture_id = answer.get("fixture_id")
        message_count = answer.get("message_count")
        key = answer.get("key")
        if not isinstance(fixture_id, str) or not isinstance(message_count, int):
            _fail(f"answer {index} is missing fixture_id/message_count")
        expected_key = _key(fixture_id, message_count)
        if key != expected_key:
            _fail(f"answer {index} key {key!r} does not match {expected_key!r}")
        if key in seen:
            _fail(f"duplicate answer key {key}")
        seen.add(key)
        if _state(answer.get("state")) not in STATES:
            _fail(f"answer {key} has invalid state")
        if not isinstance(answer.get("waiting_on"), str) or not isinstance(answer.get("topic"), str):
            _fail(f"answer {key} must contain string waiting_on/topic")
        confidence = answer.get("confidence")
        if not isinstance(confidence, int) or not 1 <= confidence <= 5:
            _fail(f"answer {key} confidence must be an integer from 1 to 5")
        validated.append(answer)
    return validated


def _score(payload: dict[str, Any], truth: dict[str, dict[str, str | int]]) -> dict[str, Any]:
    answers = _validate_answers(payload)
    answer_keys = {answer["key"] for answer in answers}
    truth_keys = set(truth)
    if answer_keys != truth_keys:
        missing = sorted(truth_keys - answer_keys)
        extra = sorted(answer_keys - truth_keys)
        _fail(f"receipt keys do not match selected truth; missing={missing}, extra={extra}")

    rows: list[dict[str, Any]] = []
    for answer in answers:
        key = answer["key"]
        expected = truth[key]
        state_ok = _state(answer["state"]) == expected["state"]
        waiting_ok, waiting_detail = _text_match(answer["waiting_on"], str(expected["waiting_on"]))
        topic_ok, topic_detail = _text_match(answer["topic"], str(expected["topic"]))
        rows.append({
            "key": key,
            "state": state_ok,
            "waiting_on": waiting_ok,
            "topic": topic_ok,
            "confidence_answered": True,
            "details": {"waiting_on": waiting_detail, "topic": topic_detail},
        })

    def count(field: str) -> int:
        return sum(1 for row in rows if row[field])

    factual_total = len(rows) * 3
    factual_correct = sum(count(field) for field in ("state", "waiting_on", "topic"))
    return {
        "fixtures": len(rows),
        "questions": {
            "state": {"correct": count("state"), "total": len(rows)},
            "waiting_on": {"correct": count("waiting_on"), "total": len(rows)},
            "topic": {"correct": count("topic"), "total": len(rows)},
            "confidence": {"answered": count("confidence_answered"), "total": len(rows), "truth_scored": False},
        },
        "overall_factual": {"correct": factual_correct, "total": factual_total},
        "rows": rows,
    }


def _percent(correct: int, total: int) -> str:
    return f"{(correct / total * 100):5.1f}%" if total else "  0.0%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--grades", type=Path, default=None, help="grades.jsonl (auto-discovered by default)")
    parser.add_argument("--variant", default=None, help="grades variant; defaults to the receipt variant")
    parser.add_argument("--details", action="store_true", help="print per-fixture mismatch details")
    args = parser.parse_args(argv)
    receipt_path = args.receipt.expanduser().resolve()
    payload = _load_json(receipt_path)
    variant = args.variant or payload.get("variant", "baseline")
    if not isinstance(variant, str):
        _fail("receipt variant must be a string")
    grades_path = _find_grades(receipt_path, args.grades)
    result = _score(payload, _load_truth(grades_path, variant))

    print("Session brief glance-test score")
    print(f"Fixtures scored: {result['fixtures']}")
    print("Question       Correct / answered    Percent")
    print("-------------- -------------------- --------")
    for label, field in (("State", "state"), ("Waiting on", "waiting_on"), ("Topic", "topic")):
        item = result["questions"][field]
        print(f"{label:<14} {item['correct']:>7} / {item['total']:<10} {_percent(item['correct'], item['total'])}")
    confidence = result["questions"]["confidence"]
    print(f"{'Confidence':<14} {confidence['answered']:>7} / {confidence['total']:<10} {_percent(confidence['answered'], confidence['total'])} (response rate; not truth-scored)")
    overall = result["overall_factual"]
    print(f"Overall factual: {overall['correct']} / {overall['total']} ({_percent(overall['correct'], overall['total']).strip()})")
    if args.details:
        for row in result["rows"]:
            mismatches = [field for field in ("state", "waiting_on", "topic") if not row[field]]
            if mismatches:
                print(f"- {row['key']}: incorrect {', '.join(mismatches)} ({row['details']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
