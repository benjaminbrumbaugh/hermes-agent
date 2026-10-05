#!/usr/bin/env python3
"""A/B the production brief prompt against a fragment-rules variant on real transcripts.

Standalone on purpose: importing ``agent.session_brief`` drags in the whole auxiliary-client
chain (credential pool -> hermes_cli.config -> ruamel), which the sandboxed eval shell cannot
resolve. This script reads the two prompt files, sends both to Space Bunny for the same
transcript, and prints both briefs plus per-brief shape metrics (string count, mean/max item
length, longest clause) so "does it scan" is a number, not an impression.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "temp" / "session-brief-corpus"
VARIANTS = REPO / "evals" / "session_brief" / "variants"
MODEL = "stealth/space-bunny-alpha"
URL = "https://openrouter.ai/api/v1/chat/completions"

SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "status": {"type": "string"},
        "completed": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["goal", "status", "completed", "blockers"],
    "additionalProperties": False,
}
RESPONSE_FORMAT = {"type": "json_schema", "json_schema": {"name": "session_brief", "strict": True, "schema": SCHEMA}}
MAX_TOKENS = 1200


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    for line in (Path.home() / ".hermes/.env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no OPENROUTER_API_KEY")


def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
    body = json.dumps({
        "model": MODEL, "messages": messages, "max_tokens": MAX_TOKENS,
        "reasoning": {"effort": "low"}, "response_format": RESPONSE_FORMAT,
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def production_prompt() -> str:
    """The shipped prompt, extracted from the module source without importing it."""
    src = (REPO / "agent/session_brief.py").read_text(encoding="utf-8")
    match = re.search(r'_SYSTEM_PROMPT = """(.*?)"""', src, re.S)
    if not match:
        raise SystemExit("could not extract _SYSTEM_PROMPT")
    return match.group(1).strip()


def elide(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    return f"{text[:head]} ... {text[-(limit - head - 5):]}"


def transcript_tail(fixture: dict[str, Any], chars: int = 60_000) -> str:
    parts = []
    for msg in fixture["messages"][-40:]:
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"[{role.upper()}]: {elide(content, 1200)}")
    return elide("\n\n".join(parts), chars)


def parse(content: str) -> dict[str, Any] | None:
    raw = (content or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fence:
        raw = fence.group(1)
    elif not raw.startswith("{"):
        start = raw.find("{")
        if start < 0:
            return None
        raw = raw[start:]
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) and isinstance(parsed.get("status"), str) else None


def shape(brief: dict[str, Any]) -> dict[str, Any]:
    items = [brief.get("status") or "", brief.get("goal") or ""]
    items += [str(x) for key in ("completed", "blockers") for x in (brief.get(key) or [])]
    clauses = [len(clause.strip()) for item in items for clause in re.split(r"[;:,]| and then | — ", item) if clause.strip()]
    return {
        "strings": len(items),
        "mean_len": round(statistics.mean(len(i) for i in items), 1) if items else 0,
        "max_len": max((len(i) for i in items), default=0),
        "longest_clause": max(clauses, default=0),
        "sentences": sum(item.count(".") for item in items),
    }


def run_one(fixture: dict[str, Any], prompts: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {"fixture_id": fixture["fixture_id"], "title": fixture.get("title")}
    tail = transcript_tail(fixture)
    for name, prompt in prompts.items():
        started = time.monotonic()
        try:
            reply = chat([
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Conversation so far:\n{tail}\n\nWrite the brief."},
            ])
            brief = parse(reply["choices"][0]["message"].get("content") or "")
            out[name] = {"brief": brief, "shape": shape(brief) if brief else None,
                         "latency_s": round(time.monotonic() - started, 1)}
        except Exception as exc:
            out[name] = {"error": repr(exc)[:200]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variants", nargs="+", default=["fragments"])
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--show", type=int, default=3, help="print N full comparisons")
    ap.add_argument("--out", type=Path, default=REPO / "temp/session-brief-eval/frag-ab.json")
    args = ap.parse_args()

    index = json.loads((CORPUS / "index.json").read_text(encoding="utf-8"))[: args.limit]
    fixtures = [json.loads((CORPUS / f"{e['fixture_id']}.json").read_text(encoding="utf-8")) for e in index]
    prompts = {"production": production_prompt()}
    for name in args.variants:
        prompts[name] = (VARIANTS / f"{name}.md").read_text(encoding="utf-8").strip()

    results: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for result in pool.map(lambda f: run_one(f, prompts), fixtures):
            results.append(result)
            print(f"  {len(results)}/{len(fixtures)}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"prompts": {k: v[:400] for k, v in prompts.items()}, "results": results}, indent=1), encoding="utf-8")

    print("\n== shape (lower max_len / longest_clause = scans better)")
    header = f"{'variant':<14}{'n':>4}{'strings':>9}{'mean_len':>10}{'max_len':>9}{'longest_clause':>16}{'sents':>7}"
    print(header)
    for name in prompts:
        shapes = [r[name]["shape"] for r in results if r.get(name, {}).get("shape")]
        if not shapes:
            print(f"{name:<14}{'0':>4}  (no parsed briefs)")
            continue
        print(f"{name:<14}{len(shapes):>4}"
              f"{statistics.mean(s['strings'] for s in shapes):>9.1f}"
              f"{statistics.mean(s['mean_len'] for s in shapes):>10.1f}"
              f"{statistics.mean(s['max_len'] for s in shapes):>9.1f}"
              f"{statistics.mean(s['longest_clause'] for s in shapes):>16.1f}"
              f"{statistics.mean(s['sentences'] for s in shapes):>7.2f}")

    for row in results[: args.show]:
        print(f"\n---- {row['fixture_id']} {(row.get('title') or '')[:50]}")
        for name in prompts:
            entry = row.get(name, {})
            if entry.get("error"):
                print(f"  [{name}] ERROR {entry['error']}")
            elif entry.get("brief"):
                print(f"  [{name}] {json.dumps(entry['brief'], ensure_ascii=False, indent=1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())