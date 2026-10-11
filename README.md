# Game Studio

Describe a game and the studio's agent builds a playable version that runs on phones and computers. Make sprites and sounds in the Assets tab, and every game can use them by name.

- **Play:** the game runs full-screen-ready. On phones it gets on-screen stick and buttons, and it supports keyboard, gamepads, and (on Möbius installs with `device.motion`) phone tilt.
- **Create:** one agent chat per game. The agent writes the game into app storage and the studio reloads it and saves a version after every turn.
- **Assets:** procedural pixel sprites (hero, ship, enemy, item, tiles), picture upload, and ZzFX sound effects.
- **Real sounds and music:** `sound_library.py` finds CC0 recordings in Kenney's audio packs and on OpenGameArt, converts them to MP3 (plays on every phone), trims and levels them, and saves them into one game or the Assets tab. Games play them with `studio.sound(name)` and `studio.music(name)`; scene games with `settings.music` and `api.sound` / `api.music`.
- **Real skies and ground:** `world_library.py` adds Poly Haven 360° skies (`settings.skybox`: backdrop and lighting) and Poly Haven / ambientCG ground materials (terrain `surface`: colour, normal and roughness maps) to scene games.
- **Single files from packs:** `packzip.py` reads a pack's file list and single files straight out of its zip with ranged downloads, so the studio never downloads a whole pack for one model or sound (art kits, `kenney.py`, ambientCG materials).

Games are single HTML files. They use Phaser 3 or three.js loaded from esm.sh, plus an injected `studio` helper (see `gameRuntime.js` and `agentPrompt.js`).

Credits: ZzFX by Frank Force (MIT, `zzfx.js`). Sounds, music, skies and materials come from Kenney, OpenGameArt (CC0 entries only), Poly Haven and ambientCG, all CC0; each saved item records its credit. Sprite generation follows the approach of zfedoran's pixel-sprite-generator.
