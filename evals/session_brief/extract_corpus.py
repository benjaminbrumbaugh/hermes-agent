"""Build the session-brief fixture corpus from a local Hermes state.db.

Each fixture is one root-lineage conversation (compression children folded in, synthetic compaction
artifacts dropped, duplicates removed — same reconstruction as ``evals/compaction/scripts/
reconstruct_lineage.py``), written as ``<corpus>/<fixture_id>.json`` with the transcript plus the
metadata graders need (title, source, outcome bucket, turn count). Secrets are redacted with the
compressor's own redactor.

The corpus is REAL conversation data and never leaves the machine; ``--out`` must be gitignored
(the default is ``temp/session-brief-corpus/`` at the repo root).

Buckets, chosen to cover the glance task's four answers (done / waiting on me / running / what):

- ``short``      6–20 turns, one objective
- ``medium``     21–120 turns
- ``long``       121+ turns, or any lineage that crossed a compression boundary
- ``pivot``      the user's last request differs materially from the first (heuristic: low token overlap)
- ``handoff``    the final assistant message asks the user for something (``[You]``, ``?``, "let me know")

Usage (read-only; the DB is opened in immutable mode, so a running gateway is fine)::

    .venv/bin/python evals/session_brief/extract_corpus.py --db ~/.hermes/state.db --out temp/session-brief-corpus --per-bucket 40
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent.context_compressor import _redact_compaction_text  # noqa: E402

SYNTH_MARKERS = (
    "[CONTEXT COMPACTION",
    "[CONTEXT SUMMARY",
    "[PRIOR CONTEXT",
    "preserved across context compression",
)
# Sources whose transcripts are a human talking to the agent; cron/tool/a2a sessions are not.
HUMAN_SOURCES = {"desktop", "cli", "tui", "telegram", "discord", "slack"}
HANDOFF_RE = re.compile(r"\[You\]|\?\s*$|let me know|should I|do you want|which (one|option)|confirm", re.I | re.M)
WORD_RE = re.compile(r"[a-z]{4,}")


def _conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _lineage(conn: sqlite3.Connection, root: str, children: Dict[str, List[str]]) -> List[str]:
    chain: List[str] = []
    frontier = [root]
    while frontier:
        sid = frontier.pop(0)
        chain.append(sid)
        frontier.extend(children.get(sid, []))
    marks = ",".join("?" * len(chain))
    starts = {r["id"]: r["started_at"] or "" for r in conn.execute(
        f"SELECT id, started_at FROM sessions WHERE id IN ({marks})", chain)}
    chain.sort(key=lambda s: starts.get(s, ""))
    return chain


def _messages(conn: sqlite3.Connection, chain: List[str]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for sid in chain:
        for r in conn.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,)):
            content = r["content"] or ""
            if any(m in content for m in SYNTH_MARKERS):
                continue
            digest = hashlib.md5((r["role"] + "\x00" + content + "\x00" + (r["tool_calls"] or "")).encode("utf-8", "replace")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            msg: Dict[str, Any] = {"role": r["role"], "content": _redact_compaction_text(content), "timestamp": r["timestamp"]}
            if r["tool_calls"]:
                try:
                    calls = json.loads(r["tool_calls"])
                    for call in calls:
                        fn = call.get("function") if isinstance(call, dict) else None
                        if isinstance(fn, dict) and isinstance(fn.get("arguments"), str):
                            fn["arguments"] = _redact_compaction_text(fn["arguments"])
                    msg["tool_calls"] = calls
                except ValueError:
                    pass
            if r["tool_call_id"]:
                msg["tool_call_id"] = r["tool_call_id"]
            if r["tool_name"]:
                msg["tool_name"] = r["tool_name"]
            out.append(msg)
    return out


def _user_texts(messages: Iterable[Dict[str, Any]]) -> List[str]:
    texts = []
    for m in messages:
        if m.get("role") == "user" and isinstance(m.get("content"), str) and m["content"].strip():
            texts.append(m["content"])
    return texts


def _overlap(a: str, b: str) -> float:
    wa, wb = set(WORD_RE.findall(a.lower())), set(WORD_RE.findall(b.lower()))
    if not wa or not wb:
        return 1.0
    return len(wa & wb) / min(len(wa), len(wb))


def _bucket(messages: List[Dict[str, Any]], compressed: bool) -> List[str]:
    users = _user_texts(messages)
    turns = len(users)
    buckets: List[str] = []
    if compressed or turns > 120:
        buckets.append("long")
    elif turns > 20:
        buckets.append("medium")
    else:
        buckets.append("short")
    if len(users) >= 3 and _overlap(users[0], users[-1]) < 0.15:
        buckets.append("pivot")
    last_assistant = next((m for m in reversed(messages) if m.get("role") == "assistant" and isinstance(m.get("content"), str)), None)
    if last_assistant and HANDOFF_RE.search(last_assistant["content"][-1500:]):
        buckets.append("handoff")
    return buckets


def build(db: Path, out: Path, per_bucket: int, seed: int, min_turns: int, max_messages: int) -> Dict[str, int]:
    conn = _conn(db)
    children: Dict[str, List[str]] = collections.defaultdict(list)
    for r in conn.execute("SELECT id, parent_session_id FROM sessions WHERE parent_session_id IS NOT NULL"):
        children[r["parent_session_id"]].append(r["id"])
    roots = conn.execute(
        "SELECT id, source, title, started_at, ended_at, end_reason, message_count FROM sessions "
        "WHERE parent_session_id IS NULL AND message_count >= ? ORDER BY started_at", (min_turns,)
    ).fetchall()

    candidates: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for row in roots:
        if (row["source"] or "") not in HUMAN_SOURCES:
            continue
        chain = _lineage(conn, row["id"], children)
        messages = _messages(conn, chain)
        if len(_user_texts(messages)) < 3 or len(messages) > max_messages:
            continue
        fixture = {
            "fixture_id": row["id"],
            "root_session_id": row["id"],
            "lineage": chain,
            "source": row["source"],
            "title": row["title"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "end_reason": row["end_reason"],
            "user_turns": len(_user_texts(messages)),
            "message_count": len(messages),
            "compressed": len(chain) > 1,
            "buckets": _bucket(messages, len(chain) > 1),
            "messages": messages,
        }
        for bucket in fixture["buckets"]:
            candidates[bucket].append(fixture)

    rng = random.Random(seed)
    chosen: Dict[str, Dict[str, Any]] = {}
    counts: Dict[str, int] = {}
    for bucket, items in sorted(candidates.items()):
        rng.shuffle(items)
        picked = 0
        for fixture in items:
            if picked >= per_bucket:
                break
            chosen.setdefault(fixture["fixture_id"], fixture)
            picked += 1
        counts[bucket] = picked

    out.mkdir(parents=True, exist_ok=True)
    for fixture_id, fixture in chosen.items():
        (out / f"{fixture_id}.json").write_text(json.dumps(fixture, ensure_ascii=False, default=str), encoding="utf-8")
    index = [
        {k: v for k, v in f.items() if k != "messages"}
        for f in sorted(chosen.values(), key=lambda f: f["started_at"] or "")
    ]
    (out / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    counts["total"] = len(chosen)
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=REPO / "temp" / "session-brief-corpus")
    parser.add_argument("--per-bucket", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-turns", type=int, default=6, help="minimum stored message_count on the root row")
    parser.add_argument("--max-messages", type=int, default=1500, help="skip lineages longer than this (grader budget)")
    args = parser.parse_args(argv)
    counts = build(args.db.expanduser(), args.out, args.per_bucket, args.seed, args.min_turns, args.max_messages)
    print(json.dumps(counts, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
