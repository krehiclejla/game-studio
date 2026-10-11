#!/usr/bin/env node
// Does the scene runtime's performance work pay off? Builds a deliberately heavy scene
// (a wide field of props, the player at one edge), plays it headless with the defaults
// ON and OFF, and prints the renderer's draw calls and triangles for each.
//
//   node scene_perf.mjs [propCount=2500]
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { buildGameDocument } from './gameRuntime.js'
import { sceneDocument } from './sceneRuntime.js'

const count = Number(process.argv[2] || 2500)
let seed = 7
const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647
const objects = [{ id: 'ground', type: 'terrain', shape: 'flat', size: 700, color: '#6fa34d', position: [0, 0, 0] },
  { id: 'hero', type: 'box', name: 'Hero', color: '#c0392b', scale: [0.6, 1.6, 0.6], position: [0, null, 0], behaviors: [{ type: 'player' }] }]
for (let i = 0; i < count; i++) {
  const shape = ['box', 'sphere', 'cylinder', 'cone'][i % 4]
  objects.push({ id: `p${i}`, type: shape, color: ['#d35400', '#2980b9', '#8e44ad', '#16a085'][i % 4], scale: [0.5 + rnd(), 0.5 + rnd() * 2, 0.5 + rnd()], position: [(rnd() - 0.5) * 640, null, (rnd() - 0.5) * 640] })
}
const scene = { version: 1, name: 'perf', settings: { sky: '#9fc9ea', fog: { color: '#cfe3f0', near: 60, far: 220 } }, objects, scripts: [] }

const dir = mkdtempSync(join(tmpdir(), 'sceneperf-'))
const engineDir = process.env.GS_ENGINE_DIR || '/data/apps/12/engine'
const index = JSON.parse(readFileSync(join(engineDir, 'index.json'), 'utf8'))
const engine = {}
const html = sceneDocument(scene, 'play')
for (const [url, name] of Object.entries(index)) if (html.includes(url) || url.includes('zzfx') || url === 'https://esm.sh/three@0.180.0') engine[url] = readFileSync(join(engineDir, name), 'utf8')
const pause = (ms) => new Promise((r) => setTimeout(r, ms))

for (const performance of [true, false]) {
  const page = join(dir, `perf-${performance}.html`)
  const doc = sceneDocument({ ...scene, settings: { ...scene.settings, performance } }, 'play')
  writeFileSync(page, buildGameDocument(doc, { engine }))
  const profile = join(dir, `profile-${performance}`)
  const br = (...a) => { try { return execFileSync('agent-browser', ['--session', `sp-${process.pid}`, '--profile', profile, ...a], { encoding: 'utf8', timeout: 120_000 }).trim() } catch (e) { return String(e.stdout || e.message) } }
  br('set', 'viewport', '390', '780')
  br('open', `file://${page}`)
  await pause(9000)
  const out = br('eval', 'JSON.stringify(window.__sceneStats && window.__sceneStats())')
  console.log(`performance ${performance ? 'ON ' : 'OFF'}: ${out}`)
  br('close')
}
rmSync(dir, { recursive: true, force: true })
