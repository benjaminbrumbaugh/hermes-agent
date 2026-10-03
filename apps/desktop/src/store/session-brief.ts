import type { SessionBrief } from '@hermes/shared'
import { atom } from 'nanostores'

import { stableRecord } from '@/lib/stable-array'

import { activeGateway } from './gateway'
import { $sessions, lineageAliases } from './session'

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
 * Pull the stored brief for a live runtime session. A failed read keeps the
 * cached answer (an older backend without the method is not evidence the
 * brief went away); a null result clears it (a fresh draft).
 */
export async function refreshSessionBrief(runtimeSessionId: string, storedSessionId: string): Promise<void> {
  const gateway = activeGateway()

  if (!gateway || !runtimeSessionId || !storedSessionId) {
    return
  }

  try {
    const result = await gateway.request<{ brief?: SessionBrief | null }>('session.brief', {
      session_id: runtimeSessionId
    })

    if (result?.brief) {
      applySessionBrief(storedSessionId, result.brief)
    }
  } catch {
    // keep whatever we already know
  }
}

export function clearAllSessionBriefs(): void {
  $briefsBySession.set({})
}
