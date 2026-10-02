import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

import { ErrorBoundary } from '@/components/error-boundary'
import { I18nProvider } from '@/i18n'
import type { TodoItem } from '@/lib/todos'
import { $activeSessionId, $selectedStoredSessionId } from '@/store/session'
import { applySessionBrief } from '@/store/session-brief'
import { $todosBySession } from '@/store/todos'
import { modePref, skinPref, ThemeProvider } from '@/themes/context'

import { BriefPane } from '../right-sidebar/brief'

/**
 * Render harness for the Brief pane: `?win=brief-fixture&fixture=<url>&width=<px>&skin=<name>&mode=<light|dark>`.
 *
 * Mounts ONLY `BriefPane` against the real stores, theme tokens and i18n — no shell, gateway or router — so
 * the design eval (`evals/session_brief/`) can screenshot hundreds of fixture briefs at the real sidebar width
 * without Electron. The fixture is `{ brief: SessionBrief, todos?: TodoItem[] }`. Not reachable from the app:
 * Electron never opens a window with this `win` kind.
 */
export function mountBriefFixture(): void {
  const root = document.getElementById('root')

  if (!root) {
    return
  }

  const params = new URLSearchParams(window.location.search)
  const skin = params.get('skin')
  const mode = params.get('mode')

  if (skin) {
    skinPref.assign('default', skin)
  }

  if (mode === 'light' || mode === 'dark') {
    modePref.assign('default', mode)
  }

  const width = Number(params.get('width')) || 320
  const fixtureUrl = params.get('fixture') ?? ''

  createRoot(root).render(
    <StrictMode>
      <ErrorBoundary label="brief-fixture">
        <I18nProvider>
          <ThemeProvider>
            <BriefFixture fixtureUrl={fixtureUrl} width={width} />
          </ThemeProvider>
        </I18nProvider>
      </ErrorBoundary>
    </StrictMode>
  )
}

interface FixturePayload {
  brief: unknown
  todos?: TodoItem[]
}

const FIXTURE_SESSION = 'brief-fixture'

function BriefFixture({ fixtureUrl, width }: { fixtureUrl: string; width: number }) {
  const [state, setState] = useState<'error' | 'loading' | 'ready'>('loading')

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const payload = (await (await fetch(fixtureUrl)).json()) as FixturePayload

        if (cancelled) {
          return
        }

        $selectedStoredSessionId.set(FIXTURE_SESSION)
        $activeSessionId.set(FIXTURE_SESSION)
        applySessionBrief(FIXTURE_SESSION, payload.brief)
        $todosBySession.set({ [FIXTURE_SESSION]: payload.todos ?? [] })
        setState('ready')
      } catch {
        if (!cancelled) {
          setState('error')
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [fixtureUrl])

  return (
    <div
      className="bg-background text-foreground h-screen overflow-hidden border-l border-(--ui-border)"
      data-fixture-state={state}
      style={{ width }}
    >
      {state === 'error' ? <p className="p-3 text-xs">fixture failed to load</p> : <BriefPane />}
    </div>
  )
}
