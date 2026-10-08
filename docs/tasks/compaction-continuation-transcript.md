# Compaction continuation transcript boundary

Base: `main_plus_our_prs` at `19fa9136909f3b428d975516685e1c1dbc22dd0f`.
Branch: `fix/compaction-continuation-transcript`.

## Final source acceptance

Independent exact-byte review **approved** implementation commit
`b814eb5dce30fd4aea08066de246544de00d4ddb`, with no blocking findings.
Parent scoped verification: **209 passed, 0 failed**, eight files. Independent
verification: **161 passed** in continuation/image-history/compressor suites and
**28 passed** in display-parity/resume suites; full-range whitespace check passed.
Earlier pending-review statements below are historical intermediate receipts.
PR #18 delivers this source to `main_plus_our_prs`; merged-state and post-merge
verification receipts are recorded in that PR. Desktop-pixel verification,
live backend rollout, and installation/relaunch remain separate unperformed
boundaries. No live session database edits are required or authorized.

## Root cause and fix

`ContextCompressor._reappend_inflight_user_task` clones the accepted request and
adds `_INFLIGHT_TASK_REPLAY_HEADER` for model continuation after the handoff.
The copy retains the accepted UID/timestamp, so display identity correctly folds
its generations at the original position, but the active/newest representative
was the synthetic prefixed content rather than the accepted row.

- Mark standalone continuations with the existing durable `model_only` display
  admission flag. Preserve the full continuation in model history and SQLite.
- Exclude pure summary-carrier continuation from the shared display projection;
  preserve genuine prior-tail text, even when it quotes the exact replay header.
- Centralize display admission in `hermes_state_display.py`. Existing unmarked
  standalone replays require an earlier same-session UID/timestamp source witness
  plus the exact generated leading prefix. Handle text and multipart first text
  parts. Do not infer identity from equal text or delete/rewrite historical rows.
- Apply admission before indexed history/timeline grouping and pagination, and
  in streaming legacy-page/resume deduplication. Already-materialized display
  indexes do not require a retrospective migration for this replay exclusion.

No schema, provider instruction, alternation policy, real session DB, or client
renderer changes. No new interruption/resumption labels. The source is pushed
in fork PR #18 targeting `main_plus_our_prs`; no deployment, install, restart,
or updater-owned main checkout edits have occurred.

## Independent review follow-up

The first exact-byte review blocked merged-carrier handling: requests quoting
the summary-end or prior-context delimiter could expose synthetic scaffolding.
An additional regression found repeated compaction truncating requests quoting
the replay header. Three quoted-token cases failed before this follow-up.

Generated merged replay now records `inflight_replay_start` in existing durable
display metadata and marks pure carriers `model_only`. Replay extraction uses
that boundary rather than splitting accepted text at quoted headers. Legacy
projection recognizes an adjacent generated end/header pair before parsing the
carrier; only a structurally leading prior-context section supplies visible text.
Summary classification checks the leading handoff prefix before quoted
delimiters. This also preserves merged-replay detection after SQLite reopen.

Final follow-up scoped run: **206 passed, 0 failed**, eight files, including four
new merged-carrier cases through SQLite reopen and another compaction, legacy
projection, compressor, display parity, resume, and TUI display/status tests.
`git diff --check` passed. These prove persistence/projection and continuation
content boundaries, not desktop pixels or live deployment. A second exact-byte
review is required before integration.

The second review caught a new stale historical-carrier activation caused by
the permissive legacy adjacent-pair fallback. A regression reproduced that
completed work quoted inside a newer summary became an in-flight request.
The execution fallback has been simplified back to the preexisting conservative
final-end-marker rule. Adjacent-pair recognition is now display-only and cannot
grant execution authority; newly generated replay continues to use durable
boundary offsets. No new migration or recovery machinery was added.

Latest final-byte scoped run: **207 passed, 0 failed**, eight files, including
the historical-only summary regression (RED before this change), all quoted-token
cases, and existing compressor/display/resume/status coverage. Whitespace check
passed. Independent exact-byte approval remains required before integration;
the live app remains untouched.

The third review found absolute offsets were incorrect for multipart carriers:
flattening text parts inserts a separator newline. The descriptor is now the
trailing generated replay's text length (`inflight_replay_text_length`), replacing
the unshipped absolute-offset field. Its boundary does not depend on preceding
text-part separators or historical image-to-placeholder rewrites. This is a
direct representation replacement, not additional fallback/migration machinery.
Added real prior-tail merge cases for string and text/image content, preserving
authentic display content/media, rewriting historical media with the production
helper, reopening SQLite, and replaying the unchanged ask on another compaction.
The multipart case failed on the prior commit before this change.
Final representation-replacement run: **209 passed, 0 failed**, eight files;
`git diff --check` passed. This proves source/persistence/display projection and
continued task extraction, not live desktop pixels or deployment.

## Verification receipts

Runner: `scripts/run_tests.sh`, existing checkout `.venv/bin/python` selected with
`HERMES_PYTHON`; `HERMES_TEST_FILE_RETRIES=0` throughout. Disposable SQLite stores
and isolated homes only. Stub only `_call_summary_llm` on the compressor class:
compression operates on a working copy, so an instance transport patch alone is
not sufficient to prove successful summary transport was exercised. The test
asserts the transport was called.

- RED on untouched base: all four new parametrized cases fail. Initial RED also
  demonstrated the accepted UID/timestamp displaying the generated prefix.
- GREEN final focused run: **291 passed, 0 failed**, 16 files, 24.2 seconds.
  Includes the four new cases, existing real image-history/repeated-compaction
  reproduction, compressor, split-turn/restart, in-place persistence, display
  parity/index/legacy paging, timeline jumps, watermark fencing, and compaction
  status suites.
- New regression: normal flush → real compactor assembly → fenced compaction
  persistence → SQLite reopen → model/display resume → indexed and read-only
  legacy paging. Repeated compaction of the same task, a later independently
  accepted identical request, text parts and images, and untouched sibling
  session are covered. Existing replay projection reads leave audit rows intact;
  model continuation still reaches Codex Responses serialization after the
  handoff and internal display metadata does not reach the provider.
- Broad state run: **1,384 passed, 63 failed, 49 skipped**, 146 files. All 63
  failing node IDs also fail on untouched base; comparison found zero newly
  failing node IDs. Base additionally fails all four new cases. Two no-test
  files are unchanged blockers: missing `aiohttp` for API projection tests and
  retired `macos_only`/`linux_only` markers in WAL capture tests.
- Broad agent/compaction/TUI run: **985 passed, 4 failed**, 102 files. All four
  failures reproduced on base: three `/var/tmp` versus `/private/var/tmp` prompt
  snapshot assumptions and missing `acp` for one manual-preview case.
- Broad state failures include host maintenance/holder tests refused by the live
  home I/O guard and host WAL assumptions; no guard was disabled and no global
  dependencies were installed to make them green.

Full receipts are in `/Users/benjaminbrumbaugh/.hermes/cache/scratch/`:
`compaction-continuation-red.log`, `compaction-continuation-base.log`,
`compaction-continuation-focused-final.log`,
`compaction-continuation-regression.log`,
`compaction-continuation-agent-regression.log`, and
`compaction-continuation-base-agent-failures.log`.

## Outstanding delivery/UI verification

This source-only work does not update the running backend. After separately
approved delivery, verify on an isolated UI session:

1. Original accepted bubble is unchanged at its original chronological position
   through automatic mid-turn compaction and subsequent history reload/resume.
2. Model continues the same unfinished task after the compaction handoff; repeat
   compaction, accept identical text again, and verify those are distinct turns.
3. Text/media rendering, timeline jumps, and older/newer pages agree; a sibling
   session is unchanged. Known historical source-witnessed replay rows project
   cleanly without database edits. No-UID/no-source historical rows are left as-is.
4. Existing compaction/context-rebuild status is visible as appropriate; neither
   `Interrupted` nor `Resumed` is emitted merely because compaction occurred.

Live desktop/browser visual verification and the aiohttp endpoint suite remain
outstanding. Parent owns independent review and any later remote delivery.
