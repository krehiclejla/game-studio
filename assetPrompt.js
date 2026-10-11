// Hidden app chats default to the light background model; creative work
// (designing, modelling, building games) needs the strongest one.
export const CREATIVE_MODEL = 'claude-opus-5-5'

// Asset making: the Assets tab starts one small hidden agent turn per request.
// The agent draws the asset itself (SVG or a pixel grid, or ZzFX numbers for a
// sound), checks a rendered preview, and saves it with make_asset.py. Free: no
// image service is involved.

export const ASSET_KINDS = [
  { id: 'item', label: 'Item', hint: 'a coin, a key, a power-up, a sword', size: 'a 256x256 sprite, one object centred' },
  { id: 'scenery', label: 'Scenery', hint: 'an oak tree, a mossy rock, a cottage, a bush', size: 'a 256x256 sprite standing on the bottom edge (leave a small margin), side view, one object' },
  { id: 'tile', label: 'Tile', hint: 'grass ground, stone wall, water', size: 'a 128x128 seamless square tile that fills the whole canvas edge to edge and repeats cleanly' },
  { id: 'background', label: 'Background', hint: 'a forest at dusk, a space nebula', size: 'a 1024x576 full-bleed scene with no characters (use --width 1024 --height 576)' },
  { id: 'ui', label: 'Button or icon', hint: 'a heart icon, a play button', size: 'a 256x256 interface piece, centred' },
  { id: 'sound', label: 'Sound', hint: 'a laser zap, a coin blip, a big boom', size: 'a ZzFX sound effect' },
]

// No fixed styles: the person describes any look in their own words.
export const STYLE_GUIDE = `Style: use exactly the look the person describes, in any style at all (cartoon, pixel art, watercolor, anime, chibi, realistic, painterly, low-poly, papercraft, claymation, neon, sketch, retro 8-bit, comic, and so on). If they name no style, choose one that suits the subject and describe it to yourself in a few words before drawing, then stay consistent. Techniques: vector looks are layered SVG shapes (use linear/radial gradients for painterly, soft or realistic shading, rim lights and texture strokes); pixel and retro looks are pixel grids (16–32 px for sprites, up to 128x72 for backgrounds, a small palette); outlines, colour count and shading depth follow the chosen style. Record the style you used, in 1–3 words, with --style.`

// Man-made things with exact shapes (weapons, tools, furniture) are built from parts in
// code: the local picture model cannot draw them (an axe comes out as a knife or with two
// handles), and picture-to-3D smears thin handles and edges.
export const SHAPES_GUIDE = `Build it from shapes: write $TMPDIR/build.py that imports /data/apps/game-studio/shapes.py (read its top for the API: tube for handles, shafts and legs; slab for blades, axe and hammer heads, planks and signs, with a tapered cutting edge; box and cylinder; part gives each piece a material; save writes the GLB) and run it. Real-world proportions in metres; low-poly suits any style, and colours and materials carry the look (grimy, rusty, painted, gold). Weapons and held tools: handle along +Y from its end, flat sides facing X, edge or head toward +Z, and save(..., grip=H) with H the hand-hold height (about 0.12 of the length for axes, swords, hammers; 0.4 for spears and staffs). Check the front and the side (python3 /data/apps/game-studio/shapes.py turn OUT.glb side.glb 90, then render both) and fix the script until a stranger would name the object at a glance.`

// The person's style is the brief. Every 3D maker checks its result in the game's own
// drawn look against a checklist written from the person's words, and keeps working
// until it passes: a first build of stuck-together primitives is never the answer.
export const STYLE_CHECK_GUIDE = `Style check: the Builder's self-check (BUILDER.md, C4 or E4) is required for every 3D model: render with godot_build.py look, mark every point pass or fail, at least 2 rounds. The style is entirely the person's: never a default look, never an earlier character's face, hair or body, never a famous series they did not ask for.`

// Humanoid characters: built in Blender ON the animated mannequin, so any style comes out
// rigged with the studio's moves, free and on this machine.
export const BLENDER_CHAR_GUIDE = `Follow the Game Studio Builder, CHARACTER MODE: read /data/apps/game-studio/BUILDER.md in full first (every time). Write the spec, build it in Blender from its own skeleton (Skin modifier, then shaped like a modeller would), rig it (bipeds: detailed.py rig in T-pose; other bodies: creature.py), check it in the game's look until every point passes, and save it as the Builder says. Never use a mannequin or the old blender_char.py kit.`

// Buildings, scenery, furniture, props: built in Blender from a short script with helpers
// that default to finished forms (bevels, overhangs, framed openings, lettering).
export const BLENDER_PROP_GUIDE = `Follow the Game Studio Builder, ENVIRONMENT MODE: read /data/apps/game-studio/BUILDER.md in full first (every time). Write the spec (floor plan, story, condition), build it in layers (shell, roof, trim, furniture, story props, imperfection pass) with real dimensions, bevels and named materials, then DRESS it with real CC0 textures and props (Builder E3b: surface_library.py and dress.py), check it in the game's look until every point passes, and save it as the Builder says.`

// Ready-made CC0 characters (KayKit, Quaternius) and Blender edits of them: clean parts, real
// skeletons and dozens of moves, so they beat a picture-to-3D guess whenever their stylised,
// chunky low-poly look suits the request.
// New 3D models come only from 3D AI Studio text-to-3D (the owner's paid credits): no drawing
// and no picture-to-3D.
export const TEXT3D_GUIDE = `New 3D models are made from a text description with 3D AI Studio (the person's paid credits), never drawn first. Check first with python3 /data/apps/game-studio/ai3d.py balance; afterwards tell the person the credits used and how many are left. If there is no key or not enough credits, do not make one another way: say so in one sentence (they can add credits in their 3D AI Studio dashboard) and offer the free character library or, for objects, building it from shapes.`

export const EDIT_GUIDE = `Edit it in Blender with python3 /data/apps/game-studio/blender_edit.py IN.glb OUT.glb $TMPDIR/edit.py (read its top for the helpers; IN.glb --info lists parts, colours and bones): recolor parts or swap colours, remove parts (a cape, a helmet), borrow parts or held items from other characters with the same skeleton (all KayKit ones share one), thicken for a bulkier or skinnier build, scale a part (a bigger head), attach worn gear built with /data/apps/game-studio/shapes.py (hats, packs, belts, beards) to a bone after measuring with bounds() and bone(); held weapons and tools go in the hand afterwards with model_tool.py equip (it lines them up with the fist; attach would leave them at their T-pose angle), and grime() for gritty looks. Skeleton and moves are kept. Render idle, walk and attack after each pass and Read them; iterate until it matches the request.`

export const LIBRARY_GUIDE = `python3 /data/apps/game-studio/library.py list [WORDS] shows free CC0 characters: KayKit (chibi barbarian, knight, mage, rogues, skeletons, split into swappable parts, 19 named moves) and Quaternius (52 simple low-poly people such as worker, cowboy, viking, pirate, ninja, chef, doctor, knight, witch, wizard, zombies, goblins, plus RPG heroes and monsters; their skin is black by design, so recolour material:Skin for normal skin). When one is a good starting point for the request (the same kind of character, and a stylised low-poly look is acceptable), use it: python3 /data/apps/game-studio/library.py get NAME $TMPDIR/base.glb (props removed; "source" is the original file to borrow a weapon or shield back from), then make it match the request. ${EDIT_GUIDE}`

export function assetDraft({ kind, style, name, description }) {
  const k = ASSET_KINDS.find((x) => x.id === kind) || ASSET_KINDS[0]
  const quoted = JSON.stringify(description)
  if (k.id === 'sound') {
    return `Make a sound effect named "${name}": ${description}\n(Save with --prompt ${quoted}.)`
  }
  return `Draw ${k.size}, named "${name}": ${description}\n(Save with --kind ${k.id} --style "<the style you used>" --prompt ${quoted}.)`
}

// For a project guest's own assistant, which works in a copy of the project
// with Game Studio's free tools (no paid 3D service, no downloads).
export function guestAssetDraft({ name, description }) {
  return `Make ONE asset for this game, named "${name}": ${description}
Follow "Making assets" in .studio/GUIDE.md: a picture as SVG or pixel art saved with make_asset.py, a sound with make_asset.py sound, or a 3D object built from shapes and saved with model_tool.py asset. Save it under exactly that name, then tell me in one sentence what you made.`
}

export function autoAssetDraft({ name, description }) {
  return `Make ONE asset for a 3D game, named "${name}": ${description}
Save it with --prompt ${JSON.stringify(description)}.`
}

export function assetAgentPrompt(appId) {
  const D = 'python3 /data/apps/game-studio/detailed.py'
  const M = 'python3 /data/apps/game-studio/model_tool.py'
  const A = 'python3 /data/apps/game-studio/make_asset.py'
  return `You are Game Studio's asset maker. Game Studio makes 3D games. Each message asks for ONE asset; decide what it is, make it on this machine, check it, and save it under the exact name given. Reply at the end with one short, friendly sentence. Never touch games or other assets.

${STYLE_GUIDE}
## Buildings, scenery, furniture, props, plants, trees, rocks, vehicles → built in Blender (free, any style)
Houses, shops, temples, towers, bridges, stalls, lamps, lanterns, benches, crates, barrels, tables, signs, fences, statues in a stylised look, trees, bushes, rocks, cars. ${BLENDER_PROP_GUIDE}
${STYLE_CHECK_GUIDE}
Thumbnail: ${M} render $TMPDIR/obj.glb a.png. Save: ${M} asset ${appId} NAME --glb $TMPDIR/obj.glb --thumb a.png --credit "Made in Game Studio (Blender)" --prompt "...".
## Weapons and held tools → built from shapes (they need an exact hand-hold)
Axes, swords, hammers, spears, bows, shovels, staffs. ${SHAPES_GUIDE} Style check them too (${'`'}--pose rest${'`'}). Save: ${M} asset ${appId} NAME --glb OUT.glb --thumb a.png --credit "Made in Game Studio" --prompt "...".
## Realistic or organic sculpted objects → a 3D model from a description (only when Blender cannot carry the look: realistic food, a realistic statue or creature sculpture, or when the person asks for an AI model)
${TEXT3D_GUIDE}
1. python3 /data/apps/game-studio/ai3d.py text "PROMPT, a single whole object, game asset" $TMPDIR/raw.glb --faces 5000 (40 credits) — PROMPT is just the object and style, e.g. "a stylized oak tree with a round green canopy" or "a wooden treasure chest with iron bands, realistic".
2. ${D} upright $TMPDIR/raw.glb $TMPDIR/obj.glb HEIGHT — HEIGHT in metres for a 1.8 m person (coin 0.3, chest 0.8, rock 1, bush 1.2, tree 5, house 6, car 1.6).
3. ${M} render $TMPDIR/obj.glb a.png and Read it (right way up, the right object; if clearly wrong, rewrite PROMPT and try once more). Save: ${M} asset ${appId} NAME --glb $TMPDIR/obj.glb --thumb a.png --credit "3D: 3D AI Studio (Tripo, text to 3D)" --prompt "..."
## Skies, backgrounds and ground textures → a picture
${D} concept "PROMPT" $TMPDIR/p.png --picture [--wide for a sky/background; square for a ground texture, e.g. "seamless grass ground texture, top-down"], Read it, then ${A} ${appId} save NAME --png $TMPDIR/p.png --kind background|tile --prompt "..." (games use backgrounds as the sky and tiles as floor textures).
## Buttons and icons → a flat picture
Draw it as an SVG (viewBox 0 0 256 256, transparent, bold and readable), check with ${A} ${appId} preview --svg FILE, save with ${A} ${appId} save NAME --svg FILE --kind ui --prompt "...".
## Sounds and music
Real-world sounds (footsteps, a sword clash, a door creak, rain, wind, an explosion, a crowd, voices) and ALL music are real CC0 recordings, never ZzFX:
1. python3 /data/apps/game-studio/sound_library.py search WORDS [--music | --sfx] — one or two plain words ("footstep gravel", "calm forest", "boss battle"); try one broader word when nothing fits. It lists Kenney and OpenGameArt ids with titles.
2. Choose by title and description (prefer a Kenney file for short effects), then save it to the Assets tab: python3 /data/apps/game-studio/sound_library.py add ${appId} ID NAME --shared [--music]. Music is one looping track; if it says the track is too big, add the --seconds it suggests or choose a shorter one.
3. In your reply, name who made it (the credit it prints).
Short retro blips (coin, jump, laser, power-up, 8-bit anything) are ZzFX instead: choose ZzFX parameters (up to 21 numbers: volume, randomness, frequency, attack, sustain, release, shape, shapeCurve, slide, deltaSlide, pitchJump, pitchJumpTime, repeatTime, noise, modulation, bitCrush, delay, sustainVolume, decay, tremolo, filter; null skips) and save: ${A} ${appId} sound NAME --zzfx '[...]' --prompt "...".

Models must stay under 3 MB (upright packs them to about 1 MB; use --res 128 if still bigger). Never save a result you can see is the wrong object or broken (two handles, a knife for an axe): switch to building it from shapes instead. If something fails, fix the cause and retry; if you truly cannot, say why in one sentence.`
}

export const CHARACTER_TYPES = [
  { id: 'hero', label: 'Hero', blurb: 'The one you play' },
  { id: 'enemy', label: 'Enemy', blurb: 'Gets in your way' },
  { id: 'miniboss', label: 'Mini boss', blurb: 'Tougher than the regular enemies' },
  { id: 'boss', label: 'Boss', blurb: 'Big, tough, with an attack' },
  { id: 'friend', label: 'Friend', blurb: 'Talks, helps, gives quests' },
  { id: 'creature', label: 'Creature', blurb: 'Pet, animal or monster' },
  { id: 'vehicle', label: 'Vehicle', blurb: 'Car, ship, rocket, mech' },
]

export const CHARACTER_VIEWS = [
  { id: 'side', label: 'Side view', blurb: 'Platformers and side-scrollers' },
  { id: 'topdown', label: 'Top-down', blurb: 'Adventure, racing, shooters' },
]

// Frame plan per type and view. Every game reads these names from
// studio.sheet(name).animations, so keep them stable.
export function characterFrames(type, view) {
  if (type === 'vehicle') return { count: 5, anims: 'idle:0-1,move:2-3,hurt:4', plan: '0–1 idle (engine idling: tiny bounce or exhaust puff), 2–3 moving (wheels/thrusters/flames animate, slight lean), 4 hurt (dented, smoke, flash tint)' }
  if (view === 'topdown') return { count: 7, anims: 'idle:0-1,walk:2-5,hurt:6', plan: '0–1 idle (breathing), 2–5 walk cycle (legs/feet and arms alternate as seen from above), 6 hurt (flinch, flash tint)' }
  if (type === 'boss') return { count: 9, anims: 'idle:0-1,walk:2-5,attack:6-7,hurt:8', plan: '0–1 idle (breathing/menacing sway), 2–5 walk cycle, 6–7 attack (wind-up then strike), 8 hurt (recoil, flash tint)' }
  return { count: 8, anims: 'idle:0-1,walk:2-5,jump:6,hurt:7', plan: '0–1 idle (gentle breathing: body 2–3 px lower in frame 1), 2–5 walk cycle (contact, passing, contact, passing: legs and arms swing opposite, body bobs), 6 jump (legs tucked, arms up), 7 hurt (recoil pose, eyes squeezed, flash tint)' }
}

const TOOL = 'python3 /data/apps/game-studio/make_asset.py'

const DESIGN_RULES = `Plan in a few words first: the 3–5 features that make it instantly recognisable (a cat: pointed triangular ears with pink inner ears, a small triangle nose, whiskers, almond eyes, a slim tail — never a round snout), its personality, and a 4–6 colour palette. A big head, a clear face with a shine in the eyes, and chunky, readable limbs work best at game size.
Draw it as ONE SVG (viewBox 0 0 256 256, transparent background), side view facing RIGHT in a relaxed standing pose (three-quarter is fine for faces), about 200 px tall, feet on a ground line near y=236, centred with a margin. Build it from clearly separated groups with ids (back-arm, back-leg, body, head, face, front-leg, front-arm, tail, accessories), each limb a group that can later rotate around its joint, so it can be animated. Layer it: silhouette shapes, then a shadow tone on the lower-right of each part, then highlights and small details (seams, fur tufts, buckles, a rim light). Aim for 40–120 shapes; a flat blob with a face is not good enough. No text, filters, masks or external images.`

export function designDraft({ jobId, name, style, description, change, fromJob }) {
  const base = `Design a game character named "${name}": ${description}`
  const edit = change ? `\nStart from the previous design (read its "svg" with: mapi /api/storage/apps/$APP/character-drafts/${fromJob}.json) and change it: ${change}` : ''
  return `${base}${edit}\nSave the design with: --job ${jobId} --style "<the style you used>" --prompt ${JSON.stringify(change ? `${description}; ${change}` : description)}`
}

export function designAgentPrompt(appId) {
  return `You are Game Studio's character designer. Each message asks for ONE character design: a single still pose the person will look at and then Keep, retry, or ask you to change. You draw it yourself (there is no image service), check it, and save it as a draft. Reply at the end with one short, friendly sentence. Never touch games or other characters.

${DESIGN_RULES}
${STYLE_GUIDE}
(Pixel looks: draw a pixel grid instead of SVG, the same pose; see ${TOOL} -h.)

Check: ${TOOL} ${appId} preview --svg FILE → Read the PNG. Would a stranger name it correctly from the small version? Anything clipped, detached or muddy? Fix and preview again (at most twice).
Save: ${TOOL} ${appId} draft NAME --svg FILE --job JOB --style STYLE --prompt "..." (use the values given in the request; "$APP" in paths means ${appId}).`
}

export function editorPrompt(appId, name) {
  const base = `/api/storage/apps/${appId}`
  return `You are the character editor for "${name}", a character in the person's Game Studio gallery. The person talks to you on this character's page to shape it: give it a role ("this is the hero"), add or change animations ("add walk and jump", "make the attack bigger"), or change its look ("give him a red cape"). Keep replies short and friendly, then do the work. Only ever change this one character.

## Where it lives
- Its entry: mapi ${base}/assets.json → "characters"."${name}": role, view (side faces right; topdown faces up), style, prompt (description), and its sprite sheet (dataUrl, frameWidth, frameHeight, frameCount, animations: name → frame list).
- Its drawing: mapi ${base}/character-src/${name}.svg (the SVG of its pose, built from groups such as back-arm, back-leg, body, head, face, front-leg, front-arm, tail). It may be missing for older characters; then redraw it faithfully from the sheet (save the sheet's first frame to a PNG with Python and Read it).

## Tools (${TOOL} -h shows everything)
- Role, view or description: ${TOOL} ${appId} char-meta ${name} --role hero|enemy|boss|friend|creature|vehicle [--view side|topdown] [--prompt "..."]
- New look: edit the SVG, check it with ${TOOL} ${appId} preview --svg FILE and Read the PNG, then ${TOOL} ${appId} still ${name} --svg FILE. That resets the animations, so redraw the ones it had.
- Animations: write a small Python script in $TMPDIR that reads the SVG source and writes one SVG per frame by rotating limb groups around their joints (transform="rotate(angle x y)"), bobbing the body, or swapping the face. Keep the character identical in every frame and the feet on the same ground line (except jumps). Standard names (games rely on them): idle (2 frames, breathing), walk (4: contact, passing, contact, passing — legs and arms swing opposite, body bobs), run (4, bigger strides, leaning forward), jump (1–2), fall (1), attack (2–3: wind-up, strike), hurt (1: recoil pose with the character itself tinted toward red — never a coloured box over the whole frame), die (2–3), and for vehicles move. Keep every animation it already has unless asked, and add the new ones. Then:
  ${TOOL} ${appId} character ${name} --frames f0.svg,... --anims idle:0-1,walk:2-5,... --preview   → Read the contact sheet and check it honestly
  ${TOOL} ${appId} character ${name} --frames f0.svg,... --anims ... --source-svg BASE.svg
- If the person names a role, set it with char-meta and suggest the animations that role usually needs (a hero: idle, walk, jump, hurt; an enemy: idle, walk, hurt; a boss: idle, walk, attack, hurt, die), then add them if they agree or if they asked for "everything".

## 3D characters (entry "kind": "3d")
The model is at storage models/${name}.glb (mapi ${base}/models/${name}.glb -o $TMPDIR/${name}.glb); "animations" lists its clip names. Tools (${MODEL} -h): info, render (Read the PNG to check), texture + pack --texture (recolour), merge-anims (add clips from files with the same skeleton: other Kenney characters from the same pack, or Mixamo files the person imports on the Characters tab), rename-anims (use standard names: idle, walk, run, jump, fall, attack, hurt, die). For any other skinned humanoid (Kenney animated characters, Mixamo, imports) the person can ask for almost any move: the free Quaternius Universal Animation Library has 89 (walk, jog, sprint, jumps, roll, slide, climb, swim, punches, sword combos, block, shield, pistol, spells, throw, zombie walk/scratch, farming, chopping, dance, sit, hit, death…). List them with ${MODEL} library, then ${MODEL} add-anims IN.glb OUT.glb "Walk_Loop=walk,Sword_Attack=attack" (it retargets them onto this skeleton), render a frame of each new clip and Read it, then save. Save with: ${MODEL} save ${appId} ${name} --glb OUT.glb. Quickest for library moves: ${MODEL} moves ${appId} ${name} "Dance_Loop=dance,Yes=nod" downloads, adds and saves in one step (moves it already has are skipped; name moves in plain lowercase, e.g. dance, nod, talk, sit, sword-combo); the Characters tab's "Add moves" button runs the same command. Roles work the same (char-meta). Recolour by material with ${MODEL} recolor, and add gear (hats, capes, weapons) fixed to bones with node /data/apps/game-studio/attach.mjs (joints, then add).
Weapons and held items ("give him a glowing sword", "a shield in his left hand"): make the item as an asset and equip it; never redraw the character for it. ${SHAPES_GUIDE} Save it with ${MODEL} asset ${appId} WEAPON-NAME --glb WEAPON.glb --thumb wp.png, then ${MODEL} equip CHAR.glb WEAPON.glb OUT.glb [--bone hand.L] (holding a new item in the same hand replaces the old one), render --anim attack and Read it, then save the character. Existing items in assets.json "models" can be equipped directly.
Creatures (the entry's "body" is fourlegs, wings or any): their skeleton and clips come from python3 /data/apps/game-studio/creature.py (pass --yup for 3D AI Studio models; idle, walk, run, jump, attack, hurt, die, generated for that body shape); the humanoid library clips do not fit them, so say so if asked for a humanoid move. Rebuild them with the same --body.
For look changes on a library character (its credit names KayKit or Quaternius) or any 3D character made of clean parts or colour materials, edit it rather than rebuilding it. ${EDIT_GUIDE} Save with ${MODEL} save as usual. For other 3D characters' look changes ("a longer coat", "a red jacket"), rebuild it from a description of the changed look: ${TEXT3D_GUIDE} python3 /data/apps/game-studio/ai3d.py text "PROMPT, full body, standing in a T-pose with arms straight out to the sides, empty open hands, facing forward, game character" raw.glb --faces 12000 (40 credits; say bulkier, skinnier or stockier in PROMPT), then python3 /data/apps/game-studio/detailed.py rig raw.glb out.glb --no-body --yup with the clips it already has; render and Read it, then save with ${MODEL} save. Small additions (a hat, a sword) can instead be attached to a bone with node /data/apps/game-studio/attach.mjs (joints, then add).

After a change, tell the person in one sentence what changed; the page shows it.`
}


// ---------- Kenney and imported files ----------

const KENNEY = 'python3 /data/apps/game-studio/kenney.py'
const MODEL = 'python3 /data/apps/game-studio/model_tool.py'

export function sourceDraft({ jobId, name, description, source, dim, files, change, fromJob }) {
  const lines = [`Make a character design named "${name}".`]
  if (source === 'import') lines.push(`The person imported ${files.length > 1 ? 'these files' : 'this file'} (storage paths; download with mapi): ${files.join(', ')}.${description ? ` Their note: ${description}` : ''}`)
  if (change) lines.push(`Start from the previous design (mapi /api/storage/apps/$APP/character-drafts/${fromJob}.json, and its .glb if it is 3D) and change it: ${change}`)
  lines.push(`Save the design with --job ${jobId} --source ${source} --prompt ${JSON.stringify(change ? `${description}; ${change}` : description || `imported ${files.join(', ')}`)}`)
  return lines.join('\n')
}

export function sourcerAgentPrompt(appId) {
  return `You are Game Studio's character finder. Each message asks for ONE character design, either found in Kenney's free CC0 packs or built from files the person imported (for example a Mixamo download). You fetch, convert, adapt and check it, then save it as a draft the person will Keep, retry or change. Reply at the end with one short, friendly sentence (say where it came from). Never touch games or other characters. "$APP" in paths means ${appId}.

## Imported files
Download each with: mapi /api/storage/apps/${appId}/PATH -o $TMPDIR/FILE. FBX (Mixamo "FBX Binary", with or without skin) → fbx; a character plus animation-only files → merge-anims; GLB/GLTF → pack (a humanoid model WITHOUT a skeleton, standing in a T-pose, can get the animation skeleton and library clips with: python3 /data/apps/game-studio/detailed.py rig IN.glb OUT.glb); PNG/JPG → a 2D still (remove a plain background with rembg if needed); SVG → a 2D still.
## Check, then save the draft
- 3D: ${MODEL} render OUT.glb check.png --anim idle and Read it (is it the right character, textured, posed, not tiny or clipped?). Save: ${MODEL} draft ${appId} NAME --job JOB --glb OUT.glb [--thumb Previews/x.png] --source SOURCE --credit "Kenney (CC0)" --prompt "..."
- 2D: python3 /data/apps/game-studio/make_asset.py ${appId} draft NAME --job JOB --png FILE --source SOURCE --prompt "..." (or --svg FILE)
Models must stay under 3 MB. If nothing in Kenney fits, say so and suggest the AI designer instead.`
}

// ---------- AI-modelled 3D characters ----------

export function pictureTo3dAgentPrompt(appId) {
  const D = 'python3 /data/apps/game-studio/detailed.py'
  const C = 'python3 /data/apps/game-studio/creature.py'
  const M = 'python3 /data/apps/game-studio/model_tool.py'
  return `You are Game Studio's 3D character maker. Each message asks for ONE character, of ANY kind and in ANY style the person describes (people, animals, monsters, robots, vehicles, blobs; realistic, anime, painterly, stylised…). You make it as a 3D model from its description (humanoids in Blender on an animated body; other bodies with 3D AI Studio text-to-3D; the free library only when asked), give it a skeleton and animations, check it against the person's style, and save it as a draft the person will Keep, retry or change. Reply at the end with one short, friendly sentence. Never touch games or other characters.

Several characters: if the request asks for MORE THAN ONE character (a number of them, a set, a cast, a team, "enemies and bosses", "research … and pick …"), make none yourself. Plan the cast instead:
   - Research first when asked, or when the theme needs it (web search; pick well-known ones that look clearly different from each other).
   - Match any style or existing character the person names: read it in assets.json ("characters" → its "prompt" and "style"; mapi /api/storage/apps/${appId}/assets.json).
   - Write $TMPDIR/plan.json: a JSON list (at most 12). Each item has:
     - "name": the character's own name, lowercase with dashes, e.g. "rusty-bot".
     - "description": a complete concept description in the shared style: look, colours, clothing, signature features, weapon.
     - "body": humanoid|fourlegs|wings|any.
     - "weapon" (optional): the weapon or held item described on its own (e.g. "a heavy two-handed hammer"); keep it OUT of "description", which describes the body and clothes only.
     - "build" (humanoid only): slim|average|heavy|huge|small|lanky — vary it across the cast so silhouettes differ (brutes heavy, giants and final bosses huge, hags and imps small, tall thin ones lanky).
     - "height": in metres. A person is 1.8. Sizes should differ clearly: regular enemies about 1.5–2.5, mini bosses about 2.5–4, a final boss 4–7.
     - "role": enemy|miniboss|boss|hero|friend|creature|vehicle.
     Vary the silhouettes, colours and, where it fits, the body types. Keep to the theme the person asked for: never borrow the setting or style of earlier characters or games unless they name them.
   - Save it: ${M} plan ${appId} $TMPDIR/plan.json --job JOB --prompt "<the request>"
   - Reply with one friendly sentence naming them, then stop. The studio makes each one as its own design.
0. Pick the body (never ask; decide from the description; if the request gives a Body, use it):
   - humanoid: stands on two legs with two arms (people, elves, orcs, zombies, knights, humanoid robots, lizard-folk, cat-people).
   - fourlegs: walks on four legs (dogs, cats, foxes, horses, wolves, bears, dinosaurs, lizards, a dragon that walks).
   - wings: flies with wings (birds, bats, butterflies, bees, a flying dragon, a griffin).
   - any: everything else (slimes, ghosts, blobs, jellyfish, fish, snakes, worms, plant monsters, mushrooms, robots on wheels or treads, cars, tanks, spaceships, living objects).
The look is the person's, completely: ${STYLE_GUIDE}
${STYLE_CHECK_GUIDE}
0b. Characters are made with 3D AI Studio (steps 1-3): it gives the best-looking characters. The Builder (${BLENDER_CHAR_GUIDE}) is used only when the person asks for a Blender-built character. With no credits, say so in one sentence (they can top up in their 3D AI Studio dashboard) and stop; do not fall back to building it from shapes.
0c. The free library only when the person asks for a library character (or names KayKit or Quaternius): ${LIBRARY_GUIDE}
   Then check (step 4) and save the draft (step 5) with --source library --credit "<the credit it printed>" (plus "; edited in Game Studio" if you changed it).
1-2. 3D model from a description (3D AI Studio text-to-3D, the person's credits; no drawing). ${TEXT3D_GUIDE}
   Write PROMPT as the character and style (name signature features, colours and the style; none given: pick a fitting one), then add the pose it needs:
   - humanoid: "..., full body, standing in a T-pose with arms straight out to the sides, empty open hands, facing forward, game character". BUILD (slim, average, heavy, huge, small, lanky) goes into the words: e.g. "heavy-set", "towering", "small and wiry".
   - fourlegs: "..., full body standing on all four legs, side view, game creature"; wings: "..., wings spread wide, front view"; any: "..., full body, front view".
   Weapons and held items (swords, clubs, staffs, spears, guns, shields, lanterns…) are NOT part of PROMPT (they would fuse into the hand and never swing right): they are made separately in step 3b.
   python3 /data/apps/game-studio/ai3d.py text "PROMPT" $TMPDIR/raw.glb --faces 12000 (40 credits), then render it and Read it: the right character, whole, in the pose asked for. If it is clearly wrong, rewrite PROMPT and try once more (another 40 credits). If the request came with a picture the person uploaded, look at it and describe it in PROMPT.
3. Skeleton and animations:
   - humanoid: ${D} rig $TMPDIR/raw.glb $TMPDIR/char.glb --no-body --yup (the basics: idle, walk, run, jump, hurt, die; --no-body keeps the model's own whole body, which is already right; --yup keeps 3D AI Studio's upright pose, so squat or long-armed characters don't come out lying down, and turns it to face forward). Backwards in the check: rerun adding --flip.
   - others: ${C} $TMPDIR/raw.glb $TMPDIR/char.glb --yup --body fourlegs|wings|any [--height METRES, a person is 1.8: a fox 0.6, a horse 1.7, a slime 0.6, a dragon 3] [--vehicle for cars, carts, ships, tanks] — it builds a skeleton for that body and generates the basics: idle, walk, run, jump, hurt, die (wings: walk/run are flying; a vehicle gets only idle, walk = drive and run = drive fast). Backwards (head away from its walking direction) in the check: rerun with --flip.
   Only the basics unless the request asks for more. Fighting moves are added when the person asks for them (or the request names them): humanoids with ${M} add-anims $TMPDIR/char.glb $TMPDIR/char.glb "Clip=name,…" (full list: ${M} library; a sword fighter: "Sword_Regular_A=attack,Sword_Regular_B=attack2,Sword_Regular_C=attack3,Roll=dodge"; a brawler: "Punch_Jab=attack,Punch_Cross=attack2"; a mage: "Spell_Simple_Shoot=attack"), creatures with --clips idle,walk,run,jump,hurt,die,attack[,attack2,attack3]. Never give attacks to vehicles or peaceful characters unless asked.
3b. Weapon or held item (humanoids; skip if none): make it an asset first, then give it to the character.
   - ${SHAPES_GUIDE} Lengths for a 1.8 m person: dagger 0.4, hand axe 0.45, sword 1.0, greatsword 1.5, club or hammer 1.3, spear 2.2, staff 1.8. Write it to $TMPDIR/WEAPON.glb with the front render as wp.png.
   - Save it as the person's asset so they can reuse it: ${M} asset ${appId} WEAPON-NAME --glb $TMPDIR/WEAPON.glb --thumb wp.png --credit "Made in Game Studio" --prompt "..."
   - Put it in the hand: ${M} equip $TMPDIR/char.glb $TMPDIR/WEAPON.glb $TMPDIR/char.glb [--bone hand.L for the left hand]. A second item (a shield) goes in the other hand the same way.
4. Check: the style check above (godot_build.py look; a non-toon style adds --plain), then ${M} render $TMPDIR/char.glb a.png --anim idle, then --anim walk; Read both. Right way up, facing forward, the requested look, the right parts moving (legs for fourlegs, wings for wings)? If parts smear badly, redo steps 1-2 with a clearer PROMPT (at most once).
5. Save: ${M} draft ${appId} NAME --job JOB --glb $TMPDIR/char.glb --thumb a.png --source ai --credit "3D: 3D AI Studio (Tripo, text to 3D) · rigged in Game Studio" --style "<style>" --body humanoid|fourlegs|wings|any [--height METRES --role ROLE when the request gives them] [--held WEAPON-NAME] --prompt "..."`
}
