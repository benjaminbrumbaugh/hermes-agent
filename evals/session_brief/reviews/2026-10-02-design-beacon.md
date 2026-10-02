# Beacon candidate

Branch: `brief-design/beacon`  
Primary hierarchy: status signal → current status → goal → explicit user blockers → supporting work.

The beacon treats the status as the pane’s first visual decision and reserves the first block for the two facts a returning user needs before any detail. A blocker moves ahead of tasks and history and gets an accent/icon treatment without inventing a new state enum.

Intended rubric coverage: `state.buried`, `waiting.missing`, `waiting.vague`, `order.wrong`, and `density.low_signal_completed`. The trade-off is that the header block is taller than the baseline, so very long status/goal strings may push supporting detail below the first glance. The implementation uses only the existing `SessionBrief`/todo stores and existing tokens; Arabic falls back through the established English catalog because no new keys are needed.

Evidence boundary: typecheck and lint prove the candidate is structurally valid; only the fixed-fixture screenshots can show whether the beacon remains legible at 280 px.
