#!/usr/bin/env python3
"""Install real game art into Game Studio storage.

Art kits are defined in kits/art/<id>.json (see kits/README.md). Each kit names
a free CC0 Kenney pack and the files to take from it. This script downloads the
pack, picks and resizes the files, and uploads one bundle that every game using
the kit receives through the `studio` helper.

  python3 build_art.py <appId> kit <artId>            install one kit (skips if present; --force rebuilds)
  python3 build_art.py <appId> kit all                install every kit
  python3 build_art.py <appId> list <artId>           print the kit's image/sheet/sound names
  python3 build_art.py <appId> game <gameId> --pack <slug> --files "glob,glob" [--max 128]
                                                      add pack files to one game's own art
  python3 build_art.py <appId> game <gameId> --image FILE --name NAME [--cutout] [--max 256]
                                                      add a local picture (e.g. an AI image) to one game

Needs API_BASE_URL and AGENT_TOKEN (present in Möbius agent runs) and Pillow.
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import gs_deps  # noqa: E402,F401  (reinstalls basic packages after a container replacement)
import local_storage  # noqa: E402  (tools in a project guest's workspace use files)
from packzip import Pack  # noqa: E402  (single files from a pack, without the whole download)
from PIL import Image

ROOT = Path(__file__).resolve().parent
KITS_DIR = ROOT / 'kits' / 'art'
MAX_BUNDLE_BYTES = 2_500_000
UA = {'User-Agent': 'MobiusGameStudio/1.0'}


def api(method, path, body=None, content_type='application/json'):
    if local_storage.active():
        # A project guest's workspace: storage is the project's files (local_storage.py).
        data, _etag = local_storage.call(method, path, body)
        return json.loads(data) if data and path.split('?')[0].endswith('.json') else data
    base = os.environ['API_BASE_URL'].rstrip('/')
    req = urllib.request.Request(base + path, method=method, data=body, headers={
        'Authorization': 'Bearer ' + os.environ['AGENT_TOKEN'],
        **({'Content-Type': content_type} if body is not None else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            data = res.read()
            return json.loads(data) if data and 'json' in (res.headers.get('Content-Type') or '') else data
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise


# Files several writers change (the app, the AI's tools, the server queue). Reads
# remember what they saw, so a save can tell if someone changed the file meanwhile.
SHARED = ('assets.json', 'design-jobs.json')
_seen = {}


def _raw(method, path, body=None, headers=None):
    if local_storage.active():
        try:
            return local_storage.call(method, path, body, headers)
        except local_storage.Conflict:
            raise urllib.error.HTTPError(path, 412, 'Precondition Failed', None, None)
    base = os.environ['API_BASE_URL'].rstrip('/')
    req = urllib.request.Request(base + path, method=method, data=body, headers={
        'Authorization': 'Bearer ' + os.environ['AGENT_TOKEN'], **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read(), res.headers.get('ETag')


def storage_get(app_id, path):
    if path not in SHARED:
        return api('GET', f'/api/storage/apps/{app_id}/{path}')
    try:
        data, etag = _raw('GET', f'/api/storage/apps/{app_id}/{path}')
    except urllib.error.HTTPError as err:
        if err.code == 404:
            _seen[(app_id, path)] = (None, None)
            return None
        raise
    value = json.loads(data) if data else None
    _seen[(app_id, path)] = (json.loads(data) if data else None, etag)
    return value


def _merge(base, mine, theirs):
    """Apply what this tool changed (base -> mine) onto the newest copy (theirs), per entry."""
    if not isinstance(mine, dict) or not isinstance(theirs, dict) or not isinstance(base, dict):
        return mine
    out = dict(theirs)
    for group in set(base) | set(mine):
        was, now = base.get(group), mine.get(group)
        if was == now:
            continue
        if isinstance(was, dict) and isinstance(now, dict):
            merged = dict(theirs.get(group) or {})
            for key in set(was) | set(now):
                if key not in now:
                    merged.pop(key, None)
                elif was.get(key) != now[key]:
                    merged[key] = now[key]
            out[group] = merged
        elif group in mine:
            out[group] = now
        else:
            out.pop(group, None)
    return out


def storage_put_json(app_id, path, value):
    url = f'/api/storage/apps/{app_id}/{path}'
    if path not in SHARED or (app_id, path) not in _seen:
        api('PUT', url, json.dumps(value).encode())
        return
    base, etag = _seen[(app_id, path)]
    mine = value
    for _ in range(6):
        headers = {'Content-Type': 'application/json', **({'If-Match': etag} if etag else {'If-None-Match': '*'})}
        try:
            _raw('PUT', url, json.dumps(value).encode(), headers)
            _seen.pop((app_id, path), None)
            return
        except urllib.error.HTTPError as err:
            if err.code != 412:
                raise
        # Someone saved in between: redo this change on top of theirs.
        data, etag = _raw('GET', url)
        theirs = json.loads(data) if data else {}
        value = _merge(base, mine, theirs)
        base, mine = theirs, value
    raise SystemExit(f'{path} kept changing while saving; run the command again.')


def select(pack, pattern):
    """Local copies of the pack files matching a glob; only those files are downloaded."""
    return pack.files(pattern)


def png_data_url(image, max_size=None):
    image = image.convert('RGBA')
    if max_size and max(image.size) > max_size:
        scale = max_size / max(image.size)
        # Pixel art keeps hard edges; everything else is smoothed.
        resample = Image.NEAREST if max(image.size) <= 64 else Image.LANCZOS
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), resample)
    buf = io.BytesIO()
    image.save(buf, 'PNG', optimize=True)
    return {'dataUrl': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(), 'w': image.width, 'h': image.height}


def name_for(path, rename=None):
    stem = path.stem.lower()
    if rename:
        for old, new in rename.items():
            stem = stem.replace(old, new)
    return re.sub(r'[^a-z0-9_]+', '_', stem).strip('_')


def strip_glb_textures(data):
    """Drop external image references from a GLB, keeping UVs and materials.

    Games load models from bytes and cannot fetch a sibling texture file, so a
    kit that shares one texture ships it as an ordinary image instead and the
    game applies it (see kits/README.md).
    """
    import struct
    magic, version, _ = struct.unpack('<III', data[:12])
    json_len, json_type = struct.unpack('<II', data[12:20])
    doc = json.loads(data[20:20 + json_len])
    rest = data[20 + json_len:]
    if not any('uri' in image for image in doc.get('images', [])):
        return data
    for material in doc.get('materials', []):
        pbr = material.get('pbrMetallicRoughness', {})
        pbr.pop('baseColorTexture', None)
        for key in ('normalTexture', 'occlusionTexture', 'emissiveTexture'):
            material.pop(key, None)
    for key in ('images', 'textures', 'samplers'):
        doc.pop(key, None)
    body = json.dumps(doc, separators=(',', ':')).encode()
    body += b' ' * (-len(body) % 4)
    out = struct.pack('<II', len(body), json_type) + body + rest
    return struct.pack('<III', magic, version, 12 + len(out)) + out


def build_kit(spec):
    base_for = lambda group: Pack(group.get('pack') or spec['pack'])
    bundle = {key: spec.get(key) for key in ('id', 'genre', 'title', 'style', 'credit', 'font', 'palette', 'notes')}
    bundle.update(images={}, sheets={}, sounds={}, models={})
    for group in spec.get('images', []):
        for path in select(base_for(group), group['glob']):
            bundle['images'][name_for(path, group.get('rename'))] = png_data_url(Image.open(path), group.get('max'))
    for sheet in spec.get('sheets', []):
        path = base_for(sheet).file(sheet['file'])
        entry = png_data_url(Image.open(path))
        entry.update({k: sheet[k] for k in ('frameWidth', 'frameHeight', 'spacing', 'margin', 'frames') if k in sheet})
        bundle['sheets'][sheet['name']] = entry
    for pattern in spec.get('sounds', []):
        pack, _, pattern = pattern.rpartition(':')
        for path in select(Pack(pack) if pack else base_for({}), pattern):
            mime = 'audio/ogg' if path.suffix == '.ogg' else 'audio/wav' if path.suffix == '.wav' else 'audio/mpeg'
            bundle['sounds'][name_for(path).removeprefix('sfx_')] = f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()
    for pattern in spec.get('models', []):
        pack, _, pattern = pattern.rpartition(':')
        for path in select(Pack(pack) if pack else base_for({}), pattern):
            data = path.read_bytes()
            if spec.get('stripTextures'):
                data = strip_glb_textures(data)
            bundle['models'][name_for(path)] = base64.b64encode(data).decode()
    size = len(json.dumps(bundle))
    if size > MAX_BUNDLE_BYTES:
        sys.exit(f'Kit {spec["id"]} is {size / 1e6:.1f} MB; trim it below {MAX_BUNDLE_BYTES / 1e6:.1f} MB so games stay fast.')
    return bundle, size


def summary(bundle):
    lines = [f'{bundle.get("title") or bundle.get("id")}: {len(bundle["images"])} images, {len(bundle["sheets"])} sheets, {len(bundle["sounds"])} sounds, {len(bundle["models"])} models']
    if bundle['images']:
        lines.append('images: ' + ', '.join(f'{k} ({v["w"]}x{v["h"]})' for k, v in bundle['images'].items()))
    for name, sheet in bundle['sheets'].items():
        frames = sheet.get('frames') or {}
        lines.append(f'sheet {name}: {sheet["w"]}x{sheet["h"]}, frame {sheet.get("frameWidth")}x{sheet.get("frameHeight")}, named frames: ' + ', '.join(f'{k}={v}' for k, v in frames.items()))
    if bundle['sounds']:
        lines.append('sounds: ' + ', '.join(bundle['sounds']))
    if bundle['models']:
        lines.append('models: ' + ', '.join(bundle['models']))
    return '\n'.join(lines)


def load_spec(art_id):
    path = KITS_DIR / f'{art_id}.json'
    if not path.exists():
        sys.exit(f'No kit named {art_id}. Kits: ' + ', '.join(p.stem for p in sorted(KITS_DIR.glob('*.json'))))
    return json.loads(path.read_text())


def cmd_kit(args):
    ids = [p.stem for p in sorted(KITS_DIR.glob('*.json'))] if args.target == 'all' else [args.target]
    for art_id in ids:
        if not args.force and storage_get(args.app, f'art/{art_id}.json') is not None:
            print(f'{art_id}: already installed')
            continue
        bundle, size = build_kit(load_spec(art_id))
        storage_put_json(args.app, f'art/{art_id}.json', bundle)
        print(f'{art_id}: installed ({size / 1e6:.2f} MB)')


def cmd_list(args):
    bundle = storage_get(args.app, f'art/{args.target}.json')
    if bundle is None:
        sys.exit(f'{args.target} is not installed; run: python3 build_art.py {args.app} kit {args.target}')
    print(summary(bundle))
    if bundle.get('notes'):
        print('notes: ' + bundle['notes'])


def cutout(image, tolerance=38):
    """Cut the subject out of a picture.

    Uses rembg's segmentation model when installed (pip install "rembg[cpu]";
    the model is cached outside /data). Without it, falls back to flood-filling
    a flat background from the corners, which suits drawings on plain paper.
    """
    try:
        os.environ.setdefault('U2NET_HOME', '/tmp/u2net')
        from rembg import new_session, remove
        out = remove(image.convert('RGBA'), session=new_session('isnet-general-use'))
        box = out.getbbox()
        return out.crop(box) if box else out
    except ImportError:
        pass
    image = image.convert('RGBA')
    w, h = image.size
    px = image.load()
    seen = set()
    stack = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    ref = [px[x, y][:3] for x, y in stack]
    close = lambda c: min(sum(abs(a - b) for a, b in zip(c, r)) for r in ref) <= tolerance * 3
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or x < 0 or y < 0 or x >= w or y >= h:
            continue
        seen.add((x, y))
        if not close(px[x, y][:3]):
            continue
        px[x, y] = (0, 0, 0, 0)
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    box = image.getbbox()
    return image.crop(box) if box else image


def add_to_game(app_id, game_id, items):
    path = f'games/{game_id}.art.json'
    art = storage_get(app_id, path) or {'images': {}, 'sheets': {}, 'sounds': {}, 'models': {}}
    art.setdefault('images', {}).update(items)
    storage_put_json(app_id, path, art)
    print(f'{game_id}: added {", ".join(items)} ({len(json.dumps(art)) / 1e6:.2f} MB of game art)')


def cmd_game(args):
    items = {}
    if args.image:
        image = Image.open(args.image)
        if args.cutout:
            image = cutout(image)
        items[args.name or name_for(Path(args.image))] = png_data_url(image, args.max or 256)
    if args.pack:
        base = Pack(args.pack)
        for pattern in (p.strip() for p in args.files.split(',') if p.strip()):
            for path in select(base, pattern):
                items[name_for(path)] = png_data_url(Image.open(path), args.max)
    if not items:
        sys.exit('Nothing to add: pass --image or --pack with --files.')
    add_to_game(args.app, args.target, items)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('app')
    parser.add_argument('command', choices=['kit', 'list', 'game'])
    parser.add_argument('target')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--pack')
    parser.add_argument('--files', default='')
    parser.add_argument('--image')
    parser.add_argument('--name')
    parser.add_argument('--cutout', action='store_true')
    parser.add_argument('--max', type=int)
    args = parser.parse_args()
    {'kit': cmd_kit, 'list': cmd_list, 'game': cmd_game}[args.command](args)


if __name__ == '__main__':
    main()
