#!/usr/bin/env python3
"""Tools for the Dream Gallery's room builder (see GALLERY_ROOMS.md).

  python3 gallery_room.py catalog                              what a recipe can contain
  python3 gallery_room.py show <appId> <roomId>                the room's current recipe ({} if none yet)
  python3 gallery_room.py validate recipe.json [--quiet]        check a recipe; prints the cleaned version and warnings
  python3 gallery_room.py starter [name]                       list the ready-made recipes, or print one to adapt
  python3 gallery_room.py put <appId> <roomId> recipe.json [--preview [--views ...] [--full]]
                                                               check it, put it in the gallery (the room updates live), and optionally render it right away
  python3 gallery_room.py preview <appId> <roomId> [--views spawn,left,right,back] [--size 800x500] [--full]
                                                               render the room and print screenshot paths (Read them)

Needs API_BASE_URL and AGENT_TOKEN (present in Möbius agent runs).
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
TOKEN = os.environ.get('AGENT_TOKEN', '')

ENVS = ['hall', 'dome', 'open', 'void']
SKIES = ['day', 'dusk', 'dawn', 'night', 'overcast', 'storm', 'alien']
SURFACES = ['wood', 'marble', 'stone', 'brick', 'tile', 'checker', 'carpet', 'sand', 'concrete', 'plaster', 'plain', 'glossy']
PROPS = ['tree', 'rock', 'grass', 'flowers', 'pillar', 'arch', 'orb', 'crystal', 'lantern', 'candle', 'plant', 'bookshelf', 'table', 'rug', 'pedestal',
         'window', 'banner', 'beam', 'ring', 'mushroom', 'cloud', 'campfire', 'model']
STANDS = ['post', 'pillar', 'easel', 'crystal', 'iron', 'vine', 'neon', 'bamboo', 'wall', 'chain', 'rail']
TREE_KINDS = ['oak', 'blossom', 'autumn', 'pine']
PARTICLES = ['fireflies', 'dust', 'snow', 'rain', 'petals', 'embers', 'bubbles', 'stars']
MODELS = ['street-lamp', 'bench', 'neon-palm', 'balloon-bunch', 'lighthouse', 'mobius-crystal', 'mobius-moon', 'sea-glow', 'party-string-lights',
          'flower-daisy', 'flower-orange', 'flower-pink', 'flower-purple', 'flower-tulip', 'grass-tuft', 'grass-tall', 'stone-big', 'stone-small']
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')

CATALOG = {
    'env': {'hall': 'indoor rectangular hall (size w,l,h); pictures hang on both long walls',
            'dome': 'indoor round room (size r,h); pictures hang around the wall; roof "closed" or "open" (sky overhead)',
            'open': 'outdoor landscape: terrain (hills, mountains, lake), sky, sun, fog; pictures stand on posts in a "ring" or along a "path" (hang)',
            'void': 'dark endless floor under a sky (night by default); pictures float in a "path"'},
    'stand styles (what pictures hang on)': {'outdoor (open, void)': ['post', 'pillar', 'easel', 'crystal', 'iron', 'vine', 'neon', 'bamboo'], 'indoor (hall, dome)': ['wall', 'chain', 'rail', 'neon']},
    'sky styles': SKIES, 'surfaces (floor / walls)': SURFACES, 'prop types': PROPS, 'tree kinds': TREE_KINDS,
    'particles': PARTICLES, 'library models (type "model", "name")': MODELS,
    'light': 'hemi{sky,ground,intensity}, ambient, sun{color,intensity,dir[x,y,z]}, lamps[{at[x,z],y,color,intensity,range,flicker}] (max 4 lamps)',
    'placing props': 'each prop has ONE of: at [x,z] | area {center[x,z],radius,inner} + count | line {from,to,count} | ring {center,radius,count}. '
                     'Coordinates are metres from the room centre; +z is toward the entrance/spawn, -z the far end. y lifts a prop (lanterns, orbs, windows). rot is degrees.',
}


def call(method, path, body=None, ctype='application/json'):
    req = urllib.request.Request(BASE + path, method=method, data=body, headers={'Authorization': 'Bearer ' + TOKEN, **({'Content-Type': ctype} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise


def num(v, lo, hi, d=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return d
    return max(lo, min(hi, f))


def pair(v):
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        a, b = num(v[0], -400, 400), num(v[1], -400, 400)
        if a is not None and b is not None:
            return [a, b]
    return None


def clean(spec, warn):
    if not isinstance(spec, dict):
        warn('the recipe must be a JSON object')
        return {}
    out = {}
    if isinstance(spec.get('name'), str) and spec['name'].strip():
        out['name'] = spec['name'].strip()[:40]
    if isinstance(spec.get('description'), str):
        out['description'] = spec['description'][:300]
    env = spec.get('env', 'hall')
    if env not in ENVS:
        warn(f'env "{env}" is not one of {ENVS}; using hall')
        env = 'hall'
    out['env'] = env
    pal = spec.get('palette') or {}
    out['palette'] = {k: pal[k] for k in ('wall', 'floor', 'ceiling', 'trim', 'accent', 'glow') if HEX.match(str(pal.get(k, '')))}
    for k in pal:
        if k not in ('wall', 'floor', 'ceiling', 'trim', 'accent', 'glow'):
            warn(f'palette.{k} is not used')
    for key in ('floor', 'walls'):
        if spec.get(key) is not None:
            if spec[key] in SURFACES:
                out[key] = spec[key]
            else:
                warn(f'{key} "{spec[key]}" is not one of {SURFACES}')
    size = spec.get('size') or {}
    out['size'] = {k: num(size[k], 1, 80) for k in ('w', 'l', 'h', 'r', 'ring') if k in size and num(size[k], 1, 80) is not None}
    for k in ('roof', 'hang'):
        if spec.get(k) in ('closed', 'open', 'ring', 'path'):
            out[k] = spec[k]
    for k in ('ceilingLights', 'rug', 'title'):
        if isinstance(spec.get(k), bool):
            out[k] = spec[k]
    if spec.get('rug') == 'kilim':
        out['rug'] = 'kilim'
    if spec.get('sound') in ('lobby', 'void', 'garden', 'memory'):
        out['sound'] = spec['sound']
    sky = spec.get('sky') or {}
    if sky:
        s = {}
        if sky.get('style') in SKIES:
            s['style'] = sky['style']
        elif 'style' in sky:
            warn(f'sky.style must be one of {SKIES}')
        for k in ('zenith', 'mid', 'horizon', 'sunColor'):
            if HEX.match(str(sky.get(k, ''))):
                s[k] = sky[k]
        if isinstance(sky.get('sun'), list) and len(sky['sun']) == 3:
            s['sun'] = [num(v, -1, 1, 0) for v in sky['sun']]
        for k, hi in (('clouds', 1), ('stars', 1)):
            if num(sky.get(k), 0, hi) is not None:
                s[k] = num(sky[k], 0, hi)
        if isinstance(sky.get('moon'), bool):
            s['moon'] = sky['moon']
        out['sky'] = s
    t = spec.get('terrain') or {}
    if t:
        tt = {}
        for k in ('ground', 'ground2', 'rock', 'snowColor'):
            if HEX.match(str(t.get(k, ''))):
                tt[k] = t[k]
        for k, hi in (('hills', 1), ('mountains', 1), ('flatRadius', 40), ('seed', 99)):
            if num(t.get(k), 0, hi) is not None:
                tt[k] = num(t[k], 0, hi)
        if isinstance(t.get('snow'), bool):
            tt['snow'] = t['snow']
        lake = t.get('lake')
        if isinstance(lake, dict) and pair(lake.get('at')):
            tt['lake'] = {'at': pair(lake['at']), 'radius': num(lake.get('radius'), 2, 30, 6), **({'color': lake['color']} if HEX.match(str(lake.get('color', ''))) else {})}
        out['terrain'] = tt
    fog = spec.get('fog') or {}
    if fog:
        out['fog'] = {**({'color': fog['color']} if HEX.match(str(fog.get('color', ''))) else {}), **({'density': num(fog['density'], 0, 0.2)} if num(fog.get('density'), 0, 0.2) is not None else {})}
    light = spec.get('light') or {}
    if light:
        lo = {}
        if isinstance(light.get('hemi'), dict):
            h = light['hemi']
            lo['hemi'] = {**{k: h[k] for k in ('sky', 'ground') if HEX.match(str(h.get(k, '')))}, **({'intensity': num(h['intensity'], 0, 4)} if num(h.get('intensity'), 0, 4) is not None else {})}
        if num(light.get('ambient'), 0, 3) is not None:
            lo['ambient'] = num(light['ambient'], 0, 3)
        if isinstance(light.get('sun'), dict):
            sn = light['sun']
            lo['sun'] = {**({'color': sn['color']} if HEX.match(str(sn.get('color', ''))) else {}), **({'intensity': num(sn['intensity'], 0, 8)} if num(sn.get('intensity'), 0, 8) is not None else {}),
                         **({'dir': [num(v, -1, 1, 0) for v in sn['dir']]} if isinstance(sn.get('dir'), list) and len(sn['dir']) == 3 else {})}
        lamps = []
        for lamp in (light.get('lamps') or [])[:4]:
            if isinstance(lamp, dict) and pair(lamp.get('at')):
                lamps.append({'at': pair(lamp['at']), **({'y': num(lamp['y'], 0.2, 20)} if num(lamp.get('y'), 0.2, 20) is not None else {}),
                              **({'color': lamp['color']} if HEX.match(str(lamp.get('color', ''))) else {}),
                              **({'intensity': num(lamp['intensity'], 0, 60)} if num(lamp.get('intensity'), 0, 60) is not None else {}),
                              **({'range': num(lamp['range'], 3, 60)} if num(lamp.get('range'), 3, 60) is not None else {}), **({'flicker': True} if lamp.get('flicker') else {})})
        if len(light.get('lamps') or []) > 4:
            warn('only the first 4 lamps are used')
        if lamps:
            lo['lamps'] = lamps
        out['light'] = lo
    if 'frame' in spec:
        warn('frame is not used: frames look the same in every room. Design the stand instead (stand.style / color / accent)')
    st = spec.get('stand')
    if isinstance(st, dict):
        so = {}
        if st.get('style') in STANDS:
            so['style'] = st['style']
        elif 'style' in st:
            warn(f'stand.style must be one of {STANDS}')
        for k in ('color', 'accent'):
            if HEX.match(str(st.get(k, ''))):
                so[k] = st[k]
        out['stand'] = so
        indoor = out['env'] in ('hall', 'dome')
        if so.get('style') and ((indoor and so['style'] not in ('wall', 'chain', 'rail', 'neon')) or (not indoor and so['style'] in ('wall', 'chain', 'rail'))):
            warn(f'stand style "{so["style"]}" does not fit env "{out["env"]}": a fitting default is used instead')
    props = []
    for i, p in enumerate((spec.get('props') or [])):
        if not isinstance(p, dict) or p.get('type') not in PROPS:
            warn(f'props[{i}]: unknown type "{p.get("type") if isinstance(p, dict) else p}" (see catalog)')
            continue
        q = {'type': p['type']}
        if p['type'] == 'tree' and p.get('kind') in TREE_KINDS:
            q['kind'] = p['kind']
        if p['type'] == 'model':
            if p.get('name') not in MODELS:
                warn(f'props[{i}]: model "{p.get("name")}" is not in the library list')
                continue
            q['name'] = p['name']
        for k, lo, hi in (('count', 1, 600), ('scale', 0.1, 30), ('vary', 0, 1.2), ('rot', -360, 360), ('y', 0, 120), ('height', 0.1, 40), ('width', 0.3, 12), ('radius', 0.1, 400), ('top', 1, 20)):
            if num(p.get(k), lo, hi) is not None:
                q[k] = num(p[k], lo, hi)
        if HEX.match(str(p.get('color', ''))):
            q['color'] = p['color']
        placed = False
        if pair(p.get('at')):
            q['at'] = pair(p['at']); placed = True
        for key in ('area', 'ring'):
            v = p.get(key)
            if isinstance(v, dict) and pair(v.get('center')) is not None:
                q[key] = {'center': pair(v['center']), 'radius': num(v.get('radius'), 0.5, 400, 8), **({'inner': num(v['inner'], 0, 400)} if key == 'area' and num(v.get('inner'), 0, 400) is not None else {}),
                          **({'count': int(num(v['count'], 1, 600))} if key == 'ring' and num(v.get('count'), 1, 600) is not None else {})}
                placed = True
        ln = p.get('line')
        if isinstance(ln, dict) and pair(ln.get('from')) and pair(ln.get('to')):
            q['line'] = {'from': pair(ln['from']), 'to': pair(ln['to']), 'count': int(num(ln.get('count'), 1, 600, 5))}; placed = True
        if not placed:
            q['at'] = [0, 0]
            warn(f'props[{i}] ({p["type"]}) has no at/area/line/ring: placed at the centre')
        props.append(q)
    if len(spec.get('props') or []) > 40:
        warn('only the first 40 props are used')
    out['props'] = props[:40]
    parts = spec.get('particles')
    if isinstance(parts, dict):
        parts = [parts]
    plist = []
    for p in (parts or [])[:3]:
        if isinstance(p, dict) and p.get('type') in PARTICLES:
            plist.append({'type': p['type'], **({'count': int(num(p['count'], 10, 500))} if num(p.get('count'), 10, 500) is not None else {}),
                          **({'color': p['color']} if HEX.match(str(p.get('color', ''))) else {}), **({'radius': num(p['radius'], 2, 80)} if num(p.get('radius'), 2, 80) is not None else {}),
                          **({'height': num(p['height'], 1, 40)} if num(p.get('height'), 1, 40) is not None else {})})
        else:
            warn(f'particles: unknown type; use one of {PARTICLES}')
    out['particles'] = plist
    if out['env'] in ('hall', 'dome') and out.get('sky') and not (out['env'] == 'dome' and out.get('roof') == 'open'):
        warn('sky is only visible in env "open", "void", or a dome with roof "open"')
    return out


def storage_path(app, room):
    return f'/api/storage/apps/{app}/public/room-{re.sub(r"[^a-z0-9_-]", "", room, flags=re.I)[:60]}.json'


def load(path):
    with open(path, encoding='utf8') as f:
        return json.load(f)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == 'catalog':
        print(json.dumps(CATALOG, indent=2))
    elif cmd == 'validate':
        warnings = []
        spec = clean(load(sys.argv[2]), warnings.append)
        print(json.dumps({'warnings': warnings} if '--quiet' in sys.argv else {'warnings': warnings, 'recipe': spec}, indent=None if '--quiet' in sys.argv else 2, ensure_ascii=False))
    elif cmd == 'show':
        raw = call('GET', storage_path(sys.argv[2], sys.argv[3]))
        print(raw.decode() if raw else '{}')
    elif cmd == 'put':
        app, room = sys.argv[2], sys.argv[3]
        warnings = []
        spec = clean(load(sys.argv[4]), warnings.append)
        spec.setdefault('name', spec.get('name'))
        prev = call('GET', storage_path(app, room))
        try:
            rev = int((json.loads(prev) if prev else {}).get('rev', 0)) + 1
        except (ValueError, TypeError):
            rev = 1
        spec['rev'] = rev
        spec['updatedAt'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        call('PUT', storage_path(app, room), json.dumps(spec, ensure_ascii=False).encode(), 'application/json')
        print(json.dumps({'ok': True, 'rev': rev, 'warnings': warnings, 'note': 'The room is updating in the gallery now.' + ('' if '--preview' in sys.argv else ' Run preview to look at it.')}, ensure_ascii=False), flush=True)
        if '--preview' in sys.argv:
            extra = [a for a in sys.argv[5:] if a != '--preview']
            proc = subprocess.run(['node', str(HERE / 'gallery_preview.mjs'), app, room, *extra], capture_output=True, text=True, timeout=900)
            print(proc.stdout.strip() or proc.stderr.strip())
            sys.exit(proc.returncode)
    elif cmd == 'starter':
        d = HERE / 'gallery_starters'
        names = sorted(p.stem for p in d.glob('*.json'))
        if len(sys.argv) < 3:
            for n in names:
                spec = load(d / f'{n}.json')
                print(f'{n}: {spec.get("env")} · {spec.get("name")}')
        elif sys.argv[2] in names:
            print((d / f'{sys.argv[2]}.json').read_text(encoding='utf8'))
        else:
            sys.exit(f'unknown starter; choose from {names}')
    elif cmd == 'preview':
        app, room = sys.argv[2], sys.argv[3]
        proc = subprocess.run(['node', str(HERE / 'gallery_preview.mjs'), app, room, *sys.argv[4:]], capture_output=True, text=True, timeout=900)
        print(proc.stdout.strip() or proc.stderr.strip())
        sys.exit(proc.returncode)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
