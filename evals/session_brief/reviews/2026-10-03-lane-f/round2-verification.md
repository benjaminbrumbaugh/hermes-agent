# Lane F Round 2 — integrator verification

| Candidate finding | Verification | Disposition |
| --- | --- | --- |
| Message-count ordering breaks after compaction | A valid compacted brief can have a lower count than its predecessor. Comparing `(updated_at, message_count)` with a refresh timestamp captured before the worker starts preserves post-compaction order and rejects a late older turn. | **Accepted; fixed and covered by `tests/hermes_state/test_session_brief.py`** |
| Zero-token new outcomes pass the evidence filter | `needed` is zero for strings such as `OK`; `if not needed or hits < needed` now drops them. | **Accepted; fixed and covered by `tests/agent/test_session_brief.py`** |
| Prior-item normalization is not literal equality | The behavior is deliberate and documented as ignoring case and surrounding whitespace, so this is not an unintentional mismatch. | **Rejected as a blocker** |
| Desktop source-map/alias ordering can select the wrong cached row | The first redesign was not sufficient. It was replaced with all-alias freshness comparison; the final round added a regression for a newly visible tip. | **Accepted; fixed in the final round** |

The review also confirmed that no finding required changing the prompt-cache boundary, v1 wire projection, or visual/i18n scope.
