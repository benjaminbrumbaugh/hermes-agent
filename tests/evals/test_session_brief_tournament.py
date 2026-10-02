"""Behavioral contracts for the session-brief render tournament.

These tests observe the deterministic evidence/index/schedule/Elo layer. They
do not pretend that a static grader proves visual glanceability; real image
evidence and human spot checks remain part of the Lane D run.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


EVAL_DIR = Path(__file__).resolve().parents[2] / "evals" / "session_brief"


@pytest.fixture(scope="module")
def tournament():
    spec = importlib.util.spec_from_file_location("session_brief_eval_tournament", EVAL_DIR / "tournament.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fixture(module, fixture_id: str, count: int, bucket: str = "short"):
    return module.Fixture(fixture_id, count, bucket, "done", "", "topic")


def test_round_robin_repeats_every_pair_per_fixture_class(tournament):
    candidates = ["alpha", "beta", tournament.CURRENT_CANDIDATE]
    matches = tournament.build_schedule(
        candidates,
        [_fixture(tournament, "f1", 1)],
        [320],
        ["dark"],
        seed=7,
        meetings=2,
    )

    pair_counts = {}
    for match in matches:
        pair = tuple(sorted((match.left, match.right)))
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    assert pair_counts == {("alpha", "beta"): 2, ("alpha", "current"): 2, ("beta", "current"): 2}


def test_schedule_uses_each_fixture_and_meets_width_comparison_contract(tournament):
    candidates = ["alpha", "beta", tournament.CURRENT_CANDIDATE]
    fixtures = [_fixture(tournament, "f1", 1), _fixture(tournament, "f2", 2)]
    matches = tournament.build_schedule(candidates, fixtures, [280, 320], ["dark", "light"], seed=11, meetings=2)
    assert {match.fixture_key for match in matches} == {fixture.key for fixture in fixtures}
    counts = tournament.comparison_counts(matches, candidates)
    assert set(counts) == {"280", "320"}
    assert all(counts[width][candidate] == 8 for width in counts for candidate in candidates)


def test_parse_verdict_accepts_fenced_json_and_rejects_ambiguous_claims(tournament):
    verdict = tournament.parse_verdict(
        "```json\n{\"winner\": \"alpha\", \"confidence\": 0.8, \"reason\": \"state cue\", \"decisive_region\": \"header\"}\n```",
        "alpha",
        "beta",
    )
    assert verdict["winner"] == "left"
    with pytest.raises(ValueError, match="winner"):
        tournament.parse_verdict('{"winner":"maybe","confidence":1,"reason":"x","decisive_region":"y"}', "alpha", "beta")
    with pytest.raises(ValueError, match="confidence"):
        tournament.parse_verdict('{"winner":"left","confidence":2,"reason":"x","decisive_region":"y"}', "alpha", "beta")


def test_compute_elo_rewards_wins_and_preserves_ungraded_rows(tournament):
    match = tournament.Match("m1", "short:f1:1", "short", 320, "dark", 0, 0, "alpha", "current")
    results = [
        {"match": match.as_json(), "result": {"status": "ok", "winner": "left"}},
        {"match": {**match.as_json(), "match_id": "m2"}, "result": {"status": "error", "error": "timeout"}},
    ]
    elo = tournament.compute_elo(results, ["alpha", "current"])
    assert elo["alpha"]["elo"] > 1500
    assert elo["alpha"]["comparisons"] == 1
    assert elo["current"]["comparisons"] == 1


def test_load_evidence_requires_both_real_png_paths(tournament, tmp_path):
    fixtures = [_fixture(tournament, "f1", 1)]
    renders = tmp_path / "renders"
    current = tmp_path / "current"
    png = b"\x89PNG\r\n\x1a\nfixture"
    for candidate, root in (("alpha", renders / "alpha"), ("beta", renders / "beta"), ("current", current)):
        for mode in ("dark", "light"):
            directory = root / f"320-{mode}"
            directory.mkdir(parents=True)
            full = directory / "f1-1.png"
            glance = directory / "f1-1.glance.png"
            full.write_bytes(png)
            glance.write_bytes(png)
            (directory / "manifest.json").write_text(
                json.dumps([{"id": "f1-1", "fixture_id": "f1", "message_count": 1, "full": str(full), "glance": str(glance)}]),
                encoding="utf-8",
            )
    candidates, evidence = tournament.load_evidence(renders, current, fixtures, [320], ["dark", "light"])
    assert candidates == ["alpha", "beta", "current"]
    assert len(evidence) == 6
