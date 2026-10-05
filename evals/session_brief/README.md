# Session brief eval

The oracle for the Brief-pane design program (`evals/session_brief/PLAN.md`).
Measures whether a brief lets a returning user answer **done / waiting on me / running / about what** in a
glance, against real transcripts.

Contextual follow-ups must retain the concrete subject; only a material user pivot replaces it.
Production refreshes include up to 12 earlier direct user requests alongside the new-turn delta,
without replaying old assistant/tool outcomes. The previous brief alone is not sufficient topic
evidence: an already-vague draft must not make "check in on them" the conversation's goal.
Synthetic delegation and compaction rows remain excluded. If compaction has removed all direct
topic evidence, the previous goal is the remaining context; the writer must not invent a referent.

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
- `variants/<name>.md` — a competing system prompt. `baseline` is always the shipped prompt (`agent.session_brief._SYSTEM_PROMPT`).
- `render.mjs` drives `apps/desktop/src/app/brief-fixture/` (`?win=brief-fixture`, DEV builds only) — the real
  `BriefPane` with real theme tokens, i18n and stores, no Electron. `*.glance.png` is the first 240 px.
- Model: `stealth/space-bunny-alpha` via OpenRouter (`OPENROUTER_API_KEY` from env or `~/.hermes/.env`), ~256
  concurrent is fine. Grader claims are claims: `report.py --worst N` prints the rows to verify by hand.
