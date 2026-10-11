// The request board: wishes friends write in a game's project (requests.md),
// and notes players leave with the Note button in the game's own app
// (playtest_notes.py copies them to notes/<gameId>.json every minute).
// game_project.py's minute sync publishes the board to requests/<gameId>.json
// and turns the owner's choices here (requests/<gameId>/<key>.json) into the
// file's [~] and [-] marks. See requests_board.py.
import React, { useEffect, useState } from 'react'
import { Check, X } from '@openai/apps-sdk-ui/components/Icon'

const store = () => window.mobius?.storage

export const REQUESTS_CSS = `
.gs-wish-btn { position: relative; }
.gs-wish-count { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: var(--accent); color: #fff; font-size: 12px; font-weight: 700; display: inline-grid; place-items: center; }
.gs-wishes { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.gs-wish { padding: 14px; border-radius: 14px; background: var(--surface); border: 1px solid var(--border); display: grid; gap: 10px; }
.gs-wish p { margin: 0; font-size: 15px; line-height: 1.4; }
.gs-wish small { color: var(--muted); font-size: 13px; }
.gs-wish-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.gs-wish-actions .gs-btn { flex: 1; min-width: 130px; }
.gs-wish.is-settled { padding: 10px 14px; grid-template-columns: 1fr auto; align-items: center; background: transparent; }
.gs-wish.is-settled p { font-size: 14px; color: var(--muted); }
.gs-wish-state { font-size: 12px; font-weight: 600; color: var(--muted); white-space: nowrap; }
.gs-wish-state.is-asked { color: var(--accent); }
.gs-note-meta { display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.gs-note-new { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--accent); }
.gs-wish-empty { padding: 18px; border-radius: 14px; border: 1px dashed var(--border); color: var(--muted); font-size: 14px; line-height: 1.5; }
@keyframes gs-wish-in { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }
.gs-wish { animation: gs-wish-in .22s ease-out both; }
@media (prefers-reduced-motion: reduce) { .gs-wish { animation: none; } }
`

const STATE = { asked: 'AI is on it', done: 'Done', declined: 'Not this time' }

// Live board for one game, with the owner's choices shown at once (the file
// catches up within a minute).
export function useRequestBoard(gameId) {
  const [items, setItems] = useState([])
  const [chosen, setChosen] = useState({})
  useEffect(() => {
    if (!gameId) return undefined
    let alive = true
    setItems([]); setChosen({})
    const path = `requests/${gameId}.json`
    const take = (value) => { if (alive) setItems(Array.isArray(value?.items) ? value.items : []) }
    store()?.get(path).then(take).catch(() => {})
    const off = store()?.subscribe(path, take)
    return () => { alive = false; off?.() }
  }, [gameId])
  const board = items.map((item) => (item.status === 'new' && chosen[item.key] ? { ...item, status: chosen[item.key] } : item))
  const decide = async (item, status) => {
    await store().set(`requests/${gameId}/${item.key}.json`, { status, at: new Date().toISOString() })
    setChosen((current) => ({ ...current, [item.key]: status }))
  }
  return { board, fresh: board.filter((item) => item.status === 'new').length, decide }
}

// Playtest notes for one game, and how many arrived since the owner last looked.
export function usePlaytestNotes(gameId) {
  const [notes, setNotes] = useState([])
  const [seenAt, setSeenAt] = useState(null)
  useEffect(() => {
    if (!gameId) return undefined
    let alive = true
    setNotes([]); setSeenAt(null)
    const path = `notes/${gameId}.json`
    const take = (value) => { if (alive) setNotes(Array.isArray(value?.items) ? value.items : []) }
    store()?.get(path).then(take).catch(() => {})
    store()?.get(`notes/${gameId}.seen.json`).then((v) => { if (alive) setSeenAt(v?.at || '') }).catch(() => { if (alive) setSeenAt('') })
    const off = store()?.subscribe(path, take)
    return () => { alive = false; off?.() }
  }, [gameId])
  const isNew = (note) => seenAt !== null && (note.at || '') > seenAt
  const markSeen = () => {
    const latest = notes.reduce((max, note) => ((note.at || '') > max ? note.at : max), seenAt || '')
    if (!latest || latest === seenAt) return
    setSeenAt(latest)
    store()?.set(`notes/${gameId}.seen.json`, { at: latest }).catch(() => {})
  }
  return { notes, fresh: notes.filter(isNew).length, isNew, markSeen }
}

export function noteMessage(note) {
  return `A player${note.name ? ` (${note.name})` : ''} left this playtest note on the game: "${note.text}". `
    + 'Think about what it means for the game and, if it points to a clear improvement, make it. Tell me briefly what you changed or why you did not.'
}

export function askMessage(item) {
  const who = item.who || 'A collaborator'
  return `${who} asked for this on the game's request board (requests.md in the project): "${item.text}". `
    + 'Please make this change. When it is done, change that line\'s box in requests.md to "[x]", then sync the project as usual.'
}

function played(seconds) {
  if (!seconds) return ''
  return seconds < 90 ? ` · played ${seconds}s` : ` · played ${Math.round(seconds / 60)} min`
}

export function RequestsSheet({ gameName, board, notes, onDecide, onAsk, onAskNote, onOpenProject, onClose }) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const [handed, setHanded] = useState({})
  const [newNotes] = useState(() => new Set(notes.notes.filter(notes.isNew).map((note) => note.id)))
  useEffect(() => { notes.markSeen() }, [notes.notes.length])
  const handNote = async (note) => {
    setBusy(note.id); setError('')
    try { await onAskNote(note); setHanded((current) => ({ ...current, [note.id]: true })) }
    catch (err) { setError(err?.message || 'That did not go through. Try again.') }
    finally { setBusy(null) }
  }
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])
  const open = board.filter((item) => item.status === 'new')
  const settled = board.filter((item) => item.status !== 'new').reverse()
  const act = async (item, status) => {
    setBusy(item.key); setError('')
    try {
      if (status === 'asked') await onAsk(item)
      await onDecide(item, status)
    } catch (err) {
      setError(err?.message || 'That did not go through. Try again.')
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="gs-sheet-scrim" onClick={onClose}>
      <section className="gs-sheet" role="dialog" aria-modal="true" aria-labelledby="gs-wishes-title" onClick={(event) => event.stopPropagation()}>
        <div className="gs-sheet-head">
          <h2 id="gs-wishes-title">Wishes for {gameName || 'this game'}</h2>
          <button type="button" className="gs-icon-btn" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
        <p className="gs-sheet-lead">What your friends asked for in the project. Hand a wish to the game's AI, or let it go.</p>
        {open.length ? (
          <ul className="gs-wishes">
            {open.map((item) => (
              <li key={item.key} className="gs-wish">
                <div><p>{item.text}</p><small>{item.who ? `From ${item.who}` : 'No name given'}</small></div>
                <div className="gs-wish-actions">
                  <button type="button" className="gs-btn gs-btn--primary" disabled={busy === item.key} onClick={() => act(item, 'asked')}>
                    <Check aria-hidden="true" />{busy === item.key ? 'Sending…' : 'Ask the AI'}</button>
                  <button type="button" className="gs-btn" disabled={busy === item.key} onClick={() => act(item, 'declined')}>Not this time</button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="gs-wish-empty">No new wishes. Friends add them in the project's requests.md, one per line, like <b>- [ ] Add a double jump (Amra)</b>.</div>
        )}
        {error && <p className="gs-hint" role="alert">{error}</p>}
        <h3 className="gs-sheet-label">From players</h3>
        {notes.notes.length ? (
          <ul className="gs-wishes">
            {notes.notes.map((note) => (
              <li key={note.id} className="gs-wish">
                <div>
                  <p>{note.text}</p>
                  <div className="gs-note-meta">
                    <small>{note.name || 'A player'}{note.at ? ` · ${new Date(note.at).toLocaleDateString()}` : ''}{played(note.playedSeconds)}</small>
                    {newNotes.has(note.id) && <span className="gs-note-new">New</span>}
                  </div>
                </div>
                <div className="gs-wish-actions">
                  <button type="button" className="gs-btn" disabled={busy === note.id || handed[note.id]} onClick={() => handNote(note)}>
                    {handed[note.id] ? 'Sent to the AI' : busy === note.id ? 'Sending…' : 'Hand to the AI'}</button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="gs-wish-empty">No playtest notes yet. Share a public link to the game (its app's ⋯ menu, then Share app): players tap Note while they play.</div>
        )}
        {settled.length > 0 && (
          <>
            <h3 className="gs-sheet-label">Earlier</h3>
            <ul className="gs-wishes">
              {settled.map((item) => (
                <li key={item.key} className="gs-wish is-settled">
                  <p>{item.text}{item.who ? ` · ${item.who}` : ''}</p>
                  <span className={`gs-wish-state is-${item.status}`}>{STATE[item.status]}</span>
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="gs-sheet-actions">
          <button type="button" className="gs-btn" onClick={onOpenProject}>Open the project</button>
        </div>
      </section>
    </div>
  )
}
