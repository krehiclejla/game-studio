# Game Studio kits

A **genre kit** is a playable starting game (`templates/<genre>.html`). An **art kit** (`art/<artId>.json`) is the real art that game draws with. `catalog.json` lists which art kits suit each genre; the studio shows it when you make a new game.

## Art kit spec (`art/<artId>.json`)

```json
{
  "id": "platformer-cartoon",
  "genre": "platformer",
  "title": "Cartoon meadow",
  "style": "Bright, rounded, hand-drawn cartoon",
  "pack": "new-platformer-pack",
  "credit": "Kenney (kenney.nl), CC0",
  "font": "Fredoka",
  "palette": { "sky": "#cfe8ff", "ink": "#2b2d42", "accent": "#ff8a3d", "panel": "#ffffffd9" },
  "images": [
    { "glob": "Sprites/Characters/Default/character_green_*.png", "max": 96, "rename": { "character_green_": "player_" } },
    { "glob": "Sprites/Tiles/Default/terrain_grass_block*.png", "max": 64, "pack": "another-pack-slug" }
  ],
  "sheets": [
    { "name": "tiles", "file": "Tilemap/tilemap_packed.png", "frameWidth": 18, "frameHeight": 18, "frames": { "grass_top": 22, "coin": 151 } }
  ],
  "sounds": ["Sounds/sfx_jump.ogg", "other-pack:Sounds/click.ogg"],
  "models": ["platformer-kit:Models/GLB format/coin-gold.glb"],
  "notes": "One paragraph for the agent: what each name is, sizes, how pieces fit (tile size, which way characters face)."
}
```

- `pack` is a Kenney asset slug (the part after `kenney.nl/assets/`). Only CC0 packs.
- Image names are file stems, lower-cased (`character_green_idle.png` becomes `character_green_idle`; `rename` swaps substrings first).
- `max` downsizes the longest side. Keep a kit under about 1.5 MB: pick what a game in that genre actually needs (a hero with its poses, 2–4 enemies, terrain pieces, pickups, a background, UI bits), not the whole pack.
- Numbered pixel tiles (`tile_0042.png`) are useless to an agent by number: use the packed tilemap as a sheet and name the useful frames.
- `font` is a Google Fonts family that fits the look.
- `palette` names colors the game should use for text, panels and background.

Install with `python3 build_art.py <appId> kit <artId>` and inspect with `python3 build_art.py <appId> list <artId>`.

## Genre template contract (`templates/<genre>.html`)

A template is the first version of every new game in its genre, so it must already feel like a real game:

- A complete single HTML file following the studio agent rules (`agentPrompt.js`): Phaser 3.90 or three 0.180 from esm.sh only; the injected `studio` helper; phone portrait and desktop; `Tap to start`; touch controls via `studio.controls`; score/lives or equivalent, win and lose, restart.
- Draws with its art kit (`studio.preloadPhaser`, `studio.image`, `studio.sheet`, `studio.model`) and **still runs with simple fallback shapes** when the kit is not installed.
- Uses the kit's look: `await studio.fontReady`, then `studio.style.font` and `studio.style.palette` for all text and panels. No default monospace text, no black void background.
- Plays the kit's real sounds with `studio.sound(name, zzfxFallback)`.
- Puts every tunable at the top in one `CONFIG` object (speeds, gravity, spawn rates, level maps as arrays of strings), so the studio agent can reshape the game quickly.
- Under about 600 lines, readable, commented only where a reader needs the why.
- Passes `node playtest.mjs <appId> <gameId>` with no errors, and its screenshots look like a finished small game.
