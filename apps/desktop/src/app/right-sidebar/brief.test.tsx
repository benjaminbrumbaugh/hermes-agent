import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import * as model from '@/components/pane-shell/tree/model'
import * as tree from '@/components/pane-shell/tree/store'
import { $activeSessionId, $selectedStoredSessionId, $sessions } from '@/store/session'
import { applySessionBrief, clearAllSessionBriefs } from '@/store/session-brief'
import { $todosBySession } from '@/store/todos'

import { BriefPane } from './brief'

const brief = (goal = 'Finish the bridge') => ({
  blockers: [],
  completed: ['Legacy outcome'],
  goal,
  message_count: 2,
  status: 'Review outstanding',
  updated_at: 10,
  version: 3,
  tasks: []
})

describe('conversation brief rendering', () => {
  beforeEach(() => {
    clearAllSessionBriefs()
    $sessions.set([])
    tree.$layoutTree.set(null)
    tree.noteActiveTreeGroup(null)
    $selectedStoredSessionId.set('a')
    $activeSessionId.set('runtime-a')
    $todosBySession.set({})
  })
  afterEach(cleanup)

  it('puts the current goal above lighter state text in a card without a Status label', () => {
    applySessionBrief('a', brief())
    render(<BriefPane />)
    const header = screen.getByRole('heading', { name: 'Current goal' })
    const goal = screen.getByText('Finish the bridge')
    const state = screen.getByText('Review outstanding')
    expect(header.compareDocumentPosition(goal) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(goal.compareDocumentPosition(state) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(goal.className).toContain('text-[14px]')
    expect(goal.className).toContain('font-[560]')
    expect(goal.className).toContain('leading-[1.45]')
    expect(state.className).toContain('text-(--ui-text-secondary)')
    expect(header.closest('section')?.className).toContain('rounded-lg')
    expect(screen.queryByText('Status')).toBeNull()
    expect(screen.queryByText('Legacy outcome')).toBeNull()
  })

  it('renders durable tasks parent-first in wire sibling order with static accessible state icons, not execution todos', () => {
    const task = (id: string, status: string, parent_id: string | null = null) => ({
      id,
      parent_id,
      goal: `Work on ${id}`,
      status,
      detail: `Context for ${id}`
    })

    applySessionBrief('a', {
      ...brief(),
      tasks: [
        task('child', 'waiting', 'parent'),
        task('parent', 'paused'),
        task('completed-child', 'completed', 'parent'),
        task('active', 'in_progress'),
        task('pending', 'pending'),
        task('timed', 'timed_wait'),
        task('cancelled', 'cancelled'),
        task('orphan', 'waiting', 'missing'),
        task('cycle-a', 'pending', 'cycle-b'),
        task('cycle-b', 'paused', 'cycle-a')
      ]
    })
    $todosBySession.set({ 'runtime-a': [{ id: 'execution', content: 'Execution only', status: 'pending' }] })
    const { container } = render(<BriefPane />)
    const rows = screen.getAllByRole('listitem')
    expect(rows.map(row => row.querySelector('p')?.textContent)).toEqual([
      'Work on parent',
      'Work on child',
      'Work on completed-child',
      'Work on active',
      'Work on pending',
      'Work on timed',
      'Work on cancelled',
      'Work on orphan',
      'Work on cycle-a',
      'Work on cycle-b'
    ])
    expect(rows[1].style.marginLeft).toBe('24px')
    expect(rows[2].style.marginLeft).toBe('24px')
    expect(rows[0].textContent).toContain('Paused · Context for parent')
    expect(rows[1].textContent).toContain('Waiting · Context for child')
    expect(rows[2].querySelector('.sr-only')?.textContent).toContain('Completed')
    expect(rows[2].textContent).not.toContain('Done')
    expect(rows[2].querySelector('svg circle')?.getAttribute('fill')).toBe('currentColor')
    // The active marker combines a split ring with the activity stroke; not a spinner.
    expect(rows[3].querySelectorAll('svg path')).toHaveLength(2)
    expect(Array.from(rows[3].querySelectorAll('svg path')).every(path => path.getAttribute('fill') === 'none')).toBe(true)
    // Waiting has its own dependency/handoff marker, distinct from not-started and timed waits.
    expect(rows[1].querySelector('svg circle')).toBeNull()
    expect(rows[1].querySelectorAll('svg path')).toHaveLength(1)
    expect(rows[4].querySelector('svg circle')?.getAttribute('fill')).toBe('none')
    expect(rows[5].querySelector('svg path')?.getAttribute('d')).toBe('M8 4v4l2.5 1.5')
    expect(rows.every(row => row.querySelector('svg[aria-hidden="true"]'))).toBe(true)
    expect(container.querySelector('[class*="animate-"]')).toBeNull()
    expect(screen.queryByText('Execution only')).toBeNull()
    expect(screen.queryByText('Legacy outcome')).toBeNull()
  })

  it.each([1, 2, 3])('keeps legacy outcomes and focused live todos without inventing a hierarchy (version %i)', version => {
    const { tasks: _tasks, ...legacy } = brief()
    applySessionBrief('a', { ...legacy, version, ...(version === 2 ? { tasks: [] } : {}) })
    $todosBySession.set({ 'runtime-a': [{ id: 'execution', content: 'Legacy live todo', status: 'pending' }] })
    render(<BriefPane />)
    expect(screen.getByText('Legacy outcome')).toBeTruthy()
    expect(screen.getByText('Legacy live todo')).toBeTruthy()
    expect(screen.getAllByRole('listitem').every(row => !row.querySelector('svg'))).toBe(true)
  })

  it('isolates durable tasks when a focused tile differs from the primary session', () => {
    applySessionBrief('a', {
      ...brief('Goal A'),
      tasks: [{ id: 'a-task', parent_id: null, goal: 'Task A', status: 'pending', detail: '' }]
    })
    applySessionBrief('b', {
      ...brief('Goal B'),
      tasks: [{ id: 'b-task', parent_id: null, goal: 'Task B', status: 'paused', detail: '' }]
    })
    render(<BriefPane />)
    expect(screen.getByText('Task A')).toBeTruthy()
    act(() => {
      tree.$layoutTree.set(model.group(['session-tile:b'], { active: 'session-tile:b', id: 'tiles' }))
      tree.noteActiveTreeGroup('tiles')
    })
    expect($selectedStoredSessionId.get()).toBe('a')
    expect(screen.getByText('Goal B')).toBeTruthy()
    expect(screen.getByText('Task B')).toBeTruthy()
    expect(screen.queryByText('Task A')).toBeNull()
    act(() => {
      tree.$layoutTree.set(null)
      tree.noteActiveTreeGroup(null)
    })
    expect(screen.getByText('Task A')).toBeTruthy()
    expect(screen.queryByText('Task B')).toBeNull()
  })
})
