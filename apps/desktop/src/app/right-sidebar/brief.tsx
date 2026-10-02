import { useStore } from '@nanostores/react'
import { computed } from 'nanostores'
import type { ReactNode } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'
import { relativeTime } from '@/lib/time'
import { type TodoItem, todoTree } from '@/lib/todos'
import { cn } from '@/lib/utils'
import { $activeSessionId, $selectedStoredSessionId } from '@/store/session'
import { $briefsBySession } from '@/store/session-brief'
import { $todosBySession } from '@/store/todos'

import { SidebarPanelLabel } from '../shell/sidebar-label'

import { RightSidebarSectionHeader } from './index'

const $activeBrief = computed([$briefsBySession, $selectedStoredSessionId], (briefs, storedId) =>
  storedId ? (briefs[storedId] ?? null) : null
)

const $activeTodos = computed([$todosBySession, $activeSessionId], (todos, runtimeId): TodoItem[] =>
  runtimeId ? (todos[runtimeId] ?? []) : []
)

const TODO_ICON: Record<TodoItem['status'], string> = {
  cancelled: 'circle-slash',
  completed: 'pass-filled',
  in_progress: 'play-circle',
  pending: 'circle-large-outline'
}

export function BriefPane() {
  const { t } = useI18n()
  const b = t.rightSidebar.brief
  const brief = useStore($activeBrief)
  const todos = useStore($activeTodos)

  if (!brief) {
    return (
      <aside aria-label={b.aria} className="flex h-full w-full min-w-0 flex-col items-center justify-center gap-1 px-4 text-center">
        <SidebarPanelLabel className="pl-0 text-(--ui-text-quaternary)">{b.emptyTitle}</SidebarPanelLabel>
        <p className="text-xs text-(--ui-text-quaternary)">{b.emptyBody}</p>
      </aside>
    )
  }

  const openTodos = todos.filter(todo => todo.status !== 'cancelled')

  return (
    <aside aria-label={b.aria} className="flex h-full w-full min-w-0 flex-col overflow-hidden">
      <RightSidebarSectionHeader>
        <SidebarPanelLabel className="flex-1">{b.aria}</SidebarPanelLabel>
        <span className="text-[0.6875rem] text-(--ui-text-quaternary)">
          {b.updated(relativeTime(brief.updated_at * 1000))}
        </span>
      </RightSidebarSectionHeader>

      <div className="min-h-0 flex-1 overflow-y-auto text-xs text-(--ui-text-secondary)">
        <div className="grid grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)] border-b border-(--ui-stroke-tertiary)">
          <InfoCell icon="pulse" label={b.status} strong value={brief.status} />
          <InfoCell icon="target" label={b.goal} value={brief.goal} />
        </div>

        {brief.blockers.length > 0 && (
          <MatrixSection accent icon="warning" title={b.blockers}>
            <List items={brief.blockers} />
          </MatrixSection>
        )}

        {openTodos.length > 0 && (
          <MatrixSection icon="list-flat" title={b.tasks}>
            <TodoList todos={openTodos} />
          </MatrixSection>
        )}

        {brief.completed.length > 0 && (
          <MatrixSection icon="check" title={b.completed}>
            <List items={brief.completed} />
          </MatrixSection>
        )}

        {brief.decisions.length > 0 && (
          <MatrixSection icon="git-commit" title={b.decisions}>
            <List items={brief.decisions} />
          </MatrixSection>
        )}
      </div>
    </aside>
  )
}

function InfoCell({ icon, label, strong = false, value }: { icon: string; label: string; strong?: boolean; value: string }) {
  return (
    <div className="min-w-0 border-r border-(--ui-stroke-tertiary) px-3 py-3 last:border-r-0">
      <div className="flex items-center gap-1.5 text-[0.6875rem] font-semibold tracking-wide uppercase text-(--ui-text-quaternary)">
        <Codicon name={icon} size="0.75rem" />
        <span className="truncate">{label}</span>
      </div>
      <p className={cn('mt-1 leading-snug', strong && 'font-medium text-(--ui-text-primary)')}>{value}</p>
    </div>
  )
}

function MatrixSection({ accent, children, icon, title }: { accent?: boolean; children: ReactNode; icon: string; title: string }) {
  return (
    <section className="border-b border-(--ui-stroke-tertiary) px-3 py-3 last:border-b-0">
      <h3 className={cn('mb-1 flex items-center gap-1.5 text-[0.6875rem] font-semibold tracking-wide uppercase', accent ? 'text-(--ui-orange)' : 'text-(--ui-text-quaternary)')}>
        <Codicon name={icon} size="0.75rem" />
        {title}
      </h3>
      {children}
    </section>
  )
}

function List({ items }: { items: readonly string[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((item, index) => (
        <li className="flex items-start gap-1.5 leading-snug" key={`${index}-${item}`}>
          <span className="mt-1 size-1 shrink-0 rounded-full bg-(--ui-text-quaternary)" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function TodoList({ todos }: { todos: TodoItem[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {todoTree(todos).map(([todo, depth]) => (
        <li className="flex items-start gap-1.5 leading-snug" key={todo.id} style={{ paddingLeft: `${depth * 0.75}rem` }}>
          <Codicon className={cn('mt-0.5 shrink-0', todo.status === 'completed' && 'text-(--ui-text-quaternary)')} name={TODO_ICON[todo.status]} size="0.75rem" />
          <span className={cn(todo.status === 'completed' && 'text-(--ui-text-quaternary) line-through')}>{todo.content}</span>
        </li>
      ))}
    </ul>
  )
}
