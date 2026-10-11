import React, { useState } from 'react'
import { ChatCompose, Check, X } from '@openai/apps-sdk-ui/components/Icon'
import { TEMPLATES } from './kits/templates.js'

// Only genres with a finished template are offered; the rest appear as they ship.
const GENRES = catalog.genres.filter((genre) => TEMPLATES[genre.id])

export default function NewGame({ onCreate, onClose, busy }) {
  const [genreId, setGenreId] = useState(GENRES[0]?.id || 'blank')
  const genre = GENRES.find((g) => g.id === genreId)
  const [name, setName] = useState('')
  const [idea, setIdea] = useState('')
  const [error, setError] = useState('')

  const pickGenre = (id) => setGenreId(id)

  const create = () => {
    if (!genre && idea.trim().length < 3) {
      setError('Describe the game you want, for example "a cat that jumps between rooftops collecting fish".')
      return
    }
    onCreate({
      name: name.trim(),
      genre: genre ? genre.id : null,
      art: null,
      html: genre ? TEMPLATES[genre.id] : '',
      idea: idea.trim(),
    })
  }

  return (
    <div className="gs-sheet-scrim" role="presentation" onClick={onClose}>
      <div className="gs-sheet" role="dialog" aria-modal="true" aria-labelledby="gs-new-title" onClick={(e) => e.stopPropagation()}>
        <div className="gs-sheet-head">
          <h2 id="gs-new-title">New game</h2>
          <button type="button" className="gs-icon-btn" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
        <p className="gs-sheet-lead">Pick a kind of game, then describe the look in your own words. The agent builds it to match.</p>
        <div className="gs-genres" role="radiogroup" aria-label="Kind of game">
          {GENRES.map((g) => (
            <button key={g.id} type="button" role="radio" aria-checked={genreId === g.id} className="gs-genre" onClick={() => pickGenre(g.id)}>
              <strong>{g.title}</strong>
              <span>{g.blurb}</span>
              {genreId === g.id && <Check className="gs-genre-check" aria-hidden="true" />}
            </button>
          ))}
          <button type="button" role="radio" aria-checked={genreId === 'blank'} className="gs-genre" onClick={() => pickGenre('blank')}>
            <strong><ChatCompose aria-hidden="true" /> Blank idea</strong>
            <span>Describe anything and the agent builds it from scratch.</span>
            {genreId === 'blank' && <Check className="gs-genre-check" aria-hidden="true" />}
          </button>
        </div>
        <label className="gs-field gs-field--wide">
          <span>{genre ? 'What should it be? (optional)' : 'What should it be?'}</span>
          <textarea rows={3} value={idea} maxLength={1000} onChange={(e) => { setIdea(e.target.value); setError('') }}
            placeholder={genre ? 'For example: a snowy level with a pink cat hero and three levels' : 'For example: a bat dodging stalactites in a glowing cave'} />
        </label>
        {error && <p className="gs-error" role="alert">{error}</p>}
        <label className="gs-field gs-field--wide">
          <span>Name (optional)</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder={genre ? genre.title : 'My game'} />
        </label>
        <div className="gs-sheet-actions">
          <button type="button" className="gs-btn" onClick={onClose}>Cancel</button>
          <button type="button" className="gs-btn gs-btn--primary" disabled={busy} onClick={create}>{busy ? 'Creating…' : idea.trim() ? 'Create and build' : 'Create game'}</button>
        </div>
        <p className="gs-hint">Art: free CC0 packs by Kenney (kenney.nl).</p>
      </div>
    </div>
  )
}
