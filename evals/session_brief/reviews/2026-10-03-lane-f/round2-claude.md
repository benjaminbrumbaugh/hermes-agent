# Lane F Round 2 — Claude / Opus

Review target: post-round-one working tree, before the final desktop alias fix.

## Findings

- Comparing only `message_count` rejects legitimate post-compression refreshes because compaction lowers the count; the desktop tie-break had the same failure mode. This was a high-severity ordering defect.
- A refresh received under the pre-rotation key can be dropped or misordered when the live session key changes. The client must use refresh order across the lineage, not message position alone.
- The zero-token concern was reviewed but the implementation still needed an explicit `not needed` guard; local verification accepted that guard as the correct conservative behavior.

## Verified safe paths

The auxiliary prompt remains separate from the main conversation, and `_wire_brief()` still projects legacy rows without exposing v1 `decisions`.

## Evidence limitation

The prompt text changed during the fix, so the prior Lane E scorecard is not a fresh score for this exact prompt. Human glanceability remains a separate product gate.
