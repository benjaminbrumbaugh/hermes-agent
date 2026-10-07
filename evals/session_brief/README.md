# Session brief eval

The oracle for the Brief-pane design program (`evals/session_brief/PLAN.md`).
Measures whether a brief lets a returning user answer **done / waiting on me / running / about what** in a
glance, against real transcripts.

## Current production contract (v3)

The model returns `goal/status/tasks/blockers`; persistence and gateway wire additionally retain
`completed`, `version`, `updated_at` and `message_count`. Current goal is a verb-led conversation
action, not a static feature noun phrase. A contextual follow-up retains the named subject but updates
the activity (for example, "Check calendar repair progress").

Each task has stable `id`, nullable `parent_id`, verb-led `goal`, explicit `status`, and compact
`detail`. States are `pending/in_progress/waiting/paused/timed_wait/completed/cancelled`.
Task history records salient conversation work, not external feature milestones or execution todos.
Omitted previous IDs remain unchanged; detours pause parents, completed children do not complete
parents, and resumption reuses IDs. Duplicate IDs, changed parent links, missing parents, invalid
states and cycles reject the update without overwriting previous work. Persistence merges tasks
atomically against the current lineage brief as well as generation merging its previous context.
Legacy rows stay readable with `tasks: []`; legacy outcomes never manufacture a task hierarchy.

External handoff is not completion of requested implementation/delivery. Accepted dispatch leaves
the outcome parent `waiting`; explicit active-worker evidence yields `in_progress`; a completion
report awaiting required verification remains `waiting`; evidenced requested delivery yields
`completed`. A distinct handoff child may complete at acceptance without completing its parent.
For a dispatch-only request, acceptance may complete the requested outcome. External waits do not
populate user blockers, and an idle tool loop does not prove that external work is finished.
Evaluate these semantics through real auxiliary generation, persistence and callback readback;
unit mocks and manually authored rendering fixtures cannot establish model judgment. The brief
is still a probabilistic, display-only interpretation of evidence, not live worker telemetry.

Production v3 refreshes include up to 12 earlier direct user requests alongside the new-turn delta.
The first legacy-to-v3 refresh rebuilds from the available transcript; the writer receives only
bounded evidence: up to 8 paired historical direct requests/assistant final responses, the latest
assistant response, and up to 3 tool results after the latest direct request. Historical outcomes
are explicitly labeled **not authority for current goal/state/latest-request completion**. Tool-call
plans are excluded; old tool results cannot become current outcome evidence. The whole evidence
view remains capped at 24,000 characters. The previous brief alone is not sufficient topic
evidence: an already-vague draft must not make "check in on them" the conversation's goal.
Previous task context is included and redacted. Output budget is 4,096 tokens; the model may emit
only changed/new tasks because omitted tasks are retained by stable ID.
Synthetic delegation and compaction rows remain excluded. If compaction has removed all direct
topic evidence, the previous goal is the remaining context; the writer must not invent a referent.
Refresh gating and both evidence renderers share the same direct-user predicate. Exact canonical
steer wrappers retain their user text; lookalike wrappers do not. A synthetic-only delta cannot
trigger a refresh that promotes historical context to a new controlling request.

```bash
# 1. corpus from a local state.db (REAL data; temp/ is gitignored — never commit it)
.venv/bin/python evals/session_brief/extract_corpus.py --db ~/.hermes/state.db --out temp/session-brief-corpus --per-bucket 60 --max-messages 6000

# 2. generate briefs turn-by-turn through the production iterative path, then grade against the rubric
.venv/bin/python evals/session_brief/runner.py generate --corpus temp/session-brief-corpus --variants baseline <other> --out temp/session-brief-eval/run1 --concurrency 128
.venv/bin/python evals/session_brief/runner.py grade --out temp/session-brief-eval/run1 --concurrency 128
.venv/bin/python evals/session_brief/report.py temp/session-brief-eval/run1        # exit 0 only if every variant ships

# 3. render the generated briefs as the sidebar shows them (starts its own Vite dev server)
npx --no playwright install chromium                                                  # once
node evals/session_brief/render.mjs --fixtures temp/session-brief-eval/run1/baseline --out temp/session-brief-eval/run1/renders --width 320 --mode dark
```

- `rubric.md` — failure modes and ship thresholds. `report.py` mirrors the thresholds; the contract test keeps them equal.
- `variants/<name>.md` — archived v1/v2 competing prompts; not evidence that the current v3 contract ships.
  `baseline` is always the shipped prompt (`agent.session_brief._SYSTEM_PROMPT`). V3 eval integration
  must pass `previous` to normalization and use the same evidence rebuild policy as production.
  Old variant schema deltas must be rebased to v3 or explicitly evaluated against a frozen legacy
  schema, never silently compared as current-contract variants.
- `render.mjs` drives `apps/desktop/src/app/brief-fixture/` (`?win=brief-fixture`, DEV builds only) — the real
  `BriefPane` with real theme tokens, i18n and stores, no Electron. `*.glance.png` is the first 240 px.
- Model: `stealth/space-bunny-alpha` via OpenRouter (`OPENROUTER_API_KEY` from env or `~/.hermes/.env`), ~256
  concurrent is fine. Grader claims are claims: `report.py --worst N` prints the rows to verify by hand.
