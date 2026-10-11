// The Studio for scene games: the live scene (Edit / Play), the list of what is in
// it, a small inspector for the selected object, and Add. Every change is saved as
// the game's scene (games/<id>.scene.json) plus its playable page (games/<id>.html);
// the Project picks both up. The assistant edits the same scene with scene.py.
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRotateCcw, ArrowRotateCw, Copy, Cube, Expand, Eye, Home, Menu, Minus, Pencil, Play, Plus, Trash, Undo, User, X } from '@openai/apps-sdk-ui/components/Icon'
import { buildGameDocument, relayVisibility } from './gameRuntime.js'
import { useEngine } from './engine.js'
import { sceneDocument } from './sceneRuntime.js'
import LaunchedGame from './LaunchedGame.jsx'

const store = () => window.mobius?.storage
const readEngineFile = (path) => store().getText(path)
// A game page minus its runtime module: a page that differs only by runtime is merely out of date, anything else is customised and left alone.
const withoutRuntime = (page) => page.replace(/<script type="module">[\s\S]*<\/script>/, '')

export const SCENE_CSS = `
.gs-sc { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.gs-sc-stage { position: relative; flex: 1; min-height: 260px; border-radius: 16px; overflow: hidden; background: #0b1020; }
.gs-sc-stage iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block; }
.gs-sc-tools { position: absolute; top: 10px; left: 10px; right: 10px; display: flex; gap: 8px; align-items: center; z-index: 3; pointer-events: none; }
.gs-sc-tools > * { pointer-events: auto; }
.gs-sc-seg { display: inline-flex; padding: 3px; border-radius: 12px; background: rgba(12,16,28,.72); backdrop-filter: blur(8px); }
.gs-sc-seg button { min-height: 38px; padding: 0 14px; border: 0; border-radius: 9px; background: transparent; color: #dfe6f5; font: 600 14px var(--font); display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.gs-sc-seg button[aria-pressed="true"] { background: #fff; color: #0b1020; }
.gs-sc-seg svg, .gs-sc-ic svg { width: 18px; height: 18px; }
.gs-sc-ic { width: 44px; height: 44px; border-radius: 12px; border: 0; display: grid; place-items: center; background: rgba(12,16,28,.72); backdrop-filter: blur(8px); color: #fff; cursor: pointer; }
.gs-sc-ic:disabled { opacity: .4; cursor: default; }
.gs-sc-ic:focus-visible, .gs-sc-seg button:focus-visible, .gs-sc-chip:focus-visible, .gs-sc-row:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-sc-spacer { flex: 1; }
.gs-sc-empty { position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); width: min(92%, 460px); padding: 16px 18px; border-radius: 16px; background: rgba(12,16,28,.8); backdrop-filter: blur(10px); color: #fff; z-index: 2; text-align: center; }
.gs-sc-empty h3 { margin: 0 0 4px; font-size: 17px; }
.gs-sc-empty p { margin: 0 0 10px; color: #c7cfe0; font-size: 14px; }
.gs-sc-chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.gs-sc-chip { min-height: 38px; padding: 0 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,.25); background: rgba(255,255,255,.08); color: #fff; font: 500 14px var(--font); cursor: pointer; }
.gs-sc-busy { position: absolute; left: 50%; top: 64px; transform: translateX(-50%); padding: 8px 14px; border-radius: 999px; background: rgba(12,16,28,.8); color: #fff; font: 500 13px var(--font); z-index: 3; display: flex; align-items: center; gap: 8px; }
.gs-sc-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); animation: gs-sc-pulse 1s ease-in-out infinite; }
@keyframes gs-sc-pulse { 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .gs-sc-dot { animation: none; } }
.gs-sc-sheet { position: absolute; left: 10px; right: 10px; bottom: 10px; max-height: 70%; overflow: auto; padding: 12px; border-radius: 16px; background: var(--surface); color: var(--text); border: 1px solid var(--border); box-shadow: 0 12px 32px rgba(0,0,0,.35); z-index: 4; }
.gs-sc-sheet header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.gs-sc-sheet h3 { margin: 0; font-size: 16px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gs-sc-sheet h4 { margin: 12px 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.gs-sc-close { width: 40px; height: 40px; border-radius: 10px; border: 0; background: transparent; color: var(--text); display: grid; place-items: center; cursor: pointer; }
.gs-sc-close svg { width: 18px; height: 18px; }
.gs-sc-actions { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 8px; }
.gs-sc-act { min-height: 56px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: 500 13px var(--font); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; cursor: pointer; }
.gs-sc-act svg { width: 18px; height: 18px; }
.gs-sc-act--danger { color: #e5484d; }
.gs-sc-act[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
.gs-sc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 8px; }
.gs-sc-tile { min-height: 84px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: 500 13px var(--font); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 6px; cursor: pointer; text-align: center; }
.gs-sc-tile img { width: 48px; height: 48px; object-fit: contain; }
.gs-sc-swatch { width: 34px; height: 34px; border-radius: 9px; }
.gs-sc-list { list-style: none; margin: 0; padding: 0; }
.gs-sc-row { width: 100%; min-height: 48px; display: flex; align-items: center; gap: 10px; padding: 0 10px; border: 0; border-radius: 10px; background: transparent; color: var(--text); font: 500 14px var(--font); text-align: left; cursor: pointer; }
.gs-sc-row[aria-current="true"] { background: var(--bg); box-shadow: inset 3px 0 0 var(--accent); }
.gs-sc-row small { margin-left: auto; color: var(--muted); font-weight: 400; }
.gs-sc-note { color: var(--muted); font-size: 14px; margin: 6px 2px; }
.gs-sc-parts { margin: 0 0 4px 38px; min-height: 32px; padding: 0 10px; border: 0; border-radius: 8px; background: transparent; color: var(--accent); font: 500 13px var(--font); cursor: pointer; }
.gs-sc-sub { margin-left: 24px; border-left: 1px solid var(--border); }
.gs-sc-cut { position: absolute; top: 62px; left: 10px; right: 10px; z-index: 3; display: flex; align-items: center; gap: 10px; padding: 6px 12px; border-radius: 12px; background: rgba(12,16,28,.72); backdrop-filter: blur(8px); color: #fff; font: 500 13px var(--font); }
.gs-sc-cut input { flex: 1; min-height: 32px; accent-color: var(--accent); }
.gs-sc-ic[aria-pressed="true"] { background: #fff; color: #0b1020; }
.gs-sc-bar { display: flex; gap: 8px; align-items: center; padding: 10px 0 0; }
@media (max-width: 959px) {
  .gs-panel--build .gs-sc { flex: 0 0 auto; }
  .gs-panel--build .gs-sc-stage { flex: 0 0 auto; height: clamp(230px, 44dvh, 560px); min-height: 0; }
  .gs-panel--build:not(:has(.gs-build-chat)) .gs-sc-stage { height: auto; flex: 1; min-height: 300px; }
  .gs-sc-bar { padding-top: 8px; }
  /* A compact strip so the object stays visible while you change it. */
  .gs-sc-sheet { left: 8px; right: 8px; bottom: 8px; padding: 8px 10px; max-height: 60%; }
  .gs-sc-sheet header { margin-bottom: 4px; }
  .gs-sc-sheet h3 { font-size: 15px; }
  .gs-sc-drag-note { display: none; }
  .gs-sc-actions { display: flex; overflow-x: auto; gap: 6px; padding-bottom: 2px; scrollbar-width: none; }
  .gs-sc-act { flex: 0 0 auto; min-width: 66px; min-height: 52px; padding: 0 8px; font-size: 12px; }
}
/* Phones: a toolbar that fits one row without squeezing the buttons, a shorter stage so
   the chat's message box stays on screen, and no cut-off hint text. */
@media (max-width: 559px) {
  .gs-panel--build .gs-sc-stage { height: clamp(210px, 36dvh, 420px); }
  .gs-sc-tools { top: 8px; left: 8px; right: 8px; gap: 5px; }
  .gs-sc-seg button { padding: 0 10px; min-height: 36px; font-size: 13px; }
  .gs-sc-seg svg { display: none; }
  .gs-sc-ic { flex: none; width: 40px; height: 40px; border-radius: 11px; }
  .gs-panel--build .gs-sc-stage { height: clamp(200px, 32dvh, 400px); }
  /* The More menu sits in the scene's corner instead of taking its own row. */
  .gs-sc { position: relative; }
  .gs-sc-bar .gs-sc-hint { display: none; }
  .gs-sc-bar { position: absolute; right: 8px; bottom: 8px; padding: 0; z-index: 4; }
  .gs-sc-bar .gs-btn { min-height: 40px; background: rgba(12,16,28,.72); color: #fff; border-color: transparent; backdrop-filter: blur(8px); }
  .gs-sc-sheet { bottom: 56px; }
  .gs-sc-empty { bottom: 56px; }
  .gs-sc-cut { top: 54px; left: 8px; right: 8px; }
  .gs-sc-empty { bottom: 10px; padding: 12px 14px; }
  .gs-sc-empty p { font-size: 13px; }
}
.gs-sc-bar .gs-sc-hint { flex: 1; min-width: 0; color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* Full screen without the browser's help (iPhone): the game fills the whole app. */
.gs-sc.is-full { position: fixed; inset: 0; z-index: 100; background: #000; }
.gs-sc.is-full .gs-sc-stage { flex: 1; height: auto; min-height: 0; border-radius: 0; }
.gs-sc.is-full .gs-sc-tools, .gs-sc.is-full .gs-sc-bar { display: none; }
.gs-launched { position: fixed; inset: 0; z-index: 1000; background: #0b1020; }
.gs-launched iframe { width: 100%; height: 100%; border: 0; display: block; }
.gs-launched-wait { position: absolute; inset: 0; display: grid; place-items: center; color: #fff; font: 600 16px system-ui, sans-serif; }
.gs-launched-close { position: absolute; top: max(10px, var(--mobius-safe-top, 0px)); right: max(10px, var(--mobius-safe-right, 0px)); width: 44px; height: 44px; border-radius: 50%; border: 0; background: rgba(0,0,0,.55); color: #fff; display: grid; place-items: center; cursor: pointer; }
.gs-sc-exit { position: absolute; top: max(10px, var(--mobius-safe-top, 0px)); right: max(10px, var(--mobius-safe-right, 0px)); z-index: 5; width: 44px; height: 44px; border-radius: 50%; border: 0; background: rgba(0,0,0,.5); color: #fff; display: grid; place-items: center; cursor: pointer; }
`

const SHAPES = [
  ['Flat ground', { type: 'terrain', name: 'Ground', shape: 'flat', size: 60, color: '#6fa34d', position: [0, 0, 0] }, '#6fa34d'],
  ['Hills', { type: 'terrain', name: 'Hills', shape: 'hills', size: 80, height: 6, color: '#6fa34d', color2: '#9c8a62', position: [0, 0, 0] }, '#7f9a55'],
  ['Water', { type: 'water', name: 'Water', size: 80, position: [0, 0.2, 0] }, '#2f7fb8'],
  ['Box', { type: 'box', name: 'Box', color: '#b0896a' }, '#b0896a'],
  ['Ball', { type: 'sphere', name: 'Ball', color: '#d9534f' }, '#d9534f'],
  ['Pillar', { type: 'cylinder', name: 'Pillar', color: '#c8c8c8', scale: [1, 3, 1] }, '#c8c8c8'],
  ['Coin', { type: 'cylinder', name: 'Coin', color: '#f2c230', scale: [0.8, 0.15, 0.8], rotation: [90, 0, 0], lift: 1, behaviors: [{ type: 'spin' }, { type: 'collectible', points: 1 }] }, '#f2c230'],
  ['Lamp', { type: 'light', name: 'Lamp', color: '#ffd9a0', intensity: 20, range: 15 }, '#ffd9a0'],
]

// A group's display name: "cabin" -> "Cabin", "old-barn" -> "Old barn".
const groupLabel = (g) => { const t = String(g).replace(/[-_]+/g, ' ').trim(); return t.charAt(0).toUpperCase() + t.slice(1) }
// The scene list: each group as one row (its parts inside), other objects as they are.
function listRows(objects) {
  const rows = [], groups = new Map()
  for (const o of objects) {
    if (o.group) {
      if (!groups.has(o.group)) { const row = { group: o.group, parts: [] }; groups.set(o.group, row); rows.push(row) }
      groups.get(o.group).parts.push(o)
    } else rows.push({ o })
  }
  return rows
}

const isPlayer = (o) => (o.behaviors || []).some((b) => b.type === 'player')
const describe = (o) => (isPlayer(o) ? 'player' : o.type === 'character' ? 'character' : o.type === 'model' ? 'asset' : o.type)

function newId(scene, name) {
  const base = String(name || 'object').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24) || 'object'
  const taken = new Set((scene.objects || []).map((o) => o.id))
  if (!taken.has(base)) return base
  let n = 2
  while (taken.has(`${base}-${n}`)) n += 1
  return `${base}-${n}`
}

export default function SceneEditor({ gameId, models, modelsReady, assets, art, saves, busy, turnSignal, onError, onSuggest, suggestions, menu }) {
  // Another game opened from inside this one (a stand you tap to play, say).
  const [launched, setLaunched] = useState(null)
  const closeLaunched = () => { setLaunched(null); frameRef.current?.contentWindow?.postMessage({ type: 'studio:game-closed' }, '*'); frameRef.current?.contentWindow?.focus() }
  const [scene, setScene] = useState(null)
  const [mode, setMode] = useState('edit')
  const [full, setFull] = useState(false)
  const [selected, setSelected] = useState(null)
  const [sheet, setSheet] = useState(null) // 'add' | 'list' | null
  const [reload, setReload] = useState(0)
  const [undo, setUndo] = useState([])
  const frameRef = useRef(null)
  // Leaving Game Studio (the shell keeps it loaded, hidden) silences and freezes the scene.
  const visibilityRef = useRef(null)
  useEffect(() => { const relay = relayVisibility(() => frameRef.current); visibilityRef.current = relay; return relay.stop }, [])
  const sceneRef = useRef(null)
  const saveTimer = useRef(null)
  const askRef = useRef(new Map())
  sceneRef.current = scene

  const post = (message) => frameRef.current?.contentWindow?.postMessage(message, '*')

  // The scene: the server's copy (agents write it), refreshed after each assistant turn.
  const fetchScene = async () => {
    const r = await store().getWithVersion(`games/${gameId}.scene.json`).catch(() => null)
    return r?.value || null
  }
  useEffect(() => {
    let alive = true
    setScene(null); setSelected(null); setUndo([]); setMode('edit'); setSheet(null)
    fetchScene().then((value) => {
      if (alive) setScene(value || { version: 1, name: 'Untitled game', settings: { sky: '#9fc9ea', light: {} }, objects: [], scripts: [] })
      // Each game keeps its own copy of the runtime in its page; bring an older copy up to date.
      if (value) {
        const page = sceneDocument(value, 'play')
        store().getText(`games/${gameId}.html`).then((stored) => { if (stored && stored !== page && withoutRuntime(stored) === withoutRuntime(page)) return store().setText(`games/${gameId}.html`, page, { contentType: 'text/html' }) }).catch(() => {})
      }
    })
    return () => { alive = false }
  }, [gameId])

  const adopt = (value) => {
    if (!value || JSON.stringify(value) === JSON.stringify(sceneRef.current)) return
    setScene(value)
    post({ type: 'scene:set', scene: value })
  }
  useEffect(() => { if (turnSignal) fetchScene().then(adopt) }, [turnSignal])
  // The scene can change from anywhere (the assistant, the Project, another device):
  // keep checking while the studio is on screen, faster while the assistant works.
  useEffect(() => {
    const tick = () => { if (document.visibilityState === 'visible' && !saveTimer.current) fetchScene().then(adopt) }
    const timer = setInterval(tick, busy ? 2000 : 4000)
    return () => clearInterval(timer)
  }, [busy, gameId])

  // The page loads once per game (and when models change); edits then go in live.
  const bootScene = useMemo(() => sceneRef.current, [gameId, reload, modelsReady, scene === null])
  const editPage = useMemo(() => (bootScene ? sceneDocument(bootScene, 'edit') : null), [bootScene])
  const sceneEngine = useEngine(editPage, readEngineFile)
  const srcDoc = useMemo(() => (editPage && modelsReady && sceneEngine.ready
    ? buildGameDocument(editPage, { sprites: assets.sprites, sounds: assets.sounds, models, art, saves, engine: sceneEngine.engine })
    : null), [editPage, modelsReady, models, sceneEngine])

  const save = (next, { record = true } = {}) => {
    if (record) setUndo((list) => [...list.slice(-29), sceneRef.current])
    setScene(next)
    clearTimeout(saveTimer.current)
    // Until this save has reached the server, checks for outside changes are skipped:
    // they would read the old copy and undo the edit on screen.
    saveTimer.current = setTimeout(() => {
      Promise.all([
        store().set(`games/${gameId}.scene.json`, next),
        store().setText(`games/${gameId}.html`, sceneDocument(next, 'play'), { contentType: 'text/html' }),
      ]).catch(() => onError?.({ message: 'Your change could not be saved. Check your connection.' }))
        .finally(() => { saveTimer.current = null })
    }, 500)
  }
  const change = (next) => { save(next); post({ type: 'scene:set', scene: next }) }
  const updateObject = (id, fn) => change({ ...scene, objects: scene.objects.map((o) => (o.id === id ? fn(o) : o)) })

  useEffect(() => {
    const onMessage = (event) => {
      if (event.source !== frameRef.current?.contentWindow) return
      const m = event.data || {}
      // A tap on any part of a group selects the whole group ("group:NAME").
      if (m.type === 'scene:pick') { setSelected(m.group ? `group:${m.group}` : m.id || null); if (m.id) setSheet(null) }
      else if (m.type === 'scene:moved') {
        const cur = sceneRef.current
        const moved = new Map((m.moves || [{ id: m.id, position: m.position }]).map((x) => [x.id, x.position]))
        save({ ...cur, objects: cur.objects.map((o) => (moved.has(o.id) ? { ...o, position: moved.get(o.id) } : o)) })
      } else if (m.type === 'scene:here') { const done = askRef.current.get(m.ask); askRef.current.delete(m.ask); done?.(m.target) }
      else if (m.type === 'studio:error') onError?.(m)
      else if (m.type === 'studio:open-game' && m.game === 'app-store') window.parent.postMessage({ type: 'moebius:open-app', appId: 'store' }, window.location.origin) // "launch": "app-store" opens the Möbius App Store
      else if (m.type === 'studio:open-game' && m.game === 'boba') { /* Worlds' juice stand: a drink in Möbius Worlds, nothing to open here */ }
      else if (m.type === 'studio:open-game' && /^[A-Za-z0-9_-]+$/.test(String(m.game || '')) && m.game !== gameId) setLaunched(String(m.game))
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [gameId])

  const where = () => new Promise((resolve) => {
    const ask = Math.random().toString(36).slice(2)
    askRef.current.set(ask, resolve)
    post({ type: 'scene:where', ask })
    setTimeout(() => { if (askRef.current.delete(ask)) resolve([0, 0]) }, 800)
  })

  const add = async (template) => {
    const [x, z] = await where()
    const o = JSON.parse(JSON.stringify(template))
    o.id = newId(sceneRef.current, o.name)
    if (o.type !== 'terrain' && o.type !== 'water') {
      const lift = o.lift; delete o.lift
      // No height means "standing on the ground"; a lift floats it at that height.
      o.position = [+(x + (Math.random() - 0.5) * 2).toFixed(2), lift ?? null, +(z + (Math.random() - 0.5) * 2).toFixed(2)]
    }
    const cur = sceneRef.current
    const next = { ...cur, objects: [...cur.objects, o] }
    change(next)
    setSheet(null)
    setSelected(o.id)
    setTimeout(() => post({ type: 'scene:select', id: o.id }), 400)
  }

  const setModeTo = (value) => {
    setMode(value)
    setSheet(null)
    if (value === 'play') setSelected(null)
    post({ type: 'scene:mode', mode: value })
    if (value === 'play') setTimeout(() => frameRef.current?.contentWindow?.focus(), 50)
  }

  // The selection: one object, or a whole group (its parts act as one).
  const groupName = typeof selected === 'string' && selected.startsWith('group:') ? selected.slice(6) : null
  const members = !scene || !selected ? [] : groupName ? scene.objects.filter((o) => o.group === groupName) : scene.objects.filter((o) => o.id === selected)
  const obj = members.length ? (groupName ? { id: selected, name: groupLabel(groupName), type: 'group', group: groupName } : members[0]) : null
  const selectIds = (key) => {
    const ids = key && key.startsWith('group:') ? (sceneRef.current?.objects || []).filter((o) => o.group === key.slice(6)).map((o) => o.id) : key ? [key] : null
    post({ type: 'scene:select', ids })
  }
  const [openGroup, setOpenGroup] = useState(null)
  // "See inside": everything above a height is sliced away (a dollhouse with the roof
  // off), measured from the ground where you're looking; starts just above head height.
  const [cutHeight, setCutHeight] = useState(null)
  useEffect(() => { post({ type: 'scene:cut', height: cutHeight }) }, [cutHeight])
  useEffect(() => { if (mode !== 'edit') setCutHeight(null) }, [mode])
  useEffect(() => { setCutHeight(null) }, [gameId])
  const characters = Object.entries(assets.characters || {}).filter(([, c]) => c.kind === '3d')
  const otherModels = Object.keys(assets.models || {}).filter((n) => !(assets.characters || {})[n])

  // Turning and resizing a group works around its middle, so the parts stay together.
  const ids = new Set(members.map((o) => o.id))
  const centre = () => {
    const pts = members.filter((o) => Array.isArray(o.position)).map((o) => o.position)
    return pts.length ? [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[2], 0) / pts.length] : [0, 0]
  }
  const updateMembers = (fn) => change({ ...scene, objects: scene.objects.map((o) => (ids.has(o.id) ? fn(o) : o)) })
  const rotate = (deg) => {
    const [cx, cz] = centre(), a = (deg * Math.PI) / 180
    updateMembers((o) => {
      const r = o.rotation || [0, 0, 0]
      const next = { ...o, rotation: [r[0], ((r[1] || 0) + deg) % 360, r[2]] }
      if (groupName && Array.isArray(o.position)) {
        const dx = o.position[0] - cx, dz = o.position[2] - cz
        next.position = [+(cx + dx * Math.cos(a) + dz * Math.sin(a)).toFixed(3), o.position[1], +(cz - dx * Math.sin(a) + dz * Math.cos(a)).toFixed(3)]
      }
      return next
    })
  }
  const resize = (k) => {
    const [cx, cz] = centre()
    updateMembers((o) => {
      let next
      if (o.type === 'terrain' || o.type === 'water') next = { ...o, size: Math.max(4, Math.round((o.size || 60) * k)) }
      else if (o.type === 'character') next = { ...o, height: +((o.height || 1.8) * k).toFixed(2) }
      else { const sc = o.scale ?? 1; next = { ...o, scale: Array.isArray(sc) ? sc.map((v) => +(v * k).toFixed(3)) : +(sc * k).toFixed(3) } }
      if (groupName && Array.isArray(o.position)) {
        const p = o.position
        next.position = [+(cx + (p[0] - cx) * k).toFixed(3), p[1] === null || p[1] === undefined ? p[1] : +(p[1] * k).toFixed(3), +(cz + (p[2] - cz) * k).toFixed(3)]
      }
      return next
    })
  }
  const duplicate = () => {
    const taken = new Set(scene.objects.map((o) => o.group).filter(Boolean))
    let g2 = groupName ? `${groupName}-2` : null
    for (let n = 2; g2 && taken.has(g2); n += 1) g2 = `${groupName}-${n + 1}`
    let working = scene
    const copies = members.map((o) => {
      const copy = JSON.parse(JSON.stringify(o))
      copy.id = newId(working, groupName ? `${g2}-${o.id.replace(new RegExp(`^${groupName}-`), '')}` : o.name || o.id)
      working = { ...working, objects: [...working.objects, copy] }
      if (!groupName) copy.name = `${o.name || o.id} copy`
      if (g2) copy.group = g2
      const shift = groupName ? 8 : 1.5
      if (Array.isArray(copy.position)) copy.position = [copy.position[0] + shift, copy.position[1], copy.position[2] + (groupName ? 0 : 1.5)]
      copy.behaviors = (copy.behaviors || []).filter((b) => b.type !== 'player')
      return copy
    })
    change({ ...scene, objects: [...scene.objects, ...copies] })
    const key = g2 ? `group:${g2}` : copies[0].id
    setSelected(key)
    setTimeout(() => selectIds(key), 400)
  }
  const remove = () => { change({ ...scene, objects: scene.objects.filter((o) => !ids.has(o.id)) }); setSelected(null) }
  const togglePlayer = () => {
    const make = !isPlayer(obj)
    change({ ...scene, objects: scene.objects.map((o) => {
      const rest = (o.behaviors || []).filter((b) => b.type !== 'player')
      return o.id === obj.id && make ? { ...o, behaviors: [...rest, { type: 'player' }] } : { ...o, behaviors: rest }
    }) })
  }
  const undoLast = () => {
    const prev = undo[undo.length - 1]
    if (!prev) return
    setUndo((list) => list.slice(0, -1))
    save(prev, { record: false })
    post({ type: 'scene:set', scene: prev })
  }

  // The browser's own full screen where it works; otherwise (iPhone, or when the page
  // isn't allowed to) the game fills the whole app, with a close button.
  const fullscreen = async () => {
    setModeTo('play')
    const frame = frameRef.current
    try {
      if (frame?.requestFullscreen) { await frame.requestFullscreen(); frame.contentWindow?.focus(); return }
    } catch { /* not allowed here: fill the app instead */ }
    setFull(true)
    window.mobius?.immersive?.set?.(true)
    frame?.contentWindow?.focus()
  }
  const exitFull = () => { setFull(false); window.mobius?.immersive?.set?.(false) }
  useEffect(() => () => { window.mobius?.immersive?.set?.(false) }, [])

  const empty = scene && !scene.objects.length
  return (
    <div className={`gs-sc${full ? ' is-full' : ''}`}>
      {launched && <LaunchedGame gameId={launched} assets={assets} models={models} onClose={closeLaunched} />}
      <div className="gs-sc-stage">
        {full && <button type="button" className="gs-sc-exit" aria-label="Exit full screen" onClick={exitFull}><X aria-hidden="true" /></button>}
        {srcDoc ? (
          <iframe key={`${gameId}-${reload}`} ref={frameRef} title={`${scene?.name || 'Game'} scene`} sandbox="allow-scripts allow-pointer-lock"
            allow="fullscreen *; gamepad *; autoplay *" srcDoc={srcDoc} onLoad={() => visibilityRef.current?.sync()} />
        ) : null}
        <div className="gs-sc-tools">
          <div className="gs-sc-seg" role="group" aria-label="Mode">
            <button type="button" aria-pressed={mode === 'edit'} onClick={() => setModeTo('edit')}><Pencil aria-hidden="true" />Edit</button>
            <button type="button" aria-pressed={mode === 'play'} onClick={() => setModeTo('play')}><Play aria-hidden="true" />Play</button>
          </div>
          <span className="gs-sc-spacer" />
          {mode === 'edit' && <>
            <button type="button" className="gs-sc-ic" aria-label="Undo" disabled={!undo.length} onClick={undoLast}><Undo aria-hidden="true" /></button>
            <button type="button" className="gs-sc-ic" aria-label="See inside buildings" aria-pressed={cutHeight !== null} onClick={() => setCutHeight(cutHeight === null ? 2.2 : null)}><Eye aria-hidden="true" /></button>
            <button type="button" className="gs-sc-ic" aria-label="Show everything" onClick={() => post({ type: 'scene:frame' })}><Home aria-hidden="true" /></button>
            <button type="button" className="gs-sc-ic" aria-label="What's in the scene" aria-expanded={sheet === 'list'} onClick={() => setSheet(sheet === 'list' ? null : 'list')}><Menu aria-hidden="true" /></button>
            <button type="button" className="gs-sc-ic" aria-label="Add to the scene" aria-expanded={sheet === 'add'} onClick={() => setSheet(sheet === 'add' ? null : 'add')}><Plus aria-hidden="true" /></button>
          </>}
          {mode === 'play' && <button type="button" className="gs-sc-ic" aria-label="Full screen" onClick={fullscreen}><Expand aria-hidden="true" /></button>}
        </div>
        {mode === 'edit' && cutHeight !== null && (
          <label className="gs-sc-cut">
            <span>See inside · cut at {cutHeight.toFixed(1)} m</span>
            <input type="range" min={0.3} max={12} step={0.1} value={cutHeight} onChange={(e) => setCutHeight(+e.target.value)} />
          </label>
        )}
        {busy && <div className="gs-sc-busy" role="status"><span className="gs-sc-dot" aria-hidden="true" />Building…</div>}
        {empty && mode === 'edit' && !sheet && !busy && (
          <div className="gs-sc-empty">
            <h3>Your scene is empty</h3>
            <p>Tell the assistant what to build, step by step, or tap + to add something yourself.</p>
            <div className="gs-sc-chips">
              {suggestions.map(([label, text]) => <button key={label} type="button" className="gs-sc-chip" onClick={() => onSuggest(text)}>{label}</button>)}
            </div>
          </div>
        )}
        {mode === 'edit' && obj && !sheet && (
          <div className="gs-sc-sheet" role="region" aria-label={`Selected: ${obj.name || obj.id}`}>
            <header>
              <h3>{obj.name || obj.id} <small className="gs-sc-note">· {groupName ? `${members.length} parts` : describe(obj)}</small></h3>
              <button type="button" className="gs-sc-close" aria-label="Deselect" onClick={() => { setSelected(null); selectIds(null) }}><X aria-hidden="true" /></button>
            </header>
            <p className="gs-sc-note gs-sc-drag-note">{groupName ? 'Drag it to move all its parts together. Single parts are in the scene list.' : 'Drag it in the scene to move it.'}</p>
            <div className="gs-sc-actions">
              <button type="button" className="gs-sc-act" onClick={() => rotate(-15)}><ArrowRotateCcw aria-hidden="true" />Turn left</button>
              <button type="button" className="gs-sc-act" onClick={() => rotate(15)}><ArrowRotateCw aria-hidden="true" />Turn right</button>
              <button type="button" className="gs-sc-act" onClick={() => resize(0.8)}><Minus aria-hidden="true" />Smaller</button>
              <button type="button" className="gs-sc-act" onClick={() => resize(1.25)}><Plus aria-hidden="true" />Bigger</button>
              {!groupName && (obj.type === 'character' || obj.type === 'model') && (
                <button type="button" className="gs-sc-act" aria-pressed={isPlayer(obj)} onClick={togglePlayer}><User aria-hidden="true" />{isPlayer(obj) ? 'Is the player' : 'Make player'}</button>
              )}
              <button type="button" className="gs-sc-act" onClick={duplicate}><Copy aria-hidden="true" />Duplicate</button>
              <button type="button" className="gs-sc-act gs-sc-act--danger" onClick={remove}><Trash aria-hidden="true" />Delete</button>
            </div>
          </div>
        )}
        {mode === 'edit' && sheet === 'list' && (
          <div className="gs-sc-sheet" role="region" aria-label="What's in the scene">
            <header><h3>In the scene</h3><button type="button" className="gs-sc-close" aria-label="Close" onClick={() => setSheet(null)}><X aria-hidden="true" /></button></header>
            {scene?.objects?.length ? (
              <ul className="gs-sc-list">
                {listRows(scene.objects).map((row) => row.group ? (
                  <li key={`g-${row.group}`}>
                    <button type="button" className="gs-sc-row" aria-current={selected === `group:${row.group}`} onClick={() => { setSelected(`group:${row.group}`); setSheet(null); selectIds(`group:${row.group}`) }}>
                      <Cube aria-hidden="true" />{groupLabel(row.group)}<small>{row.parts.length} parts</small>
                    </button>
                    <button type="button" className="gs-sc-parts" aria-expanded={openGroup === row.group} onClick={() => setOpenGroup(openGroup === row.group ? null : row.group)}>
                      {openGroup === row.group ? 'Hide parts' : 'Show parts'}
                    </button>
                    {openGroup === row.group && (
                      <ul className="gs-sc-list gs-sc-sub">
                        {row.parts.map((o) => (
                          <li key={o.id}>
                            <button type="button" className="gs-sc-row" aria-current={o.id === selected} onClick={() => { setSelected(o.id); setSheet(null); selectIds(o.id) }}>
                              {o.name || o.id}<small>{describe(o)}</small>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ) : (
                  <li key={row.o.id}>
                    <button type="button" className="gs-sc-row" aria-current={row.o.id === selected} onClick={() => { setSelected(row.o.id); setSheet(null); selectIds(row.o.id) }}>
                      {row.o.type === 'character' ? <User aria-hidden="true" /> : <Cube aria-hidden="true" />}
                      {row.o.name || row.o.id}<small>{describe(row.o)}</small>
                    </button>
                  </li>
                ))}
              </ul>
            ) : <p className="gs-sc-note">Nothing yet.</p>}
            {scene?.scripts?.length ? <p className="gs-sc-note">Game rules: {scene.scripts.map((s) => s.name).join(', ')}</p> : null}
          </div>
        )}
        {mode === 'edit' && sheet === 'add' && (
          <div className="gs-sc-sheet" role="region" aria-label="Add to the scene">
            <header><h3>Add to the scene</h3><button type="button" className="gs-sc-close" aria-label="Close" onClick={() => setSheet(null)}><X aria-hidden="true" /></button></header>
            <h4>Basics</h4>
            <div className="gs-sc-grid">
              {SHAPES.map(([label, template, swatch]) => (
                <button key={label} type="button" className="gs-sc-tile" onClick={() => add(template)}><span className="gs-sc-swatch" style={{ background: swatch }} aria-hidden="true" />{label}</button>
              ))}
            </div>
            <h4>Your characters</h4>
            {characters.length ? (
              <div className="gs-sc-grid">
                {characters.map(([name, c]) => (
                  <button key={name} type="button" className="gs-sc-tile" onClick={() => add({ type: 'character', name, character: name })}>
                    {c.thumb ? <img src={c.thumb} alt="" /> : <User aria-hidden="true" />}{name}
                  </button>
                ))}
              </div>
            ) : <p className="gs-sc-note">Make characters in the Characters tab; they show up here.</p>}
            {otherModels.length ? <>
              <h4>Your assets</h4>
              <div className="gs-sc-grid">
                {otherModels.map((name) => (
                  <button key={name} type="button" className="gs-sc-tile" onClick={() => add({ type: 'model', name, asset: name })}><Cube aria-hidden="true" />{name}</button>
                ))}
              </div>
            </> : null}
          </div>
        )}
      </div>
      <div className="gs-sc-bar">
        <span className="gs-sc-hint">{mode === 'play' ? 'Move with the stick, arrows or WASD · Space jumps' : 'Tap to select · drag to move · double-tap to fly there'}</span>
        {menu}
      </div>
    </div>
  )
}
