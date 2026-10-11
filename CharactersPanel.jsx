// The Characters tab. A gallery of kept characters; new designs arrive as
// drafts the person Keeps, retries or changes. Tapping a character opens its
// page, where its own AI chat gives it a role, animations and new looks.
import React, { useEffect, useState } from 'react'
import { Plus, Reload, Sparkles, UploadDocuments, X } from '@openai/apps-sdk-ui/components/Icon'
import { CREATIVE_MODEL, CHARACTER_TYPES, designAgentPrompt, designDraft, pictureTo3dAgentPrompt, sourceDraft, sourcerAgentPrompt } from './assetPrompt.js'
import { readModel } from './ModelView.jsx'
import { cleanName, nameFrom, uniqueName, updateShared } from './aiJobs.js'
import { SheetPreview } from './libraryUi.jsx'
import CharacterPage from './CharacterPage.jsx'

const store = () => window.mobius?.storage
const JOBS_KEY = 'design-jobs.json'
const JOB_TIMEOUT_MS = 20 * 60 * 1000

const MAX_JOBS = 20

// The queue lives on the server (design_queue.py, run every minute and kicked
// on each change), so designs keep coming while the app is closed. This hook
// adds and removes jobs and shows progress; the server starts them.
function useDesignJobs(appId, token) {
  const [jobs, setJobs] = useState([])
  const [drafts, setDrafts] = useState({})
  const reload = () => store()?.getWithVersion(JOBS_KEY).then((r) => { if (Array.isArray(r?.value)) setJobs(r.value) }).catch(() => {})
  useEffect(() => {
    reload()
    // The server job builds each planned character's request with this prompt.
    store()?.set('design-prompts.json', { pictureTo3d: pictureTo3dAgentPrompt(appId) }).catch(() => {})
  }, [appId])
  const kick = () => fetch(`/api/apps/${appId}/run-job`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
  // Read-modify-write on the server's copy, so the server's own changes are never lost.
  const mutate = async (fn) => {
    const next = await updateShared(JOBS_KEY, (list) => fn(Array.isArray(list) ? list : []).slice(0, MAX_JOBS), [])
    setJobs(next)
    return next
  }

  const pending = jobs.filter((j) => !drafts[j.id] && !j.failed)
  const pendingKey = pending.map((j) => `${j.id}${j.queued ? 'q' : ''}`).join(',')
  useEffect(() => {
    if (!pendingKey) return undefined
    let alive = true
    const check = () => {
      reload()
      pending.filter((j) => !j.queued).forEach((j) => {
        store()?.getWithVersion(`character-drafts/${j.id}.json`).then((r) => {
          if (alive && r?.value?.dataUrl) setDrafts((d) => ({ ...d, [j.id]: r.value }))
        }).catch(() => {})
      })
    }
    check()
    const timer = setInterval(check, 5000)
    return () => { alive = false; clearInterval(timer) }
  }, [pendingKey])

  const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

  function request(job) {
    const { id, name, description, change, fromJob, source, dim, files, style } = job
    const hints = [job.body && `Body: ${job.body}`, job.build && `Build: ${job.build}`, job.weapon && `Weapon (make it as an asset and equip it; draw the body with --empty-hands): ${job.weapon}`, job.height && `Height: ${job.height} m`, job.role && `Role: ${job.role}`].filter(Boolean).join('. ')
    const extra = [job.body && `--body ${job.body}`, job.height && `--height ${job.height}`, job.role && `--role ${job.role}`].filter(Boolean).join(' ')
    return {
      title: `Design ${name}`,
      model: CREATIVE_MODEL,
      systemPrompt: (source === 'ai' || (source === 'import' && dim === '3d')) && dim === '3d' ? pictureTo3dAgentPrompt(appId) : source !== 'ai' ? sourcerAgentPrompt(appId) : designAgentPrompt(appId),
      content: source === 'import' && dim === '3d'
        ? `Make a 3D character named "${name}" from the picture the person uploaded (storage path, download with mapi): ${files.join(', ')}. ${description ? `Their note: ${description}. ` : ''}Use the uploaded picture as the concept (step 1). If the upload is already a 3D model (.glb/.fbx), convert or pack it instead and rig only if it has no skeleton.\nSave the design with --job ${id} --source import --prompt ${JSON.stringify(description || 'imported picture')}`
        : source !== 'ai'
        ? sourceDraft({ jobId: id, name, description, source, dim, files, change, fromJob })
        : dim === '3d'
          ? `${job.group ? `Make ONE 3D game character, part of a planned cast (make only this one; the cast was asked for as: ${job.group})` : 'Make a 3D game character'} named "${name}": ${description}${hints ? `\n${hints}.` : ''}${change ? `\nThe previous attempt is character-drafts/${fromJob}.json (its concept prompt is in "prompt"); change it: ${change}` : ''}\nSave the design with: --job ${id} --source ai ${extra} --prompt ${JSON.stringify(change ? `${description}; ${change}` : description)}`
          : designDraft({ jobId: id, name, style, description, change, fromJob }),
    }
  }

  async function start(fields) {
    const job = { id: fields.id || newId(), source: 'ai', dim: '2d', files: [], ...fields, change: fields.change || null, queued: true, startedAt: Date.now() }
    job.launch = request(job)
    await mutate((list) => [job, ...list])
    kick()
  }
  const remove = (id) => {
    mutate((list) => list.filter((j) => j.id !== id))
    setDrafts((d) => { const n = { ...d }; delete n[id]; return n })
    store()?.remove(`character-drafts/${id}.json`).catch(() => {})
    store()?.remove(`character-drafts/${id}.glb`).catch(() => {})
  }
  return { jobs, drafts, start, remove, newId }
}

function DraftCard({ job, draft, onKeep, onRetry, onChange, onDiscard }) {
  const [changing, setChanging] = useState(false)
  const [change, setChange] = useState('')
  const [name, setName] = useState(job.name)
  const failed = job.failed || (!draft && !job.queued && !job.done && Date.now() - job.startedAt > JOB_TIMEOUT_MS)
  if (!draft) {
    return (
      <li className={`gs-draft gs-draft--${failed ? 'failed' : 'drawing'}`}>
        <div className="gs-draft-art">{failed ? '' : <div className="gs-spinner" aria-hidden="true" />}</div>
        <div className="gs-draft-body">
          <strong>{job.name}</strong>
          <span>{failed ? "This design didn't finish." : job.queued ? 'Waiting its turn…' : job.change ? `Changing: ${job.change}` : job.source === 'import' ? 'Converting your file… a minute or two.' : job.dim === '3d' ? 'Drawing a concept and building it in 3D… one to three minutes.' : 'Being designed… about a minute.'}</span>
          {failed && (
            <div className="gs-draft-actions">
              <button type="button" className="gs-btn gs-btn--small" onClick={onRetry}><Reload aria-hidden="true" />Try again</button>
              <button type="button" className="gs-icon-btn" aria-label="Discard" onClick={onDiscard}><X aria-hidden="true" /></button>
            </div>
          )}
        </div>
      </li>
    )
  }
  return (
    <li className="gs-draft">
      <div className="gs-draft-art"><img src={draft.dataUrl} alt={`Design for ${job.name}`} className={draft.pixel ? 'is-pixel' : ''} /></div>
      <div className="gs-draft-body">
        <label className="gs-field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={32} autoCapitalize="none" spellCheck={false} />
        </label>
        <span className="gs-draft-desc">
          {draft.kind === '3d' ? `3D · ${draft.animations?.length || 0} animations` : '2D'}
          {draft.source === 'import' ? ' · imported' : draft.source === 'library' ? ' · from the free library' : ''}
          {job.description ? ` · ${job.description}` : ''}
        </span>
        {changing ? (
          <div className="gs-draft-change">
            <textarea rows={2} value={change} maxLength={300} autoFocus placeholder="What should change? e.g. make the cape red, bigger eyes" onChange={(e) => setChange(e.target.value)} />
            <div className="gs-draft-actions">
              <button type="button" className="gs-btn gs-btn--small gs-btn--primary" disabled={!change.trim()} onClick={() => { onChange(change.trim()); setChanging(false); setChange('') }}>Change it</button>
              <button type="button" className="gs-btn gs-btn--small" onClick={() => setChanging(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="gs-draft-actions">
            <button type="button" className="gs-btn gs-btn--small gs-btn--primary" onClick={() => onKeep(cleanName(name) || job.name)}>Keep</button>
            <button type="button" className="gs-btn gs-btn--small" onClick={onRetry}><Reload aria-hidden="true" />Try again</button>
            <button type="button" className="gs-btn gs-btn--small" onClick={() => setChanging(true)}>Change…</button>
            <button type="button" className="gs-icon-btn" aria-label="Discard this design" onClick={onDiscard}><X aria-hidden="true" /></button>
          </div>
        )}
      </div>
    </li>
  )
}

export default function CharactersPanel({ appId, token, assets, onRefresh, onSaveAssets, onUse, guest = false }) {
  const [description, setDescription] = useState('')
  const [files, setFiles] = useState([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [openName, setOpenName] = useState(null)
  const { jobs, drafts, start, remove, newId } = useDesignJobs(appId, token)
  const characters = Object.entries(assets.characters || {})
  const taken = () => new Set([...Object.keys(assets.characters || {}), ...jobs.map((j) => j.name)])

  const design = async () => {
    const text = description.trim()
    const source = files.length ? 'import' : 'ai'
    const dim = '3d'
    if (source !== 'import' && text.length < 3) return setError('Describe your character first, for example "a brave knight with a red cape".')
    if (!window.mobius?.chat?.start) return setError('The AI is not available here.')
    setError('')
    const name = uniqueName(nameFrom(text || files[0]?.name.replace(/\.[^.]+$/, '')) || 'character', taken())
    if (source === 'import') {
      setUploading(true)
      const id = newId()
      try {
        const paths = []
        for (const file of files) {
          if (file.size > 25 * 1024 * 1024) throw new Error(`${file.name} is over 25 MB.`)
          const path = `imports/${id}/${file.name.replace(/[^A-Za-z0-9._-]+/g, '_')}`
          await store().setBlob(path, file, { contentType: file.type || 'application/octet-stream' })
          paths.push(path)
        }
        await start({ id, name, description: text, source, dim, files: paths })
      } catch (err) {
        setUploading(false)
        return setError(err?.message || 'The file could not be uploaded. Try again.')
      }
      setUploading(false)
    } else {
      await start({ name, description: text, source, dim })
    }
    setDescription('')
    setFiles([])
  }

  const keep = async (job, draft, name) => {
    const finalName = assets.characters?.[name] ? uniqueName(name, taken()) : name
    if (draft.kind === '3d') {
      const blob = await readModel(draft.model)
      if (!blob) return
      await store().setBlob(`models/${finalName}.glb`, blob, { contentType: 'model/gltf-binary' })
      if (draft.spec) await store().set(`character-src/${finalName}.json`, draft.spec).catch(() => {})
      await onSaveAssets((latest) => ({
        ...latest,
        models: { ...(latest.models || {}), [finalName]: { title: finalName, credit: draft.credit || 'Your character', size: blob.size, animations: draft.animations } },
        characters: { ...(latest.characters || {}), [finalName]: {
          kind: '3d', body: draft.body || job.body || 'humanoid', height: draft.height || job.height || null, source: draft.source, credit: draft.credit || '', role: draft.role || job.role || null, held: draft.held || [], type: '', prompt: job.description || draft.prompt,
          thumb: draft.dataUrl, dataUrl: draft.dataUrl, animations: draft.animations || [], bytes: blob.size, createdAt: new Date().toISOString() } },
      }))
      remove(job.id)
      setOpenName(finalName)
      return
    }
    const entry = {
      kind: '2d', source: draft.source || 'ai', role: null, type: '', view: draft.view || 'side', style: draft.style || job.style,
      prompt: job.change ? `${job.description}; ${job.change}` : job.description,
      dataUrl: draft.dataUrl, thumb: draft.dataUrl, frameWidth: draft.w, frameHeight: draft.h, frameCount: 1,
      animations: { idle: [0] }, pixel: draft.pixel, createdAt: new Date().toISOString(),
    }
    await onSaveAssets((latest) => ({ ...latest, characters: { ...(latest.characters || {}), [finalName]: entry } }))
    if (draft.svg) await store()?.setText(`character-src/${finalName}.svg`, draft.svg, { contentType: 'image/svg+xml' }).catch(() => {})
    remove(job.id)
    setOpenName(finalName)
  }

  if (openName && assets.characters?.[openName]) {
    const entry = assets.characters[openName]
    return (
      <CharacterPage appId={appId} name={openName} entry={entry} onBack={() => setOpenName(null)}
        onRefresh={onRefresh} onSaveAssets={onSaveAssets} onUse={onUse} onDeleted={() => setOpenName(null)} />
    )
  }

  return (
    <div className="gs-library-page">
      <section className="gs-card" aria-labelledby="gs-gallery-title">
        <div className="gs-card-head">
          <h3 id="gs-gallery-title">Your characters</h3>

        </div>

        {guest ? (
          <p className="gs-hint">These are the characters this game can use; tap one to place it in your scene. Making a new 3D character from a description runs on a paid 3D service, so it isn't available in a shared project yet. Ask your assistant to build a simple figure from shapes instead.</p>
        ) : <div className="gs-create">
          <label className="gs-visually-hidden" htmlFor="gs-char-desc">Describe a character</label>
          <textarea id="gs-char-desc" rows={3} value={description} maxLength={400}
            placeholder="Describe a character… e.g. a cowboy gunslinger, an anime mage girl, a cute robot"
            onChange={(e) => { setDescription(e.target.value); setError('') }} />
          <div className="gs-create-row">
            <label className="gs-btn gs-btn--small gs-attach">
              <UploadDocuments aria-hidden="true" />{files.length ? `${files.length} picture${files.length > 1 ? 's' : ''}` : 'Add a picture'}
              <input type="file" multiple className="gs-visually-hidden" aria-label="Add a picture or 3D file" accept=".png,.jpg,.jpeg,.webp,.svg,.glb,.gltf,.fbx" onChange={(e) => setFiles([...e.target.files])} />
            </label>
            {files.length > 0 && <button type="button" className="gs-icon-btn" aria-label="Remove pictures" onClick={() => setFiles([])}><X aria-hidden="true" /></button>}
            <button type="button" className="gs-btn gs-btn--primary gs-create-go" disabled={uploading} onClick={design}><Sparkles aria-hidden="true" />{uploading ? 'Uploading…' : 'Create'}</button>
          </div>
          {error && <p className="gs-error" role="alert">{error}</p>}
          <p className="gs-hint gs-hint--tight">Any style. It becomes an animated 3D character in about two minutes. You can also add a picture or drawing to turn into 3D.</p>
        </div>}

        {jobs.length > 0 && (
          <>
            <h4 className="gs-sheet-label">New designs</h4>
            <ul className="gs-drafts">
              {jobs.map((job) => (
                <DraftCard key={job.id} job={job} draft={drafts[job.id]}
                  onKeep={(name) => keep(job, drafts[job.id], name)}
                  onRetry={() => { remove(job.id); start({ name: job.name, description: job.description, style: job.style, source: job.source || 'ai', dim: job.dim, files: job.files || [], body: job.body, build: job.build, weapon: job.weapon, height: job.height, role: job.role, group: job.group }) }}
                  onChange={(change) => start({ name: job.name, description: job.description, style: job.style, source: job.source || 'ai', dim: job.dim, files: job.files || [], body: job.body, build: job.build, weapon: job.weapon, height: job.height, role: job.role, group: job.group, change, fromJob: job.id })}
                  onDiscard={() => remove(job.id)} />
              ))}
            </ul>
          </>
        )}

        {characters.length ? (
          <ul className="gs-char-grid" aria-label="Gallery">
            {characters.map(([key, c]) => (
              <li key={key} className="gs-char">
                <button type="button" className="gs-char-card" onClick={() => setOpenName(key)}>
                  {c.kind === '3d'
                    ? <img className="gs-char-thumb" src={c.thumb} alt="" />
                    : <SheetPreview sheet={c} anim="idle" />}
                  <strong>{key}</strong>
                  <span className="gs-tag">{c.kind === '3d' ? '3D · ' : ''}{CHARACTER_TYPES.find((t) => t.id === (c.role || c.type))?.label || 'No role yet'}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : !jobs.length ? (
          <p className="gs-hint">Characters you keep appear here. Tap one to use it in your game or change it.</p>
        ) : null}
      </section>
    </div>
  )
}
