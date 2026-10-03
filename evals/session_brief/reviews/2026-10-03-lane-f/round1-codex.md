# Lane F Round 1 — Codex / gpt-5.6-terra

Review target: `59e03c46dd26893c78d7e5cd76ae462acbbeff40`.

## Findings

- Iterative refresh does not preserve completed outcomes across turns | `agent/session_brief.py:324-339` filters every returned completion against only the new delta, despite `:221-223` instructing carry-forward | preserve explicitly carried prior outcomes with bounded dedupe and add a two-refresh regression test | high
- Concurrent off-path refreshes can persist an older snapshot after a newer one | `agent/session_brief.py:411-421`, `:349-361` and `hermes_state_brief.py:51-62` have no ordering guard; the late write also receives a later timestamp | serialize per session or compare-and-swap on `message_count`; cover inverted completion order | high

## Verified safe paths

- v1 persistence is projected to the current four-field wire shape by `hermes_state_brief.py:17-45,64-79`; the gateway and desktop store accept the current shape. No product change required; an RPC/event-level v1 test would strengthen evidence.
- The brief is an auxiliary request and is never added to the main conversation or prompt builder. Main prompt-cache isolation appears preserved.

## Rejected concerns

- Stored v1 `decisions` cannot leak through the current read RPC because `_wire_brief` strips it.
- Compression lineage lookup is not itself a migration break.

## Evidence gaps

No committed Lane E render scorecard was present at this SHA. Existing tests do not cover multi-turn carry-forward, inverted async completion, RPC-level v1 emission, or cache-key separation.

## Recommendation

Block on the two findings; fix outcome carry-forward and write ordering, then add focused end-to-end tests. Migration and cache isolation are otherwise sound.
