# Lane E implementation plan

counter: 0

## Scope and outcome

Integrate the evidence-backed Lane B content contract and Lane D render findings into the production Session Brief path on `polecat/ha-lt6`. Preserve the backend-authoritative, human-only sidecar boundary, make stored v1 rows render safely, regenerate the typed gateway contract, update the desktop store/render/i18n surface, and prove the integrated result with the full-corpus eval plus focused backend and desktop checks. The acceptance artifact is the generated baseline scorecard with `ships: true`, alongside the verified 20-fixture render set and passing tests.

## Tasks and subtasks

1. Load evidence and freeze the integration decisions.
   - Read the session-brief plan, oracle/rubric, Lane B recommendation, Lane D tournament, production prompt/schema/normalizer, backend state facade, contract generator, desktop store, current brief pane, and locale resources.
   - Identify the exact winning prompt/schema and verified render findings; reject reviewer preference that is not supported by the lane artifacts.
   - Record any config-shape delta before changing docs.
2. Integrate the backend content contract.
   - Adopt the winning prompt/schema in `agent/session_brief.py` and bump `BRIEF_VERSION`.
   - Keep normalization backward-compatible for v1 persisted rows and fail safely on malformed/partial model output according to the existing contract.
   - Preserve cache, iteration, auxiliary-call, profile, and role/message invariants.
3. Regenerate and validate the backend contract boundary.
   - Update `SessionBrief` in `tui_gateway/contracts/common.py` only where the production schema requires it.
   - Run `scripts/gen_gateway_contracts.py`; inspect generated output and store consumers for drift.
   - Update `hermes_state_brief.py` only as needed to preserve authoritative state and v1 compatibility.
4. Integrate the winning desktop render.
   - Merge the winning `brief.tsx` design and fold only Lane D findings verified against fixture PNGs.
   - Update `apps/desktop/src/store/session-brief.ts` type guards and derived helpers to match the regenerated contract.
   - Keep glanceability for DONE / WAITING ON ME (and what) / RUNNING / ABOUT WHAT at the pane boundary.
   - Update every locale for changed strings; keep translation keys stable where semantics are unchanged.
5. Documentation and support structures.
   - Update configuration docs only if the config shape changed.
   - Add or adjust focused invariant tests for v1 rendering, new schema normalization, contract generation, store guards, and pane states.
   - Keep eval output and generated fixtures under the designated gitignored temp tree; never commit run artifacts.
6. Evidence and quality gates.
   - Run baseline generation on the full corpus, grade, report, and retain the scorecard receipt with `ships: true`.
   - Render 20 design fixtures with the integrated pane and inspect the actual PNGs; semantic eval output is not a substitute for visual evidence.
   - Run focused backend tests through `scripts/run_tests.sh`, then desktop `tsc`, ESLint, and Vitest.
   - Review the diff for scope, security, profile/cache invariants, generated-file consistency, and stale docs.

## Architectural changes

- The production backend remains the single authority for brief data; the desktop remains a typed renderer and must not infer lifecycle truth from local state.
- The prompt/schema boundary changes to the Lane B winner, with explicit versioning and a compatibility normalization path for persisted v1 records.
- The gateway contract is regenerated from the source-of-truth contract rather than hand-maintained independently.
- The render changes stay within the existing right-sidebar brief surface; no new core tool, config namespace, or cross-session mutable prompt state is introduced.

## Test plan and evidence layers

- Backend unit/invariant layer: proves prompt/schema normalization, version compatibility, and state facade behavior; it does not prove generated client parity or actual UI glanceability.
- Contract-generation layer: proves source and generated schemas agree; it does not prove the desktop consumes every state correctly.
- Desktop type/behavior layer: proves store guards and component behavior compile and execute; it does not prove pixel-level glanceability.
- Full-corpus eval layer: proves transcript-truth scoring for the integrated production prompt; it does not prove visual layout.
- Render/visual layer: proves the integrated pane renders 20 fixtures and permits human/fixture inspection; semantic score alone is insufficient.
- Review diff and fixture receipts: prove scope and evidence provenance, not production deployment.

Proxy audit for this Proxy-domain work:

- Target truth: a returning user can identify DONE, WAITING ON ME (and the blocker), RUNNING, and topic in about two seconds from the integrated pane, while backend state remains authoritative and old rows remain safe.
- Required evidence: full-corpus truth scoring, generated-contract checks, backend tests, desktop tests, and actual integrated fixture renders.
- Useful but insufficient proxies: a passing unit test, a passing TypeScript build, a semantic preview, or a reviewer opinion without fixture evidence.
- Tempting false completion: declaring success from `ships: true` alone, or from a visually attractive component with stale store guards/schema drift.
- If this plan succeeds but the bug remains: the model contract could still emit ambiguous content, v1 rows could still crash only in a rare state, generated contracts could be stale, or the pane could bury the decisive state in the actual 20-fixture renders. The explicit compatibility tests, regeneration diff, and fixture inspection are intended to catch those cases.

## Support structures and docs

- `PLAN.md` records decisions and refinement passes.
- `agent-execution.log` records completed formula subtasks with timestamps and progress.
- `temp/session-brief-eval/ha-lt6/` stores local eval/render receipts only and is not committed.
- Configuration documentation changes only if the public shape changes; no new environment variable is planned.

## Execution order

Load evidence → establish winning contract/render decisions → implement backend → regenerate contract → update store/UI/i18n → add focused invariants/docs → run full eval and renders → run backend/desktop gates → self-review and commit → push and hand off to refinery.

## Stability and blocker avoidance

- Work only on the per-bead branch and keep the frozen scope boundary.
- Do not mutate past conversation context or introduce mid-conversation prompt/tool changes; Session Brief remains an auxiliary sidecar.
- Use existing generation/test scripts and the project test runner; do not use bare pytest.
- Keep generated artifacts reproducible and inspect diffs after regeneration.
- If a required external model/eval credential or dependency is unavailable, record the exact blocker and escalate to Witness rather than substituting a weaker evidence layer.
- If an unrelated base failure appears, deduplicate in the ledger and do not fold it into this change.

## Candidate parallel work

- An independent agent could inspect Lane B/D artifacts and produce a contract/render decision memo.
- Another could review the existing backend/contract/store compatibility seams and propose invariant tests.
- Another could inspect locale coverage and the desktop fixture harness.

Because the integration must reconcile all three surfaces and the current pool is constrained, I will keep ownership of the cross-boundary edits and use any parallel review findings only as evidence, not as an authority over the frozen scope.

## Refinement pass 0 — initial plan

The plan covers the required source surfaces, compatibility boundary, generated contract, visual evidence, and handoff gates. It deliberately does not assume the winning field names until the lane artifacts are read.

## Refinement pass 1 — critique of every major section

- Scope: acceptance is concrete, but the scorecard and render receipt must be captured without committing temp artifacts.
- Tasks: sequencing is correct; compatibility and generated-contract verification need explicit checks before UI edits.
- Architecture: preserves the narrow waist and sidecar boundary; it must explicitly prevent client-side truth inference.
- Test/evidence: layers are named with what they prove and do not prove; visual inspection must use the integrated pane, not a semantic substitute.
- Support/docs: temporary log and eval output need cleanup before handoff; public docs must follow actual config changes.
- Execution: end-to-end order is safe, but the existing branch/target contract must remain `polecat/ha-lt6`.
- Stability/blockers: external eval availability may be the main risk; fallback evidence must not be mislabeled as acceptance.
- Parallel work: useful reviews are possible, but cross-boundary edits need one owner to avoid contradictory contract changes.

## Refinement pass 2 — critical evaluation of that critique

The critique correctly identifies evidence and boundary risks but could overstate the need for new tests. The existing suite should be extended only where the production contract changes or a v1 regression is otherwise unprotected. The plan also needs an explicit check that all changed locale keys are present and that generated contract changes are limited to the intended schema. The eval command itself should be run from the repository's existing harness with the shared corpus and bead-specific output path.

## Refinement pass 3 — roll-up and no-change decisions

- Apply the critique: add focused invariant coverage only for changed behavior; inspect locale-key parity; compare generated contract diff; keep the exact full-corpus runner commands and bead output path.
- No change: retain backend authority, auxiliary sidecar placement, no new config namespace/env var, and no new core tool.
- No change: retain the planned execution order; it already places compatibility and generation before UI consumers.
- No change: retain the single-owner integration model; parallel agents remain review/evidence candidates rather than competing editors.
- Information-loss check after three passes: the plan still includes every requested surface, evidence layer, stability invariant, docs decision, execution gate, and refinery handoff requirement.

## Approval and execution note

This plan was prepared before implementation with the required initial `counter: 0` and three refinement passes. The autonomous polecat formula provides the execution authority for this bead, so implementation proceeds after the recorded review rather than waiting for an interactive approval response.

counter: 3

## Final evidence receipt

The final exact-code full-corpus run is at `temp/session-brief-eval/ha-lt6-final/`: 263/263 snapshots generated and graded with zero generation errors. The scorecard passes mean glance 4.20, every bucket (minimum 3.76), and verbose rate 6.5%, but reports `ships: false` because the critical-failure rate is 19.8% (state/fact/waiting rubric failures). This is recorded as an acceptance limitation rather than hidden by changing the oracle or substituting a proxy; focused tests, desktop checks, and the 20-fixture visual render all pass.
