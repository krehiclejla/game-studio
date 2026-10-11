#!/usr/bin/env python3
"""Edit a scene game one precise step at a time (the studio assistant's tool).

  python3 scene.py show     SID GID                     the scene, compactly
  python3 scene.py add      SID GID 'OBJECT' ['OBJECT' ...]   add objects (JSON); prints their ids
  python3 scene.py update   SID GID ID 'PATCH'            change fields of one object (JSON; null removes a field)
  python3 scene.py remove   SID GID ID [ID ...]
  python3 scene.py settings SID GID 'PATCH'               sky, skybox, fog, light, music, musicVolume, name, winMessage
  python3 scene.py script   SID GID NAME FILE.js          add or replace a game script (FILE '-' removes it)
  python3 scene.py library  SID                           the person's characters, 3D assets and sound files
  python3 scene.py new      SID GID                       turn a game with no content into an empty scene

Each change saves scene.json in the game's Project, rebuilds game.html (what plays in
the studio and in the installed app) and syncs the studio. See SCENE.md for the format.
Needs AGENT_TOKEN (agent runs).
"""
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import game_project as gp  # noqa: E402

TYPES = {'terrain', 'water', 'box', 'sphere', 'cylinder', 'cone', 'plane', 'model', 'character', 'light', 'spawn'}
BEHAVIORS = {'player', 'spin', 'bob', 'collectible', 'chase', 'hurts', 'solid', 'trigger', 'script'}


def runtime():
    text = (ROOT / 'sceneRuntime.js').read_text()
    start = text.index('String.raw`') + len('String.raw`')
    return text[start:text.index('\n`\n', start) + 1]


def document(scene):
    """Same page as sceneRuntime.sceneDocument(scene, 'play')."""
    name = re.sub(r'[<&]', '', str(scene.get('name') or 'Game'))
    data = json.dumps(scene, ensure_ascii=False).replace('<', '\\u003c')
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<title>{name}</title><style>html,body{{margin:0;height:100%;overflow:hidden;background:#0b1020}}</style></head><body>'
            f'<script type="application/json" id="scene">{data}</script>'
            f'<script type="module">{runtime()}</script></body></html>')


def folder(sid, gid):
    report = gp.ensure(sid, gid)
    return Path(report['folder'])


def load(root):
    path = root / 'scene.json'
    if not path.exists():
        sys.exit('This game is not a scene game (no scene.json). Run: scene.py new SID GID (only for a game with no content yet).')
    return json.loads(path.read_text())


def save(root, scene, what):
    problems = check(scene)
    (root / 'scene.json').write_text(json.dumps(scene, ensure_ascii=False, indent=2))
    (root / 'game.html').write_text(document(scene))
    meta_path = root / 'game.json'
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta['name'] = scene.get('name') or meta.get('name') or 'Untitled game'
    meta['kind'] = 'scene'
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    report = gp.sync(str(meta['studioAppId']), meta['id'], first_message=what)
    print(json.dumps({'ok': True, 'change': what, 'objects': len(scene.get('objects', [])), 'problems': problems,
                      'synced': bool(report.get('to_studio'))}, ensure_ascii=False))


def check(scene):
    out = []
    ids = set()
    for o in scene.get('objects', []):
        if o.get('id') in ids:
            out.append(f'duplicate id {o.get("id")}')
        ids.add(o.get('id'))
        if o.get('type') not in TYPES:
            out.append(f'{o.get("id")}: unknown type {o.get("type")!r} (use {", ".join(sorted(TYPES))})')
        for b in o.get('behaviors') or []:
            if b.get('type') not in BEHAVIORS:
                out.append(f'{o.get("id")}: unknown behavior {b.get("type")!r} (use {", ".join(sorted(BEHAVIORS))})')
        if o.get('type') == 'character' and not o.get('character'):
            out.append(f'{o.get("id")}: a character needs "character": NAME from the library')
        if o.get('type') == 'model' and not o.get('asset'):
            out.append(f'{o.get("id")}: a model needs "asset": NAME from the library')
    players = [o['id'] for o in scene.get('objects', []) if any(b.get('type') == 'player' for b in o.get('behaviors') or [])]
    if len(players) > 1:
        out.append(f'more than one player: {players}')
    return out


def new_id(scene, name, kind):
    base = re.sub(r'[^a-z0-9]+', '-', str(name or kind).lower()).strip('-')[:24] or kind
    taken = {o.get('id') for o in scene.get('objects', [])}
    if base not in taken:
        return base
    n = 2
    while f'{base}-{n}' in taken:
        n += 1
    return f'{base}-{n}'


def merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def summary(scene):
    lines = [f'Scene "{scene.get("name")}"  settings: {json.dumps(scene.get("settings", {}), ensure_ascii=False)}']
    for o in scene.get('objects', []):
        extra = {k: v for k, v in o.items() if k not in ('id', 'name', 'type', 'position', 'behaviors')}
        beh = ', '.join(b.get('type', '?') for b in o.get('behaviors') or [])
        pos = o.get('position')
        lines.append(f'- {o["id"]} ({o.get("type")}) "{o.get("name", "")}" at {pos}' + (f' behaviors: {beh}' if beh else '')
                     + (f' {json.dumps(extra, ensure_ascii=False)}' if extra else ''))
    for s in scene.get('scripts', []):
        lines.append(f'- script "{s["name"]}" ({len(s.get("code", ""))} chars)')
    if not scene.get('objects'):
        lines.append('(no objects yet)')
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ('show', 'add', 'update', 'remove', 'settings', 'script', 'library', 'new'):
        sys.exit(__doc__)
    action, sid = sys.argv[1], sys.argv[2]
    if action == 'library':
        assets = json.loads(gp.storage_read(sid, 'assets.json') or b'{}')
        chars = {n: {k: c.get(k) for k in ('role', 'height', 'body', 'animations')} for n, c in (assets.get('characters') or {}).items() if c.get('kind') == '3d'}
        models = sorted(n for n in (assets.get('models') or {}) if n not in chars)
        sounds = {n: a.get('kind') for n, a in (assets.get('audio') or {}).items()}
        print(json.dumps({'characters': chars, 'assets': models, 'sounds': sounds}, ensure_ascii=False, indent=1))
        return
    gid = sys.argv[3]
    root = folder(sid, gid)
    args = sys.argv[4:]
    if action == 'new':
        if (root / 'scene.json').exists():
            sys.exit('This game is already a scene.')
        if (root / 'game.html').exists() and (root / 'game.html').read_text().strip():
            sys.exit('This game already has content as an HTML game; keep editing it that way.')
        meta = json.loads((root / 'game.json').read_text())
        scene = {'version': 1, 'name': meta.get('name') or 'Untitled game', 'settings': {'sky': '#9fc9ea', 'light': {}}, 'objects': [], 'scripts': []}
        save(root, scene, 'Start an empty scene')
        return
    scene = load(root)
    if action == 'show':
        print(summary(scene))
        return
    if action == 'add':
        if not args:
            sys.exit('add needs one or more objects as JSON.')
        added = []
        for raw in args:
            o = json.loads(raw)
            o['id'] = o.get('id') or new_id(scene, o.get('name'), o.get('type', 'object'))
            if o['id'] in {x['id'] for x in scene['objects']}:
                o['id'] = new_id(scene, o['id'], o.get('type', 'object'))
            o.setdefault('name', o['id'].replace('-', ' '))
            scene['objects'].append(o)
            added.append(o['id'])
        print(json.dumps({'added': added}))
        save(root, scene, 'Add ' + ', '.join(added))
    elif action == 'update':
        oid, patch = args[0], json.loads(args[1])
        for i, o in enumerate(scene['objects']):
            if o['id'] == oid:
                scene['objects'][i] = merge(o, patch)
                break
        else:
            sys.exit(f'No object "{oid}". Run show to see the ids.')
        save(root, scene, f'Change {oid}')
    elif action == 'remove':
        before = len(scene['objects'])
        scene['objects'] = [o for o in scene['objects'] if o['id'] not in args]
        if len(scene['objects']) == before:
            sys.exit('Nothing removed: no such ids.')
        save(root, scene, 'Remove ' + ', '.join(args))
    elif action == 'settings':
        patch = json.loads(args[0])
        if 'name' in patch:
            scene['name'] = patch.pop('name')
        if 'winMessage' in patch:
            scene['winMessage'] = patch.pop('winMessage')
        scene['settings'] = merge(scene.get('settings', {}), patch)
        save(root, scene, 'Change the scene settings')
    elif action == 'script':
        name, path = args[0], args[1]
        scripts = [s for s in scene.get('scripts', []) if s['name'] != name]
        if path != '-':
            scripts.append({'name': name, 'code': Path(path).read_text()})
        scene['scripts'] = scripts
        save(root, scene, ('Remove' if path == '-' else 'Update') + f' script {name}')


if __name__ == '__main__':
    main()
