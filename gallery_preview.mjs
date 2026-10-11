#!/usr/bin/env node
// Renders one Dream Gallery room in a headless browser and saves screenshots.
//   node gallery_preview.mjs <appId> <roomId> [--views spawn,left,right,back,mid] [--size 800x500] [--full] [--file recipe.json]
// The room's recipe is read from the gallery (public/room-<id>.json) unless --file is given.
// Headless WebGL is software-rendered and slow: the default draws sparse scenery (judge colours and layout);
// --full draws a denser version. Prints JSON with the screenshot paths.
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync, writeFileSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { buildGameDocument, mergeArt, withLibrary } from './gameRuntime.js'

const [appId, roomId, ...rest] = process.argv.slice(2)
const flag = (n, d) => { const i = rest.indexOf(n); return i >= 0 && rest[i + 1] ? rest[i + 1] : d }
const [width, height] = flag('--size', '800x500').split('x').map(Number)
const views = flag('--views', 'spawn,left,right').split(',')
const full = rest.includes('--full')
const outDir = join(process.env.TMPDIR || tmpdir(), `gallery-preview-${roomId}`)
mkdirSync(outDir, { recursive: true })

const base = (process.env.API_BASE_URL || '').replace(/\/$/, '')
const auth = { Authorization: `Bearer ${process.env.AGENT_TOKEN || ''}` }
async function read(path, kind) {
  const res = await fetch(`${base}/api/storage/apps/${path}`, { headers: auth })
  if (res.status === 404) return null
  if (kind === 'json') return res.json()
  if (kind === 'bytes') return Buffer.from(await res.arrayBuffer())
  return res.text()
}
const safe = roomId.replace(/[^a-z0-9_-]/gi, '')
const spec = flag('--file') ? JSON.parse(readFileSync(flag('--file'), 'utf8')) : await read(`${appId}/public/room-${safe}.json`, 'json')
if (!spec) { console.log(JSON.stringify({ ok: false, error: 'No recipe yet: run gallery_room.py put first (or pass --file).' })); process.exit(1) }

const GAME = 'g-dreamgal', STUDIO = process.env.STUDIO_APP_ID || '12'
const html = await read(`${STUDIO}/games/${GAME}.html`)
const assets = (await read(`${STUDIO}/assets.json`, 'json')) || {}
const models = {}
for (const n of Object.keys(assets.models || {})) {
  if (!html.includes(`"${n}"`) && !html.includes(`'${n}'`)) continue
  const b = await read(`${STUDIO}/models/${n}.glb`, 'bytes')
  if (b) models[n] = b.toString('base64')
}
const svg = (w, h, a, b, c) => 'data:image/svg+xml;base64,' + Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><circle cx="${w * 0.6}" cy="${h * 0.38}" r="${h * 0.16}" fill="${c}"/></svg>`).toString('base64')
const pictures = [
  { id: 'p1', title: 'Sample picture one', note: 'Your own pictures hang here.', dataUrl: svg(800, 600, '#2b4f8f', '#e08a5a', '#ffe9a8'), aspect: 1.33, at: Date.now() },
  { id: 'p2', title: 'Sample picture two', note: '', dataUrl: svg(600, 800, '#5a2b6b', '#e0709a', '#fff1d0'), aspect: 0.75, at: Date.now() },
  { id: 'p3', title: 'Sample picture three', note: '', dataUrl: svg(900, 600, '#1d6b5a', '#c8e08a', '#ffffff'), aspect: 1.5, at: Date.now() },
]
const gallery = { v: 3, builtin: { void: false, garden: false, memory: false }, shared: false, rooms: [{ id: safe, name: spec.name || 'Preview', color: spec.palette?.accent || '#ffcf8a', style: 'warm', pictures, spec, vibe: 'preview', status: 'ready' }] }
const page = join(outDir, 'game.html')
writeFileSync(page, buildGameDocument(html, { sprites: {}, sounds: {}, saves: { gallery }, models, art: withLibrary(mergeArt(null, null), assets) }))

const session = `rp-${process.pid}`, profile = join(outDir, 'profile')
const env = { ...process.env }; delete env.AGENT_BROWSER_PROFILE; delete env.AGENT_BROWSER_SESSION
const browse = (...a) => { try { return execFileSync('agent-browser', ['--session', session, '--profile', profile, ...a], { encoding: 'utf8', timeout: 150_000, env }).trim() } catch (e) { return String(e.stdout || '') + String(e.stderr || e.message || '') } }
const pause = (ms) => new Promise((r) => setTimeout(r, ms))
// Poll the page instead of sleeping a fixed time: stop as soon as the condition holds.
const until = async (js, ms) => {
  const end = Date.now() + ms
  while (Date.now() < end) { if (browse('eval', js).includes('true')) return true; await pause(400) }
  return false
}
const shots = []
try {
  browse('set', 'viewport', String(width), String(height))
  browse('open', `file://${page}?preview&q=${full ? '0.45' : '0.18'}`)
  await until("!!document.getElementById('dg-enter')", 15000)
  browse('eval', "document.getElementById('dg-enter').click(); 'ok'")
  await until('!!window.gallery', 60000)
  browse('eval', `window.gallery.goTo(${JSON.stringify(safe)}); 'go'`)
  await until(`window.gallery.roomId === ${JSON.stringify(safe)}`, 15000)
  await pause(800)
  let v = {}
  try { v = JSON.parse(JSON.parse(browse('eval', 'JSON.stringify(window.gallery.view)'))) } catch { v = { x: 0, z: 6 } }
  const poses = {
    spawn: [v.x, v.z, 0, 0], left: [v.x, v.z, 1.0, 0], right: [v.x, v.z, -1.0, 0], back: [v.x, v.z, Math.PI, 0], up: [v.x, v.z, 0, 0.55],
    mid: [v.x, v.z - 7, 0, -0.05], far: [v.x, v.z - 14, 0.6, 0],
  }
  for (const name of views) {
    if (name === 'focus') {
      // What a visitor sees after clicking a picture: it should float up in front of them.
      browse('eval', `window.gallery.pose(${poses.spawn.join(',')}); window.gallery.focusPicture(${JSON.stringify(safe)}, 'p1'); 'f'`)
      await pause(2200)
      const file = join(outDir, 'focus.png')
      browse('screenshot', file)
      shots.push(file)
      continue
    }
    const p = poses[name]
    if (!p) continue
    browse('eval', `window.gallery.pose(${p.join(',')}); 'p'`)
    await pause(700)
    const file = join(outDir, `${name}.png`)
    browse('screenshot', file)
    shots.push(file)
  }
  const errors = browse('errors').split('\n').map((l) => l.trim()).filter((l) => l && !/^no (page )?errors/i.test(l) && !/^✓/.test(l))
  console.log(JSON.stringify({ ok: errors.length === 0, room: safe, screenshots: shots, errors: errors.slice(0, 10), next: 'Read the screenshots. Fix only what is clearly wrong, put again, and stop.' }, null, 2))
} finally {
  browse('close')
  rmSync(profile, { recursive: true, force: true })
}
