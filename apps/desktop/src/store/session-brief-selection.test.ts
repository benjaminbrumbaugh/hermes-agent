/**
 * Selecting a conversation must fetch ITS brief. The resume paths only read once a live
 * runtime is bound; a conversation opened from the list and never resumed never got there,
 * so the pane kept the previous session's brief.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const requests: string[] = []
const briefs: Record<string, unknown> = {}

vi.mock('@/store/gateway', () => ({
  activeGateway: () => ({
    request: async (_method: string, params: { session_id: string }) => {
      requests.push(params.session_id)

      return { brief: briefs[params.session_id] ?? null }
    }
  })
}))

const { $selectedStoredSessionId, $sessions } = await import('./session')
const { $briefsBySession, clearAllSessionBriefs } = await import('./session-brief')

const brief = (goal: string) => ({
  blockers: [],
  completed: [],
  goal,
  message_count: 2,
  status: 's',
  updated_at: 10,
  version: 1
})

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('brief follows the selected session', () => {
  beforeEach(() => {
    clearAllSessionBriefs()
    $sessions.set([])
    $selectedStoredSessionId.set(null)
    requests.length = 0
    briefs.a = brief('goal a')
    briefs.b = brief('goal b')
  })

  it('reads the brief for a newly selected stored id by that id', async () => {
    $selectedStoredSessionId.set('a')
    await flush()
    $selectedStoredSessionId.set('b')
    await flush()

    expect(requests).toEqual(['a', 'b'])
    expect($briefsBySession.get().a?.goal).toBe('goal a')
    expect($briefsBySession.get().b?.goal).toBe('goal b')
  })

  it('does not re-read a brief it already holds', async () => {
    $selectedStoredSessionId.set('a')
    await flush()
    $selectedStoredSessionId.set('b')
    await flush()
    $selectedStoredSessionId.set('a')
    await flush()

    expect(requests).toEqual(['a', 'b'])
  })
})
