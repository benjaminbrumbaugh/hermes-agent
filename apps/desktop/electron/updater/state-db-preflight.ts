import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

import { hiddenWindowsChildOptions } from '../windows-child-options'

interface StateDbPreflight {
  python: string | null
  script: string
  home: string
  log: (message: string) => void
  /**
   * The installation launcher of a PM-managed checkout (`.hermes/bin/hermes`).
   * A managed checkout carries no venv of its own — the launcher owns
   * interpreter and generation selection there — so the snapshot runs through
   * it exactly like the update check does (`readSourceUpdate`).
   */
  launcher?: string | null
}

// Synchronous by design: the caller must not stop the backend before the snapshot.
export function preflightStateDb({ python, script, home, log, launcher = null }: StateDbPreflight): void {
  try {
    const command: string | null = launcher ?? python

    if (!command) {
      throw new Error('Python not found')
    }

    const args: string[] = launcher ? ['--run-module', 'hermes_cli.backup_sqlite', home] : ['-I', '-S', script, home]
    const timeout: number = stateDbPreflightTimeoutMs(stateDbBytes(home))

    // Node refuses direct .cmd execFile; an older published launcher can still
    // be one. Same fail-closed guard as the update check: shell:true would
    // interpolate untrusted paths, so keep cmd.exe's one unavoidable parse
    // closed instead.
    const viaCmd: boolean = process.platform === 'win32' && /\.cmd$/i.test(command)

    if (viaCmd && [command, ...args].some((value: string): boolean => /["%&|<>^\r\n]/.test(value))) {
      throw new Error('The pre-flight snapshot contains an unsafe Windows command argument.')
    }

    const result: string = execFileSync(
      viaCmd ? (process.env.ComSpec ?? 'cmd.exe') : command,
      viaCmd
        ? ['/d', '/v:off', '/s', '/c', `""${command}" ${args.map((arg: string): string => `"${arg}"`).join(' ')}"`]
        : args,
      hiddenWindowsChildOptions({
        encoding: 'utf8',
        timeout,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsVerbatimArguments: viaCmd
      })
    )

    log(`[updates] state.db pre-flight: ${result.trim()}`)
  } catch (error: unknown) {
    const message =
      `state.db pre-flight failed: ${error instanceof Error ? error.message : String(error)}. ` +
      'Update cancelled before backend shutdown. Update the selected installation with its hermes update command, then retry.'

    log(`[updates] ${message}`)
    throw new Error(message, { cause: error })
  }
}

const MIN_PREFLIGHT_TIMEOUT_MS = 30_000
const MAX_PREFLIGHT_TIMEOUT_MS = 15 * 60_000
// SQLite's backup API on a laptop SSD moves a few hundred MB/s; a page-by-page
// copy with a busy-check callback and a following quick_check lands well under
// that. 100 MB/s leaves ~3x headroom for a loaded machine or a slower disk.
const PREFLIGHT_BYTES_PER_SECOND = 100 * 1024 * 1024

/**
 * Snapshot deadline sized from the database: a fixed 30 s cap killed the
 * copy of any state.db past ~10 GB, cancelling every update on that machine
 * with ETIMEDOUT even though the snapshot itself was healthy.
 */
export function stateDbPreflightTimeoutMs(bytes: number): number {
  const scaled: number = Math.ceil((Math.max(0, bytes) / PREFLIGHT_BYTES_PER_SECOND) * 1000) + MIN_PREFLIGHT_TIMEOUT_MS

  return Math.min(MAX_PREFLIGHT_TIMEOUT_MS, scaled)
}

/** Main file plus WAL — the backup copies the checkpointed view of both. */
function stateDbBytes(home: string): number {
  let total = 0

  for (const name of ['state.db', 'state.db-wal']) {
    try {
      total += fs.statSync(path.join(home, name)).size
    } catch {
      // missing file (fresh install, or no WAL yet) contributes nothing
    }
  }

  return total
}
