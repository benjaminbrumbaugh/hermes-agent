import { afterEach, expect, it } from 'vitest'

import { $subagentsBySession, reconcileSubagentSnapshot, upsertSubagent } from './subagents'

afterEach(() => $subagentsBySession.set({}))
it('hydrates last tool activity without claiming it is active and preserves stream history on refresh', () => {
  const child = {
    subagent_id: 'worker',
    goal: 'Actual worker',
    status: 'running',
    started_at: 1001,
    last_tool: 'read_file'
  }

  reconcileSubagentSnapshot('owner', [child])
  const first = $subagentsBySession.get().owner
  expect(first[0].stream).toMatchObject([{ kind: 'tool', text: 'Read File' }])
  expect(first[0].currentTool).toBeUndefined()
  expect(first[0].startedAt).toBe(child.started_at * 1000)
  reconcileSubagentSnapshot('owner', [child])
  expect($subagentsBySession.get().owner).toBe(first)
  upsertSubagent('other', { subagent_id: 'worker', goal: 'Other owner' })
  const other = $subagentsBySession.get().other
  upsertSubagent('owner', { subagent_id: 'worker', text: 'New progress' }, false, 'subagent.progress')
  const stream = $subagentsBySession.get().owner[0].stream
  reconcileSubagentSnapshot('owner', [child])
  expect($subagentsBySession.get().owner[0].stream).toBe(stream)
  reconcileSubagentSnapshot('owner', [])
  expect($subagentsBySession.get().owner).toEqual([])
  expect($subagentsBySession.get().other).toBe(other)
})

it('keeps projected activity structured and never regresses live call counters', () => {
  reconcileSubagentSnapshot('owner', [
    {
      api_call_count: 2,
      goal: 'Worker',
      last_tool: 'read_file',
      max_iterations: 10,
      started_at: 1001,
      status: 'running',
      subagent_id: 'worker'
    },
    {
      goal: 'Older backend worker',
      status: 'running',
      subagent_id: 'older',
      text: 'browser_click'
    }
  ])

  expect($subagentsBySession.get().owner[0]).toMatchObject({
    apiCallCount: 2,
    hasReportedStart: true,
    lastTool: 'read_file',
    maxIterations: 10
  })
  expect($subagentsBySession.get().owner[0].currentTool).toBeUndefined()
  expect($subagentsBySession.get().owner[1]).toMatchObject({
    apiCallCount: undefined,
    hasReportedStart: false,
    lastTool: undefined,
    maxIterations: undefined
  })

  upsertSubagent('owner', { api_call_count: 5, max_iterations: 12, subagent_id: 'worker' }, false, 'subagent.progress')
  reconcileSubagentSnapshot('owner', [
    {
      api_call_count: 3,
      goal: 'Worker',
      last_tool: 'read_file',
      max_iterations: 10,
      started_at: 1001,
      status: 'running',
      subagent_id: 'worker'
    }
  ])

  expect($subagentsBySession.get().owner[0]).toMatchObject({ apiCallCount: 5, maxIterations: 12 })
})
