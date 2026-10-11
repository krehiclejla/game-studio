// Local copies of the engine libraries games import from esm.sh (three.js and its
// add-ons, Phaser, physics, particles, ZzFX), built by build_engine.mjs into the
// studio's storage under engine/. A game page that gets them starts without a
// single request to the web; a library not in the set still loads from esm.sh,
// and a studio whose engine/ folder is missing just plays the old way.
import { useEffect, useState } from 'react'

const ZZFX = 'https://esm.sh/zzfx@1.3.2' // the studio helper loads it for every game
const THREE = 'https://esm.sh/three@0.180.0'

let indexPromise = null
const codes = new Map()

const readIndex = (readText) => {
  indexPromise ||= readText('engine/index.json').then((t) => JSON.parse(t)).catch(() => { indexPromise = null; return {} })
  return indexPromise
}

// The engine modules a page needs, as { url: code }. Never rejects: anything it
// cannot read is left out and loads from the web instead.
export async function loadEngine(html, readText) {
  const index = await readIndex(readText)
  const text = String(html || '')
  const wanted = Object.keys(index).filter((url) => url === ZZFX || text.includes(url))
  if (wanted.some((url) => url !== ZZFX && url !== THREE) && index[THREE]) wanted.push(THREE) // add-ons import three by its public URL
  const found = {}
  await Promise.all([...new Set(wanted)].map(async (url) => {
    if (!codes.has(url)) {
      try { codes.set(url, await readText(`engine/${index[url]}`)) } catch { return }
    }
    found[url] = codes.get(url)
  }))
  return found
}

// { ready, engine } for a page's HTML. Not ready until the library has been read
// (or found missing), so a game never starts once from the web and again locally.
export function useEngine(html, readText) {
  const [state, setState] = useState({ html: null, engine: {} })
  useEffect(() => {
    if (!html) return undefined
    let alive = true
    loadEngine(html, readText).then((engine) => { if (alive) setState({ html, engine }) })
    return () => { alive = false }
  }, [html, readText])
  return { ready: Boolean(html) && state.html === html, engine: state.engine }
}
