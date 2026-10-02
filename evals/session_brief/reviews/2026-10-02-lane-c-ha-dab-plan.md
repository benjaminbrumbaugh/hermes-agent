# Lane C execution plan — `ha-dab`

Initial counter: 0  
Final planning counter: 3  
Scope: six independent `BriefPane` candidates, a fixed 20-snapshot fixture manifest, and render receipts. The coordinator branch owns only the manifest and rationale records; each candidate implementation is pushed to its own `brief-design/<name>` branch.

## 1. Full plan, tasks, and subtasks

1. Establish the evidence baseline.
   - Confirm the Lane A corpus and locate/recover its baseline snapshot inputs.
   - Choose exactly 20 `{fixture_id, message_count}` pairs spanning all corpus buckets and the four rubric truth states.
   - Record the selection in `design-fixtures.json`; never let candidates choose different inputs.
2. Produce six independent candidates.
   - Candidate names: `beacon`, `matrix`, `pulse`, `strata`, `ledger`, and `compass`.
   - Each candidate replaces `apps/desktop/src/app/right-sidebar/brief.tsx` (and may add a local sibling only if needed), preserves backend/store authority, and uses existing design tokens/primitives.
   - Candidate branches are `brief-design/<name>` and start at `origin/main_plus_our_prs`.
   - A candidate may state a schema need, but must render against the current fixture contract and must not change stores, generator, RPC, or the model prompt.
3. Render and verify.
   - For each candidate, run the real `evals/session_brief/render.mjs` harness over the same 20 fixtures at widths 280, 320, and 400 in dark and light modes.
   - Save 120 PNGs per candidate (full and glance receipts as emitted by the harness) under `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/<name>/`.
   - Run candidate-local TypeScript, ESLint, and the existing Brief-related Vitest files.
4. Document design intent.
   - Write one rationale per candidate in `evals/session_brief/reviews/2026-10-02-design-<name>.md`.
   - Name the rubric failure modes the layout is intended to defeat and state its known trade-offs.
5. Handoff.
   - Commit only the manifest, six rationales, the plan, and execution evidence on `polecat/ha-dab`.
   - Push all six candidate branches and the coordinator branch; leave implementation-bead closure to the Refinery.

## 2. Architectural changes and boundaries

- No backend, store, schema, RPC, generator, prompt, or cache changes.
- `BriefPane` remains a read-only projection of `$briefsBySession` and `$todosBySession`.
- Candidate visual state is derived only from existing brief/todo data; the renderer must not infer state from transcript text.
- All colors, borders, shadows, controls, and spacing use `DESIGN.md` tokens/primitives. No new design-system abstraction is introduced for one pane.
- Fixture selection is an evaluation boundary: it is immutable input shared by all candidates, not product code.

## 3. Test and evidence plan

- Base preflight: TypeScript compiler, targeted ESLint, and existing `session-brief.test.ts` plus `brief-pane-toggle.test.ts`; this observes static type/lint correctness and store/layout contracts, not pixels.
- Candidate checks: the same commands on each branch plus the real render harness; this observes compile/lint/test health and actual browser pixels at the requested widths/themes.
- Render receipts prove only that the harness mounted the current BriefPane and captured images. They do not prove a human can answer the four rubric questions or that the selected snapshots represent truth states; the manifest and rationale record those limits.
- Proxy audit for this visual domain:
  - Target truth: a returning user can answer done / waiting-on-me (exact action) / running / about what within roughly two seconds from the pane.
  - Required evidence layer: Playwright screenshots from the real renderer at 280/320/400 px in both themes, with fixed real generated briefs.
  - Cheaper useful-but-insufficient proxies: tsc, ESLint, unit tests, DOM presence, and a single light-theme screenshot.
  - False-completion substitution to avoid: treating six passing builds or reviewer taste as proof of glanceability.
  - If this succeeds but the bug remains, the likely causes are a bad truth-state fixture label, a state cue below the first 240 px, a narrow-width overflow only visible in one candidate, or untranslated/missing locale copy.

## 4. Support structures and artifacts

- `evals/session_brief/reviews/2026-10-02-design-fixtures.json`: the sole fixture manifest, each row containing `fixture_id` and `message_count` plus selection metadata.
- Six rationale Markdown files: one per branch/candidate.
- `agent-execution.log`: temporary subtask receipt with PT timestamps and progress percentages.
- Git branches and render manifests are the branch/evidence index; PNGs stay in the prescribed gitignored temp tree.

## 5. Documentation changes

- Keep `PLAN.md`, `README.md`, and `rubric.md` unchanged; they define the program contract.
- Add only the six candidate rationales, the fixture manifest, and this lane execution plan.
- Each rationale must distinguish intended rubric coverage from what screenshots actually prove.

## 6. Execution order and stability strategy

1. Load/claim context and record the worktree/branch.
2. Run clean-base preflight.
3. Create the plan and execution log.
4. Recover or generate baseline snapshots, then freeze the manifest.
5. Fan out independent candidate work; no candidate edits the shared branch.
6. Render all candidates from the frozen manifest, inspect representative first-glance images, and repair candidate defects before push.
7. Run final checks, commit coordinator artifacts, verify branch tips, and submit to Refinery.

Stability rules: keep `origin/main_plus_our_prs` as the candidate base; do not rebase a candidate after rendering unless it is re-rendered; keep render outputs outside git; use deterministic fixture ids and message counts; record any unavailable Lane A artifact rather than silently substituting a different corpus.

## 7. Blocker avoidance and candidate subagent-parallel work

- Candidate implementation is independent, so it is the primary parallel lane. Each worker receives one name, one branch, the same manifest, and an explicit prohibition on touching stores/contracts/generator.
- Rendering is embarrassingly parallel only after the manifest is frozen; cap browser concurrency to avoid starving the dev server.
- Missing baseline output is handled by checking the shared Lane A temp path and its completion notes first, then regenerating only the needed baseline snapshots from the shared corpus; no hand-authored “truth” labels are accepted.
- Missing dependencies are repaired from the checked-in root lockfile; no package or lockfile changes are made for this lane.
- A candidate test failure stays on that candidate branch and is fixed there; it never weakens the shared acceptance checks.

## Planning pass 1 — counter 1

### Critique, top to bottom

- The task decomposition is complete but assumes that Lane A's temporary output survives; the notes say it is shared but the filesystem may be cleaned. The recovery path must be executable without changing the production scope.
- The architecture boundary correctly limits product code, but “existing contract” needs an explicit test that no candidate changes the contract files.
- The test plan names layers, yet it risks treating render success as visual correctness; representative image inspection and manifest truth annotations must be explicit.
- The support artifacts are sufficient, but a plan file itself could become accidental product documentation; keep it scoped to `reviews/` and do not edit program-level docs.
- The execution order places parallel work after fixture freezing, which is correct; branch pushes need a post-push hash check.
- Blocker avoidance is sound, but no assumption is made about how helper workers receive custom `brief-design/*` branch names; dispatch must be authenticated and branch names verified by the coordinator.

### Critical evaluation of that critique

The critique identifies operational risks, not reasons to widen scope. The missing Lane A artifacts are a real evidence risk, so regeneration/recovery must be a hard gate before selecting fixtures. Contract-file protection can be enforced by `git diff --name-only` rather than a new test. Visual inspection cannot be delegated to unit tests; it is a required receipt review. The custom branch-name issue is a coordination risk and must be solved before helper dispatch, not papered over in rationale text.

### Roll-up: revised decisions

- Add a manifest provenance field and a short note when baseline data is regenerated.
- Treat screenshot capture, fixture truth classification, and branch-tip verification as separate evidence artifacts.
- Preserve the no-product-scope rule; use diff allowlists for enforcement.

## Planning pass 2 — counter 2

### Critique, top to bottom

- The revised plan still implies that one baseline snapshot can be assigned a single truth state, but the rubric truth is snapshot-specific. Selection must record the truth-state source and message boundary, not infer it from fixture bucket.
- Candidate names are distinct, but the plan does not ensure designs differ in information architecture rather than just CSS. Each rationale should identify a unique primary hierarchy.
- “120 PNGs per candidate” is ambiguous because the harness emits full and glance files; count the six requested combinations as width × theme and assert the manifest has no errors.
- The worker branch workflow could accidentally land candidate code in the coordinator branch. Use branch-specific checkouts or clean switching and verify coordinator diff allowlist before submit.
- The plan does not call out RTL/Arabic fallback even though the requested locales include Arabic. Existing keys may fall back to English, which is acceptable only if documented.

### Critical evaluation of that critique

The critique is correct that truth state is a property of each generated snapshot, not the source conversation alone. If Lane A's grader receipt is unavailable, the correct response is to regenerate or explicitly block the fixture selection—not invent classifications. Distinct information architecture is necessary for a meaningful tournament. The PNG count is 20 × 3 × 2 = 120 captures per candidate, with a glance companion emitted for each. Candidate code isolation and Arabic fallback are boundary concerns that can be checked without changing the locale system.

### Roll-up: revised decisions

- The fixture manifest will contain only the required stable keys plus a `truth_state`/`bucket` provenance note if available; selection will be rejected when truth cannot be evidenced.
- Rationales will state each candidate’s primary scan order and intended rubric coverage.
- Render validation will assert 120 successful full captures and 120 successful glance captures per candidate, not just process exit 0.
- Arabic will use the established English fallback unless a candidate adds a complete translated key set; no partial locale additions.

## Planning pass 3 — counter 3

### Critical evaluation of pass 2

- The plan now has the right gates, but it must not mutate the shared oracle files while recovering artifacts. Any generated baseline stays in the external temp tree.
- Requiring truth metadata in the committed manifest is useful only if it remains auditable; record the source path/receipt rather than a hand-entered claim.
- Parallel helper workers are valuable, but the coordinator remains responsible for branch identity, diff scope, and visual receipts. A worker completion message is not evidence by itself.
- “Existing Brief-related tests” is intentionally narrow for preflight, but final candidate checks must include the harness and all six locale builds if i18n is touched.

### Critical evaluation of that critique

These are evidence and ownership clarifications. They do not change the implementation scope. The source receipt can be a compact manifest note, while large PNGs remain temp-only. Branch and render verification must run from the coordinator’s worktree after workers finish. Locale validation is already covered by the desktop typecheck when keys are typed; additional locale edits require the locale-specific diff check.

### Roll-up: final plan

- Do not edit oracle definitions or production contracts in Lane C.
- Freeze only auditable fixture rows; if Lane A receipts are unavailable, regenerate the exact rows from the shared corpus and preserve their generated records externally.
- Use subagents for independent candidate work where available, but never accept unverified branch names, diffs, tests, or screenshots.
- Keep final coordinator changes docs/evidence-only; candidate implementation branches carry the visual code.

## Explicit no-change decisions

- No change to `SessionBrief`, `agent/session_brief.py`, `session-brief` store, RPC contracts, refresh timing, or model prompt.
- No new core tool, RPC method, config key, environment variable, design-system primitive, or renderer state.
- No changes to `PLAN.md`, `README.md`, or `rubric.md`.
- No change-detector tests and no snapshot test expectations; screenshots are evaluation receipts, not frozen product tests.
