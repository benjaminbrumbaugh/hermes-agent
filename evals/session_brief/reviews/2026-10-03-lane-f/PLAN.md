# Lane F execution plan

`counter=0` at creation. This is the working plan for the adversarial review
of the integrated Session Brief at `59e03c46dd` / `origin/main_plus_our_prs`.
The named `adversarial-plan-review` and `multi-model-adversarial-review`
skills are not materialized in this worktree, so the bead description and the
frozen `evals/session_brief/PLAN.md` procedure are the authoritative fallback.

## Full plan and tasks

1. Establish the review boundary: inspect the integrated diff, its contract,
   prompt, state projection, renderer, i18n, eval harness, tests, and existing
   render/eval artifacts. Treat the backend contract as authoritative and the
   brief as a human-only sidecar.
2. Run independent, read-only review rounds in parallel across at least two
   model families where available. Round 1 attacks rubric blind spots,
   v1-to-v2 compatibility, prompt-caching isolation, contract/TypeScript drift,
   i18n completeness, and 280 px rendering. Round 2 fact-checks every PR claim
   against the actual diff. Round 3 reports ship-blockers only.
3. Store a concise brief and raw review output for each reviewer and round.
   Every candidate finding must name claim, evidence (file:line or PNG region),
   proposed change, and severity.
4. Verify every candidate finding locally against the artifact before accepting
   it. Reject false positives with a written reason. Apply only verified fixes
   within the frozen scope; avoid changing expectations merely to make a test
   pass.
5. Repeat serial rounds until one round rejects nothing. Run the confirmation
   gate: `CONFIRMED`, `CONFIRMED-WITH-NITS`, or `NOT-CONFIRMED`.
6. Run affected backend and desktop checks, plus the strongest available
   contract/eval/render evidence. Record what each check observes and what it
   cannot prove.
7. Append the verified review record and confirmation result to the program
   `PLAN.md`, commit the cohesive review artifacts/fixes, and hand off the
   branch to the refinery.

## Architecture and boundary changes

Expected default: no architecture change. Preserve the narrow Session Brief
boundary: `agent/session_brief.py` owns generation/parsing, persisted state
remains v1-compatible, `SessionBrief` is the strict gateway contract, the
desktop store consumes the contract, and `BriefPane` renders backend values.
Any accepted code change must stay within the frozen scope and must not mutate
the model prompt, caching prefix, refresh timing, or transcript authority.

## Test and evidence plan

- Backend tests observe real parsing, normalization, persistence, and contract
  serialization; they do not prove rendered pixels or human glanceability.
- Desktop typecheck/lint/unit tests observe TS drift and component behavior;
  they do not prove visual hierarchy at every locale or width.
- Contract/eval checks observe schema/prompt/eval wiring; they do not prove the
  grader is correct or that the scorecard substitutes for a human glance test.
- Rendered PNGs at 280 px, both themes, observe actual layout geometry; they do
  not prove model truth or user comprehension.
- The human-glance artifact and report thresholds are the ship decision; a
  passing proxy must not be treated as that decision.

Proxy audit: target truth is that a returning user can answer DONE, WAITING ON
ME (on what), RUNNING, and ABOUT WHAT in about two seconds from the real sidebar.
Required evidence is the real backend path plus rendered 280 px fixtures and a
human glance result. Cheaper useful-but-insufficient proxies are unit tests,
typecheck, snapshots, and the eval grader. The tempting false completion is a
green test suite or a favorable reviewer verdict while `report.py` still says
`ships=false`. Even if this review succeeds, the original bug could remain if
the critical oracle failure is accepted without a human glance run, if a v1
stored row crashes only under a missing field, or if a layout regression is
hidden outside the sampled PNGs.

## Support structures and docs

- `evals/session_brief/reviews/2026-10-03-lane-f/` stores briefs, raw review
  receipts, verification/rejection decisions, and this plan.
- `evals/session_brief/PLAN.md` receives the durable adversarial-review record.
- `agent-execution.log` records completed subtasks with PT timestamps and
  overall progress.

## Execution order and stability strategy

Read-only discovery and model reviews are parallel; finding verification and
code changes are serial. Keep the target SHA fixed while reviewing. Do not use
live user state or mutate the shared corpus. Re-run any failed check in the
prescribed test runner before deciding it is a product failure. If a provider
or visual harness is unavailable, preserve that limitation in the evidence
record rather than substituting a weaker signal.

## Blocker avoidance and candidate parallel work

Independent reviewers can inspect the same frozen SHA in parallel. Backend,
desktop-contract, and visual axes can be reviewed independently, then merged
into one verified finding list. If a model CLI is unavailable, use the other
available family plus a local independent review and record the missing family
as a limitation; do not fabricate a review. Escalate only for credentials,
missing artifacts, or a required decision outside the frozen scope.

## Planning pass 0 — initial plan

The plan covers the explicit lane requirements, keeps the product boundary
unchanged by default, names the evidence layers, and leaves room for verified
small fixes without turning review into a redesign.

## Planning pass 0 critique

The initial plan could accidentally treat model-generated findings as evidence,
and “round rejects nothing” is underspecified unless each reviewer sees the
same frozen artifact. It also needs an explicit check that the integrated PR
claims match the merged commit, and it must not imply that a missing human
glance run can be waived by the review gate.

## Critique of the critique

Those risks are real but are addressed by requiring local verification, fixed
SHA review, claim fact-checking, and explicit proxy limits. The plan should be
strengthened by requiring reviewer prompts to demand evidence locations and by
making the confirmation gate report missing ship evidence as a non-confirmed
result.

## Roll-up: revised critique

Keep the original workflow. Add a per-reviewer evidence requirement, a
claim-to-diff fact-check table, and a hard confirmation rule: no `CONFIRMED`
when the ship oracle or human-glance evidence is absent. No architecture or
scope expansion is warranted.

## Roll-up: revised plan

The execution steps above include fixed-SHA review, evidence-qualified
findings, explicit rejection reasons, and a confirmation gate that cannot turn
missing product evidence into a pass.

## No-change decisions

- Do not alter `report.py` thresholds during review.
- Do not relax v1 compatibility or change the prompt/cache boundary.
- Do not add a new core tool, RPC, config key, or env var.
- Do not claim visual or human correctness from semantic previews, tests, or
  reviewer consensus alone.

## Planning pass 1 (`counter=1`)

Re-check: the review artifacts themselves are part of the deliverable and must
be concise, reproducible, and tied to the exact SHA. Add explicit raw-output
paths and record provider limitations. No-change decisions remain correct.

## Planning pass 1 critique

The plan still permits “local independent review” to be mistaken for a second
model family. It also does not say how to handle the fact that Lane E’s full
scorecard already records `ships=false`; a review can confirm quality but
cannot silently promote that result.

## Critically evaluate that critique

The distinction matters: reviewer families are independent challenge inputs,
while the scorecard and human glance gate are product evidence. The plan must
keep these ledgers separate and make the final status reflect the strongest
available gate, not reviewer confidence.

## Roll-up: apply evaluation to critique

Require two genuinely distinct model-family receipts for a confirmed review
when both are available; label local inspection as human/agent verification,
not a model family. Treat the existing `ships=false` as an unresolved ship
condition unless new evidence on the same integrated artifact changes it.

## Roll-up: apply revised critique to plan

The final record will separate model findings, verifier decisions, and ship
evidence. A review result may be `CONFIRMED-WITH-NITS` while the product still
cannot ship if the oracle/human-glance gate remains false.

## No-change decisions

- Do not rewrite the existing Lane E scorecard from a review-only result.
- Do not present a local agent pass as a second model family.
- Do not run destructive or network-mutating commands in review tooling.

## Planning pass 2 (`counter=2`)

Final audit: verify that the execution order makes the cheapest safe reads first,
parallelizes only independent read-only work, and ends with tests, durable
records, commit, and refinery handoff. Require an explicit finding disposition
for every candidate and a final no-ship interpretation if evidence remains
incomplete.

## Planning pass 2 critique

The only remaining risk is operational: a failed external reviewer could delay
the lane or tempt a fabricated receipt. The work must remain useful with one
provider unavailable, but must not misstate the acceptance requirement.

## Critically evaluate that critique

That is a process risk, not a product reason to lower the bar. The safe result
is to run all available independent evidence, preserve the failure/limitation,
and classify confirmation honestly. The refinery can then decide merge policy
with a durable record.

## Roll-up: apply evaluation to critique

Use bounded provider commands, keep raw outputs even on non-zero exit, and
record unavailable families as limitations. Never manufacture a clean round.

## Roll-up: apply revised critique to plan

The plan is ready for execution. It has a fixed artifact boundary, three review
axes, evidence-layer definitions, serial verification, no-change constraints,
and an honest final gate.

## No-change decisions

- No additional planning pass or scope expansion is needed.
- No implementation is justified until a verified finding identifies a defect.
- No confirmation is stronger than the evidence actually collected.
