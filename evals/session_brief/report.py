"""Aggregate session-brief eval grades into a scorecard and check the rubric's ship thresholds.

The scorecard is the oracle for the design convoy: a variant ships only if this script says so. It also
prints the worst snapshots per variant with the grader's evidence so a human can verify the grader —
grader claims are claims, not facts, until a reader checks them against the transcript.

Usage::

    .venv/bin/python evals/session_brief/report.py temp/session-brief-eval/run1 [--worst 8] [--json out.json]
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

# Thresholds mirror rubric.md § Scoring. Change both or neither.
MIN_MEAN_GLANCE = 4.0
MIN_BUCKET_GLANCE = 3.5
MAX_CRITICAL_RATE = 0.03
CRITICAL = ("state.wrong", "waiting.missing", "fact.invented")
MAX_VERBOSE_RATE = 0.10


def load(run_dir: Path) -> Dict[str, Any]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    index = {e["fixture_id"]: e for e in json.loads((Path(run["corpus"]) / "index.json").read_text(encoding="utf-8"))}
    grades: List[Dict[str, Any]] = []
    for line in (run_dir / "grades.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            grades.append(json.loads(line))
    return {"run": run, "index": index, "grades": grades}


def scorecard(data: Dict[str, Any]) -> Dict[str, Any]:
    by_variant: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for g in data["grades"]:
        by_variant[g["variant"]].append(g)
    cards: Dict[str, Any] = {}
    for variant, grades in sorted(by_variant.items()):
        scored = [g for g in grades if isinstance((g.get("grade") or {}).get("glance_score"), (int, float))]
        gen_errors = [g for g in grades if g.get("grade") is None]
        failures = collections.Counter()
        per_bucket: Dict[str, List[float]] = collections.defaultdict(list)
        state_confusion = collections.Counter()
        for g in scored:
            gr = g["grade"]
            for f in gr.get("failures", []):
                if isinstance(f, dict) and f.get("id"):
                    failures[f["id"]] += 1
            truth = (gr.get("truth") or {}).get("state", "?")
            seen = (gr.get("from_brief") or {}).get("state", "?")
            state_confusion[f"{truth}->{seen}"] += 1
            for bucket in data["index"].get(g["fixture_id"], {}).get("buckets", ["unknown"]):
                per_bucket[bucket].append(float(gr["glance_score"]))
        n = len(scored)
        mean = statistics.mean(float(g["grade"]["glance_score"]) for g in scored) if scored else 0.0
        bucket_means = {b: round(statistics.mean(v), 2) for b, v in sorted(per_bucket.items())}
        critical_rate = sum(failures[c] for c in CRITICAL) / n if n else 1.0
        verbose_rate = failures["density.verbose"] / n if n else 1.0
        checks = {
            "mean_glance>=4.0": mean >= MIN_MEAN_GLANCE,
            "every_bucket>=3.5": bool(bucket_means) and min(bucket_means.values()) >= MIN_BUCKET_GLANCE,
            "critical_rate<=3%": critical_rate <= MAX_CRITICAL_RATE,
            "verbose_rate<=10%": verbose_rate <= MAX_VERBOSE_RATE,
        }
        cards[variant] = {
            "snapshots": n,
            "generation_errors": len(gen_errors),
            "mean_glance": round(mean, 2),
            "bucket_means": bucket_means,
            "state_agreement": round(sum(1 for g in scored if (g["grade"].get("truth") or {}).get("state") == (g["grade"].get("from_brief") or {}).get("state")) / n, 3) if n else 0.0,
            "state_confusion": dict(state_confusion.most_common()),
            "failure_rates": {k: round(v / n, 3) for k, v in failures.most_common()} if n else {},
            "critical_rate": round(critical_rate, 3),
            "checks": checks,
            "ships": all(checks.values()),
        }
    return cards


def worst(data: Dict[str, Any], variant: str, limit: int) -> List[Dict[str, Any]]:
    rows = [g for g in data["grades"] if g["variant"] == variant and isinstance((g.get("grade") or {}).get("glance_score"), (int, float))]
    rows.sort(key=lambda g: g["grade"]["glance_score"])
    out = []
    for g in rows[:limit]:
        gr = g["grade"]
        out.append({
            "fixture_id": g["fixture_id"], "message_count": g["message_count"], "glance_score": gr["glance_score"],
            "truth": gr.get("truth"), "from_brief": gr.get("from_brief"),
            "failures": gr.get("failures", [])[:6], "notes": (gr.get("notes") or "")[:400],
        })
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--worst", type=int, default=5)
    parser.add_argument("--json", type=Path, default=None, help="also write the scorecard here")
    args = parser.parse_args(argv)
    data = load(args.run_dir)
    cards = scorecard(data)
    print(json.dumps(cards, indent=1))
    for variant in cards:
        print(f"\n== worst {args.worst} for {variant} (verify these against the transcript before believing the grader)")
        for row in worst(data, variant, args.worst):
            print(json.dumps(row, ensure_ascii=False, indent=1))
    if args.json:
        args.json.write_text(json.dumps(cards, indent=1), encoding="utf-8")
    return 0 if all(c["ships"] for c in cards.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
