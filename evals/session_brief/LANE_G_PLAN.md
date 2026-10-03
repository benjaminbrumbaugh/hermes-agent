# Lane G implementation plan

counter: 0

## Goal and scope

Prepare a self-contained, static human glance-test deck from Lane E's real
render receipts. The user opens the generated HTML locally; each of ten
integrated-pane PNGs is shown for two seconds, then the user records state,
waiting-on action, topic, and confidence. The page randomizes fixture order and
downloads answers as JSON. A separate scorer joins those answers to the
snapshot-specific truth in `grades.jsonl` and prints per-question accuracy.

Owned source files:

- `evals/session_brief/glance_test.html` — static test UI and JSON download.
- `evals/session_brief/glance_test.py` — deterministic deck builder and render/truth validation.
- `evals/session_brief/glance_score.py` — deterministic answer/truth join and score table.

No production brief code, renderer, prompt, or config changes are in scope.
Temporary build output stays under the caller's requested `temp/` directory and
is never committed.

## Full plan, tasks, and subtasks

1. Read the Lane G contract, Lane E render/grade formats, and repository guidance.
2. Build the deck generator:
   - discover a render manifest under `--renders`, preferring a 320px dark
     integrated render when multiple manifests exist;
   - discover or accept `grades.jsonl`, filter the requested variant, and join
     render IDs to exact `(fixture_id, message_count)` truth rows;
   - select exactly ten deterministic snapshots spanning done, waiting_on_user,
     running, and abandoned, with a balanced 3/3/2/2 distribution;
   - copy only the selected full PNGs into output and embed a relative manifest
     in the generated HTML so `file://` loading needs no server;
   - fail closed on missing manifests, duplicate truth, missing images, missing
     states, or mismatched IDs.
3. Build the static test UI:
   - show a start screen and one pane image for 2,000 ms after it is loaded;
   - collect four answers with explicit enum values and visible progress;
   - randomize order with Fisher–Yates and retain the presented order in output;
   - validate required answers before advancing;
   - download a versioned JSON receipt containing deck metadata, order, timing,
     and answers, but no truth labels.
4. Build the scorer:
   - load answers and selected truth, auto-discover the deck's copied
     `grades.jsonl` when possible, and validate schema/duplicate keys;
   - score exact state, deterministic normalized free-text matching for waiting
     action and topic, and report confidence as answered-only because truth has
     no confidence field;
   - print a compact table with counts, percentages, and an overall factual
     score while keeping machine claims distinct from human glanceability.
5. Verify against a synthetic ten-answer receipt with known correct and
   incorrect rows, then build from available Lane E-compatible renders and
   inspect the generated artifact structurally.
6. Self-review, run the repository's required affected-test command if one is
   configured, commit the focused changes, push, and hand off to the refinery.

## Architectural changes

The only boundary added is a file-based evidence boundary:

`render manifest + grades.jsonl -> validated deck manifest -> local HTML ->
downloaded answers JSON -> validated score table`.

Truth remains outside the HTML so participants cannot be shown labels by the
deck itself. The builder copies only the selected truth rows into the output
directory for reproducible scoring. The browser UI is static and uses no
network, server, backend, or production imports.

## Test and evidence plan

Target truth: whether a person can answer the four status questions from the
actual integrated-pane pixels after a two-second exposure.

Required evidence layer: generated HTML opened from a local output directory,
real PNGs from the Lane E render harness, and the downloadable receipt scored
against the exact snapshot rows in `grades.jsonl`.

Useful but insufficient proxies: Python syntax checks, JSON schema checks,
image-file existence, deterministic selection, and a synthetic scorer run.
These prove plumbing and arithmetic, not human glanceability or image content.

Tempting false-completion substitution: treating a successful build or a
100%-correct synthetic receipt as proof that the UI is glanceable. The handoff
must leave the user-facing one-line invocation and explicitly state that the
user must run the deck; this lane prepares the test and does not claim its
result.

If this plan fully succeeds while the original bug remains, the likely causes
are a wrong truth join, a selected image that is not the integrated pane, a
timer that starts before the image is visible, or a UI cue that is unreadable
at the tested width. The builder therefore validates IDs and source paths, and
the handoff calls for the user-visible run.

## Support structures and docs

- Generated output contains copied images, `glance-test.json` template metadata,
  selected `grades.jsonl`, and a short local-use README; these are temp
  evidence artifacts, not repository fixtures.
- The bead notes will carry the exact build and score invocations, including
  the fact that the generated deck is intentionally not committed.
- No new dependency, environment variable, server, or production hook is
  needed.

## Execution order and stability strategy

1. Create and refine this plan before source edits.
2. Implement validation/selection and the static UI together because their
   manifest contract is shared.
3. Implement scoring against the same explicit key format.
4. Run synthetic and real-receipt smoke checks before commit.
5. Keep output deterministic except for the participant's recorded randomized
   order; seed deck selection, and record the random order in the receipt.

Missing Lane E renders or truth are an explicit blocker for real-deck evidence,
not a reason to invent fixtures. Code-level validation and synthetic scoring
can still proceed, but the final handoff must identify the missing external
artifact and leave the user invocation when a render directory is available.

## Candidate parallel work

The UI and scorer are logically separable after the manifest schema is frozen,
but the current work item is small enough that one implementation keeps the
boundary reviewable. A future parallel reviewer can independently inspect the
static timer/download behavior and the truth-join/normalization behavior.

## No-change decisions

- Do not modify `PLAN.md`, `rubric.md`, `report.py`, or production brief code.
- Do not add a server, Electron route, RPC method, browser automation, or new
  dependency for a static local test.
- Do not put truth labels in the participant-visible HTML.
- Do not score confidence as factual correctness; the oracle has no confidence
  field, so report completion only.

## Planning pass 1 — contract and evidence critique

### Critique of the full plan, top to bottom

- Goal/scope is appropriately narrow, but “Lane E render receipts” is not a
  single stable directory shape. The builder must accept a render root with
  nested manifests and must not silently pick a different design or width.
- The selection task names a 3/3/2/2 split but does not say what happens when
  one truth state has fewer than its quota or when the same snapshot appears in
  multiple manifests. It must fail with an actionable diagnostic rather than
  rebalance silently.
- The UI task says two seconds but does not define whether the timer starts at
  route load, image load, or first paint. Starting at image load is the only
  defensible browser-observable boundary; the receipt should record exposure
  start/end times for audit.
- The scorer task's free-text matching is underspecified. Exact string equality
  would punish reasonable human paraphrases; unconstrained substring matching
  would over-credit guesses. The algorithm needs a documented token rule and
  per-row evidence so its percentage is auditable.
- The test plan distinguishes plumbing from user truth, but the implementation
  needs a deterministic synthetic fixture that exercises missing truth,
  duplicate answers, an empty waiting answer for a non-waiting state, and a
  paraphrased topic—not only a happy-path 100% receipt.
- The support-structure section says `glance-test.json` template metadata but
  the browser's downloaded receipt name is not fixed. The output contract
  should use `glance-test.json` consistently and keep the deck manifest separate.
- The blocker strategy is sound, but the exact invocation cannot depend on a
  nonexistent Lane E output. We should validate with the available integrated
  pulse render root only if its IDs join to the chosen grades; otherwise report
  the real-artifact gap without generating a misleading deck.

### Critical evaluation of that critique

The critique identifies genuine boundary risks rather than cosmetic details.
The manifest is the source-of-truth join, so an implicit “first manifest” would
allow a passing deck built from the wrong theme or candidate. The timer and text
matching rules are also part of what the scorer claims, not implementation
convenience. Conversely, requiring a particular Lane E folder name would be
unnecessarily brittle; discovery plus explicit provenance is the better
contract. A synthetic test should remain outside the repository and should not
be mistaken for a human result.

### Roll-up: changes applied to the plan

- Add explicit render-manifest ranking and selected manifest provenance to the
  output metadata; prefer `320-dark`, then stable lexical order, but fail if a
  selected ID is absent from the chosen manifest.
- Use a required balanced distribution and fail closed if any state cannot meet
  its quota; deduplicate by `(fixture_id, message_count)` before selection.
- Start the exposure timer only after the selected image's `load` event; record
  `exposure_started_at`, `exposure_ended_at`, and `exposure_ms` in the result.
- Implement token-set matching with stop-word removal and a documented
  precision/recall threshold, and print matched terms in the detailed score
  output.
- Standardize the downloaded filename as `glance-test.json`; include a
  schema version and deck id, while keeping truth out of the HTML.
- Make the builder verify the selected manifest and grades join before copying
  files, and make the real smoke run conditional on that verified join.

### Revised task details and no-change decisions

The architecture, file scope, no-server decision, and confidence policy remain
unchanged. The builder gains strict provenance and quota checks; the scorer gains
auditable matching details; the UI gains load-bounded timing. No production or
oracle changes are needed.

### Proxy audit for pass 1

- Target truth: human answers from the pixels after exactly two seconds.
- Required evidence layer: a user-opened generated deck using real integrated
  PNGs plus a downloaded receipt joined to the exact grades rows.
- Cheaper useful proxies: manifest joins, copied-image hashes, timer metadata,
  Python syntax, and synthetic scoring; each covers one boundary only.
- Tempting false completion: a green build, a correct synthetic receipt, or a
  model grader score standing in for the human test.
- If the plan succeeds but the bug remains: the selected manifest may be a
  different candidate/theme, or the UI may show the image at a scale/crop that
  hides the status; provenance and the user's real run remain necessary.

counter: 1

## Planning pass 2 — implementation-boundary critique

### Critique of the revised plan, top to bottom

- The render ranking still leaves a semantic question: a root may contain
  manifests for several candidates, and lexical fallback could select a losing
  design. The caller needs an optional `--manifest`/`--render-set` selector or
  the builder should make the selected manifest path prominent and require the
  user to confirm it through the output receipt. The task only requires
  `--renders`, so adding a required selector would make the promised command
  less usable.
- “Copy selected full PNGs” does not say whether source paths in manifests may
  be relative. The loader must resolve relative paths against the manifest's
  directory and reject paths that do not exist; absolute paths are accepted
  because Lane E receipts currently use them.
- The UI's required-answer rule could block a participant who reasonably leaves
  waiting-on blank for a non-waiting state. The state question and confidence
  should be required; waiting-on and topic should be required fields too, but
  empty waiting-on is a valid answer when no blocker is visible. That value must
  still be serialized, not coerced to null.
- The scorer's token rule needs state-aware handling: waiting action must be
  blank when truth is blank and nonblank when truth is nonblank; topic should
  reject a generic “the task” answer. It should not infer truth state from
  waiting text.
- The plan says “output metadata” but does not define a stable machine-readable
  manifest. Without one, later reruns cannot prove which ten rows were shown.
- The final handoff should distinguish the build invocation, the browser file
  path, and the score invocation. “Exact one-line invocation” must mean one
  command that builds the deck, plus one command that scores the downloaded
  file; otherwise the user cannot reproduce the result.

### Critical evaluation of that critique

The selector concern is real, but a new required flag would diverge from the
bead's explicit build command. The safe compromise is deterministic ranking
with `--render-set` as an optional override, provenance in `deck-manifest.json`,
and a failure if a root contains multiple candidates at the same preferred
mode without an unambiguous `pulse`/`integrated` name. Relative path support is
necessary for portable manifests. Empty waiting text is a valid semantic value,
not missing data. The scorer must remain a deterministic heuristic and expose
its rule; it cannot claim semantic human understanding from token overlap.

### Roll-up: changes applied to the plan

- Add optional `--render-set` to select a named candidate/render subtree while
  preserving the required `--renders` command. When omitted, prefer a unique
  `pulse` or `integrated` subtree, then unique `320-dark`; ambiguous candidates
  fail with the candidate paths.
- Resolve `full`/`glance` manifest paths relative to each manifest and reject
  path traversal only for copied output names; copy by basename plus stable
  fixture key to avoid collisions.
- Require state and confidence in the UI. Require topic and a waiting-on text
  field, allowing an intentionally empty string; label the latter so a user
  knows blank is valid outside WAITING.
- Define text matching as normalized content-term precision and recall with
  stop words removed; blank-vs-nonblank is exact, and short answers require
  all expected terms. Report that rule in scorer output.
- Write `deck-manifest.json` containing schema version, selected render-set
  path, manifest path, selection seed, ten keys, and copied relative paths;
  write selected truth rows to sibling `grades.jsonl` for reproducible scoring.
- Put separate build/open/score commands in the bead notes after validation.

### Revised task details and no-change decisions

The HTML remains static and truth-free. The builder may accept `--render-set`
as a nonessential precision control, but the default path remains the bead's
one-line `build --renders ... --out ...` invocation. No server, browser
automation, or dependency is introduced. No claim of human success is emitted
by code.

### Proxy audit for pass 2

- Target truth: correct, rapid human interpretation of the real integrated pane.
- Required evidence layer: selected manifest provenance plus the user's actual
  downloaded receipt; scorer output is the answer-matching layer only.
- Cheaper useful proxies: copied file existence, `deck-manifest.json`, exact
  truth joins, and synthetic paraphrase tests.
- Tempting false completion: token-overlap percentages treated as semantic
  understanding, or a deterministic selection treated as proof the selected
  candidate is the intended Lane E output.
- If the plan succeeds but the bug remains: the chosen render-set may still be
  visually wrong at the test width, or the user may answer after more than two
  seconds; provenance helps audit this but cannot replace the live test.

counter: 2

## Planning pass 3 — final critical review and loss check

### Critique of the revised plan, top to bottom

- The plan now has enough provenance controls, but optional render-set
  selection can still be misused if it accepts arbitrary paths outside the
  supplied `--renders` root. The implementation must constrain the override to
  a descendant of that root and record the resolved path.
- The requested “one integrated-pane PNG for 2 s” is best served by the full
  image, not the `.glance.png` crop. The builder should prefer `full` and use a
  glance crop only as an explicit, visible fallback/error, not silently.
- The score table needs a stable denominator. It should score only the ten
  selected rows, reject extra/duplicate answer keys, and distinguish unanswered
  from wrong. Otherwise a participant could download a partial receipt that
  appears strong.
- The HTML must be usable without a web server in browsers that block local
  module scripts or fetch calls. Plain inline JavaScript and embedded fixture
  metadata are required; no `fetch`, ES-module import, or remote asset is safe.
- The plan mentions a local-use README in temp output but not whether the
  static source HTML is copied verbatim or rendered. The source should remain a
  readable template with one clearly delimited data token; generated output may
  replace only that token.

### Critical evaluation of that critique

All five points protect a concrete failure mode at the evidence boundary. The
override must be bounded to avoid accidentally grading unrelated screenshots;
full images preserve the integrated pane's actual layout; strict denominators
prevent partial receipts from producing a false percentage; inline JS is a
hard requirement for file:// portability; and a single replacement token keeps
the source maintainable. None expands the product surface.

### Roll-up: final plan

- Constrain `--render-set` to a directory under `--renders`; record both paths
  and reject outside selections.
- Require `full` image paths. If only a glance crop exists, fail with the
  fixture key and source manifest rather than substituting an unannounced crop.
- Enforce exactly ten unique answers matching exactly the ten deck keys; print
  answered/wrong separately and use ten as every accuracy denominator.
- Keep the page inline and embed fixture metadata by replacing a single
  `__GLANCE_FIXTURES_JSON__` marker in the copied HTML; use no fetch/import.
- Write a temp README with the build output path, local open instruction, and
  score command; do not add repository docs beyond the three owned source files
  and this required planning record.

### Lost-information check after three passes

The refinements preserve every original requirement: static/no-server delivery,
two-second exposure, randomized ten-fixture order, four answer fields, JSON
download, truth from `grades.jsonl`, build from Lane E renders, synthetic scorer
verification, user-facing invocation, and explicit evidence limits. Added
details are implementation safeguards, not scope changes. The final execution
order is: implement template → implement builder → implement scorer → run
syntax/unit smoke → attempt real render build → review diff → commit and hand
off.

### Explicit no-change decisions

- Keep the distribution 3 done / 3 waiting / 2 running / 2 abandoned; do not
  balance by including `unclear`, because Lane G explicitly requires four truth
  states and the oracle has those labels.
- Keep confidence out of factual correctness; only response completion is
  reported for it.
- Keep truth out of the HTML and output deck metadata visible to participants.
- Keep all real PNGs in caller-owned temp output; never commit binary fixtures.
- Do not add a backend route, RPC contract, production test hook, or dependency.

### Final proxy audit

- Target truth: a human's four answers after a real two-second integrated-pane
  exposure.
- Required evidence layer: the user-run static deck and its downloaded JSON,
  with a scorer receipt joined to the exact ten `grades.jsonl` snapshots.
- Cheaper useful-but-insufficient proxies: syntax checks, strict manifest joins,
  selected-image existence, timer receipt fields, and synthetic score math.
- Tempting false-completion substitution: treating any of those proxies—or the
  scorer's heuristic text percentages—as proof of human glanceability.
- If the plan fully succeeds but the original bug remains: the chosen PNG may
  still fail to expose status in two seconds, or the participant's environment
  may scale/crop the pane differently. Only the actual user run can answer that.

## Implementation evidence correction

The first real join against the available integrated render set found only one
`abandoned` snapshot. A fixed 3/3/2/2 distribution would therefore block a
valid deck or encourage an untruthful substitution. The user contract requires
ten fixtures spanning all four states, not a specific balance. The selector now
requires at least one row for each state, selects one per state, and fills the
remaining six slots in deterministic round-robin order from available rows.
The current verified set produces 3 done / 3 waiting / 3 running / 1
abandoned. The output manifest records actual counts. No truth row is invented.

counter: 3
