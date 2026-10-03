# Lane F Round 1 — Claude / Opus

Review target: `59e03c46dd26893c78d7e5cd76ae462acbbeff40`.

## Findings

- Completed outcomes are wiped when a new turn does not mention them | `agent/session_brief.py:338`, `:203`, `:206`, and the contradictory rules at `:81` versus `:222-223` | either preserve exact prior outcomes when explicitly carried by the model or redefine the field as latest-only; add a follow-up-turn regression test | high
- Two post-turn updates can commit out of order on both server and client | `hermes_state_brief.py:58-59`, `agent/session_brief.py:274`, `:349`, `:357`, and `apps/desktop/src/store/session-brief.ts:51` | make writes conditional on non-decreasing `message_count`, and compare `message_count` before `updated_at` on the client | medium
- A compression-slice concern was raised but not confirmed | `agent/session_brief.py:371-381`; the finalizer invokes the brief before turn-end compaction, and the fallback is intentionally whole-transcript when the count exceeds the current list | verify with a live post-compression path before changing it | unconfirmed

## Rejected concerns

- v1 `decisions` leakage: `_wire_brief` strips it before contract validation.
- Prompt-cache contamination: the brief uses a separate fixed auxiliary system prompt and is never injected into the main prompt.

## Evidence gaps

No test covers prior-outcome retention, reverse-order writes, or exact post-compression message slicing. Human glanceability still needs the dedicated product gate.

## Recommendation

Fix the first two findings, add focused tests, and do not claim ship readiness from review evidence alone.
