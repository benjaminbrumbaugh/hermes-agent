import { describe, expect, it } from 'vitest'

import { resolveUpdateCopy } from './update-copy'

const copy = {
  availableTitle: 'New update available',
  availableBody: 'A new version of Hermes is ready to install.',
  availableTitleBackend: 'Backend update available',
  availableBodyBackend: 'A newer version of the connected Hermes backend is ready to install.',
  availableBodyNoChangelog: 'A newer version is ready. Release notes aren’t available for this install type.',
  rebuildTitle: 'Rebuild available',
  rebuildBody: 'Changes on your branch aren’t in the running app yet.'
}

describe('resolveUpdateCopy', () => {
  it('client target with commits: client title + client body', () => {
    const r = resolveUpdateCopy({ target: 'client', shownItems: 5, copy })
    expect(r.title).toBe('New update available')
    expect(r.body).toBe('A new version of Hermes is ready to install.')
  })

  it('backend target with commits: names the backend in title and body', () => {
    const r = resolveUpdateCopy({ target: 'backend', shownItems: 5, copy })
    expect(r.title).toBe('Backend update available')
    expect(r.body).toContain('backend')
  })

  it('no changelog (pip/non-git backend): degrades honestly, still names backend target in title', () => {
    const r = resolveUpdateCopy({ target: 'backend', shownItems: 0, copy })
    expect(r.title).toBe('Backend update available')
    // Body must NOT pretend there are notes — it states they're unavailable.
    expect(r.body).toBe(copy.availableBodyNoChangelog)
  })

  it('local rebuild on client: names a rebuild, not a new version, even with a changelog', () => {
    const r = resolveUpdateCopy({ target: 'client', shownItems: 3, localRebuild: true, copy })
    expect(r.title).toBe(copy.rebuildTitle)
    expect(r.body).toBe(copy.rebuildBody)
  })

  it('local rebuild flag never re-labels a backend update', () => {
    const r = resolveUpdateCopy({ target: 'backend', shownItems: 3, localRebuild: true, copy })
    expect(r.title).toBe('Backend update available')
  })

  it('no changelog on client: same honest degrade', () => {
    const r = resolveUpdateCopy({ target: 'client', shownItems: 0, copy })
    expect(r.title).toBe('New update available')
    expect(r.body).toBe(copy.availableBodyNoChangelog)
  })
})
