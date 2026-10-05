# Session Brief — glanceable sidebar design program

> **Execution rule:** This plan is a scope ceiling. The deliverable is ONE pane (`BriefPane`), ONE generator
> prompt/schema (`agent/session_brief.py`), ONE store. No design system, no new RPC, no new core tool, nothing
> injected into the model prompt. Every lane names its consumer; every number comes from a checked-in script.

**Status:** Phase 0 complete; convoy minted 2026-10-02 as epic `ha-7nh` (lanes ha-rvo A, ha-bj0 B, ha-dab C, ha-z6q D, ha-lt6 E, ha-fsd F, ha-0ba G, ha-4lv H). Re-mint artifact: `graph-plan.json`.

## Goal

The right-sidebar Brief is a **status instrument a human scans while switching between conversations**, not a
document to be read. Within ~2 s, without reading, the user must know:

1. **Is it done?**  2. **Is it waiting on me — on what exactly?**  3. **Is it still running?**  4. **What was this about?**

Everything else is secondary. The program redesigns the brief's **content contract** (schema + prompt), its
**rendering** (hierarchy, density, state encoding at sidebar width), and its **update behavior** (freshness,
what-changed) around that task, using massive parallel generation + adversarial review against a fixed oracle.

## Why an oracle first

Agent design review without a shared measurable target converges on taste and more text. The oracle makes
reviewers argue about evidence: real transcripts, a rubric with named failure modes, a renderer that produces
the pixels a user sees, and a scoring script whose thresholds decide what ships.

## Oracle (Phase 0 — built)

| Piece | Path | What it proves |
|---|---|---|
| Fixture corpus | `evals/session_brief/extract_corpus.py` → `temp/session-brief-corpus/` (gitignored; real data never committed) | Real conversations, bucketed `short/medium/long/pivot/handoff`; lineages reconstructed across compression |
| Rubric | `evals/session_brief/rubric.md` | 30 named failure modes under state / goal / truth / density / freshness / voice; `glance_score` 0–5; ship thresholds |
| Content eval | `evals/session_brief/runner.py generate | grade` | Replays each conversation turn-by-turn through the REAL iterative path (`agent.session_brief._build_messages/_parse_brief/normalize_brief`); grader with full transcript scores each snapshot against the rubric. Space Bunny over OpenRouter, resumable, N-way concurrent |
| Scorecard | `evals/session_brief/report.py` | Per-variant means by bucket, state confusion matrix, failure rates, ship checks; prints worst snapshots with evidence for human verification |
| Render harness | `apps/desktop/src/app/brief-fixture/` (`?win=brief-fixture`, DEV only) + `evals/session_brief/render.mjs` | Screenshots `BriefPane` with real theme/i18n/stores at sidebar width; `*.glance.png` = first 240 px |
| Contract test | `tests/evals/test_session_brief_eval_contract.py` | Baseline variant == shipped prompt; boundaries == finalizer hook points; thresholds == rubric |

### Baseline measurement (smoke: 3 fixtures × 4 snapshots, 2026-10-02)

Scorecard from `report.py` — a transcript, not a typed table:

```
mean_glance 2.33   state_agreement 0.667   critical_rate 0.75   ships: false
top failures: density.padding .58  decision.not_a_decision .50  fact.invented .50  density.verbose .50
              density.low_signal_completed .42  state.wrong .25  waiting.false .25
```

The grader is a claim until a reader verifies its worst rows against the transcript (report prints them). Do that
in Lane A before trusting any number. Full-corpus baseline (41 fixtures, 6 snapshots) is Lane A's first output.

## Frozen rules

1. The brief is a human-only sidecar. Nothing from it enters the model prompt. Caching untouched.
2. Backend is authoritative; the renderer never derives brief content from the transcript.
3. Strict JSON contract; the renderer never parses prose. Schema changes bump `BRIEF_VERSION` and the TS contract regenerates.
4. One auxiliary call per completed turn, iterative (previous brief + new turns only). No full-transcript resend.
5. Config stays `auxiliary.session_brief` in `config.yaml`; no env vars.
6. The ship decision is `report.py` thresholds + a render tournament where both grader families agree. Not a reviewer's verdict alone. (A human flash-card glance test was built as Lane G and withdrawn at the user's request on 2026-10-04.)
7. Scope: `agent/session_brief.py`, `hermes_state_brief.py`, `tui_gateway/contracts/common.py::SessionBrief`, `apps/desktop/src/app/right-sidebar/brief.tsx`, `apps/desktop/src/store/session-brief.ts`, i18n strings, and `evals/session_brief/`. Anything else is a separate PR with its own justification.

## Lanes

| Lane | Work | Deps | Consumer | Output |
|---|---|---|---|---|
| **A. Baseline + rubric calibration** | Full-corpus baseline run; human-verify the 20 worst grader rows; fix rubric/grader where the grader is wrong (not where the brief is); re-run; freeze rubric v1 | — | every later lane | `temp/session-brief-eval/baseline/` scorecard; rubric v1 commit |
| **B. Content variants (K≈8)** | Independent authors write competing system prompts (+ optional schema deltas) in `evals/session_brief/variants/<name>.md`, each with a one-paragraph thesis. Run all through `generate`+`grade` on the full corpus. | A | integration | scorecards per variant |
| **C. Design candidates (N≈6)** | Independent designers each deliver a complete `brief.tsx` (+ schema needs) on a branch, rendered on a fixed 20-fixture set via `render.mjs` at 280/320/400 px, dark+light. Each ships a rationale naming which rubric modes the layout defeats. | A (fixture set) | tournament | PNG sets + branch per candidate |
| **D. Pairwise render tournament** | Vision graders (Space Bunny; a second model family for the final) compare candidates two at a time on the same fixture: "which answers the four questions faster — point at the pixel." Swiss rounds; script aggregates Elo. | C | integration | `tournament.json`, winner + verified findings from losers |
| **E. Integration** | Merge winning prompt (B) + winning layout (D); fold verified findings; regenerate contracts; i18n for all locales | B, D | review | integrated branch |
| **F. Adversarial review rounds** | Per `adversarial-plan-review`: parallel multi-family read-only reviewers; findings `claim / evidence / change / severity`; integrator verifies every finding against the artifact; serial rounds until a round rejects nothing; confirmation gate `CONFIRMED | NOT-CONFIRMED` | E | merge gate | review records in `evals/session_brief/reviews/<date>/` |
| **G. (withdrawn)** | Human flash-card glance test — built, then removed at the user's request; the two-family tournament agreement is the glanceability gate | — | — | — |
| **H. Ship** | PR to `main_plus_our_prs`; `report.py` thresholds asserted in PR body; app rebuilt via updater | F | user | merged PR |

Widest wave: B (8) ∥ C (6) → pool of 14 polecats + graders. Generation/grading jobs are not polecats; they are
`runner.py` runs at up to 256 concurrent requests.

## Where the agents run

Phase 0 ran against this checkout's Vite dev server and Space Bunny directly. Lanes B–D run on polecat worktrees:
each worktree has its own `apps/desktop` so `render.mjs` starts its own dev server on a random port — no
collision with the user's running app or dev server. The corpus is read-only shared input (`temp/session-brief-
corpus/` path passed explicitly). Nothing in the program touches `~/.hermes` state or the live backend.

## Deliberately not in this program

- Changing *when* the brief refreshes beyond the existing post-turn hook (a streaming/mid-turn brief is a different cost model) — rejected for v1.
- A brief for cron/subagent sessions — rejected (no human returns to them).
- Injecting the brief into compression summaries or the prompt — rejected (rule 1).
- Sidebar chrome beyond the pane (tab strip, toggle, layout presets) — fixed separately (`4058808a91`, `8e5c27c8cd`).

## Completion evidence

- `report.py` says `ships: true` for the shipped variant on the full corpus.
- Tournament winner beats the current render by > 100 Elo with ≥ 2 grader families agreeing.
- All existing brief tests + `test_session_brief_eval_contract.py` green; desktop vitest/tsc/eslint green.
- **Not proved by this program:** long-run cost of the aux call at scale (observe via `auxiliary` usage after ship); non-English locales' glanceability (strings translated only); human glanceability directly (the human test was withdrawn — the two-family tournament is the proxy).

## Adversarial review record

### Lane F — 2026-10-03 — target `59e03c46dd`

Model families: Claude/Opus and Codex/gpt-5.6-terra. Raw receipts and local
verification are archived under `reviews/2026-10-03-lane-f/`.

- Round 1 found and locally reproduced two blockers: later deltas discarded
  explicitly carried completed outcomes, and independent auxiliary refreshes
  could overwrite a newer result. v1 `decisions` projection, prompt-cache
  isolation, and the compression-slice concern were rejected or unconfirmed.
- Round 2 fact-checked the first fixes. It found that message-count-only
  ordering fails when compaction lowers the count, that zero-token new items
  could pass the evidence filter, and that the first desktop alias ordering
  approach was insufficient. The fixes now capture refresh order before the
  worker starts, compare `(updated_at, message_count)` atomically, reject
  zero-token new outcomes, and compare all cached lineage aliases. The
  case/whitespace-insensitive carry-forward rule is intentional and documented.
- Round 3 was ship-blocker-only. Both model families returned
  **NO SHIP-BLOCKERS** after the final alias regression test was added.

Confirmation gate: **CONFIRMED-WITH-NITS**. The adversarial review is
confirmed by two independent model families and passing affected checks. The
remaining nits are evidence-layer limits, not review blockers: Lane E's
existing full report still records `ships=false`, and the dedicated human
glance/non-English visual gates were not rerun for the changed prompt. This
review therefore does not promote the product ship decision or substitute for
Lane G/H.
