#!/usr/bin/env python3
"""Build a game's Project into one playable page (the Project's "Play" build).

Run by project/play_build.sh when anyone with edit access presses Build on a
Game Studio game's Project, so collaborators can play their changes without
Game Studio. Möbius sets PROJECT_ROOT and PROJECT_OUTPUT_DIR.

1. A game written as modules (build.py + src/) is put together into game.html
   first, so a collaborator's edit to src/ shows up. That new game.html also
   reaches Game Studio with the next sync, like any other project edit.
2. The game gets the same art, sounds and 3D models Game Studio gives it: this
   game's art, its art kit, and the Characters and Assets tabs.
3. play_bundle.mjs packs the engine into the page (previews have no network).

Saves start empty and the Möbius voice is not available here; Game Studio and
published game apps keep those.
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path('/data')
TOOLS = HERE / '.build' / 'tools'
ESBUILD = '0.28.2'
# Decode meshopt models at build time: the Play preview cannot run WebAssembly (unpack_models.mjs).
GLTF_TOOLS = ['@gltf-transform/core@4.5.1', '@gltf-transform/extensions@4.5.1', 'meshoptimizer@0.22.0']


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def ensure_esbuild():
    modules = TOOLS / 'node_modules'
    if (modules / 'esbuild' / 'package.json').exists() and (modules / 'meshoptimizer' / 'package.json').exists():
        return
    print(f'First Play build: installing the bundler (esbuild {ESBUILD}) and model tools...', flush=True)
    TOOLS.mkdir(parents=True, exist_ok=True)
    if not (TOOLS / 'package.json').exists():
        (TOOLS / 'package.json').write_text('{"private": true}\n')
    subprocess.run(['npm', 'install', '--silent', '--no-audit', '--no-fund', '--prefix', str(TOOLS),
                    f'esbuild@{ESBUILD}', *GLTF_TOOLS], check=True)


def merge_art(kit, own):
    kit, own = kit or {}, own or {}
    pick = lambda key: {**(kit.get(key) or {}), **(own.get(key) or {})}
    return {
        'title': kit.get('title'), 'style': kit.get('style'), 'font': own.get('font') or kit.get('font'),
        'palette': {**(kit.get('palette') or {}), **(own.get('palette') or {})}, 'credit': kit.get('credit'),
        'images': pick('images'), 'sheets': pick('sheets'), 'sounds': pick('sounds'), 'models': pick('models'), 'voices': pick('voices'),
    }


def with_library(art, assets):
    """Mirror of gameRuntime.withLibrary: the Characters and Assets tabs feed every game."""
    sheets, images = {}, {}
    for name, c in (assets.get('characters') or {}).items():
        sheets[name] = {k: c.get(k) for k in ('dataUrl', 'frameWidth', 'frameHeight', 'frameCount', 'animations')}
        if c.get('thumb'):
            images[name] = {'dataUrl': c['thumb']}
    for name, sprite in (assets.get('sprites') or {}).items():
        images[name] = {'dataUrl': sprite.get('dataUrl'), 'w': sprite.get('width'), 'h': sprite.get('height')}
    # Sound files from the Assets tab, once the caller has put each file's bytes in a dataUrl.
    sounds = {name: a['dataUrl'] for name, a in (assets.get('audio') or {}).items() if isinstance(a, dict) and a.get('dataUrl')}
    cast = [{'name': n, 'role': c.get('role'), 'height': c.get('height'), 'body': c.get('body') or 'humanoid',
             'animations': c.get('animations') or [], 'held': c.get('held') or []}
            for n, c in (assets.get('characters') or {}).items() if c.get('kind') == '3d']
    return {**art, 'images': {**(art.get('images') or {}), **images}, 'sheets': {**(art.get('sheets') or {}), **sheets},
            'sounds': {**(art.get('sounds') or {}), **sounds}, 'cast': cast}


def named_in(html, name):
    return re.search(r'''['"`]''' + re.escape(name) + r'''['"`]''', html) is not None


def main():
    root = Path(os.environ['PROJECT_ROOT'])
    out = Path(os.environ['PROJECT_OUTPUT_DIR'])

    if (root / 'build.py').is_file() and (root / 'src').is_dir():
        # A game's build.py writes game.html, which syncs to the studio. Without its
        # packages it would quietly write a lesser game (e.g. no brush font), so put
        # them back first and, if that fails, play the game.html already there.
        try:
            sys.path.insert(0, str(HERE))
            import gs_deps  # noqa: F401  (reinstalls packages after a container replacement)
            ready = True
        except Exception as err:
            ready = False
            print(f'Packages for build.py could not be installed ({err}); playing the current game.html.', flush=True)
        if ready:
            print('Putting the game together from src/ ...', flush=True)
            subprocess.run([sys.executable, 'build.py'], cwd=root, check=True)

    html_path = root / 'game.html'
    if not html_path.is_file():
        sys.exit('This project has no game.html yet. Make the game in Game Studio first.')
    html = html_path.read_text()
    game = read_json(root / 'game.json') or {}
    if os.environ.get('PROJECT_APP_STORAGE'):
        # A restricted build (one guests' changes can reach) sees no Game Studio
        # storage, only copies of what mobius.json lists in storage_reads.
        studio = Path(os.environ['PROJECT_APP_STORAGE'])
    else:
        sid = game.get('studioAppId')
        studio = DATA / 'apps' / str(sid) if isinstance(sid, int) else None
        if studio is None or not studio.is_dir():
            sys.exit('game.json does not name an installed Game Studio ("studioAppId").')

    gid = game.get('id')
    meta = read_json(studio / 'games' / f'{gid}.json') or game
    assets = read_json(studio / 'assets.json') or {}
    kit = read_json(studio / 'art' / f"{meta['art']}.json") if meta.get('art') else None
    own = read_json(root / 'art.json') or read_json(studio / 'games' / f'{gid}.art.json')
    models = {}
    for name in (assets.get('models') or {}):
        glb = studio / 'models' / f'{name}.glb'
        if ('studio.models(' in html or named_in(html, name)) and glb.is_file():
            models[name] = base64.b64encode(glb.read_bytes()).decode('ascii')
    for name, entry in list((assets.get('audio') or {}).items()):
        mp3 = studio / 'audio' / f'{name}.mp3'
        if ('studio.sounds(' in html or named_in(html, name)) and mp3.is_file():
            assets['audio'][name] = {**entry, 'dataUrl': 'data:audio/mpeg;base64,' + base64.b64encode(mp3.read_bytes()).decode('ascii')}
    data = {'sprites': assets.get('sprites') or {}, 'sounds': assets.get('sounds') or {}, 'models': models,
            'art': with_library(merge_art(kit, own), assets), 'saves': {}}

    ensure_esbuild()
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tmp:
        json.dump(data, tmp)
    try:
        env = {**os.environ, 'GS_TOOLS_DIR': str(TOOLS)}
        subprocess.run(['node', str(HERE / 'unpack_models.mjs'), tmp.name], env=env, check=True)
        subprocess.run(['node', str(HERE / 'play_bundle.mjs'), str(html_path), tmp.name, str(out / 'play.html')],
                       env=env, check=True)
    finally:
        os.unlink(tmp.name)
    print(f"{game.get('name') or 'Game'}: {len(models)} model(s) packed in. Press Play to try it.")


if __name__ == '__main__':
    main()
