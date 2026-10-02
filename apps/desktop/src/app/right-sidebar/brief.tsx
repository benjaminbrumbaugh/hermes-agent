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
      <aside
        aria-label={b.aria}
        className="flex h-full w-full min-w-0 flex-col items-center justify-center gap-1 px-4 text-center"
      >
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
        <div className="border-b border-(--ui-stroke-tertiary) px-3 pb-4 pt-3">
          <div className="flex items-start gap-2">
            <span
              aria-hidden="true"
              className={cn(
                'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-(--ui-stroke-primary)',
                brief.blockers.length > 0 ? 'text-(--ui-orange)' : 'text-(--theme-primary)'
              )}
            >
              <Codicon name={brief.blockers.length > 0 ? 'warning' : 'circle-filled'} size="0.625rem" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[0.6875rem] font-semibold tracking-wide uppercase text-(--ui-text-quaternary)">
                {b.status}
              </p>
              <p className="mt-1 font-medium leading-snug text-(--ui-text-primary)">{brief.status}</p>
            </div>
          </div>
          <div className="mt-4">
            <Eyebrow>{b.goal}</Eyebrow>
            <p className="mt-1 leading-snug text-(--ui-text-primary)">{brief.goal}</p>
          </div>
        </div>

        {brief.blockers.length > 0 && (
          <BriefSection accent title={b.blockers}>
            <ItemList icon="warning" items={brief.blockers} />
          </BriefSection>
        )}

        {openTodos.length > 0 && (
          <BriefSection title={b.tasks}>
            <TodoList todos={openTodos} />
          </BriefSection>
        )}

        {brief.completed.length > 0 && (
          <BriefSection title={b.completed}>
            <ItemList icon="check" items={brief.completed} muted />
          </BriefSection>
        )}

        {brief.decisions.length > 0 && (
          <BriefSection title={b.decisions}>
            <ItemList icon="git-commit" items={brief.decisions} />
          </BriefSection>
        )}
      </div>
    </aside>
  )
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-[0.6875rem] font-semibold tracking-wide uppercase text-(--ui-text-quaternary)">{children}</p>
}

function BriefSection({ accent, children, title }: { accent?: boolean; children: ReactNode; title: string }) {
  return (
    <section className="border-b border-(--ui-stroke-tertiary) px-3 py-3 last:border-b-0">
      <h3
        className={cn(
          'mb-1 text-[0.6875rem] font-semibold tracking-wide uppercase',
          accent ? 'text-(--ui-orange)' : 'text-(--ui-text-quaternary)'
        )}
      >
        {title}
      </h3>
      {children}
    </section>
  )
}

function ItemList({ icon, items, muted = false }: { icon: string; items: readonly string[]; muted?: boolean }) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((item, index) => (
        <li className={cn('flex items-start gap-1.5 leading-snug', muted && 'text-(--ui-text-tertiary)')} key={`${index}-${item}`}>
          <Codicon className="mt-0.5 shrink-0 text-(--ui-text-quaternary)" name={icon} size="0.75rem" />
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
        <li
          className={cn('flex items-start gap-1.5 leading-snug', todo.status === 'completed' && 'text-(--ui-text-quaternary)')}
          key={todo.id}
          style={{ paddingLeft: `${depth * 0.75}rem` }}
        >
          <Codicon className="mt-0.5 shrink-0" name={TODO_ICON[todo.status]} size="0.75rem" />
          <span className={cn(todo.status === 'completed' && 'line-through')}>{todo.content}</span>
        </li>
      ))}
    </ul>
  )
}
