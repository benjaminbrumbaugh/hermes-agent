import { useAui, useAuiState } from '@assistant-ui/react'
import { useStore } from '@nanostores/react'
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useSessionView } from '@/app/chat/session-view'
import { usePaneVisible } from '@/components/pane-shell/pane-visibility'
import { prefersReducedMotion } from '@/hooks/use-media-query'
import { useI18n } from '@/i18n'
import { triggerHaptic } from '@/lib/haptics'
import { useStoreSelector } from '@/lib/use-session-slice'
import { $hideThreadTimeline } from '@/store/thread-timeline'

import { messageContentText } from './content'
import {
  deriveTimelineEntries,
  EARLIER_TIMELINE_ID,
  sameTimelineEntries,
  TIMELINE_REVEAL_EVENT,
  type TimelineEntry,
  type TimelineRevealRequest,
  type TimelineSourceMessage
} from './timeline-data'
import { TimelineRail } from './timeline-rail'
import { useTranscriptWindow } from './transcript-window'
import { useTimelineHistory } from './use-timeline-history'

const VIEWPORT = '[data-slot="aui_thread-viewport"]'

// Constant-duration jump (eased), NOT native `behavior:'smooth'` — Chromium's
// smooth scroll animates proportional to distance, so jumping across a long
// thread crawls for seconds. A fixed ~170ms feels instant near or far. The
// returned cancel function lets the owning timeline stop an in-flight jump on
// another click, wheel input, session switch, or unmount.
export function jumpScroll(viewport: HTMLElement, top: number, duration = 170): () => void {
  if (prefersReducedMotion()) {
    viewport.scrollTop = top

    return () => {}
  }

  const start = viewport.scrollTop
  const delta = top - start

  if (Math.abs(delta) < 2) {
    viewport.scrollTop = top

    return () => {}
  }

  const t0 = performance.now()
  const ease = (t: number) => 1 - (1 - t) ** 3 // easeOutCubic
  let jumpRaf = 0

  const step = (now: number) => {
    const p = Math.min(1, (now - t0) / duration)
    viewport.scrollTop = start + delta * ease(p)

    if (p < 1) {
      jumpRaf = requestAnimationFrame(step)
    }
  }

  jumpRaf = requestAnimationFrame(step)

  return () => cancelAnimationFrame(jumpRaf)
}

/** A kept-alive neighbor must never receive this rail's navigation. */
export const ownViewport = (root: HTMLElement | null): HTMLElement | null =>
  (root?.closest('[data-session-anchor]') ?? document).querySelector<HTMLElement>(VIEWPORT)

/** Hidden rails do not subscribe to streaming messages or measure layout. */
export const ThreadTimeline: FC = () => {
  const paneVisible = usePaneVisible()
  const hidden = useStore($hideThreadTimeline)

  return paneVisible && !hidden ? <ActiveThreadTimeline /> : null
}

const ActiveThreadTimeline: FC = () => {
  const view = useSessionView()
  const { t } = useI18n()
  const history = useTranscriptWindow()
  const historyIndex = useTimelineHistory()
  const { entries: indexedEntries, complete: indexComplete, failed: indexFailed, loadMore } = historyIndex
  const aui = useAui()
  const auiRef = useRef(aui)
  auiRef.current = aui

  // The store contains older prompts even when the runtime/DOM only paints a tail.
  // Read text only when user IDs change, never for assistant streaming deltas.
  const storeIds = useStoreSelector(view.$messages, messages =>
    messages
      .filter(m => m.role === 'user')
      .map(m => m.id)
      .join('\n')
  )

  const runtimeIds = useAuiState(s =>
    s.thread.messages
      .filter(m => m.role === 'user')
      .map(m => m.id)
      .join('\n')
  )

  const previous = useRef<TimelineEntry[]>([])

  const entries = useMemo(() => {
    const all = view.$messages.get()

    const rows: TimelineSourceMessage[] = all.length
      ? all
          .filter(m => m.role === 'user')
          .map(m => ({ id: m.id, rowId: m.rowId, role: m.role, text: messageContentText(m.parts) }))
      : auiRef.current
          .thread()
          .getState()
          .messages.filter(m => m.role === 'user')
          .map(m => ({ id: m.id, role: m.role, text: messageContentText(m.content) }))

    const next = deriveTimelineEntries(rows)

    if (sameTimelineEntries(previous.current, next)) {
      return previous.current
    }

    previous.current = next

    return next
    // The IDs are the change signal; the source messages are read only here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeIds, runtimeIds, view])

  const railEntries = useMemo(() => {
    const indexed = indexedEntries ?? []

    const selected = history.isHistorical
      ? deriveTimelineEntries(
          (history.currentMessages ?? []).map(message => ({
            id: message.id,
            rowId: message.rowId,
            role: message.role,
            text: messageContentText(message.parts)
          }))
        )
      : []

    const loaded = new Map(
      [...entries, ...selected].filter(entry => entry.rowId !== undefined).map(entry => [entry.rowId, entry])
    )

    const seen = new Set(indexed.map(entry => entry.rowId))

    const merged = [
      ...indexed.map(entry => loaded.get(entry.rowId) ?? entry),
      ...entries.filter(entry => entry.rowId === undefined || !seen.has(entry.rowId))
    ]

    return (history.olderAvailable || indexedEntries) && !indexComplete
      ? [{ id: EARLIER_TIMELINE_ID, preview: t.assistant.thread.showEarlier }, ...merged]
      : merged
  }, [
    entries,
    indexedEntries,
    indexComplete,
    history.olderAvailable,
    history.currentMessages,
    history.isHistorical,
    t.assistant.thread.showEarlier
  ])

  const root = useRef<HTMLDivElement>(null)
  const cancelScroll = useRef<(() => void) | null>(null)
  const pending = useRef<AbortController | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const { cancelReveal, revealMessage } = history

  // Every stale intent goes at once: the in-flight page request, the eased
  // scroll, and the boundary's pending store-window expansion — a click on
  // another mark, wheel input, or a session switch must not let an earlier
  // target land later.
  const cancelJump = useCallback(() => {
    pending.current?.abort()
    pending.current = null
    cancelScroll.current?.()
    cancelScroll.current = null
    cancelReveal()
    setLoadingId(null)
  }, [cancelReveal])

  useEffect(() => cancelJump, [cancelJump, view])

  // A store-only prompt (loaded, but outside the runtime window and without a
  // durable row the around route could page to) is asked of the boundary and
  // awaited here: the runtime ids are the change signal, so the reveal request
  // to the list is raised only once assistant-ui can actually mount the target.
  const materializing = useRef<{ id: string; settle: (mounted: boolean) => void } | null>(null)

  useEffect(() => {
    const waiting = materializing.current

    if (!waiting) {
      return
    }

    if (runtimeIds.split('\n').includes(waiting.id)) {
      waiting.settle(true)
    } else if (!storeIds.split('\n').includes(waiting.id)) {
      // The transcript rewound past the target: nothing will ever mount it.
      waiting.settle(false)
    }
  }, [runtimeIds, storeIds])

  const awaitMaterialized = useCallback(
    (id: string, signal: AbortSignal) =>
      new Promise<boolean>(resolve => {
        const settle = (mounted: boolean) => {
          if (materializing.current?.id === id) {
            materializing.current = null
          }

          resolve(mounted)
        }

        materializing.current = { id, settle }
        signal.addEventListener('abort', () => settle(false), { once: true })
      }),
    []
  )

  const jump = useCallback(
    async (id: string) => {
      cancelJump()

      if (id === EARLIER_TIMELINE_ID && indexedEntries && !indexComplete && !indexFailed) {
        await loadMore()

        return
      }

      const viewport = ownViewport(root.current)

      if (!viewport) {
        return
      }

      const controller = new AbortController()
      pending.current = controller
      setLoadingId(id)
      triggerHaptic('selection')

      const entry = railEntries.find(candidate => candidate.id === id)

      try {
        // A loaded prompt with no durable row (an older gateway that sends no
        // row_id) cannot be paged in by the around route. It still sits in the
        // session store, so ask the boundary to grow the runtime window until
        // the message materializes; the list's reveal observer then finishes
        // the jump once React mounts it.
        if (
          entry?.rowId === undefined &&
          !runtimeIds.split('\n').includes(id) &&
          !viewport.querySelector(`[data-message-id="${CSS.escape(id)}"]`)
        ) {
          revealMessage(id)

          if (!(await awaitMaterialized(id, controller.signal)) || controller.signal.aborted) {
            return
          }
        }

        // The list owns loading and render budgets. Request it on THIS viewport,
        // then wait for its commit rather than clicking a translated button label.
        const revealed = await new Promise<string | false>(resolve => {
          let settled = false

          const finish = (value: string | false) => {
            if (settled) {
              return
            }

            settled = true
            clearTimeout(timeout)
            resolve(value)
          }

          const timeout = window.setTimeout(() => finish(false), 15000)
          controller.signal.addEventListener('abort', () => finish(false), { once: true })

          const detail: TimelineRevealRequest = {
            id,
            rowId: entry?.rowId,
            signal: controller.signal,
            complete: finish
          }

          viewport.dispatchEvent(new CustomEvent(TIMELINE_REVEAL_EVENT, { detail }))
        })

        if (!revealed || controller.signal.aborted) {
          return
        }

        const node = viewport.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(revealed)}"]`)

        if (!node) {
          return
        }

        const start = viewport.scrollTop
        const turn = node.closest<HTMLElement>('[data-slot="aui_turn-pair"]') ?? node

        const destination = Math.max(
          0,
          start + turn.getBoundingClientRect().top - viewport.getBoundingClientRect().top - 8
        )

        cancelScroll.current = jumpScroll(viewport, destination)
      } finally {
        if (pending.current === controller) {
          setLoadingId(null)
        }
      }
    },
    [
      awaitMaterialized,
      cancelJump,
      indexedEntries,
      indexComplete,
      indexFailed,
      loadMore,
      railEntries,
      revealMessage,
      runtimeIds
    ]
  )

  useEffect(() => {
    const viewport = ownViewport(root.current)

    if (!viewport) {
      return
    }

    let frame = 0
    const indexes = new Map(railEntries.map((entry, index) => [entry.id, index]))

    const compute = () => {
      frame = 0

      if (viewport.dataset.following === 'true' && !history.isHistorical) {
        setActiveIndex(Math.max(0, railEntries.length - 1))

        return
      }

      const top = viewport.getBoundingClientRect().top
      let first = -1
      let active = -1

      // Walk only mounted messages, never every archived prompt in the rail.
      for (const node of viewport.querySelectorAll<HTMLElement>('[data-message-id]')) {
        const index = indexes.get(node.dataset.messageId!)

        if (index === undefined) {
          continue
        }

        if (first === -1) {
          first = index
        }

        const turn = node.closest<HTMLElement>('[data-slot="aui_turn-pair"]') ?? node

        if (turn.getBoundingClientRect().top - top <= 8) {
          active = index
        }
      }

      setActiveIndex(active === -1 ? Math.max(0, first) : active)
    }

    const schedule = () => {
      if (!frame) {
        frame = requestAnimationFrame(compute)
      }
    }

    const observer = new MutationObserver(schedule)
    const content = viewport.querySelector('[data-slot="aui_thread-content"]')

    if (content) {
      observer.observe(content, { childList: true })
    }

    viewport.addEventListener('scroll', schedule, { passive: true })
    viewport.addEventListener('wheel', cancelJump, { passive: true })
    schedule()

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      viewport.removeEventListener('scroll', schedule)
      viewport.removeEventListener('wheel', cancelJump)
    }
  }, [cancelJump, railEntries, history.isHistorical])

  if (!railEntries.length) {
    return null
  }

  return (
    <div
      aria-label="Conversation timeline"
      data-slot="thread-timeline"
      data-suppress-pane-reveal=""
      ref={root}
      role="navigation"
      style={{
        position: 'absolute',
        right: 0,
        top: '50%',
        transform: 'translateY(-50%)',
        zIndex: 40,
        pointerEvents: 'auto',
        height: `min(${railEntries.length * 0.4375}rem, 50%)`
      }}
    >
      <TimelineRail
        activeIndex={activeIndex}
        entries={railEntries}
        loadingId={loadingId}
        onJump={id => void jump(id)}
      />
    </div>
  )
}
