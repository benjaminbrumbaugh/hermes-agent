/**
 * Pure copy-selection for the updates overlay's "available" state.
 *
 * Names the update target (client vs the connected backend in remote mode) and
 * degrades honestly when there's no commit changelog to show (e.g. a pip /
 * non-git backend where `git log` yields nothing) instead of generic filler.
 *
 * Extracted from updates-overlay.tsx so the wording logic is unit-testable.
 */

export type UpdateTarget = 'client' | 'backend'

export interface UpdateCopyStrings {
  availableTitle: string
  availableBody: string
  availableTitleBackend: string
  availableBodyBackend: string
  availableBodyNoChangelog: string
  rebuildTitle: string
  rebuildBody: string
}

export interface ResolveUpdateCopyInput {
  target: UpdateTarget
  /** Number of commit rows actually shown in the changelog. 0 → no notes. */
  shownItems: number
  /** Client only: the offer rebuilds the app from local commits, no pull. */
  localRebuild?: boolean
  copy: UpdateCopyStrings
}

export interface UpdateCopyResult {
  title: string
  body: string
}

export function resolveUpdateCopy({
  target,
  shownItems,
  localRebuild,
  copy
}: ResolveUpdateCopyInput): UpdateCopyResult {
  // The checkout is current: say "rebuild", not "new version" — the user
  // folded the commits in themselves and nothing is being pulled.
  if (target === 'client' && localRebuild) {
    return { title: copy.rebuildTitle, body: copy.rebuildBody }
  }

  const title = target === 'backend' ? copy.availableTitleBackend : copy.availableTitle

  const body =
    shownItems === 0
      ? copy.availableBodyNoChangelog
      : target === 'backend'
        ? copy.availableBodyBackend
        : copy.availableBody

  return { title, body }
}
