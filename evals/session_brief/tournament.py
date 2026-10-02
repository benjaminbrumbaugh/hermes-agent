"""Pairwise vision tournament for the session-brief render candidates.

The tournament compares real BriefPane screenshots, not DOM snapshots or the
brief JSON alone.  It builds a deterministic, two-meeting round-robin schedule
within each rubric fixture class, sends both the first-glance crop and full
panel to a vision grader, and aggregates the results with Elo.  A second model
family is reserved for the final schedule round.

The command intentionally fails closed when evidence is incomplete.  A model
failure is not a loss, and a smoke run cannot produce an acceptance verdict.
Generated PNGs and ``tournament.json`` live in the caller-provided temp tree;
the durable Markdown report records the machine result and the human checks.

Example::

    python evals/session_brief/tournament.py \
      --renders-root /path/to/ha-dab/renders \
      --current-root /path/to/ha-z6q/renders/current \
      --fixtures evals/session_brief/reviews/2026-10-02-design-fixtures.json \
      --truth /path/to/ha-bj0/grades.jsonl \
      --out /path/to/ha-z6q/tournament.json \
      --review evals/session_brief/reviews/2026-10-02-lane-d-tournament.md
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as futures
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Keep credential lookup and endpoint selection aligned with the existing eval
# runner.  This imports the text-only transport constants, not production code.
from runner import OPENROUTER, _api_key  # noqa: E402


CURRENT_CANDIDATE = "current"
DEFAULT_WIDTHS = (280, 320, 400)
DEFAULT_MODES = ("dark", "light")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ALLOWED_STATES = {"done", "waiting_on_user", "running", "abandoned", "unclear"}
_BASE64_LOCK = threading.Lock()
_BASE64_CACHE: dict[str, str] = {}


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    message_count: int
    bucket: str
    truth_state: str
    waiting_on: str
    topic: str

    @property
    def key(self) -> str:
        return fixture_key(self.bucket, self.fixture_id, self.message_count)

    def as_json(self) -> dict[str, Any]:
        return asdict(self) | {"key": self.key}


@dataclass(frozen=True)
class Evidence:
    candidate: str
    fixture_key: str
    width: int
    mode: str
    full: Path
    glance: Path

    def as_json(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "fixture_key": self.fixture_key,
            "width": self.width,
            "mode": self.mode,
            "full": str(self.full),
            "glance": str(self.glance),
            "full_sha256": sha256(self.full),
            "glance_sha256": sha256(self.glance),
        }


@dataclass(frozen=True)
class Match:
    match_id: str
    fixture_key: str
    bucket: str
    width: int
    mode: str
    round: int
    meeting: int
    left: str
    right: str

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def fixture_key(bucket: str, fixture_id: str, message_count: int) -> str:
    """Return a collision-resistant key for a snapshot boundary."""

    return f"{bucket}:{fixture_id}:{message_count}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing JSON evidence: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON evidence {path}: {exc}") from exc


def load_fixtures(path: Path) -> list[Fixture]:
    payload = _load_json(path)
    rows = payload.get("fixtures") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"fixture manifest must contain a non-empty fixtures list: {path}")
    fixtures: list[Fixture] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"fixture row is not an object: {row!r}")
        bucket = str(row.get("selected_bucket") or row.get("bucket") or "").strip()
        fixture_id = str(row.get("fixture_id") or "").strip()
        try:
            message_count = int(row["message_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"fixture row has invalid message_count: {row!r}") from exc
        if not bucket or not fixture_id or message_count < 0:
            raise ValueError(f"fixture row missing bucket/id or has negative message_count: {row!r}")
        key = fixture_key(bucket, fixture_id, message_count)
        if key in seen:
            raise ValueError(f"duplicate fixture key: {key}")
        seen.add(key)
        fixtures.append(Fixture(fixture_id, message_count, bucket, "", "", ""))
    return fixtures


def load_truth(path: Path, fixtures: Sequence[Fixture]) -> list[Fixture]:
    """Join Lane A's baseline truth to the exact selected snapshot boundary."""

    by_id_count: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid truth JSONL at {path}:{line_no}: {exc}") from exc
        if row.get("variant") not in (None, "baseline"):
            continue
        grade = row.get("grade") or {}
        truth = grade.get("truth") or {}
        if not truth:
            continue
        try:
            key = (str(row["fixture_id"]), int(row["message_count"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"truth row missing fixture_id/message_count at line {line_no}") from exc
        by_id_count.setdefault(key, []).append(truth)

    result: list[Fixture] = []
    for fixture in fixtures:
        truths = by_id_count.get((fixture.fixture_id, fixture.message_count), [])
        if len(truths) != 1:
            raise ValueError(
                f"expected exactly one Lane A baseline truth row for {fixture.key}, found {len(truths)}"
            )
        truth = truths[0]
        state = str(truth.get("state") or "unclear").strip()
        if state not in ALLOWED_STATES:
            raise ValueError(f"unsupported truth state for {fixture.key}: {state!r}")
        result.append(
            Fixture(
                fixture.fixture_id,
                fixture.message_count,
                fixture.bucket,
                state,
                str(truth.get("waiting_on") or "").strip(),
                str(truth.get("topic") or "").strip(),
            )
        )
    return result


def _validate_png(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"missing render: {path}")
    with path.open("rb") as handle:
        if handle.read(len(PNG_MAGIC)) != PNG_MAGIC:
            raise ValueError(f"render is not a PNG: {path}")


def _manifest_row_key(row: Mapping[str, Any]) -> tuple[str, int]:
    fixture_id = row.get("fixture_id")
    message_count = row.get("message_count")
    if fixture_id is not None and message_count is not None:
        try:
            return str(fixture_id), int(message_count)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid render manifest metadata: {row!r}") from exc
    match = re.match(r"^(.+)-(\d+)$", str(row.get("id") or ""))
    if not match:
        raise ValueError(f"render row lacks fixture_id/message_count: {row!r}")
    return match.group(1), int(match.group(2))


def _load_render_manifest(
    path: Path,
    candidate: str,
    width: int,
    mode: str,
    fixtures_by_id_count: Mapping[tuple[str, int], Fixture],
) -> dict[str, Evidence]:
    rows = _load_json(path)
    if not isinstance(rows, list):
        raise ValueError(f"render manifest must be a list: {path}")
    loaded: dict[str, Evidence] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"render row is not an object in {path}: {row!r}")
        if row.get("error"):
            raise ValueError(f"render failed for {candidate}/{width}-{mode}: {row['error']}")
        id_count = _manifest_row_key(row)
        fixture = fixtures_by_id_count.get(id_count)
        if fixture is None:
            continue
        full = Path(str(row.get("full") or ""))
        glance = Path(str(row.get("glance") or ""))
        if not full.is_absolute():
            full = path.parent / full
        if not glance.is_absolute():
            glance = path.parent / glance
        _validate_png(full)
        _validate_png(glance)
        if fixture.key in loaded:
            raise ValueError(f"duplicate render for {candidate}/{width}-{mode}/{fixture.key}")
        loaded[fixture.key] = Evidence(candidate, fixture.key, width, mode, full, glance)
    return loaded


def load_evidence(
    renders_root: Path,
    current_root: Path,
    fixtures: Sequence[Fixture],
    widths: Sequence[int],
    modes: Sequence[str],
    candidate_names: Sequence[str] | None = None,
) -> tuple[list[str], dict[tuple[str, str, int, str], Evidence]]:
    """Load and validate every candidate/current render against the fixture set."""

    candidate_dirs = sorted(p.name for p in renders_root.iterdir() if p.is_dir())
    if candidate_names is not None:
        candidate_dirs = sorted(set(candidate_names))
    if not candidate_dirs:
        raise ValueError(f"no candidate render directories found under {renders_root}")
    if CURRENT_CANDIDATE in candidate_dirs:
        raise ValueError("candidate render directory is reserved: current")
    candidates = candidate_dirs + [CURRENT_CANDIDATE]
    fixtures_by_id_count = {(f.fixture_id, f.message_count): f for f in fixtures}
    expected = {f.key for f in fixtures}
    evidence: dict[tuple[str, str, int, str], Evidence] = {}
    for candidate in candidates:
        root = current_root if candidate == CURRENT_CANDIDATE else renders_root / candidate
        if not root.is_dir():
            raise ValueError(f"missing render root for {candidate}: {root}")
        for width in widths:
            for mode in modes:
                manifest = root / f"{width}-{mode}" / "manifest.json"
                loaded = _load_render_manifest(manifest, candidate, width, mode, fixtures_by_id_count)
                missing = expected - set(loaded)
                extra = set(loaded) - expected
                if missing or extra or len(loaded) != len(expected):
                    raise ValueError(
                        f"coverage mismatch for {candidate}/{width}-{mode}: "
                        f"missing={sorted(missing)} extra={sorted(extra)} count={len(loaded)}/{len(expected)}"
                    )
                for key, item in loaded.items():
                    evidence[(candidate, key, width, mode)] = item
    return candidates, evidence


def _round_robin_rounds(candidates: Sequence[str], meetings: int) -> list[list[tuple[str, str]]]:
    """Return circle-method Swiss rounds with every pair repeated ``meetings`` times."""

    if len(candidates) < 2 or meetings < 1:
        raise ValueError("need at least two candidates and one meeting")
    entries: list[str | None] = list(candidates)
    if len(entries) % 2:
        entries.append(None)
    rounds: list[list[tuple[str, str]]] = []
    half = len(entries) // 2
    for meeting in range(meetings):
        current = entries[:]
        for round_index in range(len(entries) - 1):
            pairings = []
            for index in range(half):
                left, right = current[index], current[-index - 1]
                if left is not None and right is not None:
                    pairings.append((left, right))
            rounds.append(pairings)
            current = [current[0], current[-1], *current[1:-1]]
    return rounds


def build_schedule(
    candidates: Sequence[str],
    fixtures: Sequence[Fixture],
    widths: Sequence[int],
    modes: Sequence[str],
    *,
    seed: int = 20261002,
    meetings: int = 2,
    max_matches: int | None = None,
) -> list[Match]:
    """Build a reproducible schedule using every fixture row and both orientations."""

    if CURRENT_CANDIDATE not in candidates:
        raise ValueError("schedule must include the current pane")
    rng = random.Random(seed)
    matches: list[Match] = []
    by_bucket: dict[str, list[Fixture]] = {}
    for fixture in fixtures:
        by_bucket.setdefault(fixture.bucket, []).append(fixture)
    for width in widths:
        for mode in modes:
            for bucket in sorted(by_bucket):
                bucket_fixtures = by_bucket[bucket]
                rounds = _round_robin_rounds(candidates, meetings)
                assignment = 0
                for round_index, pairings in enumerate(rounds):
                    meeting = round_index // (len(candidates) if len(candidates) % 2 else len(candidates) - 1)
                    for match_index, (left, right) in enumerate(pairings):
                        fixture = bucket_fixtures[assignment % len(bucket_fixtures)]
                        assignment += 1
                        if rng.random() < 0.5:
                            left, right = right, left
                        matches.append(
                            Match(
                                match_id=(
                                    f"{width}-{mode}-{bucket}-r{round_index:02d}-m{match_index:02d}-"
                                    f"{fixture.fixture_id}-{fixture.message_count}"
                                ),
                                fixture_key=fixture.key,
                                bucket=bucket,
                                width=width,
                                mode=mode,
                                round=round_index,
                                meeting=meeting,
                                left=left,
                                right=right,
                            )
                        )
    matches.sort(key=lambda item: item.match_id)
    if max_matches is not None:
        if max_matches < 1:
            raise ValueError("max_matches must be positive")
        matches = matches[:max_matches]
    return matches


def comparison_counts(matches: Sequence[Match], candidates: Sequence[str]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for match in matches:
        width_counts = counts.setdefault(str(match.width), {candidate: 0 for candidate in candidates})
        width_counts[match.left] += 1
        width_counts[match.right] += 1
    return counts


def _prompt(match: Match, fixture: Fixture, left: str, right: str) -> str:
    return (
        "You are judging a pair of real screenshots of an AI-agent session sidebar. "
        "Which panel lets a returning user answer DONE / WAITING ON ME (on what) / RUNNING / ABOUT WHAT "
        "FASTER and more CORRECTLY? Use the first-glance crop for scan order and the full panel for context. "
        "Point at the region that decides the comparison. Do not reward aesthetics without task value.\n\n"
        f"Transcript truth for this snapshot: state={fixture.truth_state}; waiting_on={fixture.waiting_on!r}; "
        f"topic={fixture.topic!r}.\n"
        f"LEFT candidate: {left}\nRIGHT candidate: {right}\n\n"
        "Reply with ONLY a JSON object: {\"winner\": \"left|right|tie\", "
        "\"confidence\": 0.0-1.0, \"reason\": \"...\", \"decisive_region\": \"...\"}."
    )


def _data_url(path: Path) -> str:
    key = str(path)
    with _BASE64_LOCK:
        cached = _BASE64_CACHE.get(key)
        if cached is not None:
            return cached
    encoded = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    with _BASE64_LOCK:
        _BASE64_CACHE[key] = encoded
    return encoded


def parse_verdict(content: str, left: str, right: str) -> dict[str, Any]:
    """Parse a grader response without inventing a winner."""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"grader response is not JSON: {content[:240]!r}") from exc
    if not isinstance(data, dict):
        raise ValueError("grader response must be a JSON object")
    raw_winner = str(data.get("winner") or "").strip().lower()
    winner_aliases = {"left": "left", "right": "right", "tie": "tie", "draw": "tie", "": ""}
    if raw_winner not in winner_aliases:
        if raw_winner == left.lower():
            raw_winner = "left"
        elif raw_winner == right.lower():
            raw_winner = "right"
    winner = winner_aliases.get(raw_winner, "")
    if not winner:
        raise ValueError(f"grader winner must be left/right/tie, got {data.get('winner')!r}")
    try:
        confidence = float(data["confidence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("grader confidence must be a number") from exc
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError(f"grader confidence outside 0..1: {confidence!r}")
    reason = str(data.get("reason") or "").strip()
    region = str(data.get("decisive_region") or "").strip()
    if not reason or not region:
        raise ValueError("grader reason and decisive_region are required")
    return {"winner": winner, "confidence": confidence, "reason": reason, "decisive_region": region}


class OpenRouterGrader:
    family = "openrouter"

    def __init__(self, model: str, *, retries: int = 4, timeout: float = 240.0) -> None:
        self.model = model
        self.retries = retries
        self.timeout = timeout

    def grade(self, match: Match, fixture: Fixture, left: Evidence, right: Evidence) -> dict[str, Any]:
        user_content = [
            {"type": "text", "text": _prompt(match, fixture, match.left, match.right)},
            {"type": "text", "text": "LEFT first-glance crop (top 240px):"},
            {"type": "image_url", "image_url": {"url": _data_url(left.glance)}},
            {"type": "text", "text": "LEFT full panel:"},
            {"type": "image_url", "image_url": {"url": _data_url(left.full)}},
            {"type": "text", "text": "RIGHT first-glance crop (top 240px):"},
            {"type": "image_url", "image_url": {"url": _data_url(right.glance)}},
            {"type": "text", "text": "RIGHT full panel:"},
            {"type": "image_url", "image_url": {"url": _data_url(right.full)}},
        ]
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return only the requested JSON verdict."},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 500,
            "reasoning": {"effort": "low"},
            "response_format": {"type": "json_object"},
        }
        encoded = json.dumps(body).encode("utf-8")
        delay = 2.0
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            request = urllib.request.Request(
                OPENROUTER,
                data=encoded,
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://hermes-agent.nousresearch.com",
                    "X-Title": "hermes session-brief render tournament",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read())
                if "error" in payload:
                    raise RuntimeError(f"upstream error: {payload['error']}")
                content = payload["choices"][0]["message"].get("content") or ""
                verdict = parse_verdict(content, match.left, match.right)
                return verdict | {
                    "status": "ok",
                    "provider": self.family,
                    "model": self.model,
                    "latency_s": round(time.monotonic() - started, 2),
                    "usage": payload.get("usage") or {},
                    "raw_content": content[:4000],
                }
            except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"OpenRouter grading failed after {self.retries + 1} attempts: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        raise AssertionError("unreachable")


def _codex_output(stdout: str) -> str:
    for line in reversed(stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        for value in (
            event.get("text"),
            event.get("content"),
            (event.get("item") or {}).get("text") if isinstance(event.get("item"), dict) else None,
        ):
            if isinstance(value, str) and value.strip():
                return value
    return stdout.strip()


class CodexGrader:
    family = "codex"

    def __init__(self, model: str | None = None, *, timeout: float = 180.0, binary: str = "codex") -> None:
        self.model = model
        self.timeout = timeout
        self.binary = binary

    def grade(self, match: Match, fixture: Fixture, left: Evidence, right: Evidence) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="session-brief-codex-") as temp_dir:
            output_path = Path(temp_dir) / "last-message.txt"
            command = [
                self.binary,
                "exec",
                _prompt(match, fixture, match.left, match.right),
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--output-last-message",
                str(output_path),
                "-i",
                str(left.glance),
                "-i",
                str(left.full),
                "-i",
                str(right.glance),
                "-i",
                str(right.full),
            ]
            if self.model:
                command.extend(["--model", self.model])
            started = time.monotonic()
            completed = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=self.timeout, check=False)
            if completed.returncode:
                raise RuntimeError(f"Codex exited {completed.returncode}: {completed.stderr[-1000:]}")
            content = output_path.read_text(encoding="utf-8") if output_path.exists() else _codex_output(completed.stdout)
            verdict = parse_verdict(content, match.left, match.right)
            return verdict | {
                "status": "ok",
                "provider": self.family,
                "model": self.model or "codex-default",
                "latency_s": round(time.monotonic() - started, 2),
                "raw_content": content[:4000],
            }


class StaticGrader:
    """Deterministic test double; never used by the real CLI."""

    family = "static"

    def __init__(self, winner: str = "tie") -> None:
        self.winner = winner

    def grade(self, match: Match, fixture: Fixture, left: Evidence, right: Evidence) -> dict[str, Any]:
        return {
            "status": "ok",
            "provider": self.family,
            "model": "test",
            "winner": self.winner,
            "confidence": 1.0,
            "reason": "deterministic test verdict",
            "decisive_region": "test fixture",
            "latency_s": 0.0,
        }


def _grade_matches(
    matches: Sequence[Match],
    fixtures_by_key: Mapping[str, Fixture],
    evidence: Mapping[tuple[str, str, int, str], Evidence],
    grader: Any,
    concurrency: int,
) -> list[dict[str, Any]]:
    def grade_one(match: Match) -> dict[str, Any]:
        fixture = fixtures_by_key[match.fixture_key]
        left = evidence[(match.left, match.fixture_key, match.width, match.mode)]
        right = evidence[(match.right, match.fixture_key, match.width, match.mode)]
        try:
            verdict = grader.grade(match, fixture, left, right)
            return {"match": match.as_json(), "result": verdict}
        except Exception as exc:  # Evidence must show the failed comparison.
            return {"match": match.as_json(), "result": {"status": "error", "error": repr(exc)}}

    with futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        results = list(pool.map(grade_one, matches))
    return sorted(results, key=lambda row: row["match"]["match_id"])


def _score(result: Mapping[str, Any]) -> float | None:
    if result.get("status") != "ok":
        return None
    winner = result.get("winner")
    if winner == "left":
        return 1.0
    if winner == "right":
        return 0.0
    if winner == "tie":
        return 0.5
    return None


def compute_elo(results: Sequence[Mapping[str, Any]], candidates: Sequence[str], *, initial: float = 1500.0, k: float = 32.0) -> dict[str, Any]:
    ratings = {candidate: initial for candidate in candidates}
    counts = {candidate: {"wins": 0, "losses": 0, "ties": 0, "comparisons": 0} for candidate in candidates}
    for row in sorted(results, key=lambda item: item["match"]["match_id"]):
        score = _score(row["result"])
        if score is None:
            continue
        match = row["match"]
        left, right = match["left"], match["right"]
        expected_left = 1 / (1 + 10 ** ((ratings[right] - ratings[left]) / 400))
        expected_right = 1 - expected_left
        ratings[left] += k * (score - expected_left)
        ratings[right] += k * ((1 - score) - expected_right)
        counts[left]["comparisons"] += 1
        counts[right]["comparisons"] += 1
        if score == 1:
            counts[left]["wins"] += 1
            counts[right]["losses"] += 1
        elif score == 0:
            counts[right]["wins"] += 1
            counts[left]["losses"] += 1
        else:
            counts[left]["ties"] += 1
            counts[right]["ties"] += 1
    return {
        candidate: {"elo": round(ratings[candidate], 2), **counts[candidate]}
        for candidate in sorted(candidates, key=lambda item: (-ratings[item], item))
    }


def _final_family_agreement(primary: Sequence[Mapping[str, Any]], secondary: Sequence[Mapping[str, Any]], winner: str) -> bool:
    primary_by_id = {row["match"]["match_id"]: row for row in primary if row["result"].get("status") == "ok"}
    secondary_by_id = {row["match"]["match_id"]: row for row in secondary if row["result"].get("status") == "ok"}
    shared = sorted(set(primary_by_id) & set(secondary_by_id))
    if not shared:
        return False
    for match_id in shared:
        if primary_by_id[match_id]["result"].get("winner") != secondary_by_id[match_id]["result"].get("winner"):
            return False
    scores: dict[str, float] = {}
    for row in secondary_by_id.values():
        score = _score(row["result"])
        if score is None:
            continue
        match = row["match"]
        scores[match["left"]] = scores.get(match["left"], 0.0) + score
        scores[match["right"]] = scores.get(match["right"], 0.0) + (1 - score)
    return winner in scores and scores[winner] == max(scores.values())


def _elo_table_text(elo_by_width: Mapping[str, Mapping[str, Any]]) -> str:
    lines = ["width | candidate | Elo | comparisons | W-L-T", "--- | --- | ---: | ---: | ---"]
    for width in sorted(elo_by_width, key=int):
        for candidate, row in elo_by_width[width].items():
            lines.append(
                f"{width} | {candidate} | {row['elo']:.2f} | {row['comparisons']} | "
                f"{row['wins']}-{row['losses']}-{row['ties']}"
            )
    return "\n".join(lines)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def write_review(path: Path, data: Mapping[str, Any]) -> None:
    acceptance = data["acceptance"]
    lines = [
        "# Lane D tournament review",
        "",
        f"Status: **{acceptance['status']}**",
        "",
        "This report separates machine grader claims from the human pixel review. The screenshots are the evidence layer; Elo and model agreement are decision aids, not proof of glanceability by themselves.",
        "",
        "## Run receipt",
        "",
        f"- Seed: `{data['config']['seed']}`; candidates: {', '.join(data['candidates'])}",
        f"- Fixtures: {len(data['fixtures'])}; matches scheduled: {data['schedule']['total_matches']}",
        f"- Primary provider: `{data['config']['primary_model']}`; secondary: `{data['config']['secondary_provider']}`",
        f"- Primary errors: {data['schedule']['primary_errors']}; secondary errors: {data['schedule']['secondary_errors']}",
        "",
        "## Elo table (script output, verbatim)",
        "",
        "```text",
        data["elo_table_text"],
        "```",
        "",
        "## Width decisions",
        "",
    ]
    for width, decision in sorted(acceptance["by_width"].items(), key=lambda item: int(item[0])):
        lines.append(
            f"- `{width}px`: `{decision['status']}`; best `{decision['best_candidate']}` "
            f"({decision['best_elo']:.2f}) vs current ({decision['current_elo']:.2f}), "
            f"delta {decision['delta']:.2f}; final-family agreement={decision['final_family_agreement']}."
        )
    lines.extend(
        [
            "",
            "## Human spot-check required",
            "",
            "Open both referenced PNGs for each row and record `agree` or `disagree`, the deciding region, and why. A model verdict remains a claim until this table is completed.",
            "",
            "| # | match | left glance | right glance | machine winner | confidence | human verdict | deciding region |",
            "| ---: | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for index, row in enumerate(data["spot_checks"], 1):
        match = row["match"]
        result = row["result"]
        lines.append(
            f"| {index} | `{match['match_id']}` | `{row['left_glance']}` | `{row['right_glance']}` | "
            f"{result.get('winner', 'ERROR')} | {result.get('confidence', '')} | **PENDING** | **PENDING** |"
        )
    lines.extend(
        [
            "",
            "## Verified findings from losing designs",
            "",
            "Complete only after the spot-checks. Each finding must name the losing candidate, fixture, PNG path, and visible region that proves the issue. Do not promote grader prose to a verified finding without opening the image.",
            "",
            "- PENDING HUMAN REVIEW",
            "",
            "## Evidence limits",
            "",
            "- Render manifests prove the real harness captured the requested panes and crops; they do not prove a user can answer the four questions.",
            "- Elo depends on grader judgments and schedule coverage; it does not replace the human glance test.",
            "- This run does not measure long-run auxiliary-call cost or non-English glanceability.",
        ]
    )
    _write_atomic(path, "\n".join(lines) + "\n")


def run_tournament(
    *,
    renders_root: Path,
    current_root: Path,
    fixtures_path: Path,
    truth_path: Path,
    out_path: Path,
    review_path: Path,
    primary_grader: Any,
    secondary_grader: Any,
    widths: Sequence[int] = DEFAULT_WIDTHS,
    modes: Sequence[str] = DEFAULT_MODES,
    seed: int = 20261002,
    meetings: int = 2,
    concurrency: int = 16,
    max_matches: int | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fixtures = load_truth(truth_path, load_fixtures(fixtures_path))
    candidates, evidence = load_evidence(renders_root, current_root, fixtures, widths, modes)
    matches = build_schedule(candidates, fixtures, widths, modes, seed=seed, meetings=meetings, max_matches=max_matches)
    fixtures_by_key = {fixture.key: fixture for fixture in fixtures}
    primary = _grade_matches(matches, fixtures_by_key, evidence, primary_grader, concurrency)
    final_round = max((match.round for match in matches), default=-1)
    final_matches = [match for match in matches if match.round == final_round]
    secondary = _grade_matches(final_matches, fixtures_by_key, evidence, secondary_grader, max(1, min(concurrency, 8)))

    elo_by_width = {
        str(width): compute_elo(
            [row for row in primary if row["match"]["width"] == width], candidates
        )
        for width in widths
    }
    secondary_by_width = {
        str(width): [row for row in secondary if row["match"]["width"] == width]
        for width in widths
    }
    primary_by_width = {str(width): [row for row in primary if row["match"]["width"] == width] for width in widths}
    decisions: dict[str, Any] = {}
    for width in widths:
        ratings = elo_by_width[str(width)]
        ordered = [candidate for candidate in ratings if candidate != CURRENT_CANDIDATE]
        best = ordered[0]
        best_elo = ratings[best]["elo"]
        current_elo = ratings[CURRENT_CANDIDATE]["elo"]
        family_agreement = _final_family_agreement(primary_by_width[str(width)], secondary_by_width[str(width)], best)
        errors = any(row["result"].get("status") != "ok" for row in primary_by_width[str(width)])
        secondary_errors = any(row["result"].get("status") != "ok" for row in secondary_by_width[str(width)])
        complete = bool(secondary_by_width[str(width)]) and not errors and not secondary_errors
        if not complete:
            status = "incomplete"
        elif best_elo - current_elo > 100 and family_agreement:
            status = "winner"
        else:
            status = "no_candidate_beats_current"
        decisions[str(width)] = {
            "status": status,
            "best_candidate": best,
            "best_elo": best_elo,
            "current_elo": current_elo,
            "delta": round(best_elo - current_elo, 2),
            "final_family_agreement": family_agreement,
            "comparisons_by_candidate": comparison_counts(
                [match for match in matches if match.width == width], candidates
            ).get(str(width), {}),
        }

    overall_status = "incomplete" if any(item["status"] == "incomplete" for item in decisions.values()) else (
        "winner" if any(item["status"] == "winner" for item in decisions.values()) else "no_candidate_beats_current"
    )
    result = {
        "schema_version": 1,
        "config": {
            "seed": seed,
            "meetings": meetings,
            "widths": list(widths),
            "modes": list(modes),
            "primary_model": getattr(primary_grader, "model", primary_grader.__class__.__name__),
            "secondary_provider": getattr(secondary_grader, "family", secondary_grader.__class__.__name__),
            **(dict(config or {})),
        },
        "candidates": candidates,
        "fixtures": [fixture.as_json() for fixture in fixtures],
        "evidence": [item.as_json() for item in sorted(evidence.values(), key=lambda item: (item.candidate, item.width, item.mode, item.fixture_key))],
        "schedule": {
            "total_matches": len(matches),
            "final_round": final_round,
            "comparison_counts": comparison_counts(matches, candidates),
            "primary_errors": sum(row["result"].get("status") != "ok" for row in primary),
            "secondary_errors": sum(row["result"].get("status") != "ok" for row in secondary),
            "smoke_limited": max_matches is not None,
        },
        "primary_results": primary,
        "secondary_results": secondary,
        "elo_by_width": elo_by_width,
        "elo_table_text": _elo_table_text(elo_by_width),
        "acceptance": {"status": overall_status, "by_width": decisions},
    }
    successful = [row for row in primary if row["result"].get("status") == "ok"]
    rng = random.Random(seed + 1)
    rng.shuffle(successful)
    spot_checks = []
    for row in successful[:10]:
        match = row["match"]
        left = evidence[(match["left"], match["fixture_key"], match["width"], match["mode"])]
        right = evidence[(match["right"], match["fixture_key"], match["width"], match["mode"])]
        spot_checks.append({"match": match, "result": row["result"], "left_glance": str(left.glance), "right_glance": str(right.glance)})
    result["spot_checks"] = spot_checks
    _write_atomic(out_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    write_review(review_path, result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--renders-root", type=Path, required=True, help="Lane C root containing one directory per candidate")
    parser.add_argument("--current-root", type=Path, required=True, help="current-pane root containing width-mode directories")
    parser.add_argument("--fixtures", type=Path, required=True, help="Lane C design-fixtures.json")
    parser.add_argument("--truth", type=Path, required=True, help="Lane A grades.jsonl")
    parser.add_argument("--out", type=Path, required=True, help="gitignored tournament.json output")
    parser.add_argument("--review", type=Path, required=True, help="durable Markdown review output")
    parser.add_argument("--widths", nargs="+", type=int, default=list(DEFAULT_WIDTHS))
    parser.add_argument("--modes", nargs="+", choices=DEFAULT_MODES, default=list(DEFAULT_MODES))
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--meetings", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--max-matches", type=int, default=None, help="bounded smoke run; never reports acceptance")
    parser.add_argument("--primary-model", default="stealth/space-bunny-alpha")
    parser.add_argument("--secondary-model", default=None, help="Codex model for final-round checks; default is configured Codex model")
    parser.add_argument("--secondary-provider", choices=("codex",), default="codex")
    parser.add_argument("--codex-binary", default="codex")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    primary = OpenRouterGrader(args.primary_model)
    secondary = CodexGrader(args.secondary_model, binary=args.codex_binary)
    try:
        result = run_tournament(
            renders_root=args.renders_root,
            current_root=args.current_root,
            fixtures_path=args.fixtures,
            truth_path=args.truth,
            out_path=args.out,
            review_path=args.review,
            primary_grader=primary,
            secondary_grader=secondary,
            widths=args.widths,
            modes=args.modes,
            seed=args.seed,
            meetings=args.meetings,
            concurrency=args.concurrency,
            max_matches=args.max_matches,
            config={"secondary_model": args.secondary_model, "secondary_provider": args.secondary_provider},
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"tournament failed closed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["acceptance"]["status"], "out": str(args.out), "review": str(args.review)}, indent=1))
    return 0 if result["acceptance"]["status"] != "incomplete" and not args.max_matches else 2


if __name__ == "__main__":
    raise SystemExit(main())
