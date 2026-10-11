import React, { useRef, useState } from 'react'
import { Check, ImageSquare, Music, Play, Plus, Reload, Shuffle, SoundOnReadOutLoudSpeaker, Pause, Sparkles, Trash, UploadDocuments } from '@openai/apps-sdk-ui/components/Icon'
import { imageFileToDataUrl } from './sprites.js'
import { assetAgentPrompt, autoAssetDraft, guestAssetDraft } from './assetPrompt.js'
import { cleanName, nameFrom, uniqueName, useAiJobs } from './aiJobs.js'
import { JobList } from './libraryUi.jsx'
import { SOUND_PRESETS, playSound, varySound } from './sounds.js'
import { VOICE_PRESETS } from './voice.js'
import { readModel } from './ModelView.jsx'

// Sound files in the Assets tab (assets.json "audio", bytes at audio/<name>.mp3):
// one preview plays at a time; pressing it again stops it.
let preview = { ctx: null, src: null, name: null }
async function togglePreview(name, onChange) {
  const stop = () => { try { preview.src?.stop() } catch {} preview.src = null; preview.name = null; onChange(null) }
  if (preview.name === name) return stop()
  if (preview.src) stop()
  preview.ctx = preview.ctx || new AudioContext()
  preview.ctx.resume?.()
  preview.name = name
  onChange(name)
  try {
    const blob = await readModel(`audio/${name}.mp3`)
    if (!blob || preview.name !== name) return
    const buffer = await preview.ctx.decodeAudioData(await blob.arrayBuffer())
    if (preview.name !== name) return
    const src = preview.ctx.createBufferSource()
    src.buffer = buffer
    src.connect(preview.ctx.destination)
    src.onended = () => { if (preview.src === src) { preview.src = null; preview.name = null; onChange(null) } }
    preview.src = src
    src.start()
  } catch {
    if (preview.name === name) { preview.name = null; onChange(null) }
  }
}
const byLine = (credit) => (String(credit || '').match(/ by ([^(,]+)/) || [])[1]?.trim() || ''


function AiMaker({ appId, assets, onDelete, onUploadSave, onRefresh, onUse, guest = false }) {
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const fileRef = useRef(null)
  const { jobs, start, dismiss } = useAiJobs('asset-jobs.json', assets, onRefresh)

  const make = async (override) => {
    const text = (override?.description ?? description).trim()
    if (text.length < 3) return setError('Describe what you need, for example "a mossy oak tree" or "a laser sound".')
    if (!window.mobius?.chat?.start) return setError('The AI artist is not available here.')
    setError('')
    const taken = new Set([...Object.keys(assets.sprites || {}), ...Object.keys(assets.sounds || {}), ...Object.keys(assets.audio || {})])
    const name = override?.name || uniqueName(nameFrom(text) || 'asset', taken)
    setDescription('')
    await start({
      group: 'auto', name, description: text,
      title: `Make ${name}`, systemPrompt: assetAgentPrompt(appId),
      // A guest's request goes to their own assistant, which uses the studio's
      // free tools in its workspace (see the project's .studio/GUIDE.md).
      draft: guest ? guestAssetDraft({ name, description: text }) : autoAssetDraft({ name, description: text }),
    })
  }
  const upload = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const draft = await imageFileToDataUrl(file)
      onUploadSave(cleanName(file.name.replace(/\.[^.]+$/, '')) || 'picture', draft)
    } catch (err) {
      setError(err.message)
    }
  }
  const [playing, setPlaying] = useState(null)
  const sprites = Object.entries(assets.sprites || {})
  const sounds = Object.entries(assets.sounds || {})
  const audio = Object.entries(assets.audio || {})
  const models3d = Object.entries(assets.models || {}).filter(([k, m]) => !assets.characters?.[k] && m.thumb)

  return (
    <section className="gs-card" aria-labelledby="gs-ai-title">
      <div className="gs-card-head">
        <h3 id="gs-ai-title">Your assets</h3>
      </div>
      <div className="gs-create">
        <label className="gs-visually-hidden" htmlFor="gs-asset-desc">Describe an asset</label>
        <textarea id="gs-asset-desc" rows={2} value={description} maxLength={400}
          placeholder="Describe anything… e.g. an oak tree, a sunset sky, footsteps on gravel, calm forest music"
          onChange={(e) => { setDescription(e.target.value); setError('') }} />
        <div className="gs-create-row">
          <button type="button" className="gs-btn gs-btn--small" onClick={() => fileRef.current?.click()}><UploadDocuments aria-hidden="true" />Add a picture</button>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} />
          <button type="button" className="gs-btn gs-btn--primary gs-create-go" onClick={() => make()}><Sparkles aria-hidden="true" />Create</button>
        </div>
        {error && <p className="gs-error" role="alert">{error}</p>}
        <p className="gs-hint gs-hint--tight">Objects become 3D models; skies, ground, sounds and music too (real recordings, free to use). About a minute or two each. Use them in any of your games.</p>
      </div>
      <JobList jobs={jobs} onRetry={(job) => { dismiss(job); make({ description: job.description, name: job.name }) }} onDismiss={dismiss} verb="is being made…" />
      {sprites.length || sounds.length || audio.length || models3d.length ? (
        <ul className="gs-library" aria-label="Saved assets">
          {models3d.map(([key, m]) => (
            <li key={`m-${key}`} className="gs-asset">
              <img src={m.thumb} alt="" />
              <span>{key} <small className="gs-tag">3D</small></span>
              <div className="gs-asset-actions">
                <button type="button" className="gs-btn gs-btn--small gs-use" aria-label={`Use ${key} in the game`} onClick={() => onUse({ text: `Use my 3D asset "${key}" in the game.` })}>Use</button>
                <button type="button" className="gs-icon-btn" aria-label={`Delete ${key}`} onClick={() => onDelete('models', key)}><Trash aria-hidden="true" /></button>
              </div>
            </li>
          ))}
          {sprites.map(([key, sprite]) => (
            <li key={key} className="gs-asset">
              <img src={sprite.dataUrl} alt="" className={sprite.pixel || !sprite.ai ? 'is-pixel' : ''} />
              <span>{key}</span>
              <div className="gs-asset-actions">
                <button type="button" className="gs-btn gs-btn--small gs-use" aria-label={`Use ${key} in the game`} onClick={() => onUse({ text: `Use my asset "${key}" in the game.` })}>Use</button>
                <button type="button" className="gs-icon-btn" aria-label={`Delete ${key}`} onClick={() => onDelete('sprites', key)}><Trash aria-hidden="true" /></button>
              </div>
            </li>
          ))}
          {audio.map(([key, a]) => (
            <li key={`a-${key}`} className="gs-asset gs-asset--sound-tile" title={a.credit || undefined}>
              <button type="button" className="gs-sound-play" aria-pressed={playing === key}
                aria-label={`${playing === key ? 'Stop' : 'Play'} ${a.kind === 'music' ? 'music' : 'sound'} ${key}`}
                onClick={() => togglePreview(key, setPlaying)}>
                {playing === key ? <Pause aria-hidden="true" /> : a.kind === 'music' ? <Music aria-hidden="true" /> : <SoundOnReadOutLoudSpeaker aria-hidden="true" />}
              </button>
              <span>{key} <small className="gs-tag">{a.kind === 'music' ? 'Music' : 'Sound'}</small>{byLine(a.credit) && <small className="gs-credit">by {byLine(a.credit)}</small>}</span>
              <div className="gs-asset-actions">
                <button type="button" className="gs-btn gs-btn--small gs-use" aria-label={`Use ${key} in the game`}
                  onClick={() => onUse({ text: a.kind === 'music' ? `Play my music "${key}" in the game.` : `Use my sound "${key}" in the game.` })}>Use</button>
                <button type="button" className="gs-icon-btn" aria-label={`Delete ${key}`} onClick={() => onDelete('audio', key)}><Trash aria-hidden="true" /></button>
              </div>
            </li>
          ))}
          {sounds.map(([key, params]) => (
            <li key={`s-${key}`} className="gs-asset gs-asset--sound-tile">
              <button type="button" className="gs-sound-play" aria-label={`Play sound ${key}`} onClick={() => playSound(params)}><SoundOnReadOutLoudSpeaker aria-hidden="true" /></button>
              <span>{key}</span>
              <div className="gs-asset-actions">
                <button type="button" className="gs-btn gs-btn--small gs-use" aria-label={`Use ${key} in the game`} onClick={() => onUse({ text: `Use my sound "${key}" in the game.` })}>Use</button>
                <button type="button" className="gs-icon-btn" aria-label={`Delete ${key}`} onClick={() => onDelete('sounds', key)}><Trash aria-hidden="true" /></button>
              </div>
            </li>
          ))}
        </ul>
      ) : !jobs.length ? <p className="gs-hint">Nothing yet. Describe something above.</p> : null}
    </section>
  )
}

function SoundMaker({ assets, onSave, onDelete }) {
  const [preset, setPreset] = useState('coin')
  const [params, setParams] = useState(SOUND_PRESETS.coin)
  const [name, setName] = useState('coin')
  const choose = (key) => {
    setPreset(key)
    setName(key)
    setParams(SOUND_PRESETS[key])
    playSound(SOUND_PRESETS[key])
  }
  const vary = () => {
    const next = varySound(SOUND_PRESETS[preset])
    setParams(next)
    playSound(next)
  }
  const sounds = Object.entries(assets.sounds || {})
  return (
    <section className="gs-card" aria-labelledby="gs-sounds-title">
      <div className="gs-card-head">
        <Music aria-hidden="true" />
        <h3 id="gs-sounds-title">Sounds</h3>
      </div>
      <div className="gs-chips" role="group" aria-label="Sound type">
        {Object.keys(SOUND_PRESETS).map((key) => (
          <button key={key} type="button" className="gs-chip" aria-pressed={preset === key} onClick={() => choose(key)}>{key}</button>
        ))}
      </div>
      <div className="gs-maker-controls gs-maker-controls--row">
        <button type="button" className="gs-btn" onClick={() => playSound(params)}><Play aria-hidden="true" />Play</button>
        <button type="button" className="gs-btn" onClick={vary}><Shuffle aria-hidden="true" />Vary it</button>
        <label className="gs-field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={32} autoCapitalize="none" spellCheck={false} />
        </label>
        <button type="button" className="gs-btn gs-btn--primary" onClick={() => { const key = cleanName(name); if (key) onSave(key, params) }}>Save sound</button>
      </div>
      {sounds.length > 0 ? (
        <ul className="gs-library gs-library--sounds" aria-label="Saved sounds">
          {sounds.map(([key, value]) => (
            <li key={key} className="gs-asset gs-asset--sound">
              <button type="button" className="gs-icon-btn" aria-label={`Play sound ${key}`} onClick={() => playSound(value)}><Play aria-hidden="true" /></button>
              <span>{key}</span>
              <button type="button" className="gs-icon-btn" aria-label={`Delete sound ${key}`} onClick={() => onDelete('sounds', key)}><Trash aria-hidden="true" /></button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="gs-hint">Games play a saved sound by its name, like <b>coin</b> or <b>jump</b>.</p>
      )}
    </section>
  )
}

function ModelLibrary({ assets, models }) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const fileRef = useRef(null)
  // 3D characters live in the Characters tab; this card lists props and scenery.
  const owned = Object.fromEntries(Object.entries(assets.models || {}).filter(([name]) => !assets.characters?.[name]))
  const run = async (key, action) => {
    setBusy(key)
    setError('')
    try { await action() } catch (err) { setError(err?.message || 'That did not work. Try again.') } finally { setBusy('') }
  }
  const upload = (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const name = cleanName(file.name.replace(/\.[^.]+$/, '')) || 'model'
    run('upload', () => models.upload(file, name))
  }
  return (
    <section className="gs-card" aria-labelledby="gs-models-title">
      <div className="gs-card-head">
        <Sparkles aria-hidden="true" />
        <h3 id="gs-models-title">3D models</h3>
      </div>
      <ul className="gs-models" aria-label="Free models">
        {models.catalog.map((entry) => (
          <li key={entry.name} className="gs-model">
            <div>
              <strong>{entry.title} <span className="gs-tag">{entry.name}</span></strong>
              <span>{entry.description}</span>
              <small>{entry.credit}</small>
            </div>
            {owned[entry.name] ? (
              <span className="gs-added"><Check aria-hidden="true" />Added</span>
            ) : (
              <button type="button" className="gs-btn" disabled={!!busy} onClick={() => run(entry.name, () => models.addCatalog(entry))}>
                <Plus aria-hidden="true" />{busy === entry.name ? 'Adding…' : 'Add'}
              </button>
            )}
          </li>
        ))}
        {Object.entries(owned).filter(([name]) => !models.catalog.some((m) => m.name === name)).map(([name, info]) => (
          <li key={name} className="gs-model">
            <div>
              <strong>{info.title || name} <span className="gs-tag">{name}</span></strong>
              <small>{info.credit} · {Math.round((info.size || 0) / 1024)} KB</small>
            </div>
            <button type="button" className="gs-icon-btn" aria-label={`Delete model ${name}`} onClick={() => run(name, () => models.remove(name))}><Trash aria-hidden="true" /></button>
          </li>
        ))}
      </ul>
      <button type="button" className="gs-btn" disabled={!!busy} onClick={() => fileRef.current?.click()}>
        <UploadDocuments aria-hidden="true" />{busy === 'upload' ? 'Adding…' : 'Add your own .glb model'}
      </button>
      <input ref={fileRef} type="file" accept=".glb,model/gltf-binary" hidden onChange={upload} />
      {error && <p className="gs-error" role="alert">{error}</p>}
      <p className="gs-hint">3D games load a model by its name, for example <b>robot</b>. Models stay under 3 MB so games start fast on phones.</p>
    </section>
  )
}

function VoiceCard({ voice }) {
  const [character, setCharacter] = useState('narrator')
  const [line, setLine] = useState('Welcome, pilot. The galaxy needs you.')
  const [status, setStatus] = useState('')
  const test = async () => {
    setStatus('Speaking…')
    try {
      await voice.say(line, { voice: character })
      setStatus('')
    } catch (err) {
      setStatus(err?.message || 'This device could not speak that line.')
    }
  }
  return (
    <section className="gs-card" aria-labelledby="gs-voice-title">
      <div className="gs-card-head">
        <SoundOnReadOutLoudSpeaker aria-hidden="true" />
        <h3 id="gs-voice-title">Voice</h3>
      </div>
      <div className="gs-chips" role="radiogroup" aria-label="Voice engine">
        <button type="button" role="radio" className="gs-chip" aria-checked={voice.mode === 'browser'} aria-pressed={voice.mode === 'browser'} onClick={() => voice.setMode('browser')}>Quick voice</button>
        <button type="button" role="radio" className="gs-chip" aria-checked={voice.mode === 'mobius'} aria-pressed={voice.mode === 'mobius'} onClick={() => voice.setMode('mobius')}>Möbius voice</button>
      </div>
      <p className="gs-hint gs-hint--tight">{voice.mode === 'mobius'
        ? 'Natural neural voice that runs on this device. Download a voice once in Möbius Voice; until then games use the quick voice.'
        : "Instant, uses this device's built-in voices. Sound varies by phone and browser."}</p>
      <div className="gs-chips gs-chips--quiet" role="group" aria-label="Character">
        {Object.keys(VOICE_PRESETS).map((key) => (
          <button key={key} type="button" className="gs-chip" aria-pressed={character === key} onClick={() => setCharacter(key)}>{key}</button>
        ))}
      </div>
      <div className="gs-maker-controls gs-maker-controls--row">
        <label className="gs-field">
          <span>Line</span>
          <input value={line} onChange={(e) => setLine(e.target.value)} maxLength={200} />
        </label>
        <button type="button" className="gs-btn gs-btn--primary" onClick={test}><Play aria-hidden="true" />Say it</button>
      </div>
      {status && <p className="gs-hint" role="status">{status}</p>}
      <p className="gs-hint">Games speak with <b>studio.say('line', {'{'} voice: '{character}' {'}'})</b>. Ask the agent for "a narrator" or "talking characters": it makes the game's lines ahead of time with natural voices, so they sound the same on every device. This setting only covers lines a game makes up while playing.</p>
    </section>
  )
}

export default function AssetsPanel({ appId, assets, onChange, onRefresh, onUse, models, voice, guest = false }) {
  const saveSprite = (key, sprite) => onChange({ ...assets, sprites: { ...(assets.sprites || {}), [key]: sprite } })
  const saveSound = (key, params) => onChange({ ...assets, sounds: { ...(assets.sounds || {}), [key]: params } })
  const remove = (group, key) => {
    const next = { ...(assets[group] || {}) }
    delete next[key]
    onChange({ ...assets, [group]: next })
    // A sound file's bytes live beside assets.json.
    if (group === 'audio') window.mobius?.storage?.remove(`audio/${key}.mp3`).catch(() => {})
  }
  return (
    <div className="gs-assets gs-library-page">
      <AiMaker appId={appId} assets={assets} onUploadSave={saveSprite} onDelete={remove} onRefresh={onRefresh} onUse={onUse} guest={guest} />
      <details className="gs-more-tools">
        <summary>More tools</summary>
        <SoundMaker assets={assets} onSave={saveSound} onDelete={remove} />
        {models && <ModelLibrary assets={assets} models={models} />}
        {voice && <VoiceCard voice={voice} />}
      </details>
    </div>
  )
}
