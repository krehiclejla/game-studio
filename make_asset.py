#!/usr/bin/env python3
"""Turn AI-drawn art and sounds into Game Studio assets.

The agent draws; this script renders, checks, and saves. Nothing here calls a
paid service: art is drawn by the agent itself as SVG (smooth cartoon, flat,
painterly vector) or as a pixel grid (pixel art), and rendered locally.

  python3 make_asset.py <appId> preview --svg FILE [--width W --height H]
  python3 make_asset.py <appId> preview --grid FILE [--scale N]
      Render without saving, on a checkerboard, to $TMPDIR/asset-preview/.
      Read the PNG it prints and fix the drawing before saving.

  python3 make_asset.py <appId> save <name> --svg FILE [--width W --height H] [--game ID] [--prompt TEXT]
  python3 make_asset.py <appId> save <name> --grid FILE [--scale N] [--game ID] [--prompt TEXT]
      Save as a sprite. Without --game it goes to the shared Assets (every
      game can use it by name); with --game it goes to that game's own art.

  python3 make_asset.py <appId> sound <name> --zzfx '[1,.05,220,...]' [--prompt TEXT]
      Save a ZzFX sound effect (up to 21 numbers; null skips a value).

  python3 make_asset.py <appId> draft <name> --job ID (--svg FILE | --grid FILE | --png FILE) [--style S] [--view V] [--source ai|kenney|import] [--prompt TEXT]
      Save a character DESIGN (one still pose) for the person to Keep, retry or change.

  python3 make_asset.py <appId> still <name> (--svg FILE | --grid FILE | --png FILE)
      Replace a gallery character's look (resets its animations to one idle frame; redraw them after).

  python3 make_asset.py <appId> char-meta <name> [--role hero|enemy|boss|friend|creature|vehicle] [--view side|topdown] [--prompt TEXT]
      Change a gallery character's role, view or description.

  python3 make_asset.py <appId> character <name> --frames f0.svg,f1.svg,... --anims idle:0-1,walk:2-5,jump:6,hurt:7
        [--size 256] [--preview] [--game ID] [--role hero] [--view side] [--style cartoon] [--prompt TEXT] [--source-svg FILE]
      An animated character: every frame is one SVG (or pixel-grid .json) of the
      same character on the same canvas, rendered size x size and joined into a
      sprite sheet. --preview only renders a contact sheet to check. Saved
      characters go to the Characters library (assets.json "characters"), or with
      --game into that game's own art; games get them via studio.sheet(name)
      ({dataUrl, frameWidth, frameHeight, animations}) and studio.image(name)
      (the first frame).

Sizes: sprites default to 256 px on the longer side (use --width/--height for
backgrounds, e.g. 1024x576; tiles 128x128). Wide opaque images are stored as
WebP to stay small; anything with transparency stays PNG.

A pixel grid is JSON: {"palette": {"k": "#1b1b2f", "r": "#e8413c", ...},
"rows": ["..kkkk..", ".krrrrk.", ...]} where "." (or any key missing from the
palette) is transparent. Every row must be the same length.

Needs API_BASE_URL and AGENT_TOKEN (present in Möbius agent runs), Pillow and
resvg-py (installed automatically on first use).
"""
import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import gs_deps  # noqa: E402,F401  (reinstalls basic packages after a container replacement)
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_art import storage_get, storage_put_json  # noqa: E402

MAX_ASSET_BYTES = 450_000
MAX_SHEET_BYTES = 1_200_000
NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')


def resvg():
    try:
        import resvg_py
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', 'resvg-py'], check=True)
        import resvg_py
    return resvg_py


def svg_size(svg):
    box = re.search(r'viewBox\s*=\s*["\']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', svg)
    if box:
        return float(box.group(1)), float(box.group(2))
    w = re.search(r'<svg[^>]*\swidth\s*=\s*["\']([\d.]+)', svg)
    h = re.search(r'<svg[^>]*\sheight\s*=\s*["\']([\d.]+)', svg)
    return (float(w.group(1)), float(h.group(1))) if w and h else (256.0, 256.0)


def render_svg(path, width=None, height=None):
    svg = Path(path).read_text(encoding='utf8')
    if '<svg' not in svg:
        sys.exit('That file is not an SVG drawing.')
    vw, vh = svg_size(svg)
    if not width and not height:
        scale = 256 / max(vw, vh)
        width, height = round(vw * scale), round(vh * scale)
    elif width and not height:
        height = round(vh * width / vw)
    elif height and not width:
        width = round(vw * height / vh)
    try:
        png = resvg().svg_to_bytes(svg_string=svg, width=int(width), height=int(height))
    except Exception as err:  # resvg reports the exact parse problem
        sys.exit(f'The SVG could not be drawn: {err}')
    return Image.open(io.BytesIO(bytes(png))).convert('RGBA'), False


def render_grid(path, scale=None):
    try:
        grid = json.loads(Path(path).read_text(encoding='utf8'))
        palette, rows = grid['palette'], grid['rows']
    except Exception as err:
        sys.exit(f'The pixel grid is not valid JSON with "palette" and "rows": {err}')
    if not rows or len({len(r) for r in rows}) != 1:
        sys.exit('Every row of the pixel grid must have the same length.')
    h, w = len(rows), len(rows[0])
    if w > 128 or h > 128:
        sys.exit('Pixel grids can be at most 128x128.')
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, key in enumerate(row):
            color = palette.get(key)
            if color:
                img.putpixel((x, y), hex_rgba(color))
    scale = scale or max(1, round(192 / max(w, h)))
    return img.resize((w * scale, h * scale), Image.NEAREST), True


def hex_rgba(value):
    value = value.lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    if len(value) == 6:
        value += 'ff'
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4, 6))


def render(args):
    png = getattr(args, 'png', None)
    if sum(bool(x) for x in (args.svg, args.grid, png)) != 1:
        sys.exit('Give exactly one of --svg, --grid or --png.')
    if png:
        img = Image.open(png).convert('RGBA')
        if args.width or args.height:
            img = img.resize((args.width or img.width, args.height or img.height), Image.LANCZOS)
        elif max(img.size) > 512:
            img.thumbnail((512, 512), Image.LANCZOS)
        small = max(img.size) <= 64
        return img, small
    return render_svg(args.svg, args.width, args.height) if args.svg else render_grid(args.grid, args.scale)


def encode(img):
    """PNG keeps transparency; large opaque art (backgrounds) becomes WebP."""
    opaque = img.getchannel('A').getextrema()[0] == 255
    buf = io.BytesIO()
    if opaque and img.width * img.height > 200_000:
        img.convert('RGB').save(buf, 'WEBP', quality=86, method=6)
        mime = 'image/webp'
    else:
        img.save(buf, 'PNG', optimize=True)
        mime = 'image/png'
    data = buf.getvalue()
    return f'data:{mime};base64,' + base64.b64encode(data).decode('ascii'), len(data)


def warnings_for(img, pixel):
    notes = []
    alpha = img.getchannel('A')
    box = alpha.getbbox()
    if not box:
        return ['The image is completely transparent: nothing was drawn.']
    if alpha.getextrema()[0] < 255:
        w, h = img.size
        if box[0] == 0 or box[1] == 0 or box[2] == w or box[3] == h:
            notes.append('The drawing touches the edge of the canvas; if it is a sprite (not a tile or background), it may be clipped. Leave a small margin.')
        filled = (box[2] - box[0]) * (box[3] - box[1]) / (w * h)
        if filled < 0.3:
            notes.append('The drawing is small inside its canvas; make it fill most of the frame so it reads at game size.')
    return notes


def preview_file(img, name):
    folder = Path(os.environ.get('TMPDIR') or tempfile.gettempdir()) / 'asset-preview'
    folder.mkdir(parents=True, exist_ok=True)
    tile = 16
    board = Image.new('RGBA', img.size, (40, 44, 70, 255))
    for y in range(0, img.height, tile):
        for x in range(0, img.width, tile):
            if (x // tile + y // tile) % 2:
                board.paste((56, 60, 92, 255), (x, y, min(x + tile, img.width), min(y + tile, img.height)))
    board.alpha_composite(img)
    # Also show it at in-game size so small-size readability can be judged.
    small = img.copy()
    small.thumbnail((64, 64), Image.LANCZOS)
    out = Image.new('RGBA', (board.width + 96, max(board.height, 96)), (24, 26, 40, 255))
    out.paste(board, (0, 0))
    out.alpha_composite(small, (board.width + 16, 16))
    path = folder / f'{name}.png'
    out.convert('RGB').save(path)
    return path


def parse_anims(spec, count):
    anims = {}
    for part in (spec or '').split(','):
        if not part.strip():
            continue
        key, _, rng = part.partition(':')
        key = key.strip().lower()
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,15}', key) or not rng:
            sys.exit(f'Bad --anims entry "{part}"; use name:first-last, e.g. walk:2-5.')
        lo, _, hi = rng.partition('-')
        lo, hi = int(lo), int(hi or lo)
        if not 0 <= lo <= hi < count:
            sys.exit(f'Animation "{key}" uses frames {lo}-{hi}, but there are only {count} frames (0-{count - 1}).')
        anims[key] = list(range(lo, hi + 1))
    if 'idle' not in anims:
        anims['idle'] = [0]
    return anims


def render_frames(paths, size):
    frames, pixel = [], False
    for path in paths:
        if path.endswith('.json'):
            img, pixel = render_grid(path)
            img = img.resize((size, size), Image.NEAREST) if img.size != (size, size) else img
        else:
            img, _ = render_svg(path, size, size)
        frames.append(img)
    return frames, pixel


def contact_sheet(frames, anims, name):
    lookup = {i: key for key, idx in anims.items() for i in idx}
    size = frames[0].width
    cell = size + 8
    board = Image.new('RGBA', (cell * len(frames) + 8, size + 40), (24, 26, 40, 255))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(board)
    for i, frame in enumerate(frames):
        x = 8 + i * cell
        bg = Image.new('RGBA', frame.size, (48, 52, 80, 255))
        bg.alpha_composite(frame)
        board.paste(bg, (x, 8))
        draw.text((x + 4, size + 14), f'{i} {lookup.get(i, "")}', fill=(220, 224, 255, 255))
    folder = Path(os.environ.get('TMPDIR') or tempfile.gettempdir()) / 'asset-preview'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{name}-frames.png'
    board.convert('RGB').save(path)
    return path


def character(args):
    paths = [p.strip() for p in (args.frames or '').split(',') if p.strip()]
    if not paths:
        sys.exit('Give the frames with --frames f0.svg,f1.svg,...')
    if len(paths) > 16:
        sys.exit('Use at most 16 frames.')
    size = args.size or 256
    frames, pixel = render_frames(paths, size)
    anims = parse_anims(args.anims, len(frames))
    notes = []
    for i, frame in enumerate(frames):
        for note in warnings_for(frame, pixel):
            notes.append(f'frame {i}: {note}')
    boxes = [f.getchannel('A').getbbox() for f in frames]
    feet = [b[3] for b in boxes if b]
    if feet and max(feet) - min(feet) > size * 0.12 and 'jump' not in anims:
        notes.append('The character\'s feet move up and down a lot between frames; keep the ground line steady.')
    preview = contact_sheet(frames, anims, args.name if NAME_RE.match(args.name or '') else 'character')
    if args.preview:
        print(json.dumps({'ok': True, 'preview': str(preview), 'frames': len(frames), 'animations': anims, 'warnings': notes,
                          'next': 'Read the preview: same character in every frame, limbs clearly moving in walk, nothing clipped. Then save without --preview.'}))
        return
    check_name(args.name)
    sheet = Image.new('RGBA', (size * len(frames), size), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        sheet.alpha_composite(frame, (i * size, 0))
    buf = io.BytesIO()
    sheet.save(buf, 'PNG', optimize=True)
    data = buf.getvalue()
    if len(data) > MAX_SHEET_BYTES:
        sys.exit(f'The sheet is {len(data) // 1024} KB; keep it under {MAX_SHEET_BYTES // 1024} KB (fewer frames, simpler shapes, or --size 192).')
    thumb = frames[0].copy()
    thumb.thumbnail((128, 128), Image.NEAREST if pixel else Image.LANCZOS)
    thumb_url, _ = encode(thumb)
    entry = {'dataUrl': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii'), 'frameWidth': size, 'frameHeight': size,
             'frameCount': len(frames), 'animations': anims, 'thumb': thumb_url, 'pixel': pixel}
    if args.game:
        path = f'games/{args.game}.art.json'
        art = storage_get(args.app_id, path) or {}
        art['sheets'] = {**(art.get('sheets') or {}), args.name: entry}
        storage_put_json(args.app_id, path, art)
        where = f'game {args.game}'
    else:
        assets = storage_get(args.app_id, 'assets.json') or {}
        old = (assets.get('characters') or {}).get(args.name) or {}
        meta = {k: v for k, v in (('role', args.role or args.type), ('view', args.view), ('style', args.style), ('prompt', args.prompt)) if v}
        assets['characters'] = {**(assets.get('characters') or {}), args.name: {
            **old, **entry, 'kind': '2d', **meta, 'type': meta.get('role') or old.get('role') or old.get('type') or ''}}
        if args.source_svg:
            api_put_text(args.app_id, f'character-src/{args.name}.svg', Path(args.source_svg).read_text(encoding='utf8'))
        storage_put_json(args.app_id, 'assets.json', assets)
        where = 'Characters'
    print(json.dumps({'ok': True, 'saved': 'character', 'name': args.name, 'where': where, 'frames': len(frames),
                      'animations': anims, 'bytes': len(data), 'warnings': notes}))


def api_put_text(app_id, path, text, ctype='image/svg+xml'):
    from build_art import api
    api('PUT', f'/api/storage/apps/{app_id}/{path}', text.encode('utf8'), ctype)


def still_image(args):
    if args.png:
        img = Image.open(args.png).convert('RGBA')
        img.thumbnail((256, 256), Image.LANCZOS)
        return img, False, None
    img, pixel = render(args)
    return img, pixel, (Path(args.svg).read_text(encoding='utf8') if args.svg else None)


def draft(args):
    """A character design waiting for the person to Keep it, retry it or change it."""
    if not args.job or not re.fullmatch(r'[a-z0-9]{4,40}', args.job):
        sys.exit('draft needs --job ID (the job id given in the request).')
    img, pixel, svg = still_image(args)
    notes = warnings_for(img, pixel)
    data_url, size = encode(img)
    if size > MAX_ASSET_BYTES:
        sys.exit(f'The design is {size // 1024} KB; keep it under {MAX_ASSET_BYTES // 1024} KB.')
    record = {'id': args.job, 'name': args.name, 'dataUrl': data_url, 'w': img.width, 'h': img.height, 'pixel': pixel,
              'kind': '2d', 'source': args.source or 'ai', 'style': args.style, 'view': args.view or 'side',
              'prompt': args.prompt[:400], 'svg': svg if svg and len(svg) < 120_000 else None}
    storage_put_json(args.app_id, f'character-drafts/{args.job}.json', record)
    print(json.dumps({'ok': True, 'saved': 'draft', 'name': args.name, 'job': args.job, 'warnings': notes,
                      'next': 'Done: the person now sees the design and can Keep it, retry it, or ask for changes.'}))


def still(args):
    """Replace a kept character's look with one still pose (its animations must then be redrawn)."""
    check_name(args.name)
    img, pixel, svg = still_image(args)
    data_url, _ = encode(img)
    assets = storage_get(args.app_id, 'assets.json') or {}
    old = (assets.get('characters') or {}).get(args.name)
    if not old:
        sys.exit(f'There is no character "{args.name}" in the gallery.')
    assets['characters'][args.name] = {**old, 'kind': '2d', 'dataUrl': data_url, 'thumb': data_url, 'frameWidth': img.width,
                                       'frameHeight': img.height, 'frameCount': 1, 'animations': {'idle': [0]}, 'pixel': pixel}
    storage_put_json(args.app_id, 'assets.json', assets)
    if svg:
        api_put_text(args.app_id, f'character-src/{args.name}.svg', svg)
    print(json.dumps({'ok': True, 'saved': 'still', 'name': args.name,
                      'note': 'The look is replaced and its animations were reset to one idle frame. Redraw the animations it had: ' + ', '.join(old.get('animations', {}).keys())}))


def char_meta(args):
    check_name(args.name)
    assets = storage_get(args.app_id, 'assets.json') or {}
    old = (assets.get('characters') or {}).get(args.name)
    if not old:
        sys.exit(f'There is no character "{args.name}" in the gallery.')
    meta = {k: v for k, v in (('role', args.role), ('view', args.view), ('prompt', args.prompt), ('style', args.style)) if v}
    if 'role' in meta:
        meta['type'] = meta['role']
    assets['characters'][args.name] = {**old, **meta}
    storage_put_json(args.app_id, 'assets.json', assets)
    print(json.dumps({'ok': True, 'saved': 'meta', 'name': args.name, **meta}))


def check_name(name):
    if not NAME_RE.match(name or ''):
        sys.exit('Names are lowercase letters, numbers, - or _, up to 32 characters (e.g. hero, coin, sky-bg).')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('app_id')
    parser.add_argument('action', choices=['preview', 'save', 'sound', 'character', 'draft', 'still', 'char-meta'])
    parser.add_argument('name', nargs='?', default='preview')
    parser.add_argument('--svg')
    parser.add_argument('--grid')
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--scale', type=int)
    parser.add_argument('--game')
    parser.add_argument('--prompt', default='')
    parser.add_argument('--kind', default='')
    parser.add_argument('--style', default='')
    parser.add_argument('--zzfx')
    parser.add_argument('--frames')
    parser.add_argument('--anims', default='')
    parser.add_argument('--size', type=int)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--type', default='')
    parser.add_argument('--view', default='')
    parser.add_argument('--role', default='')
    parser.add_argument('--job')
    parser.add_argument('--png')
    parser.add_argument('--source', default='')
    parser.add_argument('--source-svg')
    args = parser.parse_args()
    sid = args.app_id

    if args.action in ('character', 'draft', 'still', 'char-meta'):
        {'character': character, 'draft': draft, 'still': still, 'char-meta': char_meta}[args.action](args)
        return

    if args.action == 'sound':
        check_name(args.name)
        try:
            params = json.loads(args.zzfx or '')
        except json.JSONDecodeError as err:
            sys.exit(f'--zzfx must be a JSON array of numbers: {err}')
        if not isinstance(params, list) or not params or len(params) > 21 or not all(v is None or isinstance(v, (int, float)) for v in params):
            sys.exit('--zzfx must be a JSON array of up to 21 numbers (null skips a value).')
        assets = storage_get(sid, 'assets.json') or {}
        assets.setdefault('sprites', {})
        assets['sounds'] = {**(assets.get('sounds') or {}), args.name: params}
        storage_put_json(sid, 'assets.json', assets)
        print(json.dumps({'ok': True, 'saved': 'sound', 'name': args.name, 'where': 'Assets'}))
        return

    img, pixel = render(args)
    notes = warnings_for(img, pixel)
    if args.action == 'preview':
        path = preview_file(img, re.sub(r'[^a-z0-9_-]', '-', args.name.lower()) or 'preview')
        print(json.dumps({'ok': True, 'preview': str(path), 'size': list(img.size), 'warnings': notes,
                          'next': 'Read the preview image. Fix clipping, muddy shapes or a weak silhouette, then save.'}))
        return

    check_name(args.name)
    data_url, size = encode(img)
    if size > MAX_ASSET_BYTES:
        sys.exit(f'The image is {size // 1024} KB; keep assets under {MAX_ASSET_BYTES // 1024} KB (simplify it or make it smaller).')
    if args.game:
        path = f'games/{args.game}.art.json'
        art = storage_get(sid, path) or {}
        art['images'] = {**(art.get('images') or {}), args.name: {'dataUrl': data_url, 'w': img.width, 'h': img.height, 'pixel': pixel}}
        storage_put_json(sid, path, art)
        where = f'game {args.game}'
    else:
        assets = storage_get(sid, 'assets.json') or {}
        assets.setdefault('sounds', {})
        assets['sprites'] = {**(assets.get('sprites') or {}), args.name: {
            'dataUrl': data_url, 'width': img.width, 'height': img.height, 'pixel': pixel,
            'ai': True, 'prompt': args.prompt[:400], 'kind': args.kind[:20], 'style': args.style[:20]}}
        storage_put_json(sid, 'assets.json', assets)
        where = 'Assets'
    print(json.dumps({'ok': True, 'saved': 'image', 'name': args.name, 'where': where, 'size': list(img.size),
                      'bytes': size, 'warnings': notes}))


if __name__ == '__main__':
    main()
