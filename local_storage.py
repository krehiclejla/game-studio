"""Game Studio's storage when its tools run in a project guest's workspace.

An invited editor or maintainer's assistant runs Game Studio's tools in a
sealed workspace: a copy of the project's files, no Möbius pass, and no
network beyond package registries. There the tools' storage calls land on
files instead, following the same guest_storage routes the server uses for
the guest's studio (mobius.json): a key with a "version" path is that file in
the project; one that is only "shared" (the owner's art) is not available
here; anything else goes to a private folder outside the project.

The project folder is GAME_STUDIO_PROJECT, or the nearest folder (from the
current one upwards) holding game.json.
"""
import hashlib
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_STORAGE = re.compile(r'^/api/storage/apps/[0-9]+/(.+)$')


def active():
    """Local mode: no Möbius pass in the environment (a guest workspace)."""
    return not (os.environ.get('AGENT_TOKEN') or os.environ.get('APP_TOKEN'))


def project_root():
    explicit = os.environ.get('GAME_STUDIO_PROJECT')
    if explicit:
        return Path(explicit).resolve()
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        if (folder / 'game.json').is_file():
            return folder
    raise SystemExit('Run this from the game project folder (the one with game.json).')


def _routes():
    try:
        manifest = json.loads((HERE / 'mobius.json').read_text(encoding='utf-8'))
        template = next(t for t in manifest.get('project_templates', []) if t.get('guest_storage'))
        return template['guest_storage']
    except (OSError, ValueError, StopIteration, KeyError):
        return {'routes': []}


def resolve(key):
    """Where a storage key lives here: (path or None, writable)."""
    root = project_root()
    spec = _routes()
    values = {}
    for name, var in (spec.get('vars') or {}).items():
        try:
            values[name] = str(json.loads((root / var['file']).read_text(encoding='utf-8'))[var['field']])
        except (OSError, ValueError, KeyError, TypeError):
            pass
    fill = lambda text: re.sub(r'\{([a-z_]+)\}', lambda m: values.get(m.group(1), '\0'), text) if text else None  # noqa: E731
    for route in spec.get('routes') or []:
        match_key, prefix = fill(route.get('key')), fill(route.get('prefix'))
        rest = '' if match_key == key else (key[len(prefix):] if prefix and key.startswith(prefix) else None)
        if rest is None or '\0' in (match_key or prefix or ''):
            continue
        if route.get('version'):
            return _inside(root, route['version'] + rest), True
        return None, False  # shared with guests by the owner: not available in the workspace
    private = Path(os.environ.get('GAME_STUDIO_PRIVATE') or Path.home() / '.game-studio-private')
    return _inside(private, key), True


def _inside(base, rel):
    path = (base / rel).resolve()
    if base.resolve() not in path.parents or '.git' in path.parts:
        raise SystemExit(f'Refusing a storage path outside the project: {rel}')
    return path


def version(data):
    return '"' + hashlib.sha256(data or b'').hexdigest()[:32] + '"' if data is not None else None


class Conflict(Exception):
    code = 412


def call(method, path, body=None, headers=None):
    """(data, etag) like the storage API; data None when absent. Non-storage
    calls (kicking a server job, ...) do nothing here."""
    match = _STORAGE.match(path.split('?', 1)[0])
    if not match:
        return None, None
    target, writable = resolve(match.group(1))
    current = target.read_bytes() if target is not None and target.is_file() else None
    if method == 'GET':
        return current, version(current)
    if not writable or target is None:
        raise SystemExit('That part of the studio is read-only here.')
    want = (headers or {}).get('If-Match')
    if want is not None and want != version(current):
        raise Conflict()
    if (headers or {}).get('If-None-Match') == '*' and current is not None:
        raise Conflict()
    if method == 'DELETE':
        if target.exists():
            target.unlink()
        return None, None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body if isinstance(body, bytes) else (body or b''))
    return None, version(target.read_bytes())
