# Conversation-task session brief

## Objective and acceptance
Replace the approved static task-context preview with the actual session brief, then build and install the desktop app. Current goal is verb-led and self-contained, above lighter state text without a literal Status label (14px goal). Tasks retain parent work through detours and conversation-specific outcomes, not external feature milestones. Hierarchy is indented 24px. Icons: static partial ring active; open circle pending/paused/ordinary waiting; clock only explicit timed wait; filled checkmark completed.

## Implementation contract
Backend remains authoritative; brief remains an off-turn sidecar, never injected into conversation prompts or used as a scheduler. Version 3 adds `tasks` to the existing wire shape. A task has `id`, nullable `parent_id`, `goal` (verb-led named activity), `status` (`pending`, `in_progress`, `waiting`, `paused`, `timed_wait`, `completed`, `cancelled`), and `detail` (compact observed state/resume context). Stable IDs preserve identity across refreshes. Missing previous tasks are retained, not implicitly completed/deleted; explicit updated states supersede them. Invalid duplicate/cyclic relationships are rejected or repaired without discarding unresolved parents. Detours pause/preserve parents; a completed child does not complete its parent. Status text and blockers retain current wire semantics. Legacy `completed` remains on the wire for older consumers; no manufactured legacy task hierarchy. New model replies use goal/status/tasks/blockers. Old persisted rows remain readable with empty tasks until refreshed. New UI can still display legacy outcomes/live todos only for legacy briefs; v3 task history is separate from execution todos.

## Verification layers
- Unit/integration tests: normalization, incremental task retention, persistence/compression lineage, gateway result/event schema, focused-session rendering. These prove data flow and ordering, not model semantic truth or pixels.
- Live auxiliary-model replay: authorized recorded conversation and a bounded detour/resume example; demonstrates named activity, parent retention and conversation accomplishments. Read-only original state.
- Rendered production component capture: approved order, typography, hierarchy and static state icons. No static HTML substitute for the actual component.
- Packaged app plus installed artifact byte/signature verification: proves built code delivered; relaunch requires a quiet session boundary so this running turn is not interrupted.

## No-change boundaries
No Gas City mutation, new scheduler, core tools, configuration/credential changes, broad home discovery, automatic SOUL deployment, or unrelated repository changes. Preserve foreign deliverables and worktrees.

## Verified contract
PR #13 implements this contract on the fork's `main_plus_our_prs` delivery line. The focused backend/state/RPC/eval suite passes 53 tests. Frontend checks pass 113 tests, TypeScript and scoped ESLint. The production renderer build passes. Four actual-model output fixtures render successfully through the existing production component/theme harness; recorded-topic and paused-parent/completed-child screenshots were inspected.

Independent review reproduced an overlapping-refresh defect: snapshot carry-forward could revert a task paused while the auxiliary call was running. The regression failed on those bytes; generation now validates against its snapshot but hands persistence only explicitly returned task IDs. The transaction retains omitted tasks from current committed history, and callbacks publish persisted readback. The regression verifies both omission retention and an explicit subsequent resume.

Independent re-review approved the race remedy. Active-only replay of the legacy compressed source reproduced missing named-topic context: only two vague follow-ups remained. A real-SQLite regression proves recovery from compacted history and exclusion of undone requests. Legacy rebuild now reads that history through the existing canonical API, in the off-turn worker, with current live turns appended last; v3 updates do not perform this migration read.

Independent review approved the legacy migration and endpoint clarification. Real Codex replay through final generation, SQLite persistence and callback readback passes all four cases: recorded compressed-topic recovery, active parent, completed detour with paused parent, and stable-ID resumption. The source database is read-only; writes target a disposable replay database.

Package/signature and installation receipts belong in PR #13 rather than ignored replay output. Relaunch must occur at a quiet session boundary. Copied bytes and a valid signature prove artifact delivery, not that the running app has restarted onto them.
