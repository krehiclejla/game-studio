"""What a game project shares with the people the owner invited to it.

Editors and maintainers of a game project run Game Studio from the shared
project page, in a space of their own (see the template's guest_storage in
mobius.json). Their library is this game's: the characters, models, sprites
and sounds its scene uses. This module, run by the owner's sync, keeps that
in step both ways:

  publish(...)      copies this game's library items into the studio storage
                    folder guest-share/<projectId>/ (read-only for guests), and
                    writes .studio/GUIDE.md in the project for their assistant.
  import_back(...)  adds what guests made (.studio/assets.json and
                    .studio/models/ in the project, once merged or made live)
                    to the owner's library, never overwriting the owner's own.

Nothing else of the owner's library or other games is shared.
"""
import json
import sys
from pathlib import Path

SECTIONS = ('characters', 'models', 'sprites', 'sounds')
STUDIO_DIR = Path(__file__).resolve().parent
GUIDE = '.studio/GUIDE.md'


def used_names(scene):
    """Library names a scene refers to (objects' "asset", at any depth)."""
    names = set()

    def walk(value):
        if isinstance(value, dict):
            asset = value.get('asset')
            if isinstance(asset, str) and asset:
                names.add(asset)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk((scene or {}).get('objects') or [])
    return names


def library_subset(library, names):
    out = {}
    for section in SECTIONS:
        items = (library or {}).get(section) or {}
        picked = {name: items[name] for name in sorted(names) if name in items}
        if picked:
            out[section] = picked
    return out


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def guide_text(shared, own, sid=12):
    lines = [
        '# Guide for this game\'s assistant',
        '',
        'This project is a Game Studio game. You edit its files; the studio on the',
        'project page shows the result after each of your replies.',
        '',
        '- `scene.json`: the 3D scene. Build the game by adding, moving and changing its',
        '  objects (format below). Keep every object\'s `id`.',
        '- `game.json`: the game\'s name, description and controls (keep `id`).',
        '- `art.json`: art made for this game only.',
        '- `.studio/assets.json`: library items made in this project; their 3D files are',
        '  in `.studio/models/<name>.glb`.',
        '',
        'Use library items by their exact name in an object\'s `"asset"`, e.g.',
        '`{"type": "model", "asset": "bench", "position": [2, 0, 3]}`.',
        '',
        '## Making assets',
        '',
        f'Game Studio\'s free tools are in `../tools/game-studio/` (next to this folder;',
        'read the top of each file for every option). The first run installs a few Python',
        'packages, which takes a minute. Each tool saves into this project\'s library',
        '(`.studio/`), and the guest sees it in the studio after your reply.',
        '',
        f'- Picture or 2D sprite: draw `NAME.svg` (or a pixel grid), check it with',
        f'  `python3 ../tools/game-studio/make_asset.py {sid} preview --svg NAME.svg` (read the',
        f'  PNG it prints), then `python3 ../tools/game-studio/make_asset.py {sid} save NAME --svg NAME.svg`.',
        f'- Sound effect: `python3 ../tools/game-studio/make_asset.py {sid} sound NAME --zzfx \'[1,.05,220,...]\'`.',
        '- 3D object (furniture, props, tools, buildings): write `build.py` that starts with',
        '  `import sys; sys.path.insert(0, "../tools/game-studio"); from shapes import *`, builds',
        '  the parts and calls `save("NAME.glb", [...])`; run it, then',
        f'  `python3 ../tools/game-studio/model_tool.py asset {sid} NAME --glb NAME.glb`.',
        '- Then place it: add an object with `"asset": "NAME"` to `scene.json`.',
        '',
        'Not available here: new 3D characters or models from a description (a paid 3D',
        'service), voices, and downloads. Reuse the characters listed below instead.',
        '',
        '## Library this game can use',
    ]
    entries = []
    for source in (shared, own):
        for section in SECTIONS:
            for name, item in sorted(((source or {}).get(section) or {}).items()):
                kind = 'character' if section == 'characters' else section.rstrip('s')
                detail = item.get('role') or item.get('title') or '' if isinstance(item, dict) else ''
                entries.append(f'- `{name}` ({kind}{": " + str(detail)[:60] if detail and detail != name else ""})')
    lines += sorted(set(entries)) or ['- (nothing yet)']
    try:
        scene_doc = (STUDIO_DIR / 'SCENE.md').read_text(encoding='utf-8')
    except OSError:
        scene_doc = ''
    if scene_doc:
        lines += ['', '## Scene format', '', scene_doc.strip()]
    return '\n'.join(lines) + '\n'


def _stale(src, dst):
    try:
        s = src.stat()
    except OSError:
        return False
    try:
        d = dst.stat()
    except OSError:
        return True
    return s.st_size != d.st_size or s.st_mtime > d.st_mtime


def publish(sid, gid, link, root, storage_dir, storage_write):
    """Share this game's library items with guests; returns whether anything changed.

    Reads come straight from the studio's storage folder on this machine (the
    sync runs here); writes go through the storage API like every studio write."""
    pid = link.get('projectId')
    if not pid:
        return False
    scene = _read_json(root / 'scene.json') or {}
    library = _read_json(storage_dir / 'assets.json') or {}
    shared = library_subset(library, used_names(scene))
    changed = False
    base = f'guest-share/{pid}'
    body = json.dumps(shared, ensure_ascii=False, sort_keys=True).encode()
    current = storage_dir / base / 'assets.json'
    if not current.is_file() or current.read_bytes() != body:
        storage_write(sid, f'{base}/assets.json', body, 'application/json')
        changed = True
    for name in set(shared.get('models', {})) | set(shared.get('characters', {})):
        src = storage_dir / 'models' / f'{name}.glb'
        if _stale(src, storage_dir / base / 'models' / f'{name}.glb'):
            storage_write(sid, f'{base}/models/{name}.glb', src.read_bytes(), 'model/gltf-binary')
            changed = True
    own = _read_json(root / '.studio' / 'assets.json') or {}
    guide = guide_text(shared, own, sid)
    path = root / GUIDE
    if not path.exists() or path.read_text(encoding='utf-8') != guide:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(guide, encoding='utf-8')
        changed = True
    return changed


def import_back(sid, root, storage_dir, storage_write):
    """Add guests' creations in the project to the owner's library."""
    own = _read_json(root / '.studio' / 'assets.json') or {}
    if not any((own.get(section) or {}) for section in SECTIONS):
        return []
    library = _read_json(storage_dir / 'assets.json') or {}
    if not any(name not in (library.get(section) or {}) for section in SECTIONS for name in (own.get(section) or {})):
        return []
    added = []
    for section in SECTIONS:
        mine = library.setdefault(section, {})
        for name, item in (own.get(section) or {}).items():
            if name in mine or not isinstance(item, dict):
                continue
            if section in ('models', 'characters'):
                model = root / '.studio' / 'models' / f'{name}.glb'
                if model.is_file() and not (storage_dir / 'models' / f'{name}.glb').exists():
                    storage_write(sid, f'models/{name}.glb', model.read_bytes(), 'model/gltf-binary')
            mine[name] = item
            added.append(name)
    if added:
        storage_write(sid, 'assets.json', json.dumps(library, ensure_ascii=False).encode(), 'application/json')
    return added


def run(sid, gid, link, root, storage_dir, storage_write):
    """Both directions; never raises (sharing must not stop the game syncing)."""
    try:
        added = import_back(sid, root, storage_dir, storage_write)
        changed = publish(sid, gid, link, root, storage_dir, storage_write)
        return {'imported': added, 'shared_changed': changed}
    except Exception as err:  # noqa: BLE001
        print(f'Note: guest sharing for {gid}: {err}', file=sys.stderr)
        return {'error': str(err)}
