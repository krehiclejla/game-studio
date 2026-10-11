# Scene games: the format

A scene game is `scene.json` (in the game's Project): settings, objects and small
scripts. `sceneRuntime.js` builds it into a 3D world; the studio edits it live and
`scene.py` is how the assistant changes it. Units are metres; a person is 1.8 m tall;
+y is up. The player starts facing +z... the camera follows from behind.

```json
{
  "version": 1,
  "name": "Meadow Walk",
  "settings": {
    "sky": "#9fc9ea",
    "fog": { "color": "#cfe3f0", "near": 30, "far": 140 },
    "light": { "sun": "#fff4e0", "sunIntensity": 2.2, "sunAngle": 50, "sunDirection": 35, "ambient": 1.0, "skyLight": "#ffffff", "groundLight": "#445544" }
  },
  "winMessage": "You found them all!",
  "objects": [ { "id": "ground", "type": "terrain", "shape": "flat", "size": 60, "color": "#6fa34d", "position": [0, 0, 0] } ],
  "scripts": [ { "name": "rules", "code": "api.onUpdate(dt => { ... })" } ]
}
```

`settings.style: "ps2"` gives the whole game a PlayStation 2 look (low resolution,
hard shadows, fewer polygons). When a game has it, keep everything you add in that
style: simple low-poly shapes, flat or simple colours, low-detail meshes and particles
in scripts (no fine subdivisions, no smooth high-res effects). The style also adds a grimy
surface texture to every solid object (`"clean": true` on an object turns it off, e.g. for
glowing things like embers or lamp glass), film grain and a vignette.

`settings.style: "toy"` gives a bright, glossy, cartoony look, like plastic toys under
studio lights: shiny clear-coated objects and models, saturated colour and a soft rim light.
Pair it with bright, saturated colours, rounded shapes and a vivid sky.

`settings.skybox: "name"` replaces the flat `sky` colour with a real photographed 360° sky
(added to the game with `python3 /data/apps/game-studio/world_library.py add ... sky ...`): it is
the backdrop AND lights the scene (soft sky colour, reflections in shiny things).
`settings.skyboxLight` (0–2, default 1) scales that light; `settings.skyboxBrightness` (default 1.1)
the backdrop. Keep `fog` in a colour from the sky's horizon so distant land blends into it.

A terrain's `"surface": "name"` covers it with a real ground material (grass, sand, dirt, rock,
snow, cobbles...; added with `world_library.py add ... ground ...`), repeating every
`"surfaceSize"` metres (default 3; the tool prints the real size). With a surface, `color` /
`color2` only tint it (leave them out for the natural look). Works on flat, hills, mountains,
island and border terrain; not on floating islands.

`settings.music: "name"` plays that sound file as looping background music while the game is
played (`settings.musicVolume`, 0–1, default 0.5). Find and save a track with
`python3 /data/apps/game-studio/sound_library.py` (see "Sounds and music" in the assistant guide).

`settings.performance: false` turns off the runtime's performance defaults, which are on
for every game: static models are skipped when off screen, small props are not drawn once
they are only a few pixels (or past the fog), the resolution drops by up to 40% when frames
stay slower than about 30 fps, and shaders compile before play starts. Terrain, water,
lights, characters, the player and `backdrop` objects are never hidden by distance.
`window.__sceneStats()` in the page reports draw calls, triangles and frame time.

## Objects

Every object: `id` (unique, lowercase-dashes; scene.py makes one from `name`), `name`,
`type`, `position` `[x, y, z]`, optional `rotation` `[x, y, z]` in degrees,
`scale` (number or `[x, y, z]`), `hidden`, `behaviors` (list).
**`position[1]` = `null` means "standing on the ground"** (terrain or a solid object
under it); give a number only to float something (a coin at 1, a platform at 3).

| type | fields |
| --- | --- |
| `terrain` | `shape`: `flat` \| `hills` \| `mountains` \| `island` (a round island whose coast sits at about 70% of its half-size; add a `water` object around it, e.g. size ×2 at height 0, for the sea) \| `floating` (a sky island, see below); `size` (square side, default 60); `height` (hills/mountains, default 4/12); `seed`; `color`, `color2` (low/high ground); `border`: `true` or `{ "width": 45, "height": 26, "snow", "rock" }` rings the terrain with a snowy mountain range outside its `size` that the player can't cross; island options: `coast` (0–0.35, headlands and bays), `hills` (height of rolling hills around a flat middle), `flat` (radius kept flat; default the paving's), `clear` (`[[x, z, radius], ...]` circles kept flat, e.g. where a bridge lands), `sand` (beach colour); `paving`: `true` or `{ "color", "mortar", "curb", "radius", "stone" }` lays a round cobblestone plaza hugging the ground, with a curb (on an island it stops short of the beach; `stone` is the stone size in metres, default 0.55); `river`: `{ "points": [[x, z], ...], "width": 4, "depth": 1.2, "color", "bed", "flow": 1 }` carves a river channel along the points (terrain coordinates) with flowing water in it (not with `border`) |
| `water` | `size`, `color`, `opacity`, `roughness` (0.15; higher = softer reflections); put it at a small height, e.g. `[0, 0.3, 0]`. The player can't walk into it: they stop at the shore, so an island with a sea around it keeps them on the land (cross to another island with a `walkable` bridge) |
| `box`, `sphere`, `cylinder`, `cone`, `plane` | `color`, `opacity`, `roughness`, `metalness`; size via `scale` (a unit shape; its position is its base) |
| `character` | `character`: a name from the person's Characters (scene.py library); `height` (default: its library height); `animation` (idle by default) |
| `model` | `asset`: a 3D asset name from the library; `height` to size it (default: its own size) |
| `light` | a lamp: `color`, `intensity` (20), `range` (15) |
| `spawn` | a marker (edit mode only) for scripts |

`backdrop: true` marks far scenery (a moon, a star dome, distant mountains): the camera doesn't zoom out to fit it.

`launch`: the id of another game in the studio (e.g. `"mobius-kart"`). In Play, tapping the object (or any part of its group) opens that game full screen; the person closes it to come back. Scripts can do the same with `api.openGame(id)`. `"launch": "app-store"` opens the Möbius App Store instead (in Möbius Worlds: its App Store card); `"launch": "boba"` is Worlds' juice stand (your ghost drinks boba tea there; nothing opens in the studio).

`solid: true` (or a `solid` behavior) makes an object block the player and lets it stand on top.

`walkable: true` on a model (a bridge, stairs, a ramp, a jetty) lets the player walk on its real surface, following its slope and steps (up to about 0.35 m at a time); rails and roofs above them don't count. Unlike `solid`, it doesn't block the way. Over water, the player can't step off its sides.

`group`: a name shared by all the parts of one thing built from several objects (a
house, a tree made of shapes, a car, a fence). In the studio a tap on any part selects
the whole group, which moves, turns, resizes, duplicates and deletes as one. **Always
give every part of a multi-part build the same `group`** (lowercase-dashes, e.g.
`"group": "cabin"`); single parts can still be picked from the scene list.

## Behaviors

| type | what it does | params |
| --- | --- | --- |
| `player` | the one the person controls (stick/WASD, Space jumps; the camera follows and swings behind them as they walk, and dragging turns the view); uses idle/walk/run/jump clips | `speed` (5), `jump` (6) |
| `spin` | turns around | `speed` degrees/s (90) |
| `bob` | floats up and down | `height` (0.3), `speed` (2) |
| `collectible` | picked up by the player; collecting all of them wins (unless scripts decide) | `points` (1), `radius`, `message` |
| `chase` | walks toward the player when near | `speed` (2.5), `range` (12) |
| `hurts` | damages the player on touch (shows health) | `damage` (10), `radius` |
| `trigger` | shows a message when the player comes close | `message`, `radius` (2) |
| `solid` | blocks the player | |
| `script` | custom code for this object: `code` runs once at start with `api`, `self`, `THREE` | `code` |

## Scripts (game rules)

`scripts[].code` runs once when Play starts, with `api` and `THREE`:

- `api.onUpdate(dt => …)`, `api.onLateUpdate(dt => …)` (after animations: pose bones on top of a clip), `api.onCollect(obj => …)`, `api.onStart(fn)`
- `api.get(idOrName)` → `{ id, name, data, object (THREE.Object3D), position, play(clip), hide(), show() }`; `api.all(typeOrBehavior)`; `api.player`
- `api.score`, `api.health` (read/write), `api.time`, `api.input` (`x`, `y`, `a`, `b`)
- `api.buttons(['Jump', 'Axe'])`: the on-screen buttons on touch screens (first = `input.a`/Space, second = `input.b`/X)
- `api.openGame(id)`: open another studio game full screen over this one
- `api.message(text, seconds)`, `api.win(text)`, `api.lose(text)`
- `api.sound(name, { volume, rate })` plays a sound file by name (the game's own or the Assets tab; add one with `sound_library.py`); `api.sound([zzfx params])` plays a ZzFX blip
- `api.music(name, { volume: 0.5, loop: true, fade: 0.8 })` switches the background track (a new one fades the old out); `api.stopMusic()`
- `api.world`, `api.camera`

Keep scripts small and focused (one rule per script, e.g. "timer", "door opens at 5 coins").

## Cutscenes

`api.cutscene(async (c) => { … }, { once: 'intro' })` plays a short scripted scene: black bars
slide in, the player can't move, chasers wait and nothing hurts, and a **Skip** button (or
button B) finishes every remaining step at once. Await each step so it reads top to bottom.
`once` remembers it was seen (in the game's saves) and never plays it again; leave it out to
play every time. It returns a promise (`true` when it played).

- `c.camera(place, lookAt, seconds = 1.5)` glides the camera; `c.cut(place, lookAt)` cuts.
  A place is `[x, y, z]` (`y` null = eye height above the ground there), a THREE.Vector3, or an
  object id/name (looks at its chest).
- `c.walk(who, to, seconds = 2)` walks a character (its `walk` clip) to a place or up to another
  object, then idles. `c.face(who, target)` turns it.
- `c.play(who, clip)` plays one of its moves once and waits (then idle; `{ then: 'dance' }`
  picks what follows, `{ loop: true }` keeps a looping move going without waiting).
- `c.say(text, { who: 'Ana', voice: 'af_heart' })` shows a subtitle and waits until it's read;
  with `voice` it is also spoken (a pre-made line from voice_lines.py with exactly this text and
  voice, otherwise the Möbius voice). Keep lines short.
- `c.wait(seconds)`, `c.message(text, seconds)`.

Who: an object id or name (`'player'` objects too: `api.player.id`). Moves are the character's
clip names (scene.py library lists them); more come from the Characters tab's **Add moves** or
`python3 /data/apps/game-studio/model_tool.py moves APP NAME "Dance_Loop=dance,Yes=nod"`.

```js
api.onStart(() => api.cutscene(async (c) => {
  c.cut([0, 6, 14], 'chief');
  await c.camera([3, 2, 4], 'chief', 2);
  await c.say('The treasure is past the bridge.', { who: 'Chief' });
  await c.play('chief', 'nod');
  await c.walk(api.player.id, 'chief', 1.5);
}, { once: 'intro' }));
```

Use cutscenes for story moments (an intro, a boss appearing, a win), 5–15 s, never in a loop.
`api.inCutscene` is true while one plays (scripts that move things can wait for it).

## Floating islands
`{"type":"terrain","shape":"floating","size":20,"position":[0,8,0]}` is one sculpted sky island: a wavy outline, rolling grass with a sandy rim, and a layered rocky underside tapering into hanging points with rock spikes. `position` is the middle of its grass (lift it with `position[1]`); things with `position[1]` `null` stand on its grass, and walking off the edge means falling. Options: `size` (width, default 24), `height` (how hilly the top is, default 1.2), `depth` (how far the rock hangs down, default size × 0.55), `seed` (a different shape), `spikes` (default 8), `color`/`color2` (grass), `sand`, `rock`/`rock2`. Several at different heights and seeds make a sky archipelago. Dress the top with grass, flower and stone assets.

