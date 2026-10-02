# Lane B execution plan — `ha-bj0`

Counter: 0

## Pass 1 — full plan and tasks

### Objective

Evaluate eight materially different session-brief content contracts plus the shipped baseline on the
full 41-fixture corpus and six sampled snapshots per fixture. Preserve baseline behavior, make schema
variants explicit and runnable, and publish one evidence-backed recommendation. Do not integrate the
winner into `agent/session_brief.py`; Lane E owns that boundary.

### Tasks and subtasks

1. **Load the oracle and establish evidence.**
   - Read `PLAN.md`, `README.md`, `rubric.md`, production prompt/schema, runner/report, and Lane A notes.
   - Verify the corpus index is the expected 41 fixtures and record the missing Lane A scorecard as a
     limitation, not as a guessed input.
   - Inspect existing tests and identify the contract seams that must remain baseline-identical.
2. **Author eight independent variants.**
   - `state_first`: first line is an explicit state answer.
   - `delta_first`: lead with what changed since the previous brief.
   - `blocker_dominant`: promote exact user action/blocker above all else.
   - `minimalist`: three compact fields with low-signal sections removed.
   - `enum_state`: add an explicit `state` enum and `waiting_on` field.
   - `decision_pruned`: reserve decisions for actual choices and rationale.
   - `user_voice`: plain-language, user-noun contract with strict anti-jargon rules.
   - `instruction_only`: retain the baseline schema and revise only the operating instructions.
   - Put each whole prompt in `variants/<name>.md`; put exact schema deltas in sidecar JSON for changed
     schemas, with a thesis comment in every prompt.
3. **Extend only the eval variant boundary.**
   - Load prompt, response schema, and normalization metadata per variant.
   - Keep baseline wired directly to `agent.session_brief` prompt/schema/normalizer and prove that in tests.
   - Normalize schema variants into the evaluator's stable `goal/status/completed/blockers/decisions`
     view without modifying production persistence or renderer contracts.
4. **Run and inspect.**
   - Run no-network contract/unit tests first.
   - Generate baseline + eight variants on all corpus fixtures, then grade and report to a bead-specific
     temp directory outside git.
   - Preserve raw report output and scorecard JSON; inspect worst rows for each variant and note grader
     claims versus what the artifact actually proves.
5. **Recommend and document.**
   - Write the review with the report output verbatim, per-variant thesis, unique wins/losses, schema
     tradeoffs, evidence boundaries, and exactly one recommended content contract.
   - Add a concise README note only if the new variant metadata format is otherwise undiscoverable.

### Architectural changes

- `evals/session_brief/runner.py` gains a variant descriptor boundary: prompt + schema + evaluator
  normalizer. It must not import or mutate production variant state beyond reading the baseline exports.
- Sidecar schema files are declarative eval inputs; they are not production API contracts.
- The grader continues to see the normalized five-section view so scores compare content contracts on
  the same rubric and renderer-facing fields.

### Test plan and evidence layers

- Add contract tests for descriptor loading, baseline identity, schema-delta normalization, and rejection
  of malformed variant metadata. These prove the local Python eval adapter, not model quality.
- Run `scripts/run_tests.sh tests/evals/test_session_brief_eval_contract.py` for repository test evidence.
- Full-corpus generation/grade/report proves comparative eval behavior at the remote-model/eval layer;
  it does not prove production prompt quality for unseen conversations, renderer pixels, or human glance
  performance. No semantic eval result substitutes for Lane C visual evidence or Lane G human testing.

### Support structures, docs, and execution order

- Support: `variants/README.md` documents prompt/schema sidecars; `agent-execution.log` remains temporary;
  `temp/session-brief-eval/ha-bj0/` remains untracked.
- Order: plan → variant fixtures → runner adapter → tests → local tests → full generation → grade/report
  → worst-row review → recommendation document → final checks → commit/push/handoff.
- Keep all generated outputs outside git and use the shared read-only corpus path named by the epic.

### Stability and blocker avoidance

- Use deterministic variant names and stable JSON formatting; never overwrite production schema.
- The runner is resumable; rerunning generation skips completed fixture files and grading skips existing
  snapshot keys. Use a fresh bead directory for this lane, deleting only its own incomplete artifacts if
  necessary.
- Bound local test commands with the repository runner. If the model/API is unavailable, preserve all
  local artifacts, escalate with the exact failed phase, and do not claim comparative completion.
- Avoid edits to Lane A-owned rubric/grader calibration, production session brief, or desktop code.

### Candidate parallel work

- Variant authoring can be parallelized conceptually, but eight prompts are small and independent; use
  sequential personas in this worktree to keep the evidence and schema conventions consistent.
- Generation and grading are already parallelized by `runner.py`; no extra process fan-out is needed.

## Pass 1 critique (top-to-bottom)

- **Objective:** clear and bounded; it names the required count, corpus, baseline, recommendation, and
  integration boundary. Risk: the absent Lane A scorecard could tempt an unsupported comparison.
- **Tasks:** cover authoring, implementation, testing, execution, and documentation. Risk: “whole prompt”
  files may drift from schema metadata unless loader validation is strict.
- **Architecture:** the normalized evaluator view is necessary for fair scoring, but a schema variant may
  hide a field needed by the grader if normalization is lossy.
- **Evidence:** correctly distinguishes adapter tests, remote evals, visual evidence, and human evidence;
  it should also call out that model stochasticity makes a single run comparative rather than absolute.
- **Support/docs/order:** appropriate and keeps generated artifacts out of source control. README changes
  should be avoided unless the sidecar format cannot be understood from the existing file.
- **Stability/blockers:** resumability and bounded commands are sufficient; a remote run may be long and
  should be monitored without treating unchanged progress as failure.
- **Parallel work:** sequential authors satisfy the task's allowed persona fallback while runner concurrency
  supplies the useful parallelism.

## Pass 1 critical evaluation of the critique

The critique identifies the real risks but under-specifies the schema-normalization invariant: every
variant response must become a complete evaluator view, while schema-specific fields remain available for
review. It also treats stochasticity as a footnote even though it affects winner claims. The plan should
require raw variant payloads plus normalized views and phrase the recommendation as evidence from one
controlled run, not a universal quality proof. The absent Lane A artifact should be recorded in the review
and not block a fresh baseline. No additional production scope is justified.

## Pass 1 roll-up and no-change decisions

- Add an explicit raw-to-normalized preservation test and include schema-specific fields in generated
  snapshots when present, while grading the stable view.
- Add a report note that the run is a controlled comparative sample and model results are stochastic.
- Keep the scope, eight variant theses, baseline preservation, and no-production-integration decisions
  unchanged.
- Do not cherry-pick Lane A's branch: it is not an ancestor of the required base and its files are outside
  this bead's ownership. Regenerate the baseline in this controlled run instead.

## Proxy audit — Pass 1

- **Target truth:** which content contract best answers done / waiting on me / running / about what on the
  real corpus while remaining truthful and glanceable.
- **Required evidence layer:** full-corpus generated snapshots graded against rubric v1, plus raw report
  and human inspection of worst rows; schema adapter tests cover only plumbing.
- **Cheaper but insufficient proxies:** prompt linting, fixture count, parser tests, and smoke runs.
- **Tempting false completion:** selecting the prettiest prompt, relying on a mean score without bucket and
  critical-rate checks, or treating the missing Lane A scorecard as if it existed.
- **If this plan fully succeeds, how could the bug remain?** The grader could miss a state/freshness error,
  the sampled snapshots could miss a pivot, or a schema could normalize away a field the renderer needs.
  The review must name those residual risks and Lane C/G must still validate visuals/humans.

## Pass 2 — refined plan

Counter: 1

Apply the roll-up: require lossless raw variant output plus normalized grading view, record controlled-run
stochasticity and missing Lane A evidence, and test the schema adapter directly. Keep production untouched.
The implementation order and eight independent theses remain unchanged because the critique found no safer
lower-footprint alternative.

### Pass 2 critique

The refined plan is implementable, but “lossless” needs a concrete shape and the review needs a machine-
checkable mapping from each variant to its schema file. It also should guard that all nine variants are in
the run metadata and that a missing/invalid sidecar fails before network calls. No additional proxy should
be added: a local mock model would prove request plumbing only.

### Pass 2 critical evaluation of the critique

This critique improves operational precision without expanding scope. A descriptor test can assert the
variant set, sidecar path, schema identity, and normalizer output. Preflight validation is valuable because
it prevents a partial expensive run. “Lossless” should mean the stored brief keeps variant-native keys while
the grader receives a deliberately projected view; it does not mean arbitrary unknown data is accepted.

### Pass 2 roll-up and no-change decisions

- Add descriptor preflight and a projection contract test before network execution.
- Store native fields under an internal metadata key only in eval output; keep the grader's five keys stable.
- Do not add a local fake-model harness, report threshold changes, or production compatibility shims.

## Pass 3 — final plan and lost-information check

Counter: 2

Final execution is: author/validate eight prompts and sidecars; implement a fail-fast descriptor loader with
baseline identity and native-to-stable projection; test it through `scripts/run_tests.sh`; run baseline + 8
variants over all 41 fixtures and six snapshots; grade/report; inspect and document worst-row evidence and
recommend exactly one contract; run final tests, commit cohesive changes, push, and hand off to Refinery.

### Pass 3 critique

The final plan retains all required work and the boundary/evidence discipline. Remaining uncertainty is
remote availability and whether graders can score newly shaped schemas fairly; the review should flag both
instead of hiding them. The runner's existing resume behavior must not allow a stale run with a different
descriptor to masquerade as current, so run metadata should record descriptor identity.

### Pass 3 critical evaluation of the critique

The stale-run warning is valid and directly affects correctness. Add a descriptor fingerprint/version to
run metadata and validate it when grading. This is still eval-boundary infrastructure, not a production
schema change. Remote availability is an execution risk, not a reason to weaken acceptance.

### Pass 3 roll-up and no-change decisions

- Add descriptor identity to run metadata and grading validation where practical.
- Preserve the frozen rubric thresholds and the lane's ownership boundary.
- Do not expand into renderer rendering or human testing; those are explicitly downstream consumers.

### Lost-information check after three passes

Retained: eight named theses, baseline, full corpus, schema deltas, fail-fast validation, stable grader
projection, raw evidence, tests, review output, proxy audit, no production integration, and Refinery handoff.
Added: evidence boundaries, stochasticity note, native-field preservation, descriptor identity, and the
missing Lane A scorecard limitation. No required information was lost.
