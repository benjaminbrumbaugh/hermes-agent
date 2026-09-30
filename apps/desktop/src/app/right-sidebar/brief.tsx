import { useStore } from '@nanostores/react'
import { computed } from 'nanostores'

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

/** The brief for the session the user is looking at (stored id; lineage aliases already fanned out). */
const $activeBrief = computed([$briefsBySession, $selectedStoredSessionId], (briefs, storedId) =>
  storedId ? (briefs[storedId] ?? null) : null
)

/** Live task list for the active runtime session — the same feed the composer status stack renders. */
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

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-3 pb-4 text-xs text-(--ui-text-secondary)">
        <Section title={b.goal}>
          <p className="font-medium text-(--ui-text-primary)">{brief.goal}</p>
        </Section>

        <Section title={b.status}>
          <p>{brief.status}</p>
        </Section>

        {brief.blockers.length > 0 && (
          <Section accent title={b.blockers}>
            <List icon="warning" items={brief.blockers} />
          </Section>
        )}

        {openTodos.length > 0 && (
          <Section title={b.tasks}>
            <ul className="flex flex-col gap-1">
              {todoTree(openTodos).map(([todo, depth]) => (
                <li
                  className={cn('flex items-start gap-1.5', todo.status === 'completed' && 'text-(--ui-text-quaternary)')}
                  key={todo.id}
                  style={{ paddingLeft: `${depth * 0.75}rem` }}
                >
                  <Codicon className="mt-0.5 shrink-0" name={TODO_ICON[todo.status]} size="0.75rem" />
                  <span className={cn(todo.status === 'completed' && 'line-through')}>{todo.content}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {brief.completed.length > 0 && (
          <Section title={b.completed}>
            <List icon="check" items={brief.completed} />
          </Section>
        )}

        {brief.decisions.length > 0 && (
          <Section title={b.decisions}>
            <List icon="git-commit" items={brief.decisions} />
          </Section>
        )}
      </div>
    </aside>
  )
}

interface SectionProps {
  accent?: boolean
  children: React.ReactNode
  title: string
}

function Section({ accent, children, title }: SectionProps) {
  return (
    <section className="flex flex-col gap-1">
      <h3
        className={cn(
          'text-[0.6875rem] font-semibold tracking-wide uppercase',
          accent ? 'text-(--ui-orange)' : 'text-(--ui-text-quaternary)'
        )}
      >
        {title}
      </h3>
      {children}
    </section>
  )
}

interface ListProps {
  icon: string
  items: readonly string[]
}

function List({ icon, items }: ListProps) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((item, i) => (
        <li className="flex items-start gap-1.5" key={`${i}-${item}`}>
          <Codicon className="mt-0.5 shrink-0 text-(--ui-text-quaternary)" name={icon} size="0.75rem" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}
