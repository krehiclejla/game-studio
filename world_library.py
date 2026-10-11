#!/usr/bin/env python3
"""Real skies and ground materials for 3D (scene) games, all CC0 (public domain).

Sources
  polyhaven  Poly Haven (polyhaven.com): about 1,000 photographed 360° skies and
             scanned ground, rock, wood and brick materials.
  ambientcg  ambientCG (ambientcg.com): thousands of PBR materials (grass, dirt,
             sand, snow, gravel, paving, planks, tiles...). Only the three maps a
             game needs are taken out of each download.

  python3 world_library.py search sky WORDS... [--max N]      e.g. "sunset", "overcast", "night", "clear sky"
  python3 world_library.py search ground WORDS... [--max N]   e.g. "grass", "sand", "forest floor", "cobblestone"
  python3 world_library.py preview ID                         a small picture of it to Read before choosing
  python3 world_library.py add APP_ID sky ID NAME --game GAME_ID
      A 2048x1024 360° picture saved in that game's art. Scene games use it with
      settings {"skybox": "NAME"}: it becomes the sky AND lights the scene (reflections,
      soft colour from the sky); "skyboxLight" 0-2 scales that light (default 1).
  python3 world_library.py add APP_ID ground ID NAME --game GAME_ID
      Colour, bump (normal) and roughness maps saved as NAME, NAME_normal, NAME_rough.
      Put it on a terrain with {"surface": "NAME", "surfaceSize": METRES} (one tile of the
      pattern; the tool prints the real-world size when the source knows it). The terrain's
      "color" then tints it (leave it out for the natural look).
  python3 world_library.py list APP_ID --game GAME_ID
  python3 world_library.py remove APP_ID NAME --game GAME_ID

Skies are about 0.5 MB and materials about 1 MB in the game, so add only what is used.
"""
import argparse
import base64
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gs_deps  # noqa: E402,F401
from PIL import Image  # noqa: E402
from build_art import storage_get, storage_put_json  # noqa: E402
from packzip import Pack  # noqa: E402

CACHE = Path.home() / '.cache' / 'game-studio'
UA = {'User-Agent': 'MobiusGameStudio/1.0 (+https://github.com/mobius-os)'}
PH = 'https://api.polyhaven.com'
ACG = 'https://ambientcg.com/api/v2/full_json'
SKY_SIZE = (2048, 1024)
MAP_SIZE = 1024
NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_]{0,39}$')
Image.MAX_IMAGE_PIXELS = None  # Poly Haven's sky pictures are 8k+ wide


def out(value):
    print(json.dumps(value, indent=1, ensure_ascii=False))


def fail(message, **extra):
    out({'ok': False, 'error': message, **extra})
    sys.exit(2)


def get(url, limit=60_000_000):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as res:
        data = res.read(limit + 1)
    if len(data) > limit:
        fail(f'{url} is larger than {limit // 1_000_000} MB.')
    return data


def get_json(url):
    return json.loads(get(url, 30_000_000))


def cached_json(key, url, days=1):
    path = CACHE / f'{key}.json'
    try:
        if time.time() - path.stat().st_mtime < days * 86400:
            return json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    data = get_json(url)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def words_of(value):
    return [w.rstrip('s') for w in re.split(r'[^a-z0-9]+', str(value).lower()) if w]


def score(words, *fields):
    hay = set()
    for f in fields:
        for item in (f if isinstance(f, list) else [f]):
            hay.update(words_of(item))
    return sum(1 for w in words if w in hay or any(h.startswith(w) for h in hay if len(w) > 3))


# ---------- search ----------

def search_polyhaven(kind, words, limit):
    assets = cached_json(f'polyhaven-{kind}', f'{PH}/assets?t={kind}')
    hits = []
    for pid, a in assets.items():
        s = score(words, pid, a.get('name', ''), a.get('tags') or [], a.get('categories') or [])
        if s:
            hits.append((s, a.get('download_count', 0), pid, a))
    hits.sort(key=lambda h: (-h[0], -h[1]))
    return [{'id': f'polyhaven:{pid}', 'name': a.get('name'), 'about': ', '.join((a.get('categories') or [])[:6]),
             **({'size_m': round(a['dimensions'][0] / 1000, 2)} if a.get('dimensions') else {})}
            for _, _, pid, a in hits[:limit]]


def search_ambientcg(words, limit):
    url = ACG + '?' + urllib.parse.urlencode({'type': 'Material', 'q': ' '.join(words), 'limit': str(limit),
                                              'sort': 'Popular', 'include': 'tagData,dimensionsData'})
    found = get_json(url).get('foundAssets') or []
    return [{'id': f"ambientcg:{a['assetId']}", 'name': a.get('displayName') or a['assetId'],
             'about': ', '.join((a.get('tags') or [])[:6]),
             **({'size_m': round(a['dimensionX'] / 100, 2)} if a.get('dimensionX') else {})} for a in found]


def cmd_search(a):
    words = [w for w in words_of(' '.join(a.words)) if len(w) > 1]
    if not words:
        fail('Give a word or two, e.g. "sunset" or "grass".')
    if a.what == 'sky':
        result = {'polyhaven': search_polyhaven('hdris', words, a.max)}
    else:
        result = {'polyhaven': search_polyhaven('textures', words, a.max)}
        try:
            result['ambientcg'] = search_ambientcg(a.words, a.max)  # its own search, with the words as typed
        except OSError as err:
            result['ambientcg_error'] = f'ambientCG did not answer ({err}).'
    empty = not any(isinstance(v, list) and v for v in result.values())
    out({**result, 'next': f'python3 world_library.py preview ID, then: add APP_ID {a.what} ID NAME --game GAME_ID',
         **({'tip': 'Nothing found: try one broader word (sky: sunset, cloudy, night, clear; ground: grass, dirt, sand, rock, snow, stone).'} if empty else {})})


# ---------- preview ----------

def cmd_preview(a):
    source, _, ref = a.id.partition(':')
    if source == 'polyhaven':
        url = f'https://cdn.polyhaven.com/asset_img/thumbs/{ref}.png?width=512&height=256'
    elif source == 'ambientcg':
        url = f'https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/512-PNG/{ref}.png'
    else:
        fail('Use an id printed by search (polyhaven:... or ambientcg:...).')
    target = Path('/tmp') / 'gs-world-preview' / f'{re.sub(r"[^A-Za-z0-9_-]+", "_", a.id)}.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(get(url, 5_000_000))
    except OSError as err:
        fail(f'No preview picture ({err}).')
    out({'ok': True, 'picture': str(target), 'next': 'Read the picture to see it.'})


# ---------- add ----------

def jpeg_data_url(image, size, quality):
    image = image.convert('RGB')
    if image.size != size:
        image = image.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, 'JPEG', quality=quality, optimize=True, progressive=True)
    return {'dataUrl': 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode(), 'w': size[0], 'h': size[1]}


def open_scaled(data, size):
    image = Image.open(io.BytesIO(data))
    image.draft('RGB', size)  # JPEG: decode at a reduced scale (much faster for 8k pictures)
    return image


def add_sky(ref):
    source, _, pid = ref.partition(':')
    if source != 'polyhaven':
        fail('Skies come from Poly Haven: use a polyhaven:... id from "search sky".')
    files = get_json(f'{PH}/files/{pid}')
    info = get_json(f'{PH}/info/{pid}')
    tonemapped = (files.get('tonemapped') or {}).get('url')
    if not tonemapped:
        fail(f'{pid} has no ready-made picture; choose another sky.')
    image = open_scaled(get(tonemapped, 80_000_000), SKY_SIZE)
    authors = ', '.join((info.get('authors') or {}).keys()) or 'Poly Haven'
    credit = f'"{info.get("name") or pid}" by {authors}, Poly Haven (CC0)'
    images = {'': {**jpeg_data_url(image, SKY_SIZE, 82), 'kind': 'sky'}}
    return images, credit, {'source': 'polyhaven', 'id': pid, 'url': f'https://polyhaven.com/a/{pid}'}, None


def add_ground(ref):
    source, _, pid = ref.partition(':')
    maps = {}
    size_m = None
    if source == 'polyhaven':
        files = get_json(f'{PH}/files/{pid}')
        info = get_json(f'{PH}/info/{pid}')
        for key, part in (('Diffuse', ''), ('nor_gl', '_normal'), ('Rough', '_rough')):
            entry = ((files.get(key) or {}).get('1k') or {}).get('jpg') or ((files.get(key) or {}).get('2k') or {}).get('jpg')
            if entry:
                maps[part] = get(entry['url'])
        if info.get('dimensions'):
            size_m = round(info['dimensions'][0] / 1000, 2)
        authors = ', '.join((info.get('authors') or {}).keys()) or 'Poly Haven'
        credit = f'"{info.get("name") or pid}" by {authors}, Poly Haven (CC0)'
        prov = {'source': 'polyhaven', 'id': pid, 'url': f'https://polyhaven.com/a/{pid}'}
    elif source == 'ambientcg':
        meta = get_json(ACG + '?' + urllib.parse.urlencode({'id': pid, 'include': 'dimensionsData'}))
        found = (meta.get('foundAssets') or [None])[0]
        if not found:
            fail(f'ambientCG has no material {pid}.')
        pack = Pack(f'https://ambientcg.com/get?file={pid}_1K-JPG.zip')
        for suffix, part in (('_Color.jpg', ''), ('_NormalGL.jpg', '_normal'), ('_Roughness.jpg', '_rough')):
            names = [n for n in pack.names() if n.endswith(suffix)]
            if names:
                maps[part] = pack.file(names[0]).read_bytes()
        if found.get('dimensionX'):
            size_m = round(found['dimensionX'] / 100, 2)
        credit = f'"{found.get("displayName") or pid}" from ambientCG.com (CC0)'
        prov = {'source': 'ambientcg', 'id': pid, 'url': f'https://ambientcg.com/view?id={pid}'}
    else:
        fail('Use an id printed by "search ground" (polyhaven:... or ambientcg:...).')
    if '' not in maps:
        fail(f'{ref} has no colour map to use; choose another material.')
    images = {}
    for part, data in maps.items():
        image = Image.open(io.BytesIO(data))
        side = min(MAP_SIZE, max(image.size))
        images[part] = {**jpeg_data_url(image, (side, side), 88 if part == '_normal' else 80), 'kind': 'surface' if not part else 'surface-map'}
    return images, credit, prov, size_m


def cmd_add(a):
    name = a.name.lower()
    if not NAME_RE.match(name):
        fail('Names are lowercase letters, digits and _ (e.g. sunset_sky, meadow_grass).')
    images, credit, prov, size_m = (add_sky if a.what == 'sky' else add_ground)(a.id)
    path = f'games/{a.game}.art.json'
    art = storage_get(a.app, path) or {'images': {}, 'sheets': {}, 'sounds': {}, 'models': {}}
    for part in ('', '_normal', '_rough'):
        art.setdefault('images', {}).pop(name + part, None)  # a replaced material may have fewer maps
    for part, image in images.items():
        art['images'][name + part] = image
    art.setdefault('credits', {})[name] = {'kind': a.what, 'credit': credit, **prov, 'license': 'CC0-1.0',
                                           **({'size_m': size_m} if size_m else {}),
                                           'updatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    storage_put_json(a.app, path, art)
    kb = round(sum(len(i['dataUrl']) * 3 / 4 for i in images.values()) / 1024)
    if a.what == 'sky':
        use = f'scene.py settings APP_ID GAME_ID \'{{"skybox":"{name}"}}\''
    else:
        use = f'terrain fields {{"surface":"{name}","surfaceSize":{size_m or 3}}}'
    out({'ok': True, 'name': name, 'kind': a.what, 'maps': [name + p for p in images], 'kb': kb, 'credit': credit,
         **({'size_m': size_m} if size_m else {}), 'use': use})


def cmd_list(a):
    art = storage_get(a.app, f'games/{a.game}.art.json') or {}
    credits = art.get('credits') or {}
    out({n: {k: c.get(k) for k in ('kind', 'credit', 'size_m')} for n, c in credits.items() if c.get('kind') in ('sky', 'ground')})


def cmd_remove(a):
    path = f'games/{a.game}.art.json'
    art = storage_get(a.app, path) or {}
    if (art.get('credits') or {}).get(a.name, {}).get('kind') not in ('sky', 'ground'):
        fail(f'{a.name} is not a sky or ground material of game {a.game}.')
    for part in ('', '_normal', '_rough'):
        (art.get('images') or {}).pop(a.name + part, None)
    art['credits'].pop(a.name, None)
    storage_put_json(a.app, path, art)
    out({'ok': True, 'removed': a.name})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('search')
    s.add_argument('what', choices=['sky', 'ground'])
    s.add_argument('words', nargs='+')
    s.add_argument('--max', type=int, default=10)
    p = sub.add_parser('preview')
    p.add_argument('id')
    d = sub.add_parser('add')
    d.add_argument('app')
    d.add_argument('what', choices=['sky', 'ground'])
    d.add_argument('id')
    d.add_argument('name')
    d.add_argument('--game', required=True)
    ls = sub.add_parser('list')
    ls.add_argument('app')
    ls.add_argument('--game', required=True)
    r = sub.add_parser('remove')
    r.add_argument('app')
    r.add_argument('name')
    r.add_argument('--game', required=True)
    a = parser.parse_args()
    {'search': cmd_search, 'preview': cmd_preview, 'add': cmd_add, 'list': cmd_list, 'remove': cmd_remove}[a.cmd](a)


if __name__ == '__main__':
    main()
