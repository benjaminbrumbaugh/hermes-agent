/**
 * Regression for the titlebar/⌘J right-side toggle on a user's live tree:
 * `[sessions-group] [main] [brief] [hermes-bots:routines]`. The toggle
 * targeted only the OUTERMOST right column, so with a plugin column past
 * it the Brief column never moved and the press looked dead.
 */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { findGroupOfPane, group, type LayoutNode, split } from '@/components/pane-shell/tree/model'
import { $collapsedTreeSides, $hiddenTreePanes, $layoutTree } from '@/components/pane-shell/tree/store'
import { registry } from '@/contrib/registry'
import { setFileBrowserOpen, setSidebarOpen, toggleRightSide } from '@/store/layout'

await import('./controller')

const groupOf = (paneId: string) => findGroupOfPane($layoutTree.get() as LayoutNode, paneId)

const liveTree = () =>
  split('row', [
    group(['sessions', 'terminal', 'files']),
    group(['workspace', 'review']),
    group(['brief']),
    group(['hermes-bots:routines'])
  ])

describe('right-side toggle with Brief in front of Files', () => {
  beforeAll(() => {
    if (!registry.getArea('panes').some(p => p.id === 'hermes-bots:routines')) {
      registry.register({
        id: 'hermes-bots:routines',
        area: 'panes',
        title: 'Routines',
        data: { placement: 'right', collapsible: true },
        render: () => null
      })
    }
  })

  beforeEach(() => {
    window.localStorage.clear()
    $collapsedTreeSides.set(new Set())
    $hiddenTreePanes.set(new Set())
    setSidebarOpen(true)
    setFileBrowserOpen(true)
  })

  it('reopens a collapsed right column when brief is the active tab', () => {
    $layoutTree.set(split('row', [group(['sessions']), group(['workspace']), group(['brief', 'files'])]))
    setFileBrowserOpen(false)
    expect($collapsedTreeSides.get().has('right')).toBe(true)

    toggleRightSide()

    expect($collapsedTreeSides.get().has('right')).toBe(false)
    expect(Boolean(groupOf('brief')?.minimized)).toBe(false)
  })

  it('folds and restores every right-side column, not only the outermost', () => {
    $layoutTree.set(liveTree())

    toggleRightSide()
    expect(Boolean(groupOf('brief')?.minimized)).toBe(true)
    expect(Boolean(groupOf('hermes-bots:routines')?.minimized)).toBe(true)

    toggleRightSide()
    expect(Boolean(groupOf('brief')?.minimized)).toBe(false)
    expect(Boolean(groupOf('hermes-bots:routines')?.minimized)).toBe(false)
  })
})
