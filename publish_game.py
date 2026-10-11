#!/usr/bin/env python3
"""Install or update one Game Studio game as its own Möbius app.

  python3 publish_game.py <studioAppId> <gameId> [--icon PNG | --generated-icon] [--no-apply]
  python3 publish_game.py <studioAppId> <gameId> --into-worlds [--no-apply]

Every game made in the studio is also a real app in Möbius: its own name,
icon and full-screen launch, with its art, sounds, models, saves, voice and
tilt. This script packs the game's current file and art into
/data/apps/<slug>/ (from the template in player/) and applies it. Re-running
after any change updates the same app; the studio remembers which app belongs
to which game in its storage at published/<gameId>.json.

The icon is a screenshot from the game's latest playtest when there is one
(or --icon), otherwise a generated tile. An existing icon is kept unless
--icon is given.

--into-worlds publishes the game inside Möbius Worlds instead of as its own
app: Worlds' own bundler for that game (WORLDS_GAMES) refreshes its copy and
Worlds is applied, so people play it from the island. The studio remembers the choice
(published/<gameId>.json "target": "worlds"), so later publishes of the same
game keep going to Worlds unless --as-app is given.

Needs API_BASE_URL and AGENT_TOKEN (present in Möbius agent runs) and Pillow.
Applying needs a Möbius agent run (it calls the apply_app tool); with
--no-apply the folder is written and you apply it yourself.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from build_art import api, storage_get, storage_put_json

ROOT = Path(__file__).resolve().parent
APPS_DIR = ROOT.parent
PLAYER = ROOT / 'player'
CONTROL = Path('/data/platform/backend/scripts/mobius_control_mcp.py')
CHUNK_CHARS = 900_000  # each source file must stay under 1 MiB
MAX_TOTAL_BYTES = 7_500_000  # all source files together must stay under 8 MiB


def js_string(value):
    return json.dumps(value, ensure_ascii=False).replace('</', '<\\/')


def studio_hash(text):
    """Same fingerprint as the studio's hashText, so both agree on 'published'."""
    h = 2166136261
    data = text.encode('utf-16-le')
    for i in range(0, len(data), 2):
        h = ((h ^ (data[i] | data[i + 1] << 8)) * 16777619) & 0xFFFFFFFF
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    while True:
        h, r = divmod(h, 36)
        out = digits[r] + out
        if not h:
            return out


def slugify(name):
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:36].strip('-')
    return slug or 'game'


def belongs_to(slug, game_id):
    """True when /data/apps/<slug> is free or is already this game's app."""
    folder = APPS_DIR / slug
    if not folder.exists():
        return True
    try:
        head = (folder / 'game.js').read_text(encoding='utf8')[:400]
    except OSError:
        return False
    return f'export const GAME = {{"id": {json.dumps(game_id)}' in head


def pick_slug(game, published):
    if published and published.get('slug'):
        return published['slug']
    base = 'game-' + slugify(game.get('name') or game['id'])
    for slug in (base, f"{base}-{game['id'].removeprefix('g-')}", *(f'{base}-{n}' for n in range(2, 100))):
        if belongs_to(slug, game['id']):
            return slug
    sys.exit('Could not find a free folder name for this game.')


def hex_color(value, fallback):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else fallback


# ---------- icon ----------

def icon_from_image(path, target):
    from PIL import Image
    img = Image.open(path).convert('RGB')
    w, h = img.size
    side = min(w, h)
    # Title screens centre their name and art, so take the middle square.
    top = (h - side) // 2
    img = img.crop(((w - side) // 2, top, (w - side) // 2 + side, top + side)).resize((512, 512), Image.LANCZOS)
    img.save(target, 'PNG', optimize=True)


def generated_icon(game, art, target):
    """A tile in the game's palette with its hero sprite (or its initial)."""
    from PIL import Image, ImageDraw, ImageFont
    palette = (art or {}).get('palette') or {}
    top = hex_color(palette.get('sky') or palette.get('bg'), '#3d5afe')
    bottom = hex_color(palette.get('accent') or palette.get('panel'), '#ff7a59')
    size = 512
    img = Image.new('RGB', (size, size))
    t, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (top, bottom))
    for y in range(size):
        k = y / (size - 1)
        ImageDraw.Draw(img).line([(0, y), (size, y)], fill=tuple(int(t[i] + (b[i] - t[i]) * k) for i in range(3)))
    images = (art or {}).get('images') or {}
    hero = next((n for n in images if re.search(r'(player|hero|character|robot|ship)', n, re.I)), None)
    if hero:
        raw = base64.b64decode(images[hero]['dataUrl'].split(',', 1)[1])
        path = Path(tempfile.mkstemp(suffix='.png')[1])
        path.write_bytes(raw)
        sprite = Image.open(path).convert('RGBA')
        scale = 300 / max(sprite.size)
        sprite = sprite.resize((max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))), Image.NEAREST if max(sprite.size) < 64 else Image.LANCZOS)
        img.paste(sprite, ((size - sprite.width) // 2, (size - sprite.height) // 2), sprite)
        path.unlink(missing_ok=True)
    else:
        letter = (game.get('name') or '?').strip()[:1].upper()
        font = None
        for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
            try:
                font = ImageFont.truetype(path, 300)
                break
            except OSError:
                continue
        font = font or ImageFont.load_default(size=300)
        draw = ImageDraw.Draw(img)
        box = draw.textbbox((0, 0), letter, font=font)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), letter, font=font, fill='white')
    img.save(target, 'PNG', optimize=True)


def latest_playtest_shot(game_id):
    """The title screen from the latest playtest: it shows the game's name and art."""
    folder = Path(os.environ.get('TMPDIR') or tempfile.gettempdir()) / f'playtest-{game_id}'
    start = folder / '1-start.png'
    if start.exists():
        return start
    shots = sorted(folder.glob('*.png'), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    return shots[0] if shots else None


# ---------- package ----------

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


def used_models(html, names):
    if 'studio.models(' in html:
        return list(names)
    return [n for n in names if re.search(r'''['"`]''' + re.escape(n) + r'''['"`]''', html)]


def store_listing(sid, gid):
    """The game project's store/ folder (listing.json + images) as a manifest "store" block; images are copied by write_package."""
    from game_project import link_of, root_of
    folder = root_of(link_of(sid, gid)) / 'store'
    spec = json.loads((folder / 'listing.json').read_text(encoding='utf8')) if (folder / 'listing.json').exists() else None
    if not spec:
        sys.exit('No store/listing.json in the game project, so there is nothing to list in the App Store.')
    return {'folder': folder, 'spec': spec}


def write_package(target, game, html, data, studio_app_id, voice_mode, saves, version, description, capabilities, listing=None):
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAYER / 'index.jsx', target / 'index.jsx')
    shutil.copyfile(ROOT / 'gameRuntime.js', target / 'gameRuntime.js')
    shutil.copyfile(ROOT / 'voice.js', target / 'voice.js')
    shutil.copyfile(ROOT / '.gitignore', target / '.gitignore')

    palette = (data.get('art') or {}).get('palette') or {}
    background = hex_color(palette.get('bg') or palette.get('sky'), '#0b1020')
    meta = {
        'id': game['id'], 'name': game.get('name') or 'Game', 'controls': game.get('controls') or '',
        'studioAppId': int(studio_app_id) if studio_app_id else None, 'voiceMode': voice_mode, 'background': background,
        'initialSaves': saves or {}, 'html': html,
    }
    (target / 'game.js').write_text(
        '// Written by Game Studio (publish_game.py). Edit the game in the studio.\n'
        f'export const GAME = {js_string(meta)}\n', encoding='utf8')

    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    chunks = [blob[i:i + CHUNK_CHARS] for i in range(0, len(blob), CHUNK_CHARS)] or ['{}']
    for old in target.glob('data-*.js'):
        old.unlink()
    names = []
    for i, chunk in enumerate(chunks):
        name = f'data-{i}.js'
        (target / name).write_text(f'export default {js_string(chunk)}\n', encoding='utf8')
        names.append(name)
    imports = '\n'.join(f"import part{i} from './{n}'" for i, n in enumerate(names))
    (target / 'data.js').write_text(
        '// The game\'s art, sounds and models, split so each file stays small.\n'
        f"{imports}\n\nexport default JSON.parse({' + '.join(f'part{i}' for i in range(len(names)))})\n", encoding='utf8')

    (target / 'README.md').write_text(
        f"# {meta['name']}\n\nA game made in Game Studio. It is published from the studio: edit it there "
        "(the Edit button in the game opens it), not in this folder, because every publish replaces these files.\n",
        encoding='utf8')

    manifest = {
        'id': target.name,
        'name': meta['name'],
        'version': version,
        'description': description,
        'entry': 'index.jsx',
        'icon': 'icon.png',
        'display': 'fullscreen',
        'offline_capable': False,
        'theme_color': background,
        'background_color': background,
        'capabilities': capabilities,
        'permissions': {},
        # On a public playtest link, players may leave notes for the maker
        # (player/index.jsx) and read what the game publishes under public/ (studio.publicWrite).
        'public_access': {'storage': {'read': True, 'write_prefix': 'public/notes/'}},
        'source_files': ['game.js', 'data.js', *names, 'gameRuntime.js', 'voice.js'],
    }
    if listing:
        spec, art_dir = listing['spec'], target / 'static' / 'store'
        shutil.rmtree(art_dir, ignore_errors=True)
        art_dir.mkdir(parents=True)
        names = [spec.get('hero')] + [x['src'] for x in spec['screenshots']]
        for name in filter(None, names):
            shutil.copyfile(listing['folder'] / name, art_dir / name)
        manifest['store'] = {'tagline': spec['tagline'], 'description': spec['description'],
                             **({'hero': 'static/store/' + spec['hero']} if spec.get('hero') else {}),
                             'screenshots': [{**x, 'src': 'static/store/' + x['src']} for x in spec['screenshots']]}
    (target / 'mobius.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

    total = sum(p.stat().st_size for p in target.iterdir() if p.is_file() and p.suffix in ('.js', '.jsx'))
    if total > MAX_TOTAL_BYTES:
        sys.exit(f'The game is too big to install as an app ({total // 1024} KB of code and art; the limit is about '
                 f'{MAX_TOTAL_BYTES // 1024} KB). Remove unused art or models and try again.')


WORLDS = APPS_DIR / 'mobius-worlds'


# Games Möbius Worlds hosts, and the Worlds tool that brings each one in: Möbius Kart,
# and the Worlds Lobby scene, which is the world itself.
WORLDS_GAMES = {'mobius-kart': 'tools/bundle_kart.py', 'g-qovj6o': 'tools/bundle_lobby.py'}


def write_into_worlds(sid, gid):
    """Refresh a game Worlds hosts, using Worlds' own bundler for it."""
    tool = WORLDS_GAMES.get(gid)
    if not tool or not (WORLDS / tool).exists():
        sys.exit(f'Möbius Worlds does not host "{gid}" yet, so it cannot be published into Worlds.')
    proc = subprocess.run([sys.executable, str(WORLDS / tool), str(sid), gid], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        sys.exit(f'Bringing the game into Worlds failed: {(proc.stderr or proc.stdout).strip()[-800:]}')
    return WORLDS


def apply(target):
    if not CONTROL.exists() or not os.environ.get('MOBIUS_RUN_TOKEN'):
        return None, 'Not in a Möbius agent run: call the apply_app tool with source_dir ' + str(target)
    proc = subprocess.run(
        [sys.executable, str(CONTROL), 'call', 'apply_app', '--args-json', json.dumps({'source_dir': str(target)})],
        capture_output=True, text=True, timeout=600)
    out = (proc.stdout or '') + (proc.stderr or '')
    match = re.search(r'"app_id"\s*:\s*(\d+)', out) or re.search(r'app_id\D{0,4}(\d+)', out)
    if proc.returncode != 0 or not match:
        return None, out.strip()[-2000:] or f'apply_app failed (exit {proc.returncode})'
    return int(match.group(1)), out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('app_id', help='Game Studio app id')
    parser.add_argument('game_id')
    parser.add_argument('--icon', help='PNG/JPG to use as the app icon (e.g. a playtest screenshot)')
    parser.add_argument('--generated-icon', action='store_true', help='use a generated tile as the icon (a later playtest screenshot replaces it)')
    parser.add_argument('--no-apply', action='store_true', help='write the app folder but do not apply it')
    parser.add_argument('--into-worlds', action='store_true', help='publish inside Möbius Worlds instead of as its own app')
    parser.add_argument('--as-app', action='store_true', help='publish as its own app even if it last went to Worlds')
    parser.add_argument('--store', action='store_true', help='this build is for public App Store listing: no saves, no studio link, plus the project\'s store/ listing art (sticks for later publishes)')
    parser.add_argument('--shared', action='store_true', help='the game has (or is getting) a public play link: ship no saves')
    args = parser.parse_args()
    sid, gid = args.app_id, args.game_id

    # Every game is also a Project (its home, with history); make sure it has one
    # and sync it to storage so we have the latest game files.
    # A problem here must not stop the app update, but we must sync before reading HTML.
    try:
        from game_project import ensure
        ensure(sid, gid)
    except (Exception, SystemExit) as err:
        print(f'Note: could not sync the game\'s project: {err}', file=sys.stderr)

    game = storage_get(sid, f'games/{gid}.json')
    if not isinstance(game, dict) or not game.get('id'):
        sys.exit(f'No game "{gid}" in Game Studio.')
    raw = storage_get(sid, f'games/{gid}.html')
    html = raw.decode('utf8') if isinstance(raw, (bytes, bytearray)) else (raw or '')
    if not html.strip():
        sys.exit(f'"{game.get("name")}" has no game file yet, so there is nothing to install.')

    assets = storage_get(sid, 'assets.json') or {}
    kit = storage_get(sid, f"art/{game['art']}.json") if game.get('art') else None
    own = storage_get(sid, f'games/{gid}.art.json')
    # Game apps carry only the library pieces the game names, so they stay small.
    used = lambda group, lister: {k: v for k, v in (assets.get(group) or {}).items()
                                  if lister in html or re.search(r'''['"`]''' + re.escape(k) + r'''['"`]''', html)}
    library = {'characters': used('characters', 'studio.sheets('), 'sprites': used('sprites', 'studio.images('), 'audio': {}}
    for name, entry in used('audio', 'studio.sounds(').items():
        data = api('GET', f'/api/storage/apps/{sid}/audio/{name}.mp3')
        if isinstance(data, (bytes, bytearray)) and data:
            library['audio'][name] = {**entry, 'dataUrl': 'data:audio/mpeg;base64,' + base64.b64encode(data).decode('ascii')}
    art = with_library(merge_art(kit, own), library)
    models = {}
    for name in used_models(html, (assets.get('models') or {}).keys()):
        data = api('GET', f'/api/storage/apps/{sid}/models/{name}.glb')
        if isinstance(data, (bytes, bytearray)) and data:
            models[name] = base64.b64encode(data).decode('ascii')
    data = {'sprites': library['sprites'], 'sounds': assets.get('sounds') or {}, 'models': models, 'art': art}
    saves = storage_get(sid, f'games/{gid}.saves.json') or {}
    voice_mode = (storage_get(sid, 'settings.json') or {}).get('voiceMode') or 'browser'
    published = storage_get(sid, f'published/{gid}.json') or {}
    store_build = args.store or bool(published.get('store'))
    if args.shared or published.get('playUrl') or store_build:
        # Anyone can read a public app's code, so a shared game ships none of
        # the owner's progress; every player, the owner's new installs too, starts fresh.
        saves = {}

    capabilities = {}
    if 'studio.say(' in html:
        capabilities['media.speech'] = {'version': 1, 'reason': 'Speak the characters\' lines with the Möbius voice.', 'limits': {'max_text_chars': 400}}
    if 'enableTilt' in html:
        capabilities['device.motion'] = {'version': 1, 'reason': 'Steer by tilting your phone.', 'limits': {'max_rate_hz': 30}}

    if (args.into_worlds or published.get('target') == 'worlds') and not args.as_app:
        if not (WORLDS / 'mobius.json').exists():
            sys.exit('Möbius Worlds is not installed here, so the game cannot be published into it.')
        target = write_into_worlds(sid, gid)
        record = {**published, 'target': 'worlds', 'hash': studio_hash(html), 'name': game.get('name'),
                  'count': int(published.get('count') or 0) + 1,
                  'publishedAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}
        if args.no_apply:
            storage_put_json(sid, f'published/{gid}.json', record)
            print(json.dumps({'ok': True, 'applied': False, 'source_dir': str(target), 'target': 'worlds',
                              'next': 'Call the apply_app tool with this source_dir.'}))
            return
        app_id, detail = apply(target)
        if not app_id:
            print(json.dumps({'ok': False, 'source_dir': str(target), 'error': detail}, ensure_ascii=False))
            sys.exit(1)
        record['worldsAppId'] = app_id
        storage_put_json(sid, f'published/{gid}.json', record)
        print(json.dumps({'ok': True, 'applied': True, 'target': 'worlds', 'app_id': app_id, 'name': game.get('name'),
                          'source_dir': str(target), 'open': f'/shell/?app={app_id}'}, ensure_ascii=False))
        return

    slug = pick_slug(game, published)
    target = APPS_DIR / slug
    count = int(published.get('count') or 0) + 1
    description = (game.get('description') or '').strip()[:280] or f"{game.get('name') or 'A game'}, made in Game Studio."
    listing = store_listing(sid, gid) if store_build else None
    write_package(target, game, html, data, None if store_build else sid, voice_mode, saves, f'1.0.{count}', description, capabilities, listing)

    # A screenshot icon, once there is one, stays; a generated placeholder is
    # swapped for a screenshot as soon as a playtest has produced one.
    icon = target / 'icon.png'
    icon_kind = published.get('icon') if icon.exists() else None
    if args.generated_icon:
        icon_kind = None
    shot = args.icon or (latest_playtest_shot(gid) if icon_kind != 'screenshot' and not args.generated_icon else None)
    if shot:
        icon_from_image(shot, icon)
        icon_kind = 'screenshot'
    elif not icon_kind:
        generated_icon(game, art, icon)
        icon_kind = 'generated'

    record = {'slug': slug, 'appId': published.get('appId'), 'hash': studio_hash(html), 'name': game.get('name'),
              'count': count, 'icon': icon_kind, 'publishedAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    if store_build:
        record['store'] = True
    if published.get('playUrl'):  # a shared play link (share_game.py) survives republishing
        record['playUrl'] = published['playUrl']
    if args.no_apply:
        print(json.dumps({'ok': True, 'applied': False, 'source_dir': str(target), 'next': 'Call the apply_app tool with this source_dir.'}))
        return
    app_id, detail = apply(target)
    if not app_id:
        print(json.dumps({'ok': False, 'source_dir': str(target), 'error': detail}, ensure_ascii=False))
        sys.exit(1)
    record['appId'] = app_id
    storage_put_json(sid, f'published/{gid}.json', record)
    if record.get('playUrl'):
        # Keep the public link on the version just published, not an old snapshot.
        try:
            api('PUT', f'/api/apps/{app_id}/hosted-publication')
        except Exception as err:  # the app itself is updated; the link refreshes next time
            print(f'Note: the public play link could not be refreshed: {err}', file=sys.stderr)
    print(json.dumps({'ok': True, 'applied': True, 'app_id': app_id, 'slug': slug, 'name': game.get('name'),
                      'source_dir': str(target), 'open': f'/shell/?app={app_id}'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
