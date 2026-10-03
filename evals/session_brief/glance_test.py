"""Build a static, two-second human glance test from session-brief renders.

The generated directory is intentionally self-contained: open its
``glance_test.html`` directly in a browser, complete the test, and download
``glance-test.json``. Truth is copied beside the deck for the scorer but is not
embedded in the participant-visible page.

Example::

    python evals/session_brief/glance_test.py build \
        --renders temp/session-brief-eval/lane-e/renders \
        --out temp/session-brief-eval/ha-0ba/glance
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable, NoReturn


HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "glance_test.html"
STATES = ("done", "waiting_on_user", "running", "abandoned")
DECK_SIZE = 10
SCHEMA_VERSION = 1
TEMPLATE_MARKER = "__GLANCE_FIXTURES_JSON__"


def _fail(message: str) -> NoReturn:
    raise SystemExit(f"glance deck build failed: {message}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"could not read JSON {path}: {exc}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _key(fixture_id: str, message_count: int) -> str:
    return f"{fixture_id}-{message_count}"


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


def _find_grades(renders: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            _fail(f"grades file does not exist: {path}")
        return path

    candidates: list[Path] = []
    current = renders.resolve()
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


def _load_truth(path: Path, variant: str) -> dict[str, dict[str, Any]]:
    truth: dict[str, dict[str, Any]] = {}
    for row in _iter_jsonl(path):
        if row.get("variant") != variant:
            continue
        fixture_id = row.get("fixture_id")
        message_count = row.get("message_count")
        grade = row.get("grade")
        raw_truth = grade.get("truth") if isinstance(grade, dict) else None
        state = raw_truth.get("state") if isinstance(raw_truth, dict) else None
        if not isinstance(fixture_id, str) or not isinstance(message_count, int):
            _fail(f"{path} has a {variant!r} row without fixture_id/message_count")
        if state not in STATES:
            continue
        if not isinstance(raw_truth, dict):
            _fail(f"{path} has no truth object for {_key(fixture_id, message_count)}")
        key = _key(fixture_id, message_count)
        if key in truth:
            _fail(f"duplicate {variant!r} truth row for {key} in {path}")
        waiting_on = raw_truth.get("waiting_on", "")
        topic = raw_truth.get("topic", "")
        if not isinstance(waiting_on, str) or not isinstance(topic, str):
            _fail(f"truth row {key} must contain string waiting_on/topic")
        truth[key] = {
            "fixture_id": fixture_id,
            "message_count": message_count,
            "state": state,
            "waiting_on": waiting_on,
            "topic": topic,
            "source_row": row,
        }
    if not truth:
        _fail(f"no usable {variant!r} truth rows found in {path}")
    return truth


def _manifest_rank(path: Path, root: Path) -> tuple[int, int, str]:
    parts = {part.casefold() for part in path.relative_to(root).parts}
    rel = path.relative_to(root).as_posix().casefold()
    if "pulse" in parts or "integrated" in parts:
        set_rank = 0
    else:
        set_rank = 1
    mode_rank = {
        "320-dark": 0,
        "320-light": 1,
        "280-dark": 2,
        "280-light": 3,
        "400-dark": 4,
        "400-light": 5,
    }
    mode = next((mode_rank[name] for name in mode_rank if name in parts), 99)
    return set_rank, mode, rel


def _choose_manifest(renders: Path, render_set: Path | None) -> Path:
    root = renders.resolve()
    if not root.is_dir():
        _fail(f"render root does not exist or is not a directory: {root}")
    if render_set is not None:
        candidate = render_set.expanduser().resolve()
        if candidate != root and root not in candidate.parents:
            _fail(f"--render-set must be inside --renders: {candidate}")
        if not candidate.is_dir():
            _fail(f"render set does not exist or is not a directory: {candidate}")
        root = candidate
    manifests = sorted(root.rglob("manifest.json"))
    if not manifests:
        _fail(f"no manifest.json found under {root}")
    ranked = sorted(manifests, key=lambda path: _manifest_rank(path, root))
    best_rank = _manifest_rank(ranked[0], root)[:2]
    best = [path for path in ranked if _manifest_rank(path, root)[:2] == best_rank]
    if len(best) != 1:
        choices = ", ".join(str(path) for path in best)
        _fail(f"render selection is ambiguous; pass --render-set; candidates: {choices}")
    return best[0]


def _resolve_render_set(renders: Path, render_set: Path | None) -> Path | None:
    if render_set is None:
        return None
    candidate = render_set.expanduser()
    if not candidate.is_absolute():
        candidate = renders / candidate
    return candidate.resolve()


def _load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    if not isinstance(payload, list):
        _fail(f"render manifest must be a JSON array: {path}")
    entries: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            _fail(f"manifest entry {index} has no string id: {path}")
        render_id = raw["id"]
        if render_id in entries:
            _fail(f"duplicate render id {render_id!r} in {path}")
        full_value = raw.get("full")
        if not isinstance(full_value, str) or not full_value:
            _fail(f"render {render_id} has no full PNG path in {path}")
        full = Path(full_value).expanduser()
        if not full.is_absolute():
            full = path.parent / full
        full = full.resolve()
        if not full.is_file():
            _fail(f"full PNG for render {render_id} is missing: {full}")
        if full.suffix.casefold() != ".png":
            _fail(f"full render for {render_id} is not a PNG: {full}")
        entries[render_id] = {"id": render_id, "full": full}
    return entries


def _stable_selection(rows: list[dict[str, Any]], seed: str) -> list[dict[str, Any]]:
    by_state: dict[str, list[dict[str, Any]]] = {state: [] for state in STATES}
    for state in STATES:
        by_state[state] = [row for row in rows if row["state"] == state]
        by_state[state].sort(key=lambda row: hashlib.sha256(f"{seed}:{row['key']}".encode()).hexdigest())
        if not by_state[state]:
            _fail(f"no {state} snapshot is available in the selected render manifest")
    selected: list[dict[str, Any]] = [by_state[state][0] for state in STATES]
    offsets = {state: 1 for state in STATES}
    while len(selected) < DECK_SIZE:
        added = False
        for state in STATES:
            offset = offsets[state]
            if offset < len(by_state[state]):
                selected.append(by_state[state][offset])
                offsets[state] += 1
                added = True
                if len(selected) == DECK_SIZE:
                    break
        if not added:
            available = len(selected)
            _fail(f"need {DECK_SIZE} snapshots spanning all four states but only found {available}")
    selected.sort(key=lambda row: row["key"])
    return selected


def _safe_image_name(key: str) -> str:
    return f"{key.replace('/', '_')}.png"


def _build(args: argparse.Namespace) -> int:
    renders = args.renders.expanduser().resolve()
    grades_path = _find_grades(renders, args.grades)
    truth = _load_truth(grades_path, args.variant)
    render_set = _resolve_render_set(renders, args.render_set)
    manifest_path = _choose_manifest(renders, render_set)
    renders_by_id = _load_manifest(manifest_path)

    joined: list[dict[str, Any]] = []
    for key, row in truth.items():
        render_id = key
        render = renders_by_id.get(render_id)
        if render is None:
            continue
        joined.append({"key": key, "render": render, **row})
    selected = _stable_selection(joined, args.seed)

    out = args.out.expanduser().resolve()
    images_dir = out / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    public_fixtures: list[dict[str, Any]] = []
    selected_grade_lines: list[str] = []
    for row in selected:
        image_name = _safe_image_name(row["key"])
        destination = images_dir / image_name
        shutil.copy2(row["render"]["full"], destination)
        public_fixtures.append({
            "key": row["key"],
            "fixture_id": row["fixture_id"],
            "message_count": row["message_count"],
            "image": f"images/{image_name}",
        })
        selected_grade_lines.append(json.dumps(row["source_row"], ensure_ascii=False))

    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(TEMPLATE_MARKER) != 1:
        _fail(f"template must contain exactly one {TEMPLATE_MARKER!r} marker: {TEMPLATE}")
    generated_html = template.replace(
        TEMPLATE_MARKER,
        json.dumps(public_fixtures, ensure_ascii=False, separators=(",", ":")),
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "glance_test.html").write_text(generated_html, encoding="utf-8")
    (out / "grades.jsonl").write_text("\n".join(selected_grade_lines) + "\n", encoding="utf-8")
    deck_manifest = {
        "schema_version": SCHEMA_VERSION,
        "deck_id": "session-brief-glance-v1",
        "variant": args.variant,
        "selection_seed": args.seed,
        "source": {
            "renders": str(renders),
            "render_set": str(render_set or renders),
            "manifest": str(manifest_path),
            "grades": str(grades_path),
        },
        "state_counts": {
            state: sum(1 for row in selected if row["state"] == state)
            for state in STATES
        },
        "fixtures": [
            {
                **fixture,
                "image_sha256": _sha256(images_dir / Path(fixture["image"]).name),
            }
            for fixture in public_fixtures
        ],
    }
    (out / "deck-manifest.json").write_text(
        json.dumps(deck_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    score_path = Path("evals/session_brief/glance_score.py")
    readme = f"""# Session brief glance test

Open `glance_test.html` directly in a browser. Each pane is shown for two
seconds before the four questions appear. The page randomizes order and the
Download results button writes `glance-test.json`.

From the repository root, score the downloaded receipt with:

    python {score_path} /absolute/path/to/glance-test.json

The selected truth rows are copied to `grades.jsonl`; the scorer uses them by
default. Truth is not embedded in the participant-visible HTML.
"""
    (out / "README.txt").write_text(readme, encoding="utf-8")
    print(f"Built {len(selected)} fixtures at {out}")
    print(f"Open: {out / 'glance_test.html'}")
    print(f"Score: python {score_path} {out / 'glance-test.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a static ten-fixture deck")
    build.add_argument("--renders", type=Path, required=True, help="Lane E render root")
    build.add_argument("--out", type=Path, required=True, help="temporary output directory")
    build.add_argument("--grades", type=Path, default=None, help="grades.jsonl (auto-discovered by default)")
    build.add_argument("--variant", default="baseline", help="grades variant to select (default: baseline)")
    build.add_argument("--render-set", type=Path, default=None, help="optional render subtree under --renders")
    build.add_argument("--seed", default="lane-g-v1", help="stable selection seed")
    build.set_defaults(handler=_build)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
