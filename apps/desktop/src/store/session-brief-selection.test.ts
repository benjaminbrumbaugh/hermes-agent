/**
 * The Brief pane must follow the conversation the user is LOOKING AT. Two ways that broke:
 * the resume paths only read once a live runtime bound (a conversation opened from the list and
 * never resumed never got there), and a tab (tile) switch never changes the primary selection at
 * all — the pane kept the previous session's brief with "Updated 4 sec ago".
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

const model = await import('@/components/pane-shell/tree/model')
const tree = await import('@/components/pane-shell/tree/store')
const { $selectedStoredSessionId, $sessions } = await import('./session')
const { $briefsBySession, clearAllSessionBriefs } = await import('./session-brief')
const { $focusedStoredSessionId } = await import('./session-states')

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

describe('brief follows the focused session', () => {
  beforeEach(() => {
    clearAllSessionBriefs()
    $sessions.set([])
    tree.$layoutTree.set(null)
    tree.noteActiveTreeGroup(null)
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

  it('reads the brief of a focused TAB while the primary selection stays put', async () => {
    $selectedStoredSessionId.set('a')
    await flush()
    tree.$layoutTree.set(
      model.split('row', [
        model.group(['workspace'], { active: 'workspace', id: 'main' }),
        model.group(['session-tile:b'], { active: 'session-tile:b', id: 'tiles' })
      ])
    )

    tree.noteActiveTreeGroup('tiles')
    await flush()

    expect($focusedStoredSessionId.get()).toBe('b')
    expect($selectedStoredSessionId.get()).toBe('a')
    expect(requests).toEqual(['a', 'b'])
  })
})
