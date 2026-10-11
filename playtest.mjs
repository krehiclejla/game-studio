#!/usr/bin/env node
// Studio agent self-test: plays one game in a headless browser exactly as the
// studio builds it, drives the controls, and reports errors plus screenshots.
//
//   node playtest.mjs <appId> <gameId> [--size 390x780] [--out DIR]
//
// Needs API_BASE_URL and AGENT_TOKEN (present in every Möbius agent run) and
// the agent-browser CLI. Prints one JSON summary; exit code 1 on page errors.
// Headless WebGL is software-rendered: judge correctness, not frame rate.
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { buildGameDocument, mergeArt, withAudio, withLibrary } from './gameRuntime.js'

const [appId, gameId, ...rest] = process.argv.slice(2)
if (!appId || !/^_?[a-z0-9-]+$/i.test(gameId || '')) {
  console.error('usage: node playtest.mjs <appId> <gameId> [--size WxH] [--out DIR]')
  process.exit(2)
}
const flag = (name, fallback) => {
  const i = rest.indexOf(name)
  return i >= 0 && rest[i + 1] ? rest[i + 1] : fallback
}
const [width, height] = flag('--size', '390x780').split('x').map(Number)
const outDir = flag('--out', join(process.env.TMPDIR || tmpdir(), `playtest-${gameId}`))
mkdirSync(outDir, { recursive: true })

const base = (process.env.API_BASE_URL || '').replace(/\/$/, '')
const auth = { Authorization: `Bearer ${process.env.AGENT_TOKEN || ''}` }
async function read(path, kind) {
  const res = await fetch(`${base}/api/storage/apps/${appId}/${path}`, { headers: auth })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  if (kind === 'json') return res.json()
  if (kind === 'bytes') return Buffer.from(await res.arrayBuffer())
  return res.text()
}

const html = await read(`games/${gameId}.html`, 'text')
if (!html) {
  console.log(JSON.stringify({ ok: false, error: `games/${gameId}.html does not exist yet` }))
  process.exit(1)
}
const assets = (await read('assets.json', 'json')) || {}
const models = {}
for (const name of Object.keys(assets.models || {})) {
  const bytes = await read(`models/${name}.glb`, 'bytes')
  if (bytes) models[name] = bytes.toString('base64')
}
const audio = {}
for (const name of Object.keys(assets.audio || {})) {
  const bytes = await read(`audio/${name}.mp3`, 'bytes')
  if (bytes) audio[name] = bytes.toString('base64')
}
const saves = (await read(`games/${gameId}.saves.json`, 'json')) || {}
const meta = (await read(`games/${gameId}.json`, 'json')) || {}
const kitArt = meta.art ? await read(`art/${meta.art}.json`, 'json') : null
if (meta.art && !kitArt) console.error(`note: art kit ${meta.art} is not installed; the game runs with its fallbacks`)
const art = withLibrary(mergeArt(kitArt, await read(`games/${gameId}.art.json`, 'json')), withAudio(assets, audio))
// The page (every model and sound inlined, often tens of MB) and the browser profile are
// throwaway: keep them on the container's own disk, not in app storage, and delete them
// at the end. Only the screenshots go to outDir.
const work = mkdtempSync(join('/tmp', 'gs-playtest-'))
const page = join(work, 'game.html')
writeFileSync(page, buildGameDocument(html, { sprites: assets.sprites || {}, sounds: assets.sounds || {}, saves, models, art, probe: true }))

// An isolated session with its own throwaway profile, so the playtest never
// collides with (or changes) the browser the agent or the studio preview uses.
const session = `playtest-${process.pid}`
const profile = join(work, 'profile')
const env = { ...process.env }
delete env.AGENT_BROWSER_PROFILE
delete env.AGENT_BROWSER_SESSION
let launchError = ''
const browse = (...args) => {
  try {
    return execFileSync('agent-browser', ['--session', session, '--profile', profile, ...args], { encoding: 'utf8', timeout: 60_000, env }).trim()
  } catch (err) {
    const text = String(err.stdout || '') + String(err.stderr || '') || String(err.message || '')
    if (/Chrome exited|DevTools/.test(text)) launchError ||= text.split('\n').find((line) => line.trim()) || 'The test browser could not start.'
    return text.trim()
  }
}
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const parseJson = (text) => { try { const v = JSON.parse(text); return typeof v === 'string' ? JSON.parse(v) : v } catch { return null } }
// Rough budgets for a phone: past these a game is likely to stutter there. They only warn.
const BUDGET = { drawCallsPerFrame: 300, trianglesPerFrame: 1_000_000 }
const shots = []
const shot = (name) => {
  const file = join(outDir, `${name}.png`)
  browse('screenshot', file)
  shots.push(file)
}
const drive = (js) => browse('eval', `(() => { try { ${js} } catch (e) { return String(e) } return 'ok' })()`)

try {
  browse('set', 'viewport', String(width), String(height))
  browse('open', `file://${page}`)
  await pause(3500)
  shot('1-start')
  // Start the game the way a player would: tap the middle, then press A.
  browse('mouse', 'move', String(Math.round(width / 2)), String(Math.round(height / 2)))
  browse('mouse', 'down')
  browse('mouse', 'up')
  browse('press', 'Space')
  await pause(1200)
  // Move right, then left, pressing A and B along the way.
  drive('studio.input.x = 1')
  await pause(900)
  browse('press', 'Space')
  drive('studio.input.x = -1; studio.input.y = -1')
  await pause(900)
  browse('press', 'x')
  drive('studio.input.x = 0; studio.input.y = 0')
  await pause(1500)
  shot('2-playing')
  await pause(3000)
  // Render cost over the next two seconds of play (the draw-call probe is in playtest pages only).
  drive('window.__glStats(true)')
  await pause(2000)
  const renderCost = parseJson(browse('eval', 'JSON.stringify(window.__glStats ? window.__glStats() : null)'))
  const sceneStats = parseJson(browse('eval', 'JSON.stringify(window.__sceneStats ? window.__sceneStats() : null)'))
  shot('3-later')
  if (launchError) {
    console.log(JSON.stringify({ ok: false, game: gameId, error: `Test browser could not start: ${launchError}`, screenshots: [] }, null, 2))
    process.exitCode = 1
  } else {
  const errors = browse('errors')
  const consoleLog = browse('console')
  const errorLines = errors.split('\n').map((line) => line.trim()).filter((line) => line && !/^no (page )?errors/i.test(line) && !/^✓/.test(line))
    .map((line) => (line === '✗' ? 'A page error with no message was thrown; add a try/catch or console.log around recent actions to find it.' : line))
  const summary = {
    ok: errorLines.length === 0,
    game: gameId,
    viewport: `${width}x${height}`,
    errors: errorLines.slice(0, 20),
    console: consoleLog.split('\n').filter(Boolean).slice(-20),
    render: renderCost && renderCost.frames > 5 ? { ...renderCost, ...(sceneStats ? { sceneObjects: sceneStats.objects, culledFar: sceneStats.culledFar, pixelRatio: sceneStats.pixelRatio } : {}), note: renderCost.drawCallsPerFrame === 0 ? 'Nothing was drawn during these two seconds: the game is probably waiting on a start tap or menu, so these counts say nothing yet.' : 'Headless frames are software-rendered, so judge the counts, not the speed.' } : undefined,
    performanceWarnings: [
      ...(renderCost && renderCost.drawCallsPerFrame > BUDGET.drawCallsPerFrame ? [`${renderCost.drawCallsPerFrame} draw calls per frame (budget ${BUDGET.drawCallsPerFrame}): merge or instance repeated meshes, and use fewer separate materials.`] : []),
      ...(renderCost && renderCost.trianglesPerFrame > BUDGET.trianglesPerFrame ? [`${renderCost.trianglesPerFrame} triangles per frame (budget ${BUDGET.trianglesPerFrame}): use lower-detail copies of repeated models far from the camera, or thin out scenery.`] : []),
    ],
    screenshots: shots,
    next: 'Read each screenshot and check the game visibly started, responds to input, and shows its HUD. Fix and re-run if not.',
  }
  console.log(JSON.stringify(summary, null, 2))
  process.exitCode = summary.ok ? 0 : 1
  }
} finally {
  browse('close')
  rmSync(work, { recursive: true, force: true })
}
