// A Game Studio game, installed as its own Möbius app. This file is the same
// for every game; publish_game.py writes the game itself (game.js) and its art
// (data*.js) next to it. Edit the game in Game Studio, not here: publishing
// replaces every file in this folder.
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Comment, EditPencil, X } from '@openai/apps-sdk-ui/components/Icon'
import { buildGameDocument, relayVisibility } from './gameRuntime.js'
import { createVoice } from './voice.js'
import { GAME } from './game.js'
import DATA from './data.js'

const CSS = `
* { box-sizing: border-box; }
html, body, #root { height: 100%; }
.gp-root { position: fixed; inset: 0; background: ${GAME.background}; overflow: hidden; }
.gp-bar { position: absolute; inset: 0 0 auto 0; height: calc(var(--mobius-safe-top, 0px) + 60px); padding: var(--mobius-safe-top, 0px) max(12px, var(--mobius-safe-right, 0px)) 0 calc(max(10px, var(--mobius-safe-left, 0px)) + 54px);
  display: flex; align-items: center; gap: 10px; color: #fff; background: rgba(0,0,0,.28); border-bottom: 1px solid rgba(255,255,255,.08); }
.gp-bar h1 { flex: 1; min-width: 0; margin: 0; font: 700 16px/1.2 system-ui, sans-serif; letter-spacing: -.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gp-stage { position: absolute; inset: calc(var(--mobius-safe-top, 0px) + 60px) 0 0 0; }
.gp-stage iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block; }
.gp-edit { flex: none; display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 14px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,.22); background: rgba(255,255,255,.1); color: #fff; font: 600 14px system-ui, sans-serif; cursor: pointer; }
.gp-edit:hover { background: rgba(255,255,255,.18); }
.gp-edit:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
.gp-edit svg { width: 16px; height: 16px; }
.gp-toast { position: absolute; z-index: 3; left: 50%; bottom: max(16px, var(--mobius-safe-bottom, 0px)); transform: translateX(-50%);
  width: min(92vw, 440px); display: flex; gap: 10px; align-items: center; padding: 12px 14px; border-radius: 14px;
  background: rgba(20,22,40,.94); color: #fff; font: 14px/1.4 system-ui, sans-serif; box-shadow: 0 8px 30px rgba(0,0,0,.4); }
.gp-toast p { margin: 0; flex: 1; }
.gp-toast button { min-height: 40px; padding: 0 12px; border-radius: 10px; border: 0; background: #fff; color: #111; font: 600 13px system-ui, sans-serif; cursor: pointer; }
.gp-note-open { flex: none; display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 14px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,.22); background: transparent; color: #fff; font: 600 14px system-ui, sans-serif; cursor: pointer; }
.gp-note-open:focus-visible, .gp-note button:focus-visible, .gp-note textarea:focus-visible, .gp-note input:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
.gp-note-open svg { width: 16px; height: 16px; }
.gp-note-scrim { position: absolute; inset: 0; z-index: 4; display: flex; align-items: flex-end; justify-content: center; background: rgba(0,0,0,.45); }
.gp-note { width: min(100%, 460px); margin: 0 0 max(12px, var(--mobius-safe-bottom, 0px)); padding: 18px; border-radius: 20px; background: #171a2e; color: #fff;
  font: 15px/1.45 system-ui, sans-serif; box-shadow: 0 -8px 40px rgba(0,0,0,.45); display: grid; gap: 12px; }
@media (min-width: 600px) { .gp-note-scrim { align-items: center; } }
.gp-note header { display: flex; align-items: center; justify-content: space-between; }
.gp-note h2 { margin: 0; font-size: 18px; }
.gp-note p { margin: 0; color: rgba(255,255,255,.7); font-size: 14px; }
.gp-note textarea, .gp-note input { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,.18); background: rgba(255,255,255,.06); color: #fff; font: inherit; }
.gp-note textarea { min-height: 110px; resize: vertical; }
.gp-note-actions { display: flex; justify-content: flex-end; gap: 8px; }
.gp-note-actions button, .gp-note-close { min-height: 44px; padding: 0 16px; border-radius: 12px; border: 0; font: 600 14px system-ui, sans-serif; cursor: pointer; }
.gp-note-send { background: #fff; color: #111; }
.gp-note-send:disabled { opacity: .5; cursor: default; }
.gp-note-close { width: 44px; padding: 0; display: grid; place-items: center; background: transparent; color: #fff; }
.gp-note-done { text-align: center; padding: 8px 0; }
.gp-rooms { position: absolute; z-index: 6; right: max(10px, var(--mobius-safe-right, 0px)); bottom: max(10px, var(--mobius-safe-bottom, 0px)); width: min(440px, calc(100% - 20px)); height: min(76vh, 640px); display: flex; flex-direction: column; border-radius: 18px; overflow: hidden; background: #171a2e; border: 1px solid rgba(255,255,255,.16); box-shadow: 0 14px 50px rgba(0,0,0,.55); }
.gp-rooms header { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 12px 10px 16px; color: #fff; font: 600 14px system-ui, sans-serif; border-bottom: 1px solid rgba(255,255,255,.1); }
.gp-rooms header button { min-height: 36px; padding: 0 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,.22); background: transparent; color: #fff; font: 600 13px system-ui, sans-serif; cursor: pointer; }
.gp-rooms-chat { flex: 1 1 0; min-height: 0; position: relative; overflow: hidden; border-top: 1px solid rgba(255,255,255,.1); }
.gp-rooms-chat > * { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
.gp-rooms-status { padding: 12px 16px 14px; color: #dfe3ff; font: 14px/1.45 system-ui, sans-serif; }
.gp-rooms-status p { margin: 0 0 6px; }
.gp-rooms-status small { color: rgba(223,227,255,.6); font-size: 12px; }
.gp-rooms-status.gp-failed p { color: #ffb9b9; }
.gp-rooms-status button { margin-top: 8px; min-height: 40px; padding: 0 16px; border-radius: 999px; border: 0; background: #fff; color: #111; font: 600 13px system-ui, sans-serif; cursor: pointer; }
.gp-bar-ind { height: 4px; border-radius: 2px; background: rgba(255,255,255,.14); overflow: hidden; margin-bottom: 10px; }
.gp-bar-ind i { display: block; height: 100%; width: 40%; border-radius: 2px; background: linear-gradient(90deg, #7b5cff, #c9b8ff); animation: gp-slide 1.5s ease-in-out infinite; }
@keyframes gp-slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(260%); } }
.gp-rooms-pill { position: absolute; z-index: 6; left: 50%; bottom: max(14px, var(--mobius-safe-bottom, 0px)); transform: translateX(-50%); display: inline-flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 18px; border-radius: 999px; border: 1px solid rgba(255,255,255,.2); background: rgba(23,26,46,.92); color: #fff; font: 600 14px system-ui, sans-serif; cursor: pointer; box-shadow: 0 8px 30px rgba(0,0,0,.4); }
.gp-spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; animation: gp-rot 0.9s linear infinite; }
@keyframes gp-rot { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .gp-bar-ind i, .gp-spin { animation-duration: 3s; } }
.gp-loading { position: absolute; inset: 0; display: grid; place-items: center; color: rgba(255,255,255,.7); font: 600 15px system-ui, sans-serif; }
`

const store = () => window.mobius?.storage
// The room builder is a creative, tool-using agent: the same model Game Studio's own chat uses.
const ROOM_MODEL = 'claude-opus-5-5'

export default function GameApp({ appId }) {
  const frameRef = useRef(null)
  const savesRef = useRef(null)
  const motionRef = useRef(null)
  const voiceRef = useRef(null)
  voiceRef.current ||= createVoice()
  const [ready, setReady] = useState(false)
  const [runKey, setRunKey] = useState(0)
  const [error, setError] = useState(null)
  // A visitor on a public link can't read the game's private saves; the owner can.
  const [visitor, setVisitor] = useState(false)
  const visitorRef = useRef(false)
  visitorRef.current = visitor
  const [noteOpen, setNoteOpen] = useState(false)
  const startedRef = useRef(Date.now())

  // Gallery rooms made by an agent: the game asks (studio.requestRoom), this host starts an app chat for the
  // room builder, shows it in a panel, and hands each recipe the builder writes (public/room-<id>.json) back to the game.
  const [roomChat, setRoomChat] = useState(null) // { roomId, name, chatId?, phase: 'starting' | 'working' | 'done' | 'failed', note, startedAt }
  const lastRequest = useRef(null)
  const [, setTick] = useState(0)
  const [panelHidden, setPanelHidden] = useState(false)
  const builds = useRef(new Map())
  const chatsRef = useRef({})
  const chatMountRef = useRef(null)
  const safeId = (id) => String(id || '').replace(/[^a-z0-9_-]/gi, '').slice(0, 60)
  const toGame = (room) => frameRef.current?.contentWindow?.postMessage({ type: 'studio:room', room }, '*')
  async function pollRoom(id) {
    const b = builds.current.get(id)
    if (!b) return
    try {
      const spec = await store()?.get(`public/room-${safeId(id)}.json`)
      if (spec && typeof spec === 'object' && spec.rev !== b.rev) {
        b.rev = spec.rev; toGame({ roomId: id, spec })
        setRoomChat((c) => (c && c.roomId === id && c.phase !== 'done' ? { ...c, phase: 'working', note: 'The first version is in your gallery. Refining it…' } : c))
      }
    } catch { /* try again on the next tick */ }
  }
  function watchRoom(id, extra = {}) {
    const prev = builds.current.get(id)
    if (prev?.timer) clearInterval(prev.timer)
    const b = { ...prev, ...extra, until: Date.now() + 25 * 60 * 1000 }
    b.timer = setInterval(() => { if (Date.now() > b.until) clearInterval(b.timer); else pollRoom(id) }, 4000)
    builds.current.set(id, b)
  }
  async function startRoomBuild(req) {
    if (visitorRef.current) return
    const id = safeId(req.id)
    if (!id) return
    const known = chatsRef.current[id]
    // A build the page lost track of (closed mid-way, or the chat never started): pick the chat up again, or start over.
    if (req.mode === 'resume') {
      if (builds.current.has(id)) return
      if (known?.chatId) { watchRoom(id); setRoomChat({ roomId: id, name: known.name, chatId: known.chatId, phase: 'working', note: 'Picking up where the builder left off…', startedAt: Date.now() }); setPanelHidden(true); return }
      if (!req.vibe) return
      req = { ...req, mode: 'create' }
    }
    lastRequest.current = req
    const name = String(req.name || '').slice(0, 40), vibe = String(req.vibe || '').slice(0, 700)
    const label = name || vibe.slice(0, 32)
    // Show something right away: the game and this panel both say the builder is starting.
    setPanelHidden(false)
    setRoomChat({ roomId: id, name: label, phase: 'starting', note: 'Waking the room builder…', startedAt: Date.now() })
    toGame({ roomId: id, status: 'working', note: 'Waking the room builder…' })
    const path = `public/room-${id}.json`
    try {
      let baseRev
      if (req.mode === 'reshape') baseRev = (await store()?.get(path))?.rev
      else await Promise.resolve(store()?.remove(path)).catch(() => {})
      if (!window.mobius?.chat?.start) throw new Error('this app has no access to the room builder')
      const draft = `Build a room for my Dream Gallery.\n\nThe vibe I want: “${vibe}”\n${name ? `Its name: ${name}` : 'Give it a fitting name.'}\n${req.mode === 'reshape' ? 'This room already exists: change it the way I describe and keep everything I did not mention.\n' : ''}\nYou are the gallery's room builder. Be quick: I am watching a progress bar. Read /data/apps/game-studio/GALLERY_ROOMS.md first (the recipe format and your tools), pick the closest starter with gallery_room.py, and adapt it heavily to my vibe. The gallery app id is ${appId} and this room's id is ${id}.${req.mode === 'reshape' ? ` Start from the current recipe: python3 /data/apps/game-studio/gallery_room.py show ${appId} ${id}` : ''}\nWrite the whole recipe as a JSON file in one go, then run it once with:\npython3 /data/apps/game-studio/gallery_room.py put ${appId} ${id} recipe.json --preview\nThat puts the room in my gallery (it shows up live) and renders screenshots: Read them, fix only what is clearly wrong with one more put, then stop. When you are done, reply with one or two friendly sentences about the room.`
      const { chatId } = await window.mobius.chat.start({ title: `Room: ${label}`, draft, model: ROOM_MODEL })
      chatsRef.current = { ...chatsRef.current, [id]: { chatId, name: label } }
      Promise.resolve(store()?.set('room-chats.json', chatsRef.current)).catch(() => {})
      watchRoom(id, { rev: baseRev })
      setRoomChat((c) => ({ ...(c || {}), roomId: id, name: label, chatId, phase: 'working', note: 'The builder is designing your room. A first version usually appears within a minute or two.' }))
      toGame({ roomId: id, status: 'working', note: 'The builder is designing your room…' })
    } catch (err) {
      const message = 'Couldn’t reach the room builder: ' + (err?.message || 'unknown error')
      setRoomChat((c) => ({ ...(c || {}), roomId: id, name: label, phase: 'failed', note: message }))
      toGame({ roomId: id, status: 'failed', error: message })
    }
  }
  // The builder finished its turn: say so, and fetch the last recipe it wrote.
  function roomTurnDone(id) {
    pollRoom(id)
    setRoomChat((c) => (c && c.roomId === id && c.phase !== 'failed' ? { ...c, phase: 'done', note: 'Your room is ready. You can keep chatting here to change it.' } : c))
    toGame({ roomId: id, status: 'done' })
  }
  useEffect(() => {
    if (!roomChat || roomChat.phase === 'done' || roomChat.phase === 'failed') return undefined
    const t = setInterval(() => {
      setTick((n) => n + 1)
      // Nothing from the builder after a long wait: don't leave the visitor guessing.
      if (roomChat.phase === 'starting' && Date.now() - roomChat.startedAt > 45000) setRoomChat((c) => (c && c.phase === 'starting' ? { ...c, phase: 'failed', note: 'The room builder did not start. Check your connection and try again.' } : c))
    }, 1000)
    return () => clearInterval(t)
  }, [roomChat?.phase, roomChat?.roomId])
  useEffect(() => {
    const mount = chatMountRef.current
    if (!roomChat?.chatId || !mount || !window.mobius?.chat) return undefined
    let handle, disposed = false
    window.mobius.chat({ chatId: roomChat.chatId, mount, picker: false, onTurnDone: () => roomTurnDone(roomChat.roomId) })
      .then((h) => { if (disposed) h.destroy(); else handle = h }).catch(() => {})
    return () => { disposed = true; handle?.destroy() }
  }, [roomChat?.chatId])
  useEffect(() => () => builds.current.forEach((b) => b.timer && clearInterval(b.timer)), [])

  // Saves (best score, progress) belong to this app. The owner's first launch
  // starts from whatever the game had saved in the studio. A visitor on a
  // shared link always starts a fresh game: none of the owner's progress, and
  // their own lasts while this page is open (they cannot write the app's saves).
  useEffect(() => {
    let alive = true
    voiceRef.current.setMode(GAME.voiceMode === 'mobius' ? 'mobius' : 'browser')
    Promise.resolve(store()?.get('room-chats.json')).then((v) => { chatsRef.current = v || {} }).catch(() => {})
    store()?.get('saves.json')
      .then((saved) => { savesRef.current = saved || GAME.initialSaves || {} })
      .catch(() => { savesRef.current = {}; if (alive) setVisitor(true) })
      .finally(() => { if (alive) setReady(true) })
    return () => { alive = false }
  }, [])

  // Games want the whole screen.
  useEffect(() => {
    const post = (value) => window.parent.postMessage({ type: 'moebius:immersive', value, appId }, '*')
    post(true)
    return () => post(false)
  }, [appId])

  const srcDoc = useMemo(() => (ready
    ? buildGameDocument(GAME.html, { sprites: DATA.sprites, sounds: DATA.sounds, models: DATA.models, art: DATA.art, saves: savesRef.current })
    : null), [ready, runKey])

  // Leaving the game (the shell keeps it loaded, hidden) silences and freezes it.
  const visibilityRef = useRef(null)
  useEffect(() => {
    const relay = relayVisibility(() => frameRef.current, (visible) => { if (!visible) voiceRef.current?.stop() })
    visibilityRef.current = relay
    return relay.stop
  }, [])

  useEffect(() => {
    const onMessage = (event) => {
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return
      const msg = event.data || {}
      if (msg.type === 'studio:error') {
        setError(String(msg.message || 'Something went wrong'))
      } else if (msg.type === 'studio:save' && typeof msg.key === 'string') {
        savesRef.current = { ...savesRef.current, [msg.key]: msg.value }
        if (!visitorRef.current) store()?.set('saves.json', savesRef.current).catch(() => {})
      } else if (msg.type === 'studio:room-request') {
        startRoomBuild(msg)
      } else if (msg.type === 'studio:room-chat') {
        const c = chatsRef.current[safeId(msg.id)]
        if (c) { setPanelHidden(false); setRoomChat((cur) => (cur && cur.roomId === safeId(msg.id) ? cur : { roomId: safeId(msg.id), chatId: c.chatId, name: c.name, phase: 'done', note: 'You can keep chatting here to change the room.', startedAt: Date.now() })) }
      } else if (msg.type === 'studio:public-read') {
        const path = `public/${String(msg.key || '').replace(/[^a-z0-9_-]/gi, '').slice(0, 64)}.json`
        const reply = (value) => frameRef.current?.contentWindow?.postMessage({ type: 'studio:public-result', id: msg.id, value, visitor: visitorRef.current }, '*')
        Promise.resolve(store()?.get(path)).then((value) => reply(value ?? null), () => reply(null))
      } else if (msg.type === 'studio:public-write') {
        const path = `public/${String(msg.key || '').replace(/[^a-z0-9_-]/gi, '').slice(0, 64)}.json`
        if (!visitorRef.current) (msg.value === null ? store()?.remove(path) : store()?.set(path, msg.value))?.catch?.(() => {})
      } else if (msg.type === 'studio:tilt-start') {
        startTilt()
      } else if (msg.type === 'studio:say') {
        const reply = (err) => frameRef.current?.contentWindow?.postMessage({ type: 'studio:say-done', id: msg.id, error: err }, '*')
        voiceRef.current.say(msg.text, { voice: msg.voice, pitch: msg.pitch, rate: msg.rate, lang: msg.lang })
          .then(() => reply(), (err) => reply(String(err?.message || err)))
      } else if (msg.type === 'studio:say-stop') {
        voiceRef.current.stop()
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  function startTilt() {
    const caps = window.mobius?.capabilities
    if (motionRef.current || !caps?.available?.('device.motion', 1)) return
    const session = caps.open('device.motion', { rateHz: 30 })
    motionRef.current = session
    session.on('sample', ({ orientation, screenAngle }) => {
      if (!orientation || orientation.gamma == null) return
      let x = orientation.gamma / 35
      let y = (orientation.beta - 40) / 35
      if (screenAngle === 90) [x, y] = [y, -x]
      else if (screenAngle === 270 || screenAngle === -90) [x, y] = [-y, x]
      frameRef.current?.contentWindow?.postMessage({ type: 'studio:tilt', x, y }, '*')
    })
    const clear = () => { motionRef.current = null }
    session.ready?.catch(clear)
    session.result?.then(clear, clear)
  }
  useEffect(() => () => { motionRef.current?.finish?.(); motionRef.current = null; voiceRef.current?.stop() }, [runKey])

  const restart = () => { setError(null); setRunKey((k) => k + 1) }
  const edit = () => window.parent.postMessage({ type: 'moebius:open-app', appId: GAME.studioAppId, intent: `game:${GAME.id}` }, '*')

  return (
    <div className="gp-root">
      <style>{CSS}</style>
      <header className="gp-bar">
        <h1>{GAME.name}</h1>
        <button type="button" className="gp-note-open" onClick={() => setNoteOpen(true)}><Comment aria-hidden="true" />Note</button>
        {GAME.studioAppId && !visitor && (
          <button type="button" className="gp-edit" onClick={edit} aria-label={`Edit ${GAME.name} in Game Studio`}>
            <EditPencil aria-hidden="true" />Edit
          </button>
        )}
      </header>
      <main className="gp-stage">
        {srcDoc ? (
          <iframe
            key={runKey}
            ref={frameRef}
            title={GAME.name}
            sandbox="allow-scripts allow-pointer-lock"
            allow="fullscreen *; gamepad *; autoplay *"
            srcDoc={srcDoc}
            onLoad={() => { visibilityRef.current?.sync(); frameRef.current?.contentWindow?.focus() }}
          />
        ) : <div className="gp-loading">Loading {GAME.name}…</div>}
      </main>
      {roomChat && (
        <aside className="gp-rooms" aria-label="Room builder" style={panelHidden ? { display: 'none' } : undefined}>
          <header>
            <span className="gp-rooms-title">{roomChat.phase === 'done' ? 'Room ready: ' : roomChat.phase === 'failed' ? 'Couldn’t build: ' : 'Building '}“{roomChat.name}”</span>
            <button type="button" onClick={() => { setPanelHidden(true); frameRef.current?.contentWindow?.focus() }}>Hide</button>
          </header>
          <div className={`gp-rooms-status gp-${roomChat.phase}`} role="status">
            {(roomChat.phase === 'starting' || roomChat.phase === 'working') && <div className="gp-bar-ind" aria-hidden="true"><i /></div>}
            <p>{roomChat.note}</p>
            {(roomChat.phase === 'starting' || roomChat.phase === 'working') && <small>{Math.floor((Date.now() - roomChat.startedAt) / 60000)}:{String(Math.floor(((Date.now() - roomChat.startedAt) / 1000) % 60)).padStart(2, '0')} · rooms usually take two to four minutes</small>}
            {roomChat.phase === 'failed' && lastRequest.current && <button type="button" onClick={() => startRoomBuild({ ...lastRequest.current })}>Try again</button>}
          </div>
          {roomChat.chatId && <div className="gp-rooms-chat" ref={chatMountRef} />}
        </aside>
      )}
      {roomChat && panelHidden && (roomChat.phase === 'starting' || roomChat.phase === 'working') && (
        <button type="button" className="gp-rooms-pill" onClick={() => setPanelHidden(false)}><span className="gp-spin" aria-hidden="true" />Building “{roomChat.name}”…</button>
      )}
      {noteOpen && <NoteSheet startedAt={startedRef.current} onClose={() => { setNoteOpen(false); frameRef.current?.contentWindow?.focus() }} />}
      {error && (
        <div className="gp-toast" role="alert">
          <p>The game hit a problem: {error.slice(0, 140)}</p>
          <button type="button" onClick={restart}>Restart</button>
          {GAME.studioAppId && !visitor && <button type="button" onClick={edit}>Fix in studio</button>}
        </div>
      )}
    </div>
  )
}

// A playtest note for the maker. Notes go to the game's private inbox
// (public/notes/), which public visitors may add to but never read; Game Studio
// collects them for the owner.
function NoteSheet({ startedAt, onClose }) {
  const [text, setText] = useState('')
  const [name, setName] = useState('')
  const [state, setState] = useState('idle')
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])
  const send = async (event) => {
    event.preventDefault()
    if (!text.trim()) return
    setState('sending')
    const at = new Date().toISOString()
    const id = `${at.replace(/[^0-9]/g, '').slice(0, 14)}-${Math.random().toString(36).slice(2, 8)}`
    try {
      await store().set(`public/notes/${id}.json`, {
        text: text.trim().slice(0, 1000), name: name.trim().slice(0, 40) || null, at,
        playedSeconds: Math.round((Date.now() - startedAt) / 1000),
      })
      setState('sent')
    } catch {
      setState('failed')
    }
  }
  return (
    <div className="gp-note-scrim" onClick={onClose}>
      <form className="gp-note" role="dialog" aria-modal="true" aria-labelledby="gp-note-title" onClick={(event) => event.stopPropagation()} onSubmit={send}>
        <header>
          <h2 id="gp-note-title">Note for the maker</h2>
          <button type="button" className="gp-note-close" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></button>
        </header>
        {state === 'sent' ? (
          <>
            <p className="gp-note-done">Thanks! Your note is on its way.</p>
            <div className="gp-note-actions"><button type="button" className="gp-note-send" onClick={onClose}>Back to the game</button></div>
          </>
        ) : (
          <>
            <p>What was fun, what was confusing, what would you change? Only the game's maker sees this.</p>
            <textarea autoFocus value={text} maxLength={1000} onChange={(event) => setText(event.target.value)} aria-label="Your note" placeholder="The second jump felt too hard…" />
            <input value={name} maxLength={40} onChange={(event) => setName(event.target.value)} aria-label="Your name (optional)" placeholder="Your name (optional)" />
            {state === 'failed' && <p role="alert">That didn't send. Check your connection and try again.</p>}
            <div className="gp-note-actions">
              <button type="submit" className="gp-note-send" disabled={!text.trim() || state === 'sending'}>{state === 'sending' ? 'Sending…' : 'Send note'}</button>
            </div>
          </>
        )}
      </form>
    </div>
  )
}
