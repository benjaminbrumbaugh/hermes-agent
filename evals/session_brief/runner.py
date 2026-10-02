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
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent import session_brief as sb  # noqa: E402

HERE = Path(__file__).resolve().parent
VARIANTS = HERE / "variants"
DEFAULT_MODEL = "stealth/space-bunny-alpha"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
GRADER_MAX_TOKENS = 1800
_print_lock = threading.Lock()


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

def load_variant(name: str) -> str:
    if name == "baseline":
        return sb._SYSTEM_PROMPT
    path = VARIANTS / f"{name}.md"
    if not path.exists():
        raise SystemExit(f"unknown variant {name!r}; add {path}")
    return path.read_text(encoding="utf-8").strip()


def _generate_one(previous: Optional[Dict[str, Any]], delta: List[Dict[str, Any]], *, system_prompt: str,
                  model: str, message_count: int) -> Optional[Dict[str, Any]]:
    delta_text = sb._render_turn_delta(delta)
    if not delta_text.strip():
        return None
    messages = sb._build_messages(previous, delta_text)
    messages[0] = {"role": "system", "content": system_prompt}
    reply = chat(messages, model=model, max_tokens=sb.BRIEF_MAX_TOKENS, response_format=sb._RESPONSE_FORMAT)
    parsed = sb._parse_brief(reply["content"])
    if parsed is None:
        return {"_error": "unparseable", "_raw": reply["content"][:500], "_usage": reply["usage"]}
    brief = sb.normalize_brief(parsed, message_count=message_count)
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


def generate_fixture(fixture: Dict[str, Any], variant: str, system_prompt: str, model: str, out_dir: Path,
                     snapshots: int) -> Dict[str, Any]:
    out_path = out_dir / variant / f"{fixture['fixture_id']}.json"
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
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
    record: Dict[str, Any] = {"fixture_id": fixture["fixture_id"], "variant": variant, "model": model, "snapshots": []}
    for bound in picked:
        delta = messages[seen:bound]
        brief = _generate_one(previous, delta, system_prompt=system_prompt, model=model, message_count=bound)
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
    shown = {k: brief[k] for k in ("goal", "status", "completed", "blockers", "decisions")}
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
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps({
        "corpus": str(args.corpus), "variants": args.variants, "model": args.model, "snapshots": args.snapshots,
        "fixtures": [f["fixture_id"] for f in fixtures], "started_at": time.time(),
    }, indent=1), encoding="utf-8")
    jobs = []
    for variant in args.variants:
        prompt = load_variant(variant)
        (out / variant).mkdir(parents=True, exist_ok=True)
        (out / variant / "_system_prompt.md").write_text(prompt, encoding="utf-8")
        for fixture in fixtures:
            jobs.append((fixture, variant, prompt, args.model, out, args.snapshots))
    results = _run(jobs, generate_fixture, args.concurrency, "generate")
    errors = [r for r in results if "error" in r]
    print(json.dumps({"generated": len(results) - len(errors), "errors": errors[:5]}, indent=1))
    return 1 if errors else 0


def cmd_grade(args: argparse.Namespace) -> int:
    run = json.loads((args.out / "run.json").read_text(encoding="utf-8"))
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
