// Another studio game opened from inside a scene game (an object with "launch",
// or api.openGame): it plays full screen over the scene until the person closes it.
// The game is built exactly as the studio builds it: its page, art, saves and the
// shared library models.
import React, { useEffect, useRef, useState } from 'react'
import { X } from '@openai/apps-sdk-ui/components/Icon'
import { buildGameDocument, mergeArt, relayVisibility, withLibrary } from './gameRuntime.js'
import { loadEngine } from './engine.js'

const store = () => window.mobius?.storage
const readEngineFile = (path) => store().getText(path)

export default function LaunchedGame({ gameId, assets, models, onClose }) {
  const [doc, setDoc] = useState(null)
  const [error, setError] = useState('')
  const frameRef = useRef(null)
  const savesRef = useRef({})

  useEffect(() => {
    let alive = true
    const load = async () => {
      const [html, meta, own, saves] = await Promise.all([
        store().getText(`games/${gameId}.html`).catch(() => null),
        store().get(`games/${gameId}.json`).catch(() => null),
        store().get(`games/${gameId}.art.json`).catch(() => null),
        store().get(`games/${gameId}.saves.json`).catch(() => null),
      ])
      if (!alive) return
      if (!html) { setError('That game could not be found.'); return }
      const kit = meta?.art ? await store().get(`art/${meta.art}.json`).catch(() => null) : null
      savesRef.current = saves || {}
      const engine = await loadEngine(html, readEngineFile)
      if (alive) {
        setDoc(buildGameDocument(html, {
          sprites: assets.sprites, sounds: assets.sounds, models, art: withLibrary(mergeArt(kit, own), assets), saves: savesRef.current, engine,
        }))
      }
    }
    load()
    return () => { alive = false }
  }, [gameId])

  const visibilityRef = useRef(null)
  useEffect(() => { const relay = relayVisibility(() => frameRef.current); visibilityRef.current = relay; return relay.stop }, [])

  // The launched game keeps its own saves (best times, unlocks).
  useEffect(() => {
    const onMessage = (event) => {
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return
      const msg = event.data || {}
      if (msg.type === 'studio:save' && typeof msg.key === 'string') {
        savesRef.current = { ...savesRef.current, [msg.key]: msg.value }
        store().set(`games/${gameId}.saves.json`, savesRef.current).catch(() => {})
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [gameId])

  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="gs-launched" role="dialog" aria-label="Game">
      {doc ? (
        <iframe ref={frameRef} title="Game" sandbox="allow-scripts allow-pointer-lock" allow="fullscreen *; gamepad *; autoplay *" srcDoc={doc}
          onLoad={() => { visibilityRef.current?.sync(); frameRef.current?.contentWindow?.focus() }} />
      ) : (
        <div className="gs-launched-wait">{error || 'Loading…'}</div>
      )}
      <button type="button" className="gs-launched-close" aria-label="Back to the world" onClick={onClose}><X aria-hidden="true" /></button>
    </div>
  )
}
