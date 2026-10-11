// AI-made things (characters, sprites, sounds) are drawn by a small hidden
// agent turn each. A job is remembered in storage until its result lands in
// assets.json, so leaving the tab or reopening the studio keeps the status.
import { useEffect, useState } from 'react'
import { CREATIVE_MODEL } from './assetPrompt.js'

const JOB_TIMEOUT_MS = 8 * 60 * 1000
const MAX_JOBS = 12

export function cleanName(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32)
}

// A name from the description's first real words: "a pink cat with a hat" -> pink-cat.
export function nameFrom(description) {
  const words = String(description || '').toLowerCase().match(/[a-z0-9]+/g) || []
  const skip = new Set(['a', 'an', 'the', 'some', 'my', 'of', 'with', 'and', 'for', 'that', 'little', 'big', 'cute', 'very', 'in', 'on', 'at', 'to', 'from', 'who', 'is', 'wearing', 'holding', 'i', 'want', 'need', 'make', 'me', 'create', 'draw', 'please', '2d', '3d', 'like', 'would']) 
  return cleanName(words.filter((w) => !skip.has(w)).slice(0, 2).join('-'))
}

export function uniqueName(base, taken) {
  let name = base || 'thing'
  for (let n = 2; taken.has(name); n += 1) name = `${base}-${n}`.slice(0, 32)
  return name
}

// group: where the result appears in assets.json ('characters', 'sprites', 'sounds').
export function useAiJobs(storageKey, assets, onRefresh) {
  const [jobs, setJobs] = useState([])
  const [now, setNow] = useState(Date.now())
  const store = window.mobius?.storage

  useEffect(() => {
    store?.get(storageKey).then((list) => Array.isArray(list) && setJobs(list)).catch(() => {})
    const timer = setInterval(() => setNow(Date.now()), 5000)
    return () => clearInterval(timer)
  }, [storageKey])

  const save = (list) => {
    setJobs(list)
    store?.set(storageKey, list).catch(() => {})
  }

  const landed = (job) => {
    // 'auto' jobs let the AI decide between an image and a sound.
    const item = job.group === 'auto' ? (assets.models?.[job.name] || assets.sprites?.[job.name] || assets.sounds?.[job.name]) : assets[job.group]?.[job.name]
    if (!item) return false
    if (!job.previous) return true
    return (Array.isArray(item) ? JSON.stringify(item) : item.dataUrl || item.thumb) !== job.previous
  }
  const finished = jobs.filter((job) => job.status === 'drawing' && landed(job))
  useEffect(() => {
    if (finished.length) save(jobs.filter((job) => !finished.includes(job)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished.length])

  // Agents write on the server; read its copy while anything is being made.
  const drawing = jobs.some((job) => job.status === 'drawing')
  useEffect(() => {
    if (!drawing || !onRefresh) return undefined
    const timer = setInterval(onRefresh, 5000)
    return () => clearInterval(timer)
  }, [drawing, onRefresh])

  async function start({ group, name, description, extra = {}, title, systemPrompt, draft }) {
    const startedAt = Date.now()
    const current = assets[group]?.[name]
    const job = {
      id: `${startedAt.toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      group, name, description, startedAt, status: 'drawing', ...extra,
      previous: current ? (Array.isArray(current) ? JSON.stringify(current) : current.dataUrl) : null,
    }
    const next = [job, ...jobs].slice(0, MAX_JOBS)
    save(next)
    try {
      await window.mobius.chat.start({ model: CREATIVE_MODEL, scope: `${group}:${job.id}`, ownerVisible: false, title, systemPrompt, draft })
    } catch {
      save(next.map((j) => (j.id === job.id ? { ...j, status: 'failed' } : j)))
    }
  }
  const dismiss = (job) => save(jobs.filter((j) => j.id !== job.id))
  const visible = jobs.map((job) => (job.status === 'drawing' && now - job.startedAt > JOB_TIMEOUT_MS ? { ...job, status: 'failed' } : job))
  return { jobs: visible, start, dismiss }
}

// Change a shared JSON file (the server's tools write it too) without losing
// anyone's update: read the server copy, apply the change, save only if nobody
// saved in between, otherwise read again and redo the change.
export async function updateShared(path, change, fallback) {
  const storage = window.mobius.storage
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const fresh = await storage.getWithVersion(path).catch(() => null)
    const next = change(fresh?.value ?? fallback)
    if (!storage.durableWrite || !fresh?.version) {
      await storage.set(path, next)
      return next
    }
    try {
      await storage.durableWrite(path, next, { ifMatch: fresh.version })
      return next
    } catch (err) {
      if (err?.code !== 'conflict') throw err
    }
  }
  throw new Error(`${path} kept changing; try again.`)
}
