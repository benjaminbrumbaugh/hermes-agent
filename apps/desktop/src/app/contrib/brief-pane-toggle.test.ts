/**
 * The titlebar / ⌘J right-side toggle reopens a collapsed right column through
 * the ACTIVE tab's registered opener. Brief stacks in front of Files, so
 * without its own binding the press found no opener and did nothing.
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { findGroupOfPane, group, type LayoutNode, split } from '@/components/pane-shell/tree/model'
import { $collapsedTreeSides, $hiddenTreePanes, $layoutTree } from '@/components/pane-shell/tree/store'
import { $fileBrowserOpen, setFileBrowserOpen, setSidebarOpen, toggleRightSide } from '@/store/layout'

await import('./controller')

const groupOf = (paneId: string) => findGroupOfPane($layoutTree.get() as LayoutNode, paneId)

describe('right-side toggle with Brief in front of Files', () => {
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
    expect($fileBrowserOpen.get()).toBe(true)
  })
})
