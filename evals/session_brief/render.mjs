#!/usr/bin/env node
/**
 * Screenshot Brief-pane fixtures at the real sidebar width via the Vite dev server + Playwright chromium.
 *
 *   node evals/session_brief/render.mjs --fixtures <dir-of-json> --out <png-dir> [--width 320] [--skin <name>]
 *                                        [--mode dark|light] [--server http://127.0.0.1:5174] [--concurrency 6]
 *
 * Each input is `{ brief, todos? }` (the shape the eval runner's snapshots carry under `brief`; a snapshot file
 * from `runner.py generate` is accepted too — every snapshot in it is rendered as `<fixture>-<message_count>.png`).
 * Starts the desktop dev server itself unless `--server` points at a running one. The page is the
 * `?win=brief-fixture` harness in `apps/desktop/src/app/brief-fixture/`, DEV only.
 *
 * Besides the full-height capture, a `*.glance.png` is written: the top 240 px — what a user sees before any
 * scroll — so graders judge what the first glance actually shows.
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from '@playwright/test'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '../..')
const desktop = path.join(repo, 'apps/desktop')

const args = parseArgs(process.argv.slice(2))
const width = Number(args.width ?? 320)
const concurrency = Number(args.concurrency ?? 6)
const outDir = path.resolve(args.out)
fs.mkdirSync(outDir, { recursive: true })

const jobs = collectJobs(path.resolve(args.fixtures))
if (jobs.length === 0) {
  console.error('no fixtures found')
  process.exit(2)
}

let devServer = null
let server = args.server
if (!server) {
  const port = 5190 + Math.floor(Math.random() * 100)
  server = `http://127.0.0.1:${port}`
  devServer = spawn('npx', ['vite', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: desktop,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, BROWSER: 'none' }
  })
  await waitFor(server, 60_000)
}

// Fixtures are served by a tiny static server so the harness can `fetch()` them (file:// is blocked).
const fixtureServer = http.createServer((req, res) => {
  const job = jobs.find(j => `/${j.id}.json` === req.url)
  if (!job) {
    res.writeHead(404).end()
    return
  }
  res.writeHead(200, { 'content-type': 'application/json', 'access-control-allow-origin': '*' })
  res.end(JSON.stringify(job.payload))
})
await new Promise(resolve => fixtureServer.listen(0, '127.0.0.1', resolve))
const fixtureBase = `http://127.0.0.1:${fixtureServer.address().port}`

const browser = await chromium.launch()
const manifest = []
let next = 0
await Promise.all(
  Array.from({ length: concurrency }, async () => {
    const context = await browser.newContext({ viewport: { width: width + 2, height: 1400 }, deviceScaleFactor: 2 })
    while (next < jobs.length) {
      const job = jobs[next++]
      const page = await context.newPage()
      const url = new URL('/', server)
      url.searchParams.set('win', 'brief-fixture')
      url.searchParams.set('fixture', `${fixtureBase}/${job.id}.json`)
      url.searchParams.set('width', String(width))
      if (args.skin) url.searchParams.set('skin', args.skin)
      if (args.mode) url.searchParams.set('mode', args.mode)
      try {
        await page.goto(url.toString(), { waitUntil: 'networkidle' })
        await page.waitForSelector('[data-fixture-state="ready"]', { timeout: 20_000 })
        await page.evaluate(() => document.fonts.ready)
        const full = path.join(outDir, `${job.id}.png`)
        const glance = path.join(outDir, `${job.id}.glance.png`)
        await page.locator('[data-fixture-state]').screenshot({ path: full })
        await page.screenshot({ path: glance, clip: { x: 0, y: 0, width: width + 2, height: 240 } })
        manifest.push({ id: job.id, full, glance, ...job.meta })
      } catch (error) {
        manifest.push({ id: job.id, error: String(error), ...job.meta })
      } finally {
        await page.close()
      }
      if (manifest.length % 10 === 0) console.error(`[render] ${manifest.length}/${jobs.length}`)
    }
    await context.close()
  })
)

await browser.close()
fixtureServer.close()
if (devServer) devServer.kill()
fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 1))
const failed = manifest.filter(m => m.error)
console.log(JSON.stringify({ rendered: manifest.length - failed.length, failed: failed.length, out: outDir }))
process.exit(failed.length ? 1 : 0)

function collectJobs(dir) {
  const jobs = []
  for (const file of fs.readdirSync(dir).filter(f => f.endsWith('.json') && !f.startsWith('_') && f !== 'manifest.json')) {
    const data = JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8'))
    const stem = file.replace(/\.json$/, '')
    if (Array.isArray(data.snapshots)) {
      for (const snap of data.snapshots) {
        if (snap.brief && !snap.brief._error) {
          jobs.push({ id: `${stem}-${snap.message_count}`, payload: { brief: snap.brief }, meta: { fixture_id: data.fixture_id, variant: data.variant, message_count: snap.message_count } })
        }
      }
    } else if (data.brief) {
      jobs.push({ id: stem, payload: data, meta: {} })
    }
  }
  return jobs
}

function parseArgs(argv) {
  const out = {}
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      out[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true
    }
  }
  return out
}

async function waitFor(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      await new Promise((resolve, reject) => http.get(url, res => (res.statusCode < 500 ? resolve() : reject(new Error(res.statusCode)))).on('error', reject))
      return
    } catch {
      await new Promise(r => setTimeout(r, 500))
    }
  }
  throw new Error(`dev server at ${url} did not come up`)
}
