import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { atom } from 'nanostores'
import { type ReactNode, useSyncExternalStore } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PRIMARY_SESSION_VIEW, type SessionView, SessionViewProvider } from '@/app/chat/session-view'
import type { ChatMessage } from '@/lib/chat-messages'
import { setHideThreadTimeline } from '@/store/thread-timeline'

import { TIMELINE_REVEAL_EVENT, type TimelineRevealRequest } from './timeline-data'
import { TranscriptWindowProvider } from './transcript-window'

/**
 * The timeline must do NO work it can't currently show. Two gates are proven
 * here by rendering the real component and counting the work it performs:
 *
 *  - a background (kept-alive but hidden) tab derives nothing and subscribes
 *    to nothing — the transcript selector is never even called;
 *  - an unhovered rail builds only a bounded tick slice, never a label list.
 *
 * The prompt-id selector is also asserted to be content-blind, which is what
 * keeps a streaming assistant reply from re-deriving previews per token.
 */

interface FakeMessage {
  content: unknown
  id: string
  role: string
}

const selectorCalls = vi.fn()
const transcriptReads = vi.fn()
const messageListeners = new Set<() => void>()
let messages: FakeMessage[] = []

vi.mock('@assistant-ui/react', () => ({
  useAui: () => ({
    thread: () => ({
      getState: () => {
        transcriptReads()

        return { messages }
      }
    })
  }),
  useAuiState: (selector: (state: { thread: { messages: FakeMessage[] } }) => unknown) => {
    selectorCalls()

    return useSyncExternalStore(
      listener => {
        messageListeners.add(listener)

        return () => messageListeners.delete(listener)
      },
      () => selector({ thread: { messages } })
    )
  }
}))

let paneActive = true

vi.mock('@/components/pane-shell/pane-visibility', () => ({
  usePaneVisible: () => paneActive
}))

vi.mock('@/lib/haptics', () => ({ triggerHaptic: () => {} }))

const { ThreadTimeline } = await import('./timeline')

const userTurn = (id: string, text: string): FakeMessage => ({
  content: [{ text, type: 'text' }],
  id,
  role: 'user'
})

const transcript = (count: number): FakeMessage[] =>
  Array.from({ length: count }, (_, i) => userTurn(`u${i}`, `prompt ${i}`))

const renderTimeline = (ui: ReactNode = <ThreadTimeline />) => render(ui)

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(300)
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(48)
})

afterEach(() => {
  cleanup()
  globalThis.document.body.replaceChildren()
  setHideThreadTimeline(false)
  vi.restoreAllMocks()
  selectorCalls.mockClear()
  transcriptReads.mockClear()
  paneActive = true
  messages = []
})

describe('ThreadTimeline in a background tab', () => {
  it('renders nothing and never reads the transcript', () => {
    paneActive = false
    messages = transcript(6)

    const { container } = renderTimeline()

    expect(container.querySelector('[data-slot="thread-timeline"]')).toBeNull()
    expect(selectorCalls).not.toHaveBeenCalled()
    expect(transcriptReads).not.toHaveBeenCalled()
  })

  it('renders the rail once its pane becomes the visible tab', () => {
    messages = transcript(6)

    const { container } = renderTimeline()

    expect(container.querySelector('[data-slot="thread-timeline"]')).not.toBeNull()
    expect(selectorCalls).toHaveBeenCalled()
  })
})

describe('ThreadTimeline idle work', () => {
  it('builds ticks without a separate popover or mounted labels', () => {
    messages = transcript(6)

    const { container } = renderTimeline()
    const popover = container.querySelector('[data-slot="thread-timeline-popover"]')

    expect(popover).toBeNull()
    expect(container.querySelectorAll('[data-timeline-id]')).toHaveLength(6)
    expect(screen.queryByText('prompt 0')).toBeNull()
  })

  it('keeps a large rail bounded before and after pointer movement', () => {
    messages = transcript(5000)

    const { container } = renderTimeline()
    const rail = container.querySelector<HTMLElement>('[data-slot="thread-timeline-ticks"]')!
    const ticks = Array.from(rail.querySelectorAll('[data-timeline-id]'))

    expect(ticks.length).toBeGreaterThan(0)
    expect(ticks.length).toBeLessThan(60)

    fireEvent.pointerMove(rail, { clientY: 100, pointerType: 'mouse' })
    fireEvent.pointerLeave(rail)

    expect(Array.from(rail.querySelectorAll('[data-timeline-id]'))).toEqual(ticks)
    expect(container.querySelector('[data-slot="thread-timeline-popover"]')).toBeNull()
    expect(screen.queryByText('prompt 0')).toBeNull()
  })

  it('schedules no history read for an unsaved conversation', () => {
    messages = transcript(2)
    const schedule = vi.spyOn(window, 'setTimeout')

    renderTimeline()

    expect(schedule.mock.calls.filter(([, delay]) => delay === 200)).toHaveLength(0)
  })
})

/** A stored prompt without a durable row: loaded in the session store, but
 *  outside the runtime window and unreachable through the around route. */
const storedPrompt = (id: string, text: string): ChatMessage => ({
  id,
  role: 'user',
  parts: [{ type: 'text', text }]
})

const storeView = (messages: ChatMessage[], runtimeId = 'runtime-1'): SessionView => ({
  ...PRIMARY_SESSION_VIEW,
  kind: 'tile',
  $messages: atom(messages),
  $runtimeId: atom<string | null>(runtimeId),
  $storedId: atom<string | null>(null)
})

const rect = (top: number, height: number): DOMRect =>
  ({
    bottom: top + height,
    height,
    left: 0,
    right: 800,
    top,
    width: 800,
    x: 0,
    y: top,
    toJSON: () => ({})
  }) as DOMRect

/** Mount a chat surface with its own viewport; the rail renders inside `host`. */
function mountSurface() {
  const surface = globalThis.document.createElement('div')
  const viewport = globalThis.document.createElement('div')
  const host = globalThis.document.createElement('div')

  surface.dataset.sessionAnchor = 'timeline-test'
  viewport.dataset.slot = 'aui_thread-viewport'
  viewport.getBoundingClientRect = () => rect(0, 400)
  surface.append(viewport, host)
  globalThis.document.body.append(surface)

  const revealRequests: TimelineRevealRequest[] = []

  // Stand in for the transcript list: acknowledge the reveal for whatever is
  // mounted under the id, exactly as use-timeline-reveal resolves it.
  viewport.addEventListener(TIMELINE_REVEAL_EVENT, event => {
    const request = (event as CustomEvent<TimelineRevealRequest>).detail
    revealRequests.push(request)
    request.complete(viewport.querySelector(`[data-message-id="${request.id}"]`) ? request.id : false)
  })

  const mountPrompt = (id: string, top: number) => {
    const node = globalThis.document.createElement('div')
    node.dataset.messageId = id
    node.getBoundingClientRect = () => rect(top, 100)
    viewport.append(node)
  }

  return { host, viewport, revealRequests, mountPrompt }
}

describe('ThreadTimeline with a bounded runtime window', () => {
  // Installed per test and removed explicitly: the shared setup file stubs
  // ResizeObserver through the same registry, so unstubAllGlobals would strip
  // it for every test that follows.
  const originalCss = globalThis.CSS
  const originalMatchMedia = globalThis.matchMedia

  beforeEach(() => {
    globalThis.CSS = { escape: (value: string) => value } as typeof CSS
    globalThis.matchMedia = vi.fn().mockReturnValue({ matches: true }) as unknown as typeof matchMedia
  })

  afterEach(() => {
    globalThis.CSS = originalCss
    globalThis.matchMedia = originalMatchMedia
  })

  it('keeps stored prompts in the rail and asks the window to reveal hidden targets', () => {
    messages = transcript(6).slice(4)
    const stored = Array.from({ length: 6 }, (_, i) => storedPrompt(`u${i}`, `prompt ${i}`))
    const cancelReveal = vi.fn()
    const revealMessage = vi.fn()
    const { host } = mountSurface()

    render(
      <SessionViewProvider value={storeView(stored)}>
        <TranscriptWindowProvider value={{ cancelReveal, expandWindow: vi.fn(), olderAvailable: true, revealMessage }}>
          <ThreadTimeline />
        </TranscriptWindowProvider>
      </SessionViewProvider>,
      { container: host }
    )

    expect(screen.getAllByRole('button', { name: /^prompt \d$/ })).toHaveLength(6)

    fireEvent.click(screen.getByRole('button', { name: 'prompt 0' }))

    expect(cancelReveal).toHaveBeenCalledOnce()
    expect(revealMessage).toHaveBeenCalledWith('u0')
    expect(cancelReveal.mock.invocationCallOrder[0]).toBeLessThan(revealMessage.mock.invocationCallOrder[0])

    // A second click replaces the first intent before asking for the new target.
    fireEvent.click(screen.getByRole('button', { name: 'prompt 1' }))

    expect(cancelReveal).toHaveBeenCalledTimes(2)
    expect(revealMessage).toHaveBeenNthCalledWith(2, 'u1')
    expect(cancelReveal.mock.invocationCallOrder[1]).toBeLessThan(revealMessage.mock.invocationCallOrder[1])
  })

  it('hands a rendered prompt to the owning list before scrolling to it', async () => {
    messages = transcript(6)
    const revealMessage = vi.fn()
    const { host, viewport, revealRequests, mountPrompt } = mountSurface()
    mountPrompt('u0', 100)

    render(
      <TranscriptWindowProvider value={{ expandWindow: vi.fn(), olderAvailable: false, revealMessage }}>
        <ThreadTimeline />
      </TranscriptWindowProvider>,
      { container: host }
    )

    fireEvent.click(screen.getByRole('button', { name: 'prompt 0' }))

    await waitFor(() => expect(viewport.scrollTop).toBe(92))
    expect(revealRequests.map(request => request.id)).toEqual(['u0'])
    expect(revealMessage).not.toHaveBeenCalled()
  })

  it('scrolls to the prompt after the window materializes it', async () => {
    messages = transcript(6).slice(4)
    const stored = Array.from({ length: 6 }, (_, i) => storedPrompt(`u${i}`, `prompt ${i}`))
    const view = storeView(stored)
    const cancelReveal = vi.fn()
    const revealMessage = vi.fn()
    const { host, viewport, revealRequests, mountPrompt } = mountSurface()

    const ui = (
      <SessionViewProvider value={view}>
        <TranscriptWindowProvider value={{ cancelReveal, expandWindow: vi.fn(), olderAvailable: true, revealMessage }}>
          <ThreadTimeline />
        </TranscriptWindowProvider>
      </SessionViewProvider>
    )

    render(ui, { container: host })

    fireEvent.click(screen.getByRole('button', { name: 'prompt 0' }))
    expect(revealMessage).toHaveBeenCalledWith('u0')
    expect(revealRequests).toHaveLength(0)

    // The boundary grew the runtime window: the target is now in assistant-ui
    // and mounted by the list.
    mountPrompt('u0', 100)
    messages = [userTurn('u0', 'prompt 0'), userTurn('u1', 'prompt 1')]
    act(() => messageListeners.forEach(listener => listener()))

    await waitFor(() => expect(viewport.scrollTop).toBe(92))
    expect(revealRequests.map(request => request.id)).toEqual(['u0'])

    // Once rendered, the same prompt no longer needs the window to grow.
    fireEvent.click(screen.getByRole('button', { name: 'prompt 0' }))

    expect(cancelReveal).toHaveBeenCalledTimes(2)
    expect(revealMessage).toHaveBeenCalledOnce()
  })

  it('cancels a pending hidden-target jump when the session view changes', async () => {
    messages = transcript(6).slice(4)
    const stored = Array.from({ length: 6 }, (_, i) => storedPrompt(`u${i}`, `prompt ${i}`))
    const cancelReveal = vi.fn()
    const { host, revealRequests, mountPrompt } = mountSurface()

    const ui = (view: SessionView) => (
      <SessionViewProvider value={view}>
        <TranscriptWindowProvider
          value={{ cancelReveal, expandWindow: vi.fn(), olderAvailable: true, revealMessage: vi.fn() }}
        >
          <ThreadTimeline />
        </TranscriptWindowProvider>
      </SessionViewProvider>
    )

    const { rerender } = render(ui(storeView(stored, 'runtime-1')), { container: host })

    fireEvent.click(screen.getByRole('button', { name: 'prompt 0' }))
    expect(cancelReveal).toHaveBeenCalledOnce()

    rerender(ui(storeView(stored, 'runtime-2')))
    expect(cancelReveal).toHaveBeenCalledTimes(2)

    // The stale target lands later; the abandoned jump must not consume it.
    mountPrompt('u0', 100)
    messages = [userTurn('u0', 'prompt 0'), userTurn('u1', 'prompt 1')]
    act(() => messageListeners.forEach(listener => listener()))
    await act(async () => {
      await Promise.resolve()
    })

    expect(revealRequests).toHaveLength(0)
  })
})

describe('ThreadTimeline availability', () => {
  it('hides every rail without reading transcripts and restores them when enabled', () => {
    messages = transcript(2)
    setHideThreadTimeline(true)

    const { container } = renderTimeline(
      <>
        <ThreadTimeline />
        <ThreadTimeline />
      </>
    )

    const rails = () => container.querySelectorAll('[data-slot="thread-timeline"]')

    expect(rails()).toHaveLength(0)
    expect(selectorCalls).not.toHaveBeenCalled()
    expect(transcriptReads).not.toHaveBeenCalled()

    act(() => setHideThreadTimeline(false))
    expect(rails()).toHaveLength(2)

    act(() => setHideThreadTimeline(true))
    expect(rails()).toHaveLength(0)
  })

  it('keeps navigation available for a short thread', () => {
    messages = transcript(2)

    const { container } = renderTimeline()

    expect(container.querySelector('[data-slot="thread-timeline"]')).not.toBeNull()
    expect(container.querySelectorAll('[data-timeline-id]')).toHaveLength(2)
  })
})

describe('ThreadTimeline while a reply streams', () => {
  it('does not re-derive the rail as assistant content grows', () => {
    messages = [...transcript(6), { content: [{ text: 'th', type: 'text' }], id: 'a1', role: 'assistant' }]

    renderTimeline()
    const derivations = transcriptReads.mock.calls.length

    // A token lands: the assistant message's content changes, the user prompt
    // ids do not — so the memo's change signal is untouched and the previews
    // are never rebuilt.
    messages = [
      ...messages.slice(0, -1),
      { content: [{ text: 'thinking…', type: 'text' }], id: 'a1', role: 'assistant' }
    ]
    act(() => messageListeners.forEach(listener => listener()))

    expect(transcriptReads.mock.calls.length).toBe(derivations)
  })

  it('re-derives once a new prompt is sent', () => {
    messages = transcript(6)

    renderTimeline()
    const derivations = transcriptReads.mock.calls.length

    messages = [...messages, userTurn('u6', 'prompt 6')]
    act(() => messageListeners.forEach(listener => listener()))

    expect(transcriptReads.mock.calls.length).toBeGreaterThan(derivations)
  })
})
