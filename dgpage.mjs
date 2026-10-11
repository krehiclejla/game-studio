import { writeFileSync, mkdirSync } from 'node:fs'
import { buildGameDocument, mergeArt, withLibrary } from './gameRuntime.js'
const [appId, gameId, out] = process.argv.slice(2)
const base = process.env.API_BASE_URL.replace(/\/$/, '')
const auth = { Authorization: `Bearer ${process.env.AGENT_TOKEN}` }
const get = async (p, k) => { const r = await fetch(`${base}/api/storage/apps/${appId}/${p}`, { headers: auth }); if (r.status === 404) return null; return k === 'json' ? r.json() : k === 'bytes' ? Buffer.from(await r.arrayBuffer()) : r.text() }
const html = await get(`games/${gameId}.html`)
const assets = (await get('assets.json', 'json')) || {}
const models = {}
for (const n of Object.keys(assets.models || {})) if (html.includes('"'+n+'"') || html.includes("'"+n+"'")) { const b = await get(`models/${n}.glb`, 'bytes'); if (b) models[n] = b.toString('base64') }
const saves = process.env.DG_SAVES ? JSON.parse(process.env.DG_SAVES) : (await get(`games/${gameId}.saves.json`, 'json')) || {}
mkdirSync(out, { recursive: true })
writeFileSync(`${out}/game.html`, buildGameDocument(html, { sprites: {}, sounds: {}, saves, models, art: withLibrary(mergeArt(null, null), assets) }))
console.log('models', Object.keys(models).join(','))
