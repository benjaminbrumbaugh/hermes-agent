import type { SessionBriefTask } from '@hermes/shared'
import { useStore } from '@nanostores/react'
import { computed } from 'nanostores'
import type { ReactNode } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'
import { relativeTime } from '@/lib/time'
import { type TodoItem, todoTree } from '@/lib/todos'
import { cn } from '@/lib/utils'
import { $briefsBySession } from '@/store/session-brief'
import { $focusedRuntimeId, $focusedStoredSessionId } from '@/store/session-states'
import { $todosBySession } from '@/store/todos'

import { SidebarPanelLabel } from '../shell/sidebar-label'

import { RightSidebarSectionHeader } from './index'

/** The brief for the session the user is LOOKING AT — a tile tab or the primary selection — never
 *  only the primary: with conversations open as tabs the primary never changes on a tab switch. */
const $activeBrief = computed([$briefsBySession, $focusedStoredSessionId], (briefs, storedId) =>
  storedId ? (briefs[storedId] ?? null) : null
)

/** Live task list for the focused runtime session — the same feed the composer status stack renders. */
const $activeTodos = computed([$todosBySession, $focusedRuntimeId], (todos, runtimeId): TodoItem[] =>
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
  const legacy = !brief.tasks || (brief.version < 3 && brief.tasks.length === 0)

  return (
    <aside aria-label={b.aria} className="flex h-full w-full min-w-0 flex-col overflow-hidden">
      <RightSidebarSectionHeader>
        <SidebarPanelLabel className="flex-1">{b.aria}</SidebarPanelLabel>
        <span className="text-[0.6875rem] text-(--ui-text-quaternary)">
          {b.updated(relativeTime(brief.updated_at * 1000))}
        </span>
      </RightSidebarSectionHeader>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 text-xs text-(--ui-text-secondary)">
        <PulseSection title={b.goal}>
          <p className="text-[14px] font-[560] leading-[1.45] text-pretty text-(--ui-text-primary)">{brief.goal}</p>
          <p className="mt-3.5 text-[13px] leading-normal text-(--ui-text-secondary)">{brief.status}</p>
        </PulseSection>

        {brief.blockers.length > 0 && (
          <PulseSection accent title={b.blockers}>
            <ItemList icon="warning" items={brief.blockers} />
          </PulseSection>
        )}

        {!legacy && (brief.tasks?.length ?? 0) > 0 && (
          <PulseSection title={b.tasks}>
            <TaskList tasks={brief.tasks ?? []} />
          </PulseSection>
        )}

        {legacy && openTodos.length > 0 && (
          <PulseSection title={b.tasks}>
            <TodoList todos={openTodos} />
          </PulseSection>
        )}

        {legacy && brief.completed.length > 0 && (
          <PulseSection title={b.completed}>
            <ItemList icon="pass-filled" items={brief.completed} />
          </PulseSection>
        )}
      </div>
    </aside>
  )
}

function PulseSection({ accent, children, title }: { accent?: boolean; children: ReactNode; title: string }) {
  return (
    <section className="mt-4 rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-widget-surface-background) p-4">
      <h3
        className={cn(
          'mb-2 text-[0.6875rem] font-semibold tracking-wide uppercase',
          accent ? 'text-(--ui-orange)' : 'text-(--ui-text-quaternary)'
        )}
      >
        {title}
      </h3>
      {children}
    </section>
  )
}

function ItemList({ icon, items }: { icon: string; items: readonly string[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((item, index) => (
        <li className="flex items-start gap-1.5 leading-snug" key={`${index}-${item}`}>
          <Codicon className="mt-0.5 shrink-0 text-(--ui-text-quaternary)" name={icon} size="0.75rem" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

/** Preserve backend sibling order; parents precede children, including when a child arrives first.
 * Dangling and cyclic relationships remain visible instead of hiding unresolved work. */
function taskTree(tasks: SessionBriefTask[]): [SessionBriefTask, number][] {
  const ids = new Set(tasks.map(task => task.id))
  const children = new Map<string, SessionBriefTask[]>()
  const roots: SessionBriefTask[] = []

  for (const task of tasks) {
    if (task.parent_id && ids.has(task.parent_id) && task.parent_id !== task.id) {
      const siblings = children.get(task.parent_id) ?? []
      siblings.push(task)
      children.set(task.parent_id, siblings)
    } else {
      roots.push(task)
    }
  }

  const rows: [SessionBriefTask, number][] = []
  const seen = new Set<string>()

  const visit = (task: SessionBriefTask, depth: number) => {
    if (seen.has(task.id)) {
      return
    }

    seen.add(task.id)
    rows.push([task, depth])

    for (const child of children.get(task.id) ?? []) {
      visit(child, depth + 1)
    }
  }

  for (const root of roots) {
    visit(root, 0)
  }

  for (const task of tasks) {
    if (!seen.has(task.id)) {
      seen.add(task.id)
      rows.push([task, 0])
    }
  }

  return rows
}

function TaskList({ tasks }: { tasks: SessionBriefTask[] }) {
  const { t } = useI18n()

  return (
    <ol className="list-none">
      {taskTree(tasks).map(([task, depth]) => (
        <li
          className="py-3.5 first:pt-1.5 last:pb-0 not-first:border-t not-first:border-(--ui-stroke-tertiary)"
          key={task.id}
          style={{ marginLeft: `${depth * 24}px` }}
        >
          <div className="grid grid-cols-[13px_minmax(0,1fr)] items-start gap-[7px]">
            <TaskIcon status={task.status} />
            <div>
              <p className="text-[14px] font-medium leading-[1.45] text-pretty text-(--ui-text-primary)">{task.goal}</p>
              <p className="mt-1.5 text-xs leading-normal text-(--ui-text-secondary)">
                <span className={cn(task.status === 'completed' && 'sr-only')}>
                  {t.rightSidebar.brief.taskStates[task.status]}
                  {task.status === 'completed' ? '. ' : task.detail ? ' · ' : ''}
                </span>
                {task.detail}
              </p>
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}

function TaskIcon({ status }: { status: SessionBriefTask['status'] }) {
  return (
    <svg aria-hidden="true" className="mt-[4px] size-[13px] text-(--ui-text-secondary)" viewBox="0 0 16 16">
      {status === 'completed' ? (
        <>
          <circle cx="8" cy="8" fill="currentColor" r="8" />
          <path
            d="m4.2 8.1 2.4 2.5 5.2-5.2"
            fill="none"
            stroke="var(--ui-widget-surface-background)"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.5"
          />
        </>
      ) : status === 'in_progress' ? (
        <>
          <circle
            cx="8"
            cy="8"
            fill="none"
            r="6.7"
            stroke="currentColor"
            strokeWidth="1.3"
          />
          <path
            d="M4.3 8h7.4M8.6 4.9 11.7 8l-3.1 3.1"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.3"
          />
        </>
      ) : status === 'waiting' ? (
        <path
          d="M7 2H2v12h5M5 8h9m-3-3 3 3-3 3"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      ) : (
        <>
          <circle cx="8" cy="8" fill="none" r="6.7" stroke="currentColor" strokeWidth="1.4" />
          {status === 'timed_wait' && (
            <path d="M8 4v4l2.5 1.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.4" />
          )}
          {status === 'cancelled' && (
            <path d="M3.3 12.7 12.7 3.3" fill="none" stroke="currentColor" strokeWidth="1.4" />
          )}
        </>
      )}
    </svg>
  )
}

function TodoList({ todos }: { todos: TodoItem[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {todoTree(todos).map(([todo, depth]) => (
        <li
          className="flex items-start gap-1.5 leading-snug"
          key={todo.id}
          style={{ paddingLeft: `${depth * 0.75}rem` }}
        >
          <Codicon className="mt-0.5 shrink-0" name={TODO_ICON[todo.status]} size="0.75rem" />
          <span className={cn(todo.status === 'completed' && 'text-(--ui-text-quaternary) line-through')}>
            {todo.content}
          </span>
        </li>
      ))}
    </ul>
  )
}
