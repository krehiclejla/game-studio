#!/usr/bin/env python3
"""Free (CC0) surface textures and props for dressing Game Studio environments.

  python3 surface_library.py search textures WORDS... [--max 20]   e.g. "plaster", "roof tiles", "wet cobblestone"
  python3 surface_library.py search models WORDS... [--max 20]     e.g. "air conditioner", "crate", "street lamp"
  python3 surface_library.py preview ID OUT.png                     a small picture to Read before choosing
  python3 surface_library.py get ID                                 download it (cached) and print its files

IDs look like polyhaven:grey_plaster, ambientcg:Bricks076 (textures) or polyhaven:wooden_crate_01
(models). Textures come at 1k (colour, normal, roughness); models as glTF with 1k textures.
Everything is CC0 (public domain): credit "Poly Haven" / "ambientCG" in the asset's credit line.
Files are cached in ~/.cache/game-studio/surfaces (outside /data; re-downloaded if missing).

Used by dress.py; read BUILDER.md ("Dressing") for how environments use them.
"""
import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

CACHE = Path.home() / '.cache' / 'game-studio' / 'surfaces'
UA = {'User-Agent': 'MobiusGameStudio/1.0 (game asset dressing; credits Poly Haven and ambientCG)'}


def get(url, timeout=180):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def cached_json(name, url, days=7):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f'{name}.json'
    if p.exists() and time.time() - p.stat().st_mtime < days * 86400:
        return json.loads(p.read_text())
    data = json.loads(get(url))
    p.write_text(json.dumps(data))
    return data


def words_of(s):
    return set(re.findall(r'[a-z0-9]+', str(s).lower()))


def score(words, *fields):
    hay = set()
    for f in fields:
        if isinstance(f, (list, tuple)):
            for x in f:
                hay |= words_of(x)
        else:
            hay |= words_of(f)
    return sum(1 for w in words if w in hay or any(h.startswith(w) for h in hay))


def search(kind, words, limit):
    words = [w.lower() for w in words]
    out = []
    t = 'textures' if kind == 'textures' else 'models'
    ph = cached_json(f'polyhaven-{t}', f'https://api.polyhaven.com/assets?t={t}')
    for k, v in ph.items():
        s = score(words, k.replace('_', ' '), v.get('name', ''), v.get('tags', []), v.get('categories', []))
        if s:
            out.append((s, f'polyhaven:{k}', v.get('name', k), ', '.join(v.get('categories', [])[:3])))
    if kind == 'textures':
        try:
            import urllib.parse
            qs = urllib.parse.urlencode({'type': 'Material', 'q': ' '.join(words), 'limit': '40', 'sort': 'Popular', 'include': 'tagData'})
            data = json.loads(get(f'https://ambientcg.com/api/v2/full_json?{qs}'))
            for a in data.get('foundAssets', []):
                s = score(words, a.get('assetId', ''), a.get('displayName', ''), a.get('tags', []))
                out.append((max(s, 1), f"ambientcg:{a['assetId']}", a.get('displayName', a['assetId']), a.get('displayCategory', '')))
        except Exception as e:
            print(f'(ambientCG search failed: {e})', file=sys.stderr)
    out.sort(key=lambda x: -x[0])
    # both sources side by side, so neither crowds the other out
    ph_hits = [x for x in out if x[1].startswith('polyhaven:')]
    acg_hits = [x for x in out if x[1].startswith('ambientcg:')]
    half = max(1, limit // 2) if acg_hits else limit
    picked = ph_hits[:half] + acg_hits[:limit - len(ph_hits[:half])]
    return [{'id': i, 'name': n, 'kind': c} for _, i, n, c in picked]


def _ph_files(pid):
    return json.loads(get(f'https://api.polyhaven.com/files/{pid}'))


def get_texture(ref):
    src, name = ref.split(':', 1)
    d = CACHE / 'tex' / f'{src}_{name}'
    meta = d / 'files.json'
    if meta.exists():
        return json.loads(meta.read_text())
    d.mkdir(parents=True, exist_ok=True)
    files = {}
    if src == 'polyhaven':
        f = _ph_files(name)
        for m, key in (('color', 'Diffuse'), ('normal', 'nor_gl'), ('rough', 'Rough')):
            e = f.get(key, {}).get('1k', {}).get('jpg') or f.get(key, {}).get('1k', {}).get('png')
            if e:
                p = d / f'{m}{Path(e["url"]).suffix}'
                p.write_bytes(get(e['url']))
                files[m] = str(p)
    elif src == 'ambientcg':
        z = zipfile.ZipFile(io.BytesIO(get(f'https://ambientcg.com/get?file={name}_1K-JPG.zip')))
        for n in z.namelist():
            low = n.lower()
            m = 'color' if '_color' in low else 'normal' if '_normalgl' in low else 'rough' if '_roughness' in low else None
            if m:
                p = d / f'{m}.jpg'
                p.write_bytes(z.read(n))
                files[m] = str(p)
    else:
        sys.exit(f'Unknown source in {ref}')
    if 'color' not in files:
        sys.exit(f'{ref} has no colour map at 1k.')
    meta.write_text(json.dumps(files))
    return files


def get_model(ref):
    src, name = ref.split(':', 1)
    if src != 'polyhaven':
        sys.exit('Models come from polyhaven: for now (Kenney packs: python3 kenney.py).')
    d = CACHE / 'models' / name
    main = d / f'{name}.gltf'
    if main.exists():
        return {'gltf': str(main)}
    d.mkdir(parents=True, exist_ok=True)
    g = _ph_files(name)['gltf']['1k']['gltf']
    main.write_bytes(get(g['url']))
    for rel, inc in g.get('include', {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(get(inc['url']))
    return {'gltf': str(main)}


def fetch(ref):
    """Texture or model by id; models are recognised from the catalogue."""
    src, name = ref.split(':', 1)
    if src == 'polyhaven':
        models = cached_json('polyhaven-models', 'https://api.polyhaven.com/assets?t=models')
        if name in models:
            return {'type': 'model', **get_model(ref)}
    return {'type': 'texture', **get_texture(ref)}


def preview(ref, out):
    src, name = ref.split(':', 1)
    if src == 'polyhaven':
        data = get(f'https://cdn.polyhaven.com/asset_img/thumbs/{name}.png?width=256&height=256')
    else:
        data = get(f'https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/256-JPG-242424/{name}.jpg')
    Path(out).write_bytes(data)
    print(json.dumps({'preview': out}))


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == 'search' and a[1] in ('textures', 'models'):
        lim = 20
        if '--max' in a:
            i = a.index('--max'); lim = int(a[i + 1]); a = a[:i] + a[i + 2:]
        print(json.dumps(search(a[1], a[2:], lim), indent=1))
    elif len(a) == 3 and a[0] == 'preview':
        preview(a[1], a[2])
    elif len(a) == 2 and a[0] == 'get':
        print(json.dumps(fetch(a[1]), indent=1))
    else:
        print(__doc__)
        sys.exit(2)
