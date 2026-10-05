# Same-session compaction image history identity

Base: `66d7e2ad455376ccdd7509737b566f185f3bb181` (`origin/main_plus_our_prs`, remote reverified before delivery).
Fork issues are disabled; this tracked task is the continuation record.
Branch: `fix/compaction-image-history-identity`. Parent exact-byte review completed; source integration authorized after the scoped gate below.

## Verified cause and source boundary

Normal session persistence projects multimodal content to text (`agent/session_persistence.py::_durable_content`), while ContextCompressor retains a protected opening image-bearing message and in-place compaction inserts its multipart content directly. `_display_dedupe_key` keys on encoded content plus timestamp. Those representations differ despite sharing the durable `message_uid` assigned during flush. `_reconcile_display_orders` previously computed different display identities and assigned the retained image copy a new insertion-order position. Same timestamp alone is not an identity proof.

The retained active multipart row is legitimate historical grounding; its presence does not establish that the model acted on the old task. `_find_inflight_user_task` correctly selects the newest actionable request. Neither that selection nor the compressor's image-retention policy is changed.

`SessionMessagesMixin._display_identity` now folds shared-UID generations onto their earliest visible content identity. Its existing content/timestamp fallback remains for legacy generations. The same rule is used by transactional compaction reconciliation, unpaged resume/lineage deduplication, and bounded legacy read-only paging. Active/newest representative selection is unchanged. No schema, prompt, provider, live conversation, or config changes.

## Independently reviewable behavioral evidence

`tests/agent/test_compaction_image_history_identity.py` exercises real agent flush → compressor assembly → leased/fenced in-place commit → SQLite close/reopen → indexed display, desktop/model resume and Codex Responses input conversion. Only summarizer transport is stubbed. Inputs are nonsecret text and a one-pixel data-URL image.

- Three compaction/resume cycles preserve one displayed occurrence and original display order for the opening image UID, with an unaffected sibling session.
- Several completed later requests precede the newest unfinished request. The Codex wire input has exactly one newest-request continuation after the summary boundary and no old request there; retained opening image/text/role are before that boundary, with matching tool-call/result IDs and no persistence metadata on the wire.
- Image retention is checked on the first cycle only: protected opening history intentionally decays on later compactions. This fix does not fossilize images.
- The newest request remains represented once in display history, including its legitimate current-task replay decoration; this is not a redesign of synthetic-continuation display policy.
- A second test proves ordinary and both-direction paged legacy read-only projections fold multipart/text copies without swallowing a later independently accepted identical text request.

The tests establish persistence and request serialization, not inference behavior. No provider inference was invoked. No live state was read or changed by these tests. The already-materialized indexes of production sessions are not migrated here; subsequent compaction reconciliation uses the corrected rule.

## Reproduction and gates

Set `HERMES_PYTHON` to the existing test interpreter and `HERMES_TEST_FILE_RETRIES=0` for all commands below. The runner isolates `HERMES_HOME`, clears credentials, and uses per-file subprocesses.

```sh
export HERMES_PYTHON=/Users/benjaminbrumbaugh/Documents/Hermes-Agent/venv/bin/python
export HERMES_TEST_FILE_RETRIES=0
scripts/run_tests.sh tests/agent/test_compaction_image_history_identity.py --tb=short -j 1
```

RED on the untouched base worktree with this test copied in: exit **1**, **2 failed / 0 passed**. First failure is duplicate opening UID in desktop resume (`2 != 1`); second is the extra opening-image occurrence in legacy display. All model-wire assertions preceding the first failure pass on base, supporting the narrower display/storage diagnosis rather than blaming active-task selection.

GREEN scoped integration gate (final test bytes): exit **0**, **299 passed / 0 failed**, **17 files**:

```sh
scripts/run_tests.sh \
  tests/agent/test_compaction_image_history_identity.py \
  tests/hermes_state/test_display_split_heal.py \
  tests/hermes_state/test_get_messages_include_compacted.py \
  tests/hermes_state/test_message_uid.py \
  tests/hermes_state/test_display_projection_parity.py \
  tests/agent/test_in_place_compaction.py \
  tests/agent/test_split_turn_compaction.py \
  tests/agent/test_compression_persistence.py \
  tests/agent/test_compression_concurrent_fork.py \
  tests/agent/test_resume_stale_active_task.py \
  tests/agent/test_micro_compaction.py \
  tests/tui_gateway/test_deferred_model_history.py \
  tests/tui_gateway/test_session_resume_db_ownership.py \
  tests/hermes_cli/test_resume_display.py \
  tests/agent/test_codex_responses_adapter.py \
  tests/agent/test_codex_multimodal_tool_result.py \
  tests/agent/test_codex_runtime_history_seed.py --tb=short -j 8
```

Broader diagnostic gate: the earlier scoped set (without display-projection parity/Codex files) plus all `tests/hermes_state/`, same runner flags. Fixed worktree: exit **1**, **1522 passed / 63 failed / 49 skipped**, one collection-error file. Base with regression tests: exit **1**, **1520 passed / 65 failed / 49 skipped**, same collection-error file. Parsed failure node-ID set difference is exactly the two new regression tests; no fix-only failures. Existing failures include real-home open-file-scan guards, Linux mount assumptions on macOS, and obsolete platform markers. They are not silently treated as green or changed in this focused fix.

Local raw receipts are under `/Users/benjaminbrumbaugh/.hermes/cache/scratch/`: `compaction-identity-red.log`, `compaction-identity-scoped-gate.log`, `compaction-identity-baseline-broad.log`. Fixed broad receipt: `/Users/benjaminbrumbaugh/.hermes/cache/terminal-output/out-1791230167-36315-d810.log`. The detached base worktree is `temp/compaction-image-history-base` for re-running RED. No giant telemetry logs are committed.

Official latest session-storage documentation was fetched and inspected; the source behavior and executed tests, not a docs inference, establish the defect and fix. The search-only extraction backend could not fetch documents; direct HTTPS retrieval succeeded.

## Continuation

Parent independently inspected the production diff and behavioral tests, reproduced both failures on the untouched base (exit 1), and reran the 17-file scoped gate (299 passed, exit 0). Programmatic comparison of broad-gate failure node IDs confirmed no fix-only failures and exactly the two new regressions removed. PR #12 targets the fork's `main_plus_our_prs`; source merge is authorized. This completes source verification, not runtime rollout.

Do not deploy, restart services, or mutate production transcripts as part of this source delivery. Existing materialized display indexes remain unchanged until reconciliation runs under the corrected code. Retrospective index healing or a live-session repair requires a separately reviewed, scoped operation; no transcript deletion or rewrite is necessary for the source fix.
