# Lane F Round 2 — Codex / gpt-5.6-terra

Review target: post-round-one working tree, before the final desktop alias fix.

## Findings

- Case-insensitive and whitespace-insensitive prior-item matching is broader than literal equality. This is a contract choice, not a blocker, because the prompt and helper docstring state the normalization explicitly.
- New completion strings with no meaningful tokens (for example, `OK`) could pass the old `needed and hits` guard. The guard must reject `needed == 0`.
- The first desktop lineage implementation could compare the wrong cached alias after compression. A lower-count root value could replace a newer tip value; the client needs one refresh-order comparison across the lineage.

## Verified safe paths

The SQLite compare-and-update runs inside the existing write transaction. Prompt-cache isolation, the v1 projection, and the unchanged renderer/i18n boundary remained intact.

## Disposition

The zero-token guard and timestamp-based ordering were implemented. The initial desktop source-map approach was removed; the final client compares all cached aliases and uses message count only for equal refresh timestamps.
