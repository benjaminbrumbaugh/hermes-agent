"""Session-brief content eval: generate briefs over the fixture corpus, then grade them against the transcript.

Two phases, both resumable and both driven to Space Bunny over OpenRouter by default:

``generate``
    For each fixture, replay the conversation as the agent would have seen it — one brief refresh per
    completed user turn, each fed the previous brief plus only the new turns (the real iterative path in
    ``agent.session_brief.generate_brief``). Snapshots are kept at every turn so graders can judge the brief
    a returning user would actually have seen mid-conversation, not only the final one. A *variant* swaps
    the system prompt (and optionally schema) so prompts compete on identical inputs.

``grade``
    For each (variant, fixture, snapshot) a grader with the full transcript-to-that-point scores the brief
    against ``rubric.md``: every failure mode gets ``present: bool``, a one-line ``evidence`` citing the
    transcript, and the glance answers (done / waiting-on-me / running / topic) it would give from the brief
    alone versus from the transcript. Output is JSONL; ``report.py`` aggregates. Numbers are never typed.

Usage::

    .venv/bin/python evals/session_brief/runner.py generate --corpus temp/session-brief-corpus --variants baseline --out temp/session-brief-eval/run1 --concurrency 128
    .venv/bin/python evals/session_brief/runner.py grade    --out temp/session-brief-eval/run1 --concurrency 128
    .venv/bin/python evals/session_brief/report.py temp/session-brief-eval/run1

Variants live in ``variants/<name>.md`` (the whole system prompt). ``baseline`` is the shipped prompt,
exported from ``agent.session_brief`` so the eval can never drift from production.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent import session_brief as sb  # noqa: E402

HERE = Path(__file__).resolve().parent
VARIANTS = HERE / "variants"
DEFAULT_MODEL = "stealth/space-bunny-alpha"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
GRADER_MAX_TOKENS = 1800
_print_lock = threading.Lock()

# Archived Lane B prompts and sidecars describe v1, not the production task contract.
# Keep their declared comparison base explicit while baseline follows production.
_CANONICAL_FIELDS = ("goal", "status", "completed", "blockers", "decisions")
_ARCHIVED_PROPERTIES = {
    "goal": {"type": "string"}, "status": {"type": "string"},
    **{field: {"type": "array", "items": {"type": "string"}}
       for field in ("completed", "blockers", "decisions")},
}


@dataclass(frozen=True)
class VariantSpec:
    """Eval-only content contract; production remains the baseline source of truth."""

    name: str
    system_prompt: str
    response_format: Dict[str, Any]
    normalize: Callable[..., Dict[str, Any]]
    schema_delta: Dict[str, Any]
    fingerprint: str


# --------------------------------------------------------------------------- OpenRouter transport

def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    env = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENROUTER_API_KEY not found")


def chat(messages: List[Dict[str, str]], *, model: str, max_tokens: int, response_format: Optional[dict] = None,
         retries: int = 4) -> Dict[str, Any]:
    """One chat completion; returns {content, usage, latency_s}. 200-with-error bodies count as failures."""
    body: Dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens, "reasoning": {"effort": "low"}}
    if response_format:
        body["response_format"] = response_format
    data = json.dumps(body).encode()
    delay = 2.0
    for attempt in range(retries + 1):
        started = time.monotonic()
        req = urllib.request.Request(OPENROUTER, data=data, headers={
            "Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json",
            "HTTP-Referer": "https://hermes-agent.nousresearch.com", "X-Title": "hermes session-brief eval",
        })
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                payload = json.loads(resp.read())
            if "error" in payload:
                raise RuntimeError(f"upstream error: {payload['error']}")
            choice = payload["choices"][0]
            return {
                "content": choice["message"].get("content") or "",
                "finish_reason": choice.get("finish_reason"),
                "usage": payload.get("usage") or {},
                "latency_s": round(time.monotonic() - started, 2),
            }
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError, json.JSONDecodeError, TimeoutError) as exc:
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------- variants

def _stable_fingerprint(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _string_list(value: Any, cap: int) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, (str, int, float)) and str(item).strip()][:cap]


def _normalize_variant(parsed: Dict[str, Any], *, message_count: int,
                       field_map: Dict[str, Optional[str]]) -> Dict[str, Any]:
    """Project a native variant response into the stable renderer-facing eval view."""
    goal_source = field_map.get("goal", "goal")
    status_source = field_map.get("status", "status")
    completed_source = field_map.get("completed", "completed")
    blockers_source = field_map.get("blockers", "blockers")
    decisions_source = field_map.get("decisions", "decisions")
    status = str(parsed.get(status_source) or "").strip() if status_source else ""
    blockers = _string_list(parsed.get(blockers_source), 6) if blockers_source else []
    waiting_on = parsed.get("waiting_on")
    if not blockers and isinstance(waiting_on, str) and waiting_on.strip():
        blockers = [waiting_on.strip()]
    return {
        "version": 1,
        "goal": str(parsed.get(goal_source) or "").strip() if goal_source else "",
        "status": status,
        "completed": _string_list(parsed.get(completed_source), 8) if completed_source else [],
        "blockers": blockers,
        "decisions": _string_list(parsed.get(decisions_source), 6) if decisions_source else [],
        "updated_at": time.time(),
        "message_count": int(message_count),
    }


def _load_schema_sidecar(name: str) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Optional[str]]]:
    path = VARIANTS / f"{name}.schema.json"
    if not path.exists():
        response_format = {"type": "json_schema", "json_schema": {
            "name": f"session_brief_{name}", "strict": True, "schema": {
                "type": "object", "properties": _ARCHIVED_PROPERTIES,
                "required": list(_ARCHIVED_PROPERTIES), "additionalProperties": False,
            },
        }}
        return response_format, {"added": {}, "removed": []}, {field: field for field in _CANONICAL_FIELDS}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid schema sidecar {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("schema"), dict):
        raise SystemExit(f"schema sidecar {path} must contain an object-valued schema")
    schema = payload["schema"]
    properties = schema.get("properties")
    if (
        schema.get("type") != "object"
        or not isinstance(properties, dict)
        or schema.get("additionalProperties") is not False
    ):
        raise SystemExit(f"schema sidecar {path} must be a strict object schema")
    base_properties = _ARCHIVED_PROPERTIES
    shared = set(properties) & set(base_properties)
    changed = sorted(key for key in shared if properties[key] != base_properties[key])
    if changed:
        raise SystemExit(f"schema sidecar {path} changes production fields: {changed}")
    actual_added = {key: properties[key] for key in sorted(set(properties) - set(base_properties))}
    actual_removed = sorted(set(base_properties) - set(properties))
    delta = payload.get("schema_delta")
    if not isinstance(delta, dict) or delta.get("added") != actual_added or delta.get("removed") != actual_removed:
        raise SystemExit(
            f"schema sidecar {path} has inaccurate schema_delta; expected added={actual_added!r}, "
            f"removed={actual_removed!r}"
        )
    required = schema.get("required")
    if not isinstance(required, list) or set(required) != set(properties):
        raise SystemExit(f"schema sidecar {path} must require exactly every declared property")
    mapping = payload.get("normalization") or {}
    if not isinstance(mapping, dict):
        raise SystemExit(f"schema sidecar {path} normalization must be an object")
    field_map: Dict[str, Optional[str]] = {}
    for field in _CANONICAL_FIELDS:
        source = mapping.get(field, field)
        if source is not None and source not in properties:
            raise SystemExit(f"schema sidecar {path} maps {field!r} to missing field {source!r}")
        field_map[field] = source
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": f"session_brief_{name}", "strict": True, "schema": schema},
    }
    return response_format, delta, field_map


def load_variant_spec(name: str) -> VariantSpec:
    if name == "baseline":
        return VariantSpec(
            name=name,
            system_prompt=sb._SYSTEM_PROMPT,
            response_format=sb._RESPONSE_FORMAT,
            normalize=sb.normalize_brief,
            schema_delta={"added": {}, "removed": []},
            fingerprint=_stable_fingerprint(name, sb._SYSTEM_PROMPT, sb._RESPONSE_FORMAT, "production-normalizer"),
        )
    prompt_path = VARIANTS / f"{name}.md"
    if not prompt_path.exists():
        raise SystemExit(f"unknown variant {name!r}; add {prompt_path}")
    system_prompt = prompt_path.read_text(encoding="utf-8").strip()
    response_format, schema_delta, field_map = _load_schema_sidecar(name)

    def normalize(parsed: Dict[str, Any], message_count: int) -> Dict[str, Any]:
        brief = _normalize_variant(parsed, message_count=message_count, field_map=field_map)
        brief["_variant_fields"] = dict(parsed)
        return brief

    fingerprint = _stable_fingerprint(name, system_prompt, response_format, schema_delta, field_map)
    return VariantSpec(name, system_prompt, response_format, normalize, schema_delta, fingerprint)


def load_variant(name: str) -> str:
    """Compatibility helper retained for callers that need only the prompt text."""
    return load_variant_spec(name).system_prompt


def _descriptor_fingerprint(specs: Iterable[VariantSpec]) -> str:
    return _stable_fingerprint([(spec.name, spec.fingerprint) for spec in specs])


def _generate_one(previous: Optional[Dict[str, Any]], delta: List[Dict[str, Any]], *, spec: VariantSpec,
                  model: str, message_count: int) -> Optional[Dict[str, Any]]:
    delta_text = sb._render_brief_input(delta)
    if not delta_text.strip():
        return None
    messages = sb._build_messages(previous, delta_text)
    messages[0] = {"role": "system", "content": spec.system_prompt}
    if previous and spec.name != "baseline":
        messages[1]["content"] = (
            f"Previous variant brief (untrusted draft):\n{json.dumps(previous.get('_variant_fields', previous), ensure_ascii=False)}\n\n"
            f"New conversation evidence since that brief:\n{delta_text}"
        )
    reply = chat(messages, model=model, max_tokens=sb.BRIEF_MAX_TOKENS, response_format=spec.response_format)
    parsed = sb._parse_brief(reply["content"])
    if parsed is None:
        return {"_error": "unparseable", "_raw": reply["content"][:500], "_usage": reply["usage"]}
    if spec.name == "baseline":
        brief = spec.normalize(parsed, message_count=message_count, previous=previous)
    else:
        brief = spec.normalize(parsed, message_count=message_count)
    brief["completed"] = sb._evidence_backed_completed(brief, delta_text, previous=previous)
    brief["_usage"] = reply["usage"]
    brief["_latency_s"] = reply["latency_s"]
    return brief


def _turn_boundaries(messages: List[Dict[str, Any]]) -> List[int]:
    """Index just past each completed assistant turn (the finalizer's hook point)."""
    bounds = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and not msg.get("tool_calls"):
            nxt = messages[i + 1] if i + 1 < len(messages) else None
            if nxt is None or nxt.get("role") == "user":
                bounds.append(i + 1)
    return bounds


def generate_fixture(fixture: Dict[str, Any], spec: VariantSpec, model: str, out_dir: Path,
                     snapshots: int) -> Dict[str, Any]:
    variant = spec.name
    out_path = out_dir / variant / f"{fixture['fixture_id']}.json"
    if out_path.exists():
        record = json.loads(out_path.read_text(encoding="utf-8"))
        if record.get("descriptor_fingerprint") != spec.fingerprint:
            raise ValueError(f"stale descriptor for {variant}/{fixture['fixture_id']}; start a fresh eval run")
        return record
    messages = fixture["messages"]
    bounds = _turn_boundaries(messages)
    # Sample evenly so long conversations don't dominate the grader bill; the last boundary always counts.
    if snapshots and len(bounds) > snapshots:
        step = len(bounds) / snapshots
        picked = sorted({bounds[int(i * step)] for i in range(snapshots)} | {bounds[-1]})
    else:
        picked = bounds
    previous: Optional[Dict[str, Any]] = None
    seen = 0
    record: Dict[str, Any] = {
        "fixture_id": fixture["fixture_id"], "variant": variant, "model": model,
        "descriptor_fingerprint": spec.fingerprint, "snapshots": [],
    }
    for bound in picked:
        delta = messages[seen:bound]
        brief = _generate_one(previous, delta, spec=spec, model=model, message_count=bound)
        if brief and "_error" not in brief:
            previous = brief
            seen = bound
        record["snapshots"].append({"message_count": bound, "brief": brief})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return record


# --------------------------------------------------------------------------- grading

def _grader_prompt(rubric: str) -> str:
    return (
        "You are grading a 'session brief': a short sidebar panel a user glances at when returning to a "
        "conversation with an AI agent, to learn in about two seconds whether the work is DONE, WAITING ON THEM, "
        "STILL RUNNING, or what it was ABOUT. You have the full transcript up to the moment the brief was written. "
        "Judge the brief ONLY against that transcript. Be adversarial: a brief that sounds fine but would make the "
        "returning user misjudge the state is a failure.\n\n"
        f"RUBRIC (failure modes, each with an id):\n{rubric}\n\n"
        "Reply with ONLY a JSON object:\n"
        '{"truth": {"state": "done|waiting_on_user|running|abandoned|unclear", "waiting_on": string, "topic": string},\n'
        ' "from_brief": {"state": "done|waiting_on_user|running|abandoned|unclear", "waiting_on": string, "topic": string},\n'
        ' "failures": [{"id": string, "evidence": string}],\n'
        ' "glance_score": 0-5, "notes": string}\n'
        "truth = what the transcript shows; from_brief = what a user reading ONLY the brief would conclude. "
        "List every rubric id that applies, with evidence quoting the brief and/or transcript. glance_score 5 = the "
        "four answers are correct and obvious in the first two lines; 0 = actively misleading."
    )


def grade_snapshot(fixture: Dict[str, Any], record: Dict[str, Any], snap: Dict[str, Any], rubric: str, model: str,
                   transcript_chars: int) -> Dict[str, Any]:
    brief = snap["brief"]
    base = {"fixture_id": fixture["fixture_id"], "variant": record["variant"], "message_count": snap["message_count"]}
    if not brief or "_error" in (brief or {}):
        return {**base, "grade": None, "generation_error": (brief or {}).get("_error", "none")}
    transcript = sb._render_turn_delta(fixture["messages"][: snap["message_count"]])
    if len(transcript) > transcript_chars:
        transcript = transcript[: transcript_chars // 2] + "\n\n[... middle elided for length ...]\n\n" + transcript[-transcript_chars // 2:]
    # Mirror BriefPane's real hierarchy and conditional sections. Showing empty arrays or the retired
    # decisions field to the grader would create density failures that the user never sees.
    shown = {"goal": brief.get("goal", ""), "status": brief.get("status", "")}
    if brief.get("blockers"):
        shown["blockers"] = brief["blockers"]
    if brief.get("tasks"):
        shown["tasks"] = brief["tasks"]
    elif brief.get("version", 1) < 3 and brief.get("completed"):
        shown["completed"] = brief["completed"]
    user = f"TRANSCRIPT:\n{transcript}\n\nBRIEF (as the sidebar would show it, sections in this order):\n{json.dumps(shown, ensure_ascii=False, indent=1)}"
    reply = chat([{"role": "system", "content": _grader_prompt(rubric)}, {"role": "user", "content": user}],
                 model=model, max_tokens=GRADER_MAX_TOKENS, response_format={"type": "json_object"})
    try:
        grade = json.loads(reply["content"])
    except json.JSONDecodeError:
        grade = {"_unparseable": reply["content"][:500]}
    return {**base, "grade": grade, "grader_usage": reply["usage"]}


# --------------------------------------------------------------------------- commands

def _load_corpus(corpus: Path, limit: Optional[int]) -> List[Dict[str, Any]]:
    index = json.loads((corpus / "index.json").read_text(encoding="utf-8"))
    fixtures = []
    for entry in index[: limit or None]:
        fixtures.append(json.loads((corpus / f"{entry['fixture_id']}.json").read_text(encoding="utf-8")))
    return fixtures


def _run(jobs: Iterable, fn, concurrency: int, label: str) -> List[Any]:
    jobs = list(jobs)
    results: List[Any] = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(fn, *job) for job in jobs]
        for fut in cf.as_completed(futures):
            done += 1
            try:
                results.append(fut.result())
            except Exception as exc:  # one failed job must not sink the run
                results.append({"error": repr(exc)})
            if done % 10 == 0 or done == len(jobs):
                with _print_lock:
                    print(f"[{label}] {done}/{len(jobs)}", file=sys.stderr)
    return results


def cmd_generate(args: argparse.Namespace) -> int:
    fixtures = _load_corpus(args.corpus, args.limit)
    specs = [load_variant_spec(name) for name in args.variants]
    if len({spec.name for spec in specs}) != len(specs):
        raise SystemExit("variants must be unique")
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps({
        "corpus": str(args.corpus), "variants": args.variants, "model": args.model, "snapshots": args.snapshots,
        "fixtures": [f["fixture_id"] for f in fixtures], "started_at": time.time(),
        "descriptor_fingerprint": _descriptor_fingerprint(specs),
    }, indent=1), encoding="utf-8")
    jobs = []
    for spec in specs:
        variant = spec.name
        (out / variant).mkdir(parents=True, exist_ok=True)
        (out / variant / "_system_prompt.md").write_text(spec.system_prompt, encoding="utf-8")
        for fixture in fixtures:
            jobs.append((fixture, spec, args.model, out, args.snapshots))
    results = _run(jobs, generate_fixture, args.concurrency, "generate")
    errors = [r for r in results if "error" in r]
    print(json.dumps({"generated": len(results) - len(errors), "errors": errors[:5]}, indent=1))
    return 1 if errors else 0


def cmd_grade(args: argparse.Namespace) -> int:
    run = json.loads((args.out / "run.json").read_text(encoding="utf-8"))
    specs = [load_variant_spec(name) for name in run["variants"]]
    descriptor_fingerprint = _descriptor_fingerprint(specs)
    if run.get("descriptor_fingerprint") != descriptor_fingerprint:
        raise SystemExit("run descriptor does not match current variant prompts/schemas; regenerate the run")
    corpus = Path(run["corpus"])
    rubric = (HERE / "rubric.md").read_text(encoding="utf-8")
    fixtures = {f["fixture_id"]: f for f in _load_corpus(corpus, None) if f["fixture_id"] in set(run["fixtures"])}
    grades_path = args.out / "grades.jsonl"
    already = set()
    if grades_path.exists():
        for line in grades_path.read_text(encoding="utf-8").splitlines():
            g = json.loads(line)
            already.add((g["variant"], g["fixture_id"], g["message_count"]))
    jobs = []
    for variant in run["variants"]:
        for path in sorted((args.out / variant).glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            spec = next(spec for spec in specs if spec.name == variant)
            if record.get("descriptor_fingerprint") != spec.fingerprint:
                raise SystemExit(f"stale descriptor in {path}; regenerate the run")
            fixture = fixtures.get(record["fixture_id"])
            if not fixture:
                continue
            for snap in record["snapshots"]:
                if (variant, record["fixture_id"], snap["message_count"]) in already:
                    continue
                jobs.append((fixture, record, snap, rubric, args.grader_model, args.transcript_chars))
    results = _run(jobs, grade_snapshot, args.concurrency, "grade")
    with grades_path.open("a", encoding="utf-8") as fh:
        for r in results:
            if "error" not in r:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    errors = [r for r in results if "error" in r]
    print(json.dumps({"graded": len(results) - len(errors), "errors": errors[:5]}, indent=1))
    return 1 if errors else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--corpus", type=Path, required=True)
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--variants", nargs="+", default=["baseline"])
    g.add_argument("--model", default=DEFAULT_MODEL)
    g.add_argument("--snapshots", type=int, default=6, help="max brief snapshots per fixture (0 = every turn)")
    g.add_argument("--concurrency", type=int, default=64)
    g.add_argument("--limit", type=int, default=None, help="first N fixtures only (smoke runs)")
    g.set_defaults(fn=cmd_generate)
    r = sub.add_parser("grade")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--grader-model", default=DEFAULT_MODEL)
    r.add_argument("--transcript-chars", type=int, default=400_000)
    r.add_argument("--concurrency", type=int, default=64)
    r.set_defaults(fn=cmd_grade)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
