#!/usr/bin/env node
// Measure how a game loads: engine requests, bytes, time to first frames, frame rate.
//
//   node perf_baseline.mjs <page.html>... [--wait 6000] [--offline]
//
// Opens each page in a headless browser and prints one JSON line per page.
// Headless WebGL is software-rendered, so frame rate only compares builds of the
// same game; request count, bytes and load time are the meaningful numbers.
import { execFileSync } from 'node:child_process'
import { statSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const args = process.argv.slice(2)
const flag = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args.splice(i, 2)[1] : d }
const wait = Number(flag('--wait', 6000))
const offline = args.includes('--offline') && args.splice(args.indexOf('--offline'), 1)
const pages = args.map((p) => resolve(p))
const pause = (ms) => new Promise((r) => setTimeout(r, ms))

const PROBE = `(async () => {
  const frames = await new Promise((done) => { let n = 0; const t0 = performance.now();
    const tick = () => { n++; performance.now() - t0 < 2000 ? requestAnimationFrame(tick) : done(n / ((performance.now() - t0) / 1000)) }; requestAnimationFrame(tick) });
  const res = performance.getEntriesByType('resource');
  const nav = performance.getEntriesByType('navigation')[0];
  return JSON.stringify({
    webRequests: res.filter((r) => /^https?:/.test(r.name)).length,
    webBytes: res.filter((r) => /^https?:/.test(r.name)).reduce((a, r) => a + (r.transferSize || r.encodedBodySize || 0), 0),
    domContentLoadedMs: Math.round(nav.domContentLoadedEventEnd), loadMs: Math.round(nav.loadEventEnd),
    lastResourceEndMs: Math.round(Math.max(0, ...res.map((r) => r.responseEnd))),
    canvas: !!document.querySelector('canvas'), fps: Math.round(frames * 10) / 10 })
})()`

for (const page of pages) {
  const profile = mkdtempSync(join(tmpdir(), 'perf-'))
  const session = `perf-${process.pid}`
  const br = (...a) => { try { return execFileSync('agent-browser', ['--session', session, '--profile', profile, ...a], { encoding: 'utf8', timeout: 90_000 }).trim() } catch (e) { return String(e.stdout || e.message) } }
  try {
    br('set', 'viewport', '390', '780')
    if (offline) br('set', 'offline', 'on')
    br('open', `file://${page}`)
    await pause(wait)
    const out = br('eval', PROBE)
    let probe; try { probe = JSON.parse(JSON.parse(out)) } catch { try { probe = JSON.parse(out) } catch { probe = { raw: out.slice(0, 300) } } }
    const errors = br('errors').split('\n').filter((l) => l && !/^no (page )?errors/i.test(l) && !/^✓/.test(l)).slice(0, 3)
    console.log(JSON.stringify({ page, kb: Math.round(statSync(page).size / 1024), offline: !!offline, ...probe, errors }))
  } finally { br('close'); rmSync(profile, { recursive: true, force: true }) }
}
