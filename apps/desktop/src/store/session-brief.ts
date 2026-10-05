import type { SessionBrief, SessionBriefTask } from '@hermes/shared'
import { atom } from 'nanostores'

import { stableRecord } from '@/lib/stable-array'

import { activeGateway } from './gateway'
import { $sessions, lineageAliases } from './session'
import { $focusedStoredSessionId } from './session-states'

/**
 * Backend-authoritative session brief (goal / status / completed / blockers),
 * cached per STORED session id and every lineage alias so a tab
 * that holds a pre-compression id still finds it. Fed by the live
 * `session.brief` event after each turn and a `session.brief` read on
 * session open. The renderer never derives a brief from the transcript.
 */
export const $briefsBySession = atom<Record<string, SessionBrief>>({})

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(item => typeof item === 'string')

const TASK_STATES: readonly SessionBriefTask['status'][] = [
  'pending',
  'in_progress',
  'waiting',
  'paused',
  'timed_wait',
  'completed',
  'cancelled'
]

const isTaskArray = (value: unknown): value is SessionBriefTask[] => {
  if (!Array.isArray(value)) {
    return false
  }

  const ids = new Set<string>()

  return value.every(item => {
    if (!item || typeof item !== 'object') {
      return false
    }

    const task = item as Partial<SessionBriefTask>

    if (
      typeof task.id !== 'string' ||
      !task.id ||
      ids.has(task.id) ||
      (task.parent_id !== null && typeof task.parent_id !== 'string') ||
      typeof task.goal !== 'string' ||
      typeof task.detail !== 'string' ||
      !TASK_STATES.includes(task.status as SessionBriefTask['status'])
    ) {
      return false
    }

    ids.add(task.id)

    return true
  })
}

const isBrief = (value: unknown): value is SessionBrief => {
  if (!value || typeof value !== 'object') {
    return false
  }

  const candidate = value as Partial<SessionBrief>

  return (
    typeof candidate.version === 'number' &&
    typeof candidate.goal === 'string' &&
    typeof candidate.status === 'string' &&
    isStringArray(candidate.completed) &&
    (candidate.tasks === undefined || isTaskArray(candidate.tasks)) &&
    isStringArray(candidate.blockers) &&
    typeof candidate.updated_at === 'number' &&
    typeof candidate.message_count === 'number'
  )
}

/** Newest wins: refresh order is primary; message position breaks timestamp ties. */
export function applySessionBrief(storedSessionId: string, brief: unknown): void {
  const id = storedSessionId.trim()

  if (!id || !isBrief(brief)) {
    return
  }

  const current = $briefsBySession.get()
  const aliases = lineageAliases(id, $sessions.get())

  const existing = aliases.reduce<SessionBrief | undefined>((newest, alias) => {
    const candidate = current[alias]

    if (!candidate) {
      return newest
    }

    if (
      !newest ||
      candidate.updated_at > newest.updated_at ||
      (candidate.updated_at === newest.updated_at && candidate.message_count > newest.message_count)
    ) {
      return candidate
    }

    return newest
  }, undefined)

  if (
    existing &&
    (existing.updated_at > brief.updated_at ||
      (existing.updated_at === brief.updated_at && existing.message_count > brief.message_count))
  ) {
    return
  }

  const next = { ...current }

  for (const alias of aliases) {
    next[alias] = brief
  }

  $briefsBySession.set(stableRecord(current, next))
}

/**
 * Pull the stored brief for a session. `session.brief` resolves a live runtime id or a stored
 * id/key, so the sidebar can ask by whichever it holds. A failed read keeps the cached answer
 * (an older backend without the method is not evidence the brief went away); a null result
 * clears nothing (a fresh draft simply has no brief yet).
 */
export async function refreshSessionBrief(sessionId: string, storedSessionId: string = sessionId): Promise<void> {
  const gateway = activeGateway()

  if (!gateway || !sessionId || !storedSessionId) {
    return
  }

  try {
    const result = await gateway.request<{ brief?: SessionBrief | null }>('session.brief', {
      session_id: sessionId
    })

    if (result?.brief) {
      applySessionBrief(storedSessionId, result.brief)
    }
  } catch {
    // keep whatever we already know
  }
}

// The pane keys by the session the user is LOOKING AT (a tile tab or the
// primary selection). The resume paths only refresh once a live runtime is
// bound, which a conversation opened from the list and never resumed never
// reaches; and a tab switch never changes the primary selection at all — so
// the pane kept showing the previous session's brief. Focus is the event to
// read on.
$focusedStoredSessionId.listen(focused => {
  if (focused && !$briefsBySession.get()[focused]) {
    void refreshSessionBrief(focused)
  }
})

export function clearAllSessionBriefs(): void {
  $briefsBySession.set({})
}
