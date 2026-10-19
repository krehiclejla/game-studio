// One gallery character: preview its animations, give it a role, and shape it
// further with its own AI chat ("this is the hero", "add walk and jump").
import React, { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Play, Plus, Trash } from '@openai/apps-sdk-ui/components/Icon'
import { editorPrompt } from './assetPrompt.js'
import { SheetPreview } from './libraryUi.jsx'
import ModelView from './ModelView.jsx'
import { embedOptions, modelFor } from './aiModel.js'

// Moves from the free Quaternius Universal Animation Library (CC0) that fit any humanoid:
// [label, library clip, the name games use].
const MOVE_GROUPS = [
  ['Everyday', [
    ['Nod yes', 'Yes', 'nod'], ['Shake head', 'Idle_No_Loop', 'no'], ['Talk', 'Idle_Talking_Loop', 'talk'],
    ['On the phone', 'Idle_TalkingPhone_Loop', 'phone'], ['Arms folded', 'Idle_FoldArms_Loop', 'arms-folded'],
    ['Sit down', 'Sitting_Enter', 'sit-down'], ['Sit', 'Sitting_Idle_Loop', 'sit'], ['Sit and talk', 'Sitting_Talking_Loop', 'sit-talk'],
    ['Stand up', 'Sitting_Exit', 'stand-up'], ['Pick up', 'PickUp_Table', 'pick-up'], ['Use something', 'Interact', 'interact'],
    ['Open a chest', 'Chest_Open', 'open-chest'], ['Eat or drink', 'Consume', 'eat'], ['Push', 'Push_Loop', 'push'],
    ['Carry', 'Walk_Carry_Loop', 'carry'], ['Crouch', 'Crouch_Idle_Loop', 'crouch'], ['Sneak', 'Crouch_Fwd_Loop', 'sneak'],
    ['Sprint', 'Sprint_Loop', 'sprint'], ['Formal walk', 'Walk_Formal_Loop', 'walk-formal'], ['Swim', 'Swim_Fwd_Loop', 'swim'],
    ['Drive', 'Driving_Loop', 'drive'], ['Climb up', 'ClimbUp_1m_RM', 'climb'], ['Roll', 'Roll', 'roll'], ['Slide', 'Slide_Loop', 'slide'],
    ['Chop wood', 'TreeChopping_Loop', 'chop'], ['Fix (kneeling)', 'Fixing_Kneeling', 'fix'], ['Water plants', 'Farm_Watering', 'water'],
    ['Hold a lantern', 'Idle_Lantern_Loop', 'lantern'], ['Hold a torch', 'Idle_Torch_Loop', 'torch'],
  ]],
  ['Fighting', [
    ['Jab', 'Punch_Jab', 'jab'], ['Cross punch', 'Punch_Cross', 'cross'], ['Hook', 'Melee_Hook', 'hook'],
    ['Sword attack', 'Sword_Attack', 'sword-attack'], ['Sword combo', 'Sword_Regular_Combo', 'sword-combo'], ['Block', 'Sword_Block', 'block'],
    ['Shield bash', 'Shield_OneShot', 'shield-bash'], ['Cast a spell', 'Spell_Simple_Shoot', 'cast'], ['Shoot', 'Pistol_Shoot', 'shoot'],
    ['Reload', 'Pistol_Reload', 'reload'], ['Throw', 'OverhandThrow', 'throw'], ['Get hit', 'Hit_Chest', 'hit'],
    ['Knocked back', 'Hit_Knockback', 'knockback'], ['Get up', 'LayToIdle', 'get-up'],
  ]],
  ['Fun', [
    ['Dance', 'Dance_Loop', 'dance'], ['Ninja jump', 'NinjaJump_Start', 'ninja-jump'], ['Zombie walk', 'Zombie_Walk_Fwd_Loop', 'zombie-walk'],
    ['Zombie idle', 'Zombie_Idle_Loop', 'zombie-idle'], ['Zombie attack', 'Zombie_Scratch', 'zombie-attack'],
  ]],
]

// Adds library moves in a small hidden agent turn (the server does the retargeting), then
// waits for them to show up in the character's animations.
function MovesPicker({ appId, name, have, onRefresh }) {
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState([])
  const [waiting, setWaiting] = useState(null) // names being added
  const [error, setError] = useState('')
  const refreshRef = useRef(onRefresh)
  refreshRef.current = onRefresh
  useEffect(() => {
    if (!waiting) return undefined
    if (waiting.every((m) => have.includes(m))) { setWaiting(null); return undefined }
    const started = Date.now()
    const timer = setInterval(() => {
      refreshRef.current?.()
      if (Date.now() - started > 4 * 60 * 1000) { setWaiting(null); setError('The moves did not arrive. Try again.') }
    }, 4000)
    return () => clearInterval(timer)
  }, [waiting, have.join(',')])
  const toggle = (move) => setPicked((list) => (list.includes(move) ? list.filter((m) => m !== move) : [...list, move]))
  const add = async () => {
    const chosen = MOVE_GROUPS.flatMap(([, moves]) => moves).filter(([, , as]) => picked.includes(as))
    if (!chosen.length || !window.mobius?.chat?.start) return
    setError('')
    const spec = chosen.map(([, clip, as]) => clip + '=' + as).join(',')
    try {
      await window.mobius.chat.start({
        scope: 'moves:' + name + ':' + Date.now(),
        ownerVisible: false,
        title: 'Add moves to ' + name,
        ...(await modelFor('quick')),
        systemPrompt: 'You add animations to Game Studio characters. Run the one command you are given with the Bash tool, then reply in one short sentence saying whether it worked. If it fails, say why in plain words. Do nothing else.',
        draft: 'Run: python3 /data/apps/game-studio/model_tool.py moves ' + appId + ' ' + name + ' "' + spec + '"',
      })
      setWaiting(chosen.map(([, , as]) => as))
      setPicked([])
      setOpen(false)
    } catch {
      setError('The moves could not be started. Try again.')
    }
  }
  if (waiting) return <p className="gs-hint" role="status">Adding {waiting.length === 1 ? 'a move' : waiting.length + ' moves'}… about a minute.</p>
  return (
    <div className="gs-moves">
      {error && <p className="gs-error" role="alert">{error}</p>}
      {!open ? (
        <button type="button" className="gs-btn gs-btn--small" onClick={() => setOpen(true)}><Plus aria-hidden="true" />Add moves</button>
      ) : (
        <div className="gs-moves-sheet">
          {MOVE_GROUPS.map(([group, moves]) => (
            <div key={group} className="gs-moves-group">
              <h3>{group}</h3>
              <div className="gs-chips gs-chips--quiet">
                {moves.map(([label, , as]) => {
                  const owned = have.includes(as)
                  return (
                    <button key={as} type="button" className="gs-chip gs-chip--plain" disabled={owned}
                      aria-pressed={owned || picked.includes(as)} onClick={() => toggle(as)}>{label}</button>
                  )
                })}
              </div>
            </div>
          ))}
          <div className="gs-draft-actions">
            <button type="button" className="gs-btn gs-btn--small gs-btn--primary" disabled={!picked.length} onClick={add}>
              {picked.length ? 'Add ' + picked.length + (picked.length === 1 ? ' move' : ' moves') : 'Pick moves'}
            </button>
            <button type="button" className="gs-btn gs-btn--small" onClick={() => { setOpen(false); setPicked([]) }}>Cancel</button>
          </div>
          <p className="gs-hint gs-hint--tight">Free moves from the Quaternius animation library (CC0). Games play them by name.</p>
        </div>
      )}
    </div>
  )
}

function CharacterChat({ appId, name, onTurnDone }) {
  const mountRef = useRef(null)
  const doneRef = useRef(onTurnDone)
  doneRef.current = onTurnDone
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const mount = mountRef.current
    if (!mount || !window.mobius?.chat) return undefined
    let handle
    let disposed = false
    embedOptions(`character-chats/${name}.json`, 'creative').then((pick) => window.mobius.chat({
      ...pick,
      mount,
      persist: `character-chats/${name}.json`,
      systemPrompt: editorPrompt(appId, name),
      picker: false,
      guidance: 'Change it by chatting: "this is the hero", "add a sword attack", "give him a red cape".',
      onMessageSent: () => setBusy(true),
      onTurnDone: () => { setBusy(false); doneRef.current?.() },
    })).then((h) => { if (disposed) h.destroy(); else handle = h })
      .catch((err) => setError(err?.message || 'The character chat could not start.'))
    return () => { disposed = true; handle?.destroy() }
  }, [appId, name])
  // The editor saves on the server while it works; show progress as it lands.
  useEffect(() => {
    if (!busy) return undefined
    const timer = setInterval(() => doneRef.current?.(), 6000)
    return () => clearInterval(timer)
  }, [busy])
  return (
    <>
      {error && <p className="gs-error" role="alert">{error}</p>}
      <div className="gs-chat gs-chat--character" ref={mountRef} />
    </>
  )
}

export default function CharacterPage({ appId, name, entry, onBack, onRefresh, onSaveAssets, onUse, onDeleted }) {
  const is3d = entry.kind === '3d'
  const anims = is3d ? (entry.animations || []).filter((a) => a !== 'static') : Object.keys(entry.animations || {})
  const [anim, setAnim] = useState(anims.includes('walk') ? 'walk' : anims[0] || 'idle')
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => { if (!anims.includes(anim)) setAnim(anims.includes('walk') ? 'walk' : anims[0] || 'idle') }, [anims.join(',')])
  const role = entry.role || entry.type || null

  const remove = async () => {
    await onSaveAssets((latest) => {
      const characters = { ...(latest.characters || {}) }
      const models = { ...(latest.models || {}) }
      delete characters[name]
      delete models[name] // its 3D file goes too, so it doesn't linger in Assets and games
      return { ...latest, characters, models }
    })
    window.mobius?.storage?.remove(`models/${name}.glb`).catch(() => {})
    onDeleted()
  }

  return (
    <div className="gs-library-page gs-char-page">
      <div className="gs-char-page-head">
        <button type="button" className="gs-btn gs-btn--small" onClick={onBack}><ArrowLeft aria-hidden="true" />Gallery</button>
        <h2>{name}</h2>
      </div>
      <section className="gs-card gs-char-hero">
        <div className="gs-char-stage">
          {is3d
            ? <ModelView key={entry.updatedAt || entry.bytes} path={`models/${name}.glb`} anim={anim} fallback={entry.thumb} />
            : <SheetPreview sheet={entry} anim={anim} className="gs-sheet-preview--big" />}
        </div>
        <div className="gs-char-info">
          {anims.length > 1 ? (
            <div className={`gs-chips gs-chips--quiet${anims.length > 8 ? ' gs-chips--scroll' : ''}`} role="radiogroup" aria-label="Animation">
              {anims.map((a) => (
                <button key={a} type="button" role="radio" className="gs-chip gs-chip--plain" aria-checked={anim === a} aria-pressed={anim === a} onClick={() => setAnim(a)}>{a}</button>
              ))}
            </div>
          ) : (
            <p className="gs-hint gs-hint--tight">No animations yet. Ask below, for example "add walk and jump animations".</p>
          )}
          {is3d && (entry.body || 'humanoid') === 'humanoid' && <MovesPicker appId={appId} name={name} have={anims} onRefresh={onRefresh} />}
          {entry.prompt && <p className="gs-hint">{entry.prompt}</p>}
          <div className="gs-draft-actions">
            <button type="button" className="gs-btn gs-btn--primary" onClick={() => onUse({ text: `Use my character "${name}"${role ? ` (${role})` : ''} in the game${role === 'hero' ? ' as the player' : ''}, with its animations.` })}><Play aria-hidden="true" />Use in game</button>
            {confirmDelete ? (
              <>
                <button type="button" className="gs-btn gs-btn--danger" onClick={remove}>Delete {name}</button>
                <button type="button" className="gs-btn" onClick={() => setConfirmDelete(false)}>Keep</button>
              </>
            ) : (
              <button type="button" className="gs-icon-btn" aria-label={`Delete ${name}`} onClick={() => setConfirmDelete(true)}><Trash aria-hidden="true" /></button>
            )}
          </div>
        </div>
      </section>
      <section className="gs-card gs-char-chat" aria-label={`Shape ${name} with AI`}>
        <CharacterChat appId={appId} name={name} onTurnDone={onRefresh} />
      </section>
    </div>
  )
}
