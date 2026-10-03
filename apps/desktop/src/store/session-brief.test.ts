import { beforeEach, describe, expect, it } from 'vitest'

import { $sessions } from './session'
import { $briefsBySession, applySessionBrief, clearAllSessionBriefs } from './session-brief'

const brief = (goal: string, updatedAt: number) => ({
  blockers: [],
  completed: [],
  goal,
  message_count: 2,
  status: 's',
  updated_at: updatedAt,
  version: 1
})

describe('session brief store', () => {
  beforeEach(() => {
    clearAllSessionBriefs()
    $sessions.set([])
  })

  it('publishes under every lineage alias so a pre-compression tab still finds it', () => {
    $sessions.set([
      { _lineage_root_id: 'root', id: 'root' },
      { _lineage_root_id: 'root', id: 'tip' }
    ] as never)
    applySessionBrief('tip', brief('g', 10))
    expect($briefsBySession.get().root?.goal).toBe('g')
    expect($briefsBySession.get().tip?.goal).toBe('g')
  })

  it('drops an out-of-order older brief', () => {
    applySessionBrief('s', brief('new', 20))
    applySessionBrief('s', brief('old', 10))
    expect($briefsBySession.get().s?.goal).toBe('new')
  })

  it('ignores payloads that are not briefs', () => {
    applySessionBrief('s', { goal: 1 })
    applySessionBrief('', brief('g', 1))
    expect($briefsBySession.get()).toEqual({})
  })

  it('rejects payloads missing a current contract field', () => {
    const { status: _status, ...missingStatus } = brief('g', 1)
    applySessionBrief('s', missingStatus)
    expect($briefsBySession.get()).toEqual({})
  })
})
