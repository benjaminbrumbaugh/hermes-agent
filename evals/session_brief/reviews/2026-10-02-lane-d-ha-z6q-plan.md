# Lane D execution plan — `ha-z6q`

Initial counter: 0  
Scope: pairwise vision tournament over the six Lane C render candidates plus the current pane.

## 1. Full plan, tasks, and subtasks

1. Load and freeze evidence inputs.
   - Read the session-brief oracle, rubric, and Lane C fixture manifest.
   - Verify the shared Lane C render tree has complete candidate manifests for 20 fixtures × 3 widths × 2 themes.
   - Treat the current pane as an explicit candidate sourced from the same fixture data; do not substitute semantic DOM or text-only evidence for pixels.
2. Implement `evals/session_brief/tournament.py`.
   - Discover candidate PNG pairs (full image + first-240px `.glance.png`) from the Lane C render manifests and a current-pane render set.
   - Validate fixture/width/mode coverage before calling graders; fail closed on missing or mismatched evidence.
   - Generate randomized left/right pairings with Swiss-style rounds and at least two meetings per candidate pair in each fixture class; keep decisions reproducible via a seed.
   - Send transcript truth (`state`, `waiting_on`, `topic`) and both image crops/full PNGs to a vision grader using a bounded, retryable provider client.
   - Aggregate outcomes into Elo per candidate and width, retain raw verdicts, and run a second model family only on each width’s final round.
3. Produce the review artifact.
   - Write `temp/session-brief-eval/ha-z6q/tournament.json` (gitignored) with inputs, pairings, raw verdicts, Elo tables, final-round cross-family checks, and spot-check bookkeeping.
   - Write `evals/session_brief/reviews/2026-10-02-lane-d-tournament.md` with the Elo table pasted verbatim, winner/current comparison, and verified losing-design findings tied to exact PNGs and regions.
4. Validate.
   - Unit-test pure pairing/Elo/coverage/serialization helpers with behavioral contracts.
   - Run the real script in a bounded smoke mode against local fixtures with provider calls stubbed or replayed only for the harness layer; keep this distinct from the real vision evidence.
   - Run `scripts/run_tests.sh` for affected tests and inspect representative pair verdicts by eye; record 10 agreements/disagreements in the review artifact.

## 2. Architectural changes and boundaries

- Add one evaluation module under `evals/session_brief/`; no product, prompt, store, contract, RPC, or desktop changes.
- Keep provider transport behind a small adapter so pair generation, evidence validation, Elo, and report writing remain deterministic and testable.
- Keep truth data sourced from Lane A receipts/fixture metadata and image paths sourced from the real render manifests; never infer state from candidate text or transcript prose inside the tournament.
- The current pane is a comparison candidate, not a special baseline path. Candidate names and image roots stay data-driven.

## 3. Test and evidence plan

- Target truth: a returning user answers done / waiting-on-me (exact action) / running / topic faster and more correctly from the actual pane pixels.
- Required evidence layer: paired PNGs from the real renderer, including `.glance.png` and full images, with transcript truth and model verdicts; final-round agreement from two model families; human spot-checks of 10 verdicts.
- Useful but insufficient proxies: type checks, unit tests, image-file existence, candidate manifests, and a single grader family. These prove plumbing or deterministic math, not glanceability.
- False-completion substitution to avoid: treating a passing script, Elo winner, or semantic preview as proof that a candidate beats the current pane.
- If the plan succeeds but the bug remains: the winner may be selected from incomplete/nondeterministic fixtures, the current pane may be rendered from a different contract, the decisive state cue may fall below 240 px, or grader claims may disagree with the human eye. The review must name these residual risks.

## 4. Support structures and artifacts

- `agent-execution.log`: temporary subtask receipts with PT timestamps and progress percentages.
- `temp/session-brief-eval/ha-z6q/tournament.json`: raw run output; never commit temp outputs.
- `evals/session_brief/reviews/2026-10-02-lane-d-tournament.md`: durable report and human spot-check record.
- Optional replay fixture/JSONL input for deterministic tests, kept under `tests/evals/fixtures/` only if needed; do not add generated screenshots to git.

## 5. Documentation changes

- Add the lane-specific plan and final tournament review only.
- Do not edit `PLAN.md`, `README.md`, or `rubric.md`; they are the shared oracle contract.
- Document provider/model names, seeds, image roots, and limitations in the review so another reviewer can reproduce or audit the run.

## 6. Execution order and stability strategy

1. Claim, branch, and clean-base preflight.
2. Write and refine this plan; record execution receipts.
3. Inspect manifests and current-pane availability; stop before grading if evidence is incomplete.
4. Implement pure tournament primitives and provider adapters.
5. Add focused tests, then run a bounded real-data smoke/replay check.
6. Run the full requested tournament with bounded concurrency, preserve raw output, and inspect 10 verdicts by eye.
7. Commit code/tests/docs, run affected checks, verify the branch, and hand off to Refinery.

Stability: explicit seed, deterministic candidate ordering, bounded retries/timeouts, atomic output files, no mutation of shared temp inputs, and no use of process-global model or profile state.

## 7. Blocker avoidance and candidate subagent-parallel work

- Independent evidence inspection can be parallelized across candidate render roots, but the coordinator owns the single validated input index and final report.
- Pure math/test review can be delegated independently from provider-client implementation if an authenticated helper is available; no helper result substitutes for branch/diff/test verification.
- If the second model family or current-pane render is unavailable, preserve the first-family results but report “no candidate beats current” only when the evidence supports it; otherwise mark the tournament incomplete and escalate rather than fabricate acceptance.
- Avoid installing new dependencies or changing lockfiles; use existing HTTP/image tooling and the checked-in environment.

## No-change decisions

- No changes to `SessionBrief`, `agent/session_brief.py`, desktop components, stores, i18n, RPC, config, or model prompts.
- No change-detector tests and no committed PNG snapshots.
- No automatic human-verdict substitution for the required pixel-level evidence.

## Planning pass 1 — counter 1

### Critique, top to bottom

- The plan names a current-pane candidate but does not yet define how its render root is located or proven to use the same fixture contract as Lane C. The implementation must accept an explicit current render root and fail closed when it is absent; it must not silently reuse a candidate as “current.”
- “Swiss-style” is underspecified. A tournament needs a deterministic schedule, at least two meetings for every unordered pair within each fixture class, and enough rounds to meet the acceptance threshold of 40 comparisons per candidate per width. The schedule and its proof counts belong in JSON.
- The provider adapter is too abstract about model families and credentials. It must support the existing OpenRouter-compatible path without logging secrets, allow an offline replay/stub mode for tests, and expose bounded request failures as incomplete evidence rather than synthetic wins.
- The review artifact requirement should distinguish raw grader claims from human-verified findings. A winner is not a verified design fact until the 10 spot-check rows identify the exact image and region.
- The test plan does not identify the image encoding boundary. Full PNGs and glance crops must both be sent or represented in the prompt, with file-size/format validation, while deterministic tests should avoid embedding large binary fixtures.

### Critical evaluation of that critique

These are necessary contract clarifications, not scope expansion. Explicit current-pane input prevents a false baseline. A schedule validator can prove pair counts without hardcoding a candidate count. Provider failures must remain visible in the receipt because a missing model response cannot be treated as a loss or win. The human-review section should remain a report-level field so model output is not upgraded to truth by serialization. Image validation belongs at the evidence boundary; pure tests can exercise it with tiny generated PNGs or malformed bytes.

### Roll-up: revised decisions

- Add CLI inputs for `--renders-root`, `--current-root`, `--fixtures`, `--out`, `--seed`, and provider/model settings; require the current root unless an explicit incomplete dry-run is requested.
- Define comparison units as `(fixture_id, message_count, bucket, width, mode)` and schedule every candidate pair at least twice per fixture class, then add deterministic Swiss rounds until each candidate has ≥40 comparisons per width where evidence exists.
- Store provider failures and skipped comparisons with reasons; exit non-zero for an incomplete real tournament.
- Keep model verdicts, Elo calculations, and human spot-check records separate in the output schema and Markdown report.

## Planning pass 2 — counter 2

### Critique, top to bottom

- The evidence inspection found that Lane C manifests are per `(candidate, width, mode)` and contain 20 rows, while no current-pane render tree exists in the shared temp directory. The plan must explicitly include generating current renders with the real `render.mjs` from this branch before the tournament; accepting a candidate render as current would invalidate the comparison.
- The fixture manifest repeats conversation ids across buckets and message counts. Pair keys must use the full render id/message boundary plus the selected bucket, not only `fixture_id`, or pivot/medium rows will collide.
- Existing `runner.py` has a usable OpenRouter transport but no image-capable tournament abstraction. Reimplementing unbounded HTTP in the new module risks divergent credential loading and retry behavior; the tournament should reuse or narrowly wrap the existing transport while extending it for multimodal content.
- “At least 40 comparisons per width” cannot be satisfied by one pair per fixture: seven candidates and 20 fixtures provide 120 comparisons per candidate if every unordered pair is played once per fixture, but class balancing and duplicate meetings need an explicit count formula. The schedule should report both total and distinct fixture-class comparisons per candidate.
- The current output requirements say “winner beats current by >100 Elo with both grader families agreeing, OR no candidate beats current,” but the script must not claim the second outcome merely because the second family is missing. It needs a tri-state completion verdict (`winner`, `no_candidate_beats_current`, `incomplete`).

### Critical evaluation of that critique

The render harness evidence is decisive: current renders must be generated from the current branch, and the command plus commit must be recorded. Full render ids are the stable unit because the same conversation appears at multiple boundaries. Reusing `runner.chat` would couple the tournament to a text-only message type, so a small shared transport wrapper with the same API-key policy is safer than modifying production code. With seven candidates, a complete round-robin on every fixture produces ample evidence; the scheduler can use all unordered pairs twice and then compute the 40-comparison gate rather than invent additional pairings. The tri-state result prevents an availability failure from becoming a scientific conclusion.

### Roll-up: revised decisions

- Add a pre-run support step to render `current` at 280/320/400 dark/light from Lane A fixture JSONs using `render.mjs`; pass that root explicitly and record its manifest hashes.
- Use a stable fixture key `(selected_bucket, fixture_id, message_count)` and verify every candidate/current manifest maps exactly once to each width/mode row.
- Keep `runner.py` unchanged; implement an image-aware adapter in `tournament.py` with identical OpenRouter credential lookup and bounded retries, plus a codex/Claude command adapter for the final-round family.
- Use a complete two-meeting round-robin per fixture class, seed only the left/right orientation and fixture ordering, and calculate `comparisons_by_candidate_width` before grading.
- Make acceptance explicit: `winner` only if a candidate clears +100 Elo over current and both families agree on final-round direction; `no_candidate_beats_current` only after both families complete; otherwise `incomplete`.

## Planning pass 3 — counter 3

### Critical evaluation of pass 2, top to bottom

- Generating the current pane is necessary, but the selected Lane A snapshot JSONs and the Lane C fixture manifest must be joined by `(fixture_id, message_count)` and checked against the Lane A `grades.jsonl` truth row. A render can succeed while truth is missing or from a different boundary.
- A complete round-robin repeated twice per fixture class is intentionally more than the minimum and may create a large bill. The script should support `--max-comparisons`/`--limit` for smoke runs, but the acceptance run must keep the full schedule and record request counts, latency, and skipped/error rows.
- The OpenRouter response may contain JSON wrapped in markdown or a malformed winner. Parsing must validate the four required fields and normalize only harmless casing/whitespace; malformed responses are provider failures, never guessed winners.
- Codex CLI final-round review can observe the repository or invoke tools unless sandboxed. The adapter must pass images as initial attachments, use an ephemeral read-only invocation, cap subprocess time, and parse only the final assistant message; it must not expose secrets or allow file mutation.
- The review document cannot truthfully list verified findings until a human actually inspects the referenced PNGs. The script should emit a report template with raw rows and a required `spot_check` section; the completed artifact can only be marked verified after manual edits.

### Critical evaluation of that critique

The join and truth checks are the core evidence boundary and should be enforced before any grader calls. A smoke limit is safe only when the output labels itself incomplete and the test never treats it as an acceptance result. Strict response validation is preferable to silently repairing a model claim. The Codex subprocess should be optional/configurable but required for a claimed final acceptance. Human verification remains outside automation; the durable report must make unverified rows visually obvious.

### Roll-up: final plan

- Build a validated index from the fixture manifest, Lane A `grades.jsonl`, and each candidate/current render manifest; require exactly one truth row and both PNG paths per comparison unit.
- Implement deterministic two-meeting round-robin scheduling across all seven candidates for every selected bucket, with an optional bounded smoke mode that cannot report acceptance.
- Use strict JSON verdict validation, bounded OpenRouter retries, optional Codex CLI final-round checks, raw request receipts, and a tri-state outcome.
- Generate a Markdown report containing the verbatim machine table plus a clearly marked “human spot-check required” table; manually complete 10 rows only after opening the actual images.

## Lost-information check after three passes

- Preserved: fixed 20-row fixture selection, per-width/theme pixel evidence, current-pane control, two grader families, ≥40 comparisons per candidate/width, Elo winner threshold, human spot-checks, no-product scope, and explicit proxy limits.
- Added without dropping earlier constraints: current renders are generated from the real harness; truth is joined at the message boundary; provider failures produce `incomplete`; raw and verified claims remain separate; test smoke runs cannot satisfy acceptance.
- No-change decisions remain intact: oracle docs and product contracts are not edited, generated PNGs stay outside git, and no test expectation is changed.

## Explicit no-change decisions

- No changes to the shared oracle definitions or any production/session-brief contract.
- No committed screenshots, model keys, transcripts, or temporary run output.
- No claim that a grader result proves user glanceability without the required human image checks.
