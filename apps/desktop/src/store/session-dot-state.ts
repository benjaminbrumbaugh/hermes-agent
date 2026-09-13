/**
 * SESSION DOT STATE — one map from session id to the single status a surface
 * should paint, so the sidebar, the pane tabs, and the switcher can never
 * disagree about what a session is doing.
 *
 * It exists for two reasons the individual membership atoms cannot cover:
 *
 * 1. PRIORITY IN ONE PLACE. The signals overlap — a session can be working AND
 *    unread AND running a background job — and resolving that per call site is
 *    how surfaces drift apart.
 * 2. LINEAGE. Compression rotates a conversation's stored id, so a sidebar row,
 *    a persisted tile, and the route can each hold a different tip of one
 *    lineage. Every state is claimed under every alias (see `lineageAliases`),
 *    so a surface gets the right answer whichever tip it happens to hold.
 *
 * The inputs are all reference-stable across stream deltas, so this recomputes
 * on status edges rather than per token.
 *
 * Unread has TWO sources, both claiming the same state: the runtime marker
 * (a turn finished in the background while this window wasn't looking at it,
 * $unreadFinishedSessionIds — transient) and the backend's derived read-state
 * watermark (row.unread — persists across restarts and is visible to every
 * surface). The write side of the persisted flag lives in session-unread.ts.
 */

import { computed } from 'nanostores'

import { stableArray, stableRecord } from '@/lib/stable-array'

import { $backgroundRunningSessionIds } from './composer-status'
import { $messagingSessions, $sessions, $unreadFinishedSessionIds, lineageAliases } from './session'
import {
  $attentionSessionIds,
  $draftSessionIds,
  $sessionStates,
  $stalledSessionIds,
  $workingSessionIds
} from './session-states'
import { $unreadWriteGuard, UNREAD_WRITE_GUARD_MS } from './session-unread-remote'
import {
  $subagentsBySession,
  activeSubagentProgress,
  type ActiveSubagentProgress,
  type SubagentProgress
} from './subagents'

// Sessions parked in async delegation: the parent turn has ended (busy=false —
// delegate_task(background=true) returns its handle the moment the children
// are spawned) while those subagents keep working for minutes. The projection
// carries the same runtime→stored lineage bridge as the canonical dot state.
let delegatedProgressById: Readonly<Record<string, ActiveSubagentProgress>> = {}

const sameDelegatedProgress = (a: ActiveSubagentProgress | undefined, b: ActiveSubagentProgress): boolean =>
  a?.activeCount === b.activeCount &&
  a.apiCallCount === b.apiCallCount &&
  a.lastTool === b.lastTool &&
  a.maxIterations === b.maxIterations &&
  a.startedAt === b.startedAt

const activeSubagent = (item: SubagentProgress): boolean => item.status === 'queued' || item.status === 'running'

/** Resolve duplicate child snapshots across runtime aliases without depending
 * on map insertion order. Terminal lifecycle is monotonic; while active, the
 * newest frame wins, with cumulative counters breaking equal-time snapshots. */
const preferAliasProgress = (current: SubagentProgress, candidate: SubagentProgress): SubagentProgress => {
  const currentActive = activeSubagent(current)
  const candidateActive = activeSubagent(candidate)

  if (currentActive !== candidateActive) {
    return candidateActive ? current : candidate
  }

  const compare =
    candidate.updatedAt - current.updatedAt ||
    (candidate.apiCallCount ?? -1) - (current.apiCallCount ?? -1) ||
    (candidate.maxIterations ?? -1) - (current.maxIterations ?? -1) ||
    Number(candidate.hasReportedStart === true) - Number(current.hasReportedStart === true) ||
    (current.startedAt ?? Number.POSITIVE_INFINITY) - (candidate.startedAt ?? Number.POSITIVE_INFINITY) ||
    (candidate.lastTool ?? '').localeCompare(current.lastTool ?? '') ||
    candidate.status.localeCompare(current.status)

  return compare > 0 ? candidate : current
}

export const $delegatedProgressBySessionId = computed(
  [$subagentsBySession, $sessionStates, $sessions],
  (bySession, states, sessions) => {
    const next: Record<string, ActiveSubagentProgress> = {}
    const groups = new Map<string, { aliases: string[]; items: Map<string, SubagentProgress> }>()

    for (const [runtimeId, items] of Object.entries(bySession)) {
      const aliases = lineageAliases(states[runtimeId]?.storedSessionId ?? runtimeId, sessions)
      const key = JSON.stringify([...aliases].sort())
      const group = groups.get(key) ?? { aliases, items: new Map() }

      for (const alias of aliases) {
        if (!group.aliases.includes(alias)) {
          group.aliases.push(alias)
        }
      }

      for (const item of items) {
        const previous = group.items.get(item.id)

        group.items.set(item.id, previous ? preferAliasProgress(previous, item) : item)
      }

      groups.set(key, group)
    }

    for (const [key, group] of groups) {
      const progress = activeSubagentProgress([...group.items.values()])

      if (!progress) {
        continue
      }

      const previous = group.aliases.map(alias => delegatedProgressById[alias]).find(Boolean)
      const stable = previous && sameDelegatedProgress(previous, progress) ? previous : progress

      for (const alias of group.aliases) {
        next[alias] = stable
      }
    }

    return (delegatedProgressById = stableRecord(delegatedProgressById, next))
  }
)

let delegatingIds: readonly string[] = []
export const $delegatingSessionIds = computed(
  $delegatedProgressBySessionId,
  byId => (delegatingIds = stableArray(delegatingIds, Object.keys(byId)))
)

export type SessionDotState = 'background' | 'draft' | 'idle' | 'needs-input' | 'stalled' | 'unread' | 'working'

/** The sidebar row's arc. A quiet turn is still authoritatively running, so
 *  `stalled` keeps it; a blocking prompt drops it, because the amber dot is the
 *  louder cue and two treatments at once fight each other. */
export const showsRunningArc = (state: SessionDotState): boolean => state === 'stalled' || state === 'working'

/** Whether this turn is the session's own, live: brighter title, and the row's
 *  age yields to the actions menu. Wider than the arc — a turn waiting on an
 *  answer has not ended. */
export const hasLiveTurn = (state: SessionDotState): boolean => showsRunningArc(state) || state === 'needs-input'

/** The buckets the sidebar's status filter and ordering work in. `stalled` and
 *  `background` fold into the state a user would name them. */
export type SessionStatusBucket = 'draft' | 'idle' | 'needs-input' | 'unread' | 'working'

export const sessionStatusBucket = (state: SessionDotState = 'idle'): SessionStatusBucket =>
  state === 'stalled' || state === 'background' ? 'working' : state

const STATUS_RANK: Record<SessionStatusBucket, number> = {
  'needs-input': 0,
  working: 1,
  unread: 2,
  draft: 3,
  idle: 4
}

/** Loudest first — what ordering by status sorts on. */
export const sessionStatusRank = (state?: SessionDotState): number => STATUS_RANK[sessionStatusBucket(state)]

let dotStates: Readonly<Record<string, SessionDotState>> = {}

export const $sessionDotStateById = computed(
  [
    $attentionSessionIds,
    $workingSessionIds,
    $stalledSessionIds,
    $backgroundRunningSessionIds,
    $delegatingSessionIds,
    $unreadFinishedSessionIds,
    $draftSessionIds,
    $sessions,
    $unreadWriteGuard
  ],
  (attention, working, stalled, background, delegating, unread, draft, sessions, unreadWriteGuard) => {
    const next: Record<string, SessionDotState> = {}

    const claim = (ids: readonly string[], state: SessionDotState) => {
      for (const id of ids) {
        for (const alias of lineageAliases(id, sessions)) {
          next[alias] = state
        }
      }
    }

    // Weakest claim first — each pass overwrites the one above it, so the order
    // below IS the priority order. A blocking prompt outranks everything: it is
    // the only state that needs the user.
    //
    // Draft is weakest of all: it says only "no turn has happened here yet", so
    // the first thing that does happen speaks over it.
    claim(draft, 'draft')
    claim(unread, 'unread')

    // Persisted read state (backend watermark): a row marked unread keeps the
    // same emerald dot a background finish would paint, and survives
    // restarts. Same tier as the runtime marker — both mean "there is
    // something here you haven't opened". A list page that predates one of
    // our own writes is fenced out by the write guard: keep OUR value until a
    // page confirms it or the guard expires.
    const persistedUnread: string[] = []

    for (const s of sessions) {
      const entry = unreadWriteGuard.get(s.id)

      if (entry && Date.now() - entry.at < UNREAD_WRITE_GUARD_MS) {
        if (entry.value) {
          persistedUnread.push(s.id)
        }

        continue
      }

      if (s.unread === true) {
        persistedUnread.push(s.id)
      }
    }

    claim(persistedUnread, 'unread')

    claim(background, 'background')
    // Async delegation: the parent turn has ended but its subagents are still
    // running, so the session's work continues in child sessions. Same visual
    // claim as background processes — and it yields to `working` below the
    // moment the parent turn itself is live (synchronous orchestrator children).
    claim(delegating, 'background')
    claim(working, 'working')

    // Stalled REFINES working rather than rivalling it — the turn is still
    // authoritatively running, it has just gone quiet — so it only downgrades a
    // session already claimed as working. The hint outlives its turn by a tick
    // on some paths; without this it could invent a running session.
    for (const id of stalled) {
      for (const alias of lineageAliases(id, sessions)) {
        if (next[alias] === 'working') {
          next[alias] = 'stalled'
        }
      }
    }

    claim(attention, 'needs-input')

    return (dotStates = stableRecord(dotStates, next))
  }
)

/** Listed, non-archived rows whose resolved status is unread. Alias keys in
 *  `$sessionDotStateById` are ignored unless they are themselves a listed row. */
export function unreadSessionCount(
  byId: Readonly<Record<string, SessionDotState>>,
  ...lists: Array<readonly { archived?: boolean; id: string }[]>
): number {
  let n = 0

  for (const rows of lists) {
    for (const row of rows) {
      if (!row.archived && byId[row.id] === 'unread') {
        n++
      }
    }
  }

  return n
}

/** The titlebar badge. Cron sessions are deliberately EXCLUDED: cron runs
 *  finish unwatched by design, so counting them turns the badge into a cron
 *  run counter that is permanently lit (#93552). Their unread state stays
 *  visible where it belongs — the sidebar's cron section rows — and
 *  "mark all as read" still acks them (ackAllSessionsRead iterates cron rows). */
export const $unreadSessionCount = computed(
  [$sessionDotStateById, $sessions, $messagingSessions],
  (byId, sessions, messaging) => unreadSessionCount(byId, sessions, messaging)
)
