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
    spec = runner.load_variant_spec("baseline")
    assert spec.response_format is session_brief._RESPONSE_FORMAT
    assert spec.normalize is session_brief.normalize_brief


def test_baseline_replay_retains_omitted_tasks_and_grades_the_visible_hierarchy(runner, monkeypatch):
    """Evaluation must observe the same longitudinal document and ordering as the sidebar."""
    parent = dict(id="repair", parent_id=None, goal="Repair calendar sync", status="paused", detail="Resume after diagnosis")
    previous = dict(version=3, goal="Repair calendar sync", status="RUNNING: Repair underway",
                    completed=["Legacy milestone"], tasks=[parent], blockers=[], updated_at=1, message_count=2)
    child = dict(id="diagnose", parent_id="repair", goal="Diagnose duplicate alerts", status="completed", detail="Cause explained")
    monkeypatch.setattr(runner, "chat", lambda *_a, **_kw: dict(
        content=json.dumps(dict(goal=child["goal"], status="DONE: Cause explained", tasks=[child], blockers=[])),
        usage={}, latency_s=0))
    messages = [dict(role="user", content="First diagnose duplicate alerts"),
                dict(role="assistant", content="Cause explained, calendar sync repair paused")]
    brief = runner._generate_one(previous, messages, spec=runner.load_variant_spec("baseline"), model="test", message_count=4)
    assert brief["tasks"] == [parent, child]
    captured = []
    monkeypatch.setattr(runner, "chat", lambda msgs, **_kw: captured.append(msgs) or dict(content="{}", usage={}))
    runner.grade_snapshot(dict(fixture_id="fixture", messages=messages), dict(variant="baseline"),
                          dict(brief=brief, message_count=4), "rubric", "test", 10000)
    shown = json.loads(captured[0][1]["content"].split("sections in this order):\n", 1)[1])
    assert list(shown)[:2] == ["goal", "status"]
    assert shown["tasks"] == [parent, child]
    assert "completed" not in shown


def test_lane_b_variants_have_distinct_descriptors_and_expected_schema_deltas(runner):
    names = {
        "state_first", "delta_first", "blocker_dominant", "minimalist",
        "enum_state", "decision_pruned", "user_voice", "instruction_only", "evidence_first",
    }
    specs = [runner.load_variant_spec(name) for name in sorted(names)]
    assert {spec.name for spec in specs} == names
    assert len({spec.fingerprint for spec in specs}) == len(specs)
    assert runner.load_variant_spec("delta_first").schema_delta["added"] == {
        "changed": {"type": "array", "items": {"type": "string"}}
    }
    assert runner.load_variant_spec("minimalist").schema_delta == {"added": {}, "removed": ["decisions"]}
    assert set(runner.load_variant_spec("enum_state").schema_delta["added"]) == {"state", "waiting_on"}


def test_schema_variant_projects_native_fields_without_losing_them(runner):
    spec = runner.load_variant_spec("enum_state")
    brief = spec.normalize({
        "goal": "choose a plan",
        "state": "waiting_on_user",
        "status": "WAITING ON YOU: choose one",
        "waiting_on": "Choose plan A or B",
        "completed": ["Compared both plans"],
        "blockers": [],
        "decisions": [],
    }, message_count=12)
    assert brief["blockers"] == ["Choose plan A or B"]
    assert brief["_variant_fields"]["state"] == "waiting_on_user"
    assert brief["message_count"] == 12


def test_schema_sidecar_delta_is_fail_fast(runner, tmp_path, monkeypatch):
    (tmp_path / "bad.md").write_text("prompt", encoding="utf-8")
    (tmp_path / "bad.schema.json").write_text(json.dumps({
        "schema_delta": {"added": {}, "removed": []},
        "schema": {
            "type": "object", "properties": {"goal": {"type": "string"}},
            "required": ["goal"], "additionalProperties": False,
        },
    }), encoding="utf-8")
    monkeypatch.setattr(runner, "VARIANTS", tmp_path)
    with pytest.raises(SystemExit, match="inaccurate schema_delta"):
        runner.load_variant_spec("bad")


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
