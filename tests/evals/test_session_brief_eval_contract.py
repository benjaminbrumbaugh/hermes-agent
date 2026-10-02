"""The eval must grade what production ships: its prompt, parser and schema come from ``agent.session_brief``.

Guards the contract between ``evals/session_brief/runner.py`` and the shipped generator (no network):
the baseline variant IS the production prompt, turn boundaries land where the finalizer hooks, and the
report thresholds are the ones ``rubric.md`` states.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "evals" / "session_brief"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"session_brief_eval_{name}", EVAL_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load("runner")


@pytest.fixture(scope="module")
def report():
    return _load("report")


def test_baseline_variant_is_the_shipped_prompt(runner):
    from agent import session_brief

    assert runner.load_variant("baseline") == session_brief._SYSTEM_PROMPT


def test_turn_boundaries_follow_completed_assistant_turns(runner):
    messages = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x", "arguments": "{}"}}]},
        {"role": "tool", "content": "r"},
        {"role": "assistant", "content": "done a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "done b"},
    ]
    assert runner._turn_boundaries(messages) == [4, 6]


def test_rubric_thresholds_match_report(report):
    rubric = (EVAL_DIR / "rubric.md").read_text(encoding="utf-8")
    assert f"≥ {report.MIN_MEAN_GLANCE:.1f}" in rubric
    assert f"< {report.MIN_BUCKET_GLANCE:.1f}" in rubric
    assert f"≤ {int(report.MAX_CRITICAL_RATE * 100)} %" in rubric
    assert f"≤ {int(report.MAX_VERBOSE_RATE * 100)} %" in rubric
    for failure_id in report.CRITICAL:
        assert f"`{failure_id}`" in rubric


def test_scorecard_ships_only_when_every_check_passes(report, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "index.json").write_text(json.dumps([{"fixture_id": "f1", "buckets": ["short"]}]), encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"corpus": str(corpus), "variants": ["v"], "fixtures": ["f1"]}), encoding="utf-8")
    good = {"glance_score": 5, "truth": {"state": "done"}, "from_brief": {"state": "done"}, "failures": []}
    bad = {**good, "glance_score": 0, "failures": [{"id": "state.wrong", "evidence": "x"}]}
    (run / "grades.jsonl").write_text(
        "\n".join(json.dumps({"variant": "v", "fixture_id": "f1", "message_count": n, "grade": g}) for n, g in ((1, good), (2, good)))
        + "\n", encoding="utf-8")
    assert report.scorecard(report.load(run))["v"]["ships"] is True
    (run / "grades.jsonl").write_text(
        json.dumps({"variant": "v", "fixture_id": "f1", "message_count": 3, "grade": bad}) + "\n", encoding="utf-8")
    card = report.scorecard(report.load(run))["v"]
    assert card["ships"] is False and card["checks"]["critical_rate<=3%"] is False
