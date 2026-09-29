/**
 * Legacy update-check helpers moved to hermes_cli/source_check.py and the
 * updater strategy layer. Keep only the shared changelog row shape used by
 * bundle-skew's local-rebuild fold.
 */
export interface CompareCommit {
  sha: string
  summary: string
  author: string
  at: number
}
