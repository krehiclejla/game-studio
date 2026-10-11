// Small pieces shared by the Characters and Assets tabs.
import React, { useEffect, useState } from 'react'
import { X } from '@openai/apps-sdk-ui/components/Icon'

export function JobList({ jobs, onRetry, onDismiss, verb = 'is being drawn…' }) {
  if (!jobs.length) return null
  return (
    <ul className="gs-jobs" aria-label="Being made">
      {jobs.map((job) => (
        <li key={job.id} className={`gs-job gs-job--${job.status}`}>
          <span className="gs-job-dot" aria-hidden="true" />
          <span><b>{job.name}</b> {job.status === 'failed' ? "didn't finish." : verb}</span>
          {job.status === 'failed' && (
            <>
              <button type="button" className="gs-btn gs-btn--small" onClick={() => onRetry(job)}>Try again</button>
              <button type="button" className="gs-icon-btn" aria-label={`Dismiss ${job.name}`} onClick={() => onDismiss(job)}><X aria-hidden="true" /></button>
            </>
          )}
        </li>
      ))}
    </ul>
  )
}

// Sends one editable request to the current game's studio chat.
export function UseInGameSheet({ request, gameName, onSend, onClose }) {
  const [text, setText] = useState(request?.text || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { setText(request?.text || ''); setError('') }, [request])
  if (!request) return null
  const send = async () => {
    if (!text.trim()) return
    setBusy(true)
    setError('')
    try {
      await onSend(text.trim())
    } catch (err) {
      setError(err?.message || 'That could not be sent. Try again.')
      setBusy(false)
    }
  }
  return (
    <div className="gs-sheet-scrim" role="presentation" onClick={onClose}>
      <div className="gs-sheet" role="dialog" aria-modal="true" aria-labelledby="gs-use-title" onClick={(e) => e.stopPropagation()}>
        <div className="gs-sheet-head">
          <h2 id="gs-use-title">Use in {gameName || 'your game'}</h2>
          <button type="button" className="gs-icon-btn" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
        <p className="gs-sheet-lead">The studio agent adds it to the game. Say how you want it used.</p>
        <label className="gs-field gs-field--area">
          <span>Tell the agent</span>
          <textarea rows={3} value={text} maxLength={600} onChange={(e) => setText(e.target.value)} />
        </label>
        {error && <p className="gs-error" role="alert">{error}</p>}
        <div className="gs-sheet-actions">
          <button type="button" className="gs-btn" onClick={onClose}>Cancel</button>
          <button type="button" className="gs-btn gs-btn--primary" disabled={busy || !text.trim()} onClick={send}>{busy ? 'Sending…' : 'Send to the studio'}</button>
        </div>
      </div>
    </div>
  )
}

// Plays one animation from a character sheet by stepping its frames.
export function SheetPreview({ sheet, anim = 'walk', className = '' }) {
  const frames = sheet.animations?.[anim] || sheet.animations?.move || sheet.animations?.idle || [0]
  const [step, setStep] = useState(0)
  useEffect(() => {
    setStep(0)
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || frames.length < 2) return undefined
    const timer = setInterval(() => setStep((s) => s + 1), anim === 'idle' ? 380 : 140)
    return () => clearInterval(timer)
  }, [anim, sheet.dataUrl])
  const count = sheet.frameCount || 1
  const frame = frames[step % frames.length]
  return (
    <div
      className={`gs-sheet-preview ${sheet.pixel ? 'is-pixel' : ''} ${className}`}
      role="img"
      aria-label={`${anim} animation`}
      style={{ backgroundImage: `url(${sheet.dataUrl})`, backgroundSize: `${count * 100}% 100%`, backgroundPosition: `${count > 1 ? (frame / (count - 1)) * 100 : 0}% 0` }}
    />
  )
}
