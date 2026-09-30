import type { SessionBrief } from '@hermes/shared'
import { atom } from 'nanostores'

import { stableRecord } from '@/lib/stable-array'

import { activeGateway } from './gateway'
import { $sessions, lineageAliases } from './session'

/**
 * Backend-authoritative session brief (goal / status / completed / blockers /
 * decisions), cached per STORED session id and every lineage alias so a tab
 * that holds a pre-compression id still finds it. Fed by the live
 * `session.brief` event after each turn and a `session.brief` read on
 * session open. The renderer never derives a brief from the transcript.
 */
export const $briefsBySession = atom<Record<string, SessionBrief>>({})

const isBrief = (value: unknown): value is SessionBrief =>
  Boolean(value) &&
  typeof value === 'object' &&
  typeof (value as SessionBrief).goal === 'string' &&
  Array.isArray((value as SessionBrief).completed)

/** Newest wins: an out-of-order event for an older `updated_at` is dropped. */
export function applySessionBrief(storedSessionId: string, brief: unknown): void {
  const id = storedSessionId.trim()

  if (!id || !isBrief(brief)) {
    return
  }

  const current = $briefsBySession.get()
  const aliases = lineageAliases(id, $sessions.get())
  const existing = aliases.map(alias => current[alias]).find(Boolean)

  if (existing && existing.updated_at > brief.updated_at) {
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
