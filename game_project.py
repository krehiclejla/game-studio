#!/usr/bin/env python3
"""Every Game Studio game is a Möbius Project.

  python3 game_project.py ensure <studioAppId> <gameId>   make sure the game has a project, then sync
  python3 game_project.py sync <studioAppId> [<gameId>]   sync one game, or every game that has a project
  python3 game_project.py path <studioAppId> <gameId>     print the game's project folder
  python3 game_project.py sync-folder <projectFolder>      sync the game whose project folder this is

The project folder is the game's home: game.html (the game), game.json (its
name, description, controls, genre and art kit) and art.json (art made for
this game only), with a Git history of every change. Game Studio keeps a copy
of the same three files in its storage (games/<id>.html, .json, .art.json),
which is what the studio plays; the player's saves stay in the studio.

sync copies whichever side changed since the last sync to the other side and
commits the project, so an edit in the project (by the game's assistant or in
Projects) reaches the studio, and an edit in the studio (restoring an earlier
version, new art) reaches the project. If both sides changed, the project wins.
The link and the last-synced fingerprints live in studio storage at
projects/<gameId>.json.

Creating a project needs the owner's authority (AGENT_TOKEN, present in agent
runs); syncing works with the app's own token too (APP_TOKEN, in app jobs).
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import guest_share
import requests_board

BASE = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
OWNER_TOKEN = os.environ.get('AGENT_TOKEN', '')
TOKEN = OWNER_TOKEN or os.environ.get('APP_TOKEN', '')
DATA = Path(os.environ.get('DATA_DIR', '/data'))
TEMPLATE = 'game-studio:game'

# project file -> (studio storage path, content type)
FILES = {
    'game.html': ('games/{gid}.html', 'text/html'),
    'game.json': ('games/{gid}.json', 'application/json'),
    'art.json': ('games/{gid}.art.json', 'application/json'),
    'scene.json': ('games/{gid}.scene.json', 'application/json'),  # scene games (scene.py); game.html is built from it
}


def call(method, path, body=None, content_type='application/json', token=None):
    req = urllib.request.Request(BASE + path, method=method, data=body, headers={
        'Authorization': 'Bearer ' + (token or TOKEN),
        **({'Content-Type': content_type} if body is not None else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise


def storage_read(sid, path):
    return call('GET', f'/api/storage/apps/{sid}/{path}')


def storage_write(sid, path, data, content_type):
    call('PUT', f'/api/storage/apps/{sid}/{path}', data, content_type)


def storage_json(sid, path):
    raw = storage_read(sid, path)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def fingerprint(data, name=''):
    """What the file says, not how it is spaced: storage re-formats JSON it saves."""
    if data is None:
        return None
    if name.endswith('.json'):
        try:
            data = json.dumps(json.loads(data), sort_keys=True, ensure_ascii=False).encode()
        except ValueError:
            pass
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=30)


def commit(root, message):
    if not (root / '.git').exists():
        git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Game Studio')
    git(root, 'config', 'user.email', 'game-studio@mobius.local')
    git(root, 'add', '-A')
    if git(root, 'diff', '--cached', '--quiet').returncode:
        git(root, 'commit', '-q', '-m', message)
        return True
    return False


def link_of(sid, gid):
    link = storage_json(sid, f'projects/{gid}.json')
    return link if isinstance(link, dict) and link.get('projectId') else None


def root_of(link):
    root = (DATA / link['root']).resolve()
    return root if root.is_dir() and str(root).startswith(str(DATA / 'projects')) else None


def create(sid, gid, game):
    if not OWNER_TOKEN:
        sys.exit('Creating a project needs an agent run (AGENT_TOKEN).')
    name = (game.get('name') or 'Untitled game').strip() or 'Untitled game'
    # The same request id always answers with the same project, so a retry after a
    # failure halfway never leaves a second, orphaned project behind. If the owner
    # deleted that project, the next attempt starts a fresh one.
    body = {'name': name, 'template_id': TEMPLATE, 'recovery_request_id': f'game-studio:{sid}:{gid}'}
    try:
        raw = call('POST', '/api/projects', json.dumps(body).encode(), token=OWNER_TOKEN)
    except urllib.error.HTTPError as err:
        if err.code != 409:
            raise
        body['recovery_request_id'] += ':' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        raw = call('POST', '/api/projects', json.dumps(body).encode(), token=OWNER_TOKEN)
    project = json.loads(raw)
    # Möbius keeps every project's folder at projects/<id> under the data folder.
    link = {'projectId': project['id'], 'root': f"projects/{project['id']}", 'name': name, 'synced': {},
            'createdAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    storage_write(sid, f'projects/{gid}.json', json.dumps(link).encode(), 'application/json')
    return link


def board_store(sid, gid):
    """Studio storage for one game's request board: requests/<gid>.json and requests/<gid>/<key>.json."""
    def store(action, name, data=None):
        path = f'requests/{gid}.json' if name == 'board' else f'requests/{gid}/{name[len("decisions/"):]}'
        if action == 'get':
            return storage_json(sid, path)
        if action == 'put':
            return storage_write(sid, path, json.dumps(data, ensure_ascii=False).encode(), 'application/json')
        if action == 'delete':
            return call('DELETE', f'/api/storage/apps/{sid}/{path}')
        raw = call('GET', f'/api/storage/apps-list/{sid}/requests/{gid}/')
        try:
            entries = (json.loads(raw) if raw else {}).get('entries') or []
        except (ValueError, AttributeError):
            entries = []
        return [e['name'] for e in entries if e.get('type') == 'file' and e.get('name', '').endswith('.json')]
    return store


def board_notify(sid, gid):
    def notify(title, body):
        try:
            call('POST', '/api/notifications/send', json.dumps({
                'title': title, 'body': body, 'target': f'/shell/?app={sid}', 'tag': f'requests:{gid}',
            }).encode())
        except urllib.error.HTTPError as err:
            print(f'Note: could not send the wish notification: HTTP {err.code}', file=sys.stderr)
    return notify


def sync(sid, gid, link=None, first_message=None):
    """Two-way sync of one game; returns a short report."""
    link = link or link_of(sid, gid)
    if not link:
        return {'game': gid, 'skipped': 'no project'}
    root = root_of(link)
    if not root:
        return {'game': gid, 'skipped': 'project folder is gone'}
    game_raw = storage_read(sid, f'games/{gid}.json')
    if game_raw is None and not (root / 'game.json').exists():
        return {'game': gid, 'skipped': 'game deleted in the studio'}
    synced = dict(link.get('synced') or {})
    to_studio, to_project = [], []
    for name, (spath, ctype) in FILES.items():
        spath = spath.format(gid=gid)
        pfile = root / name
        pdata = pfile.read_bytes() if pfile.exists() else None
        sdata = game_raw if name == 'game.json' else storage_read(sid, spath)
        p, s, last = fingerprint(pdata, name), fingerprint(sdata, name), synced.get(name)
        if p == s:
            synced[name] = p
            continue
        project_changed = p != last and p is not None
        if project_changed or s is None:
            if name == 'game.json':
                # The studio finds games by id: keep it, whatever the file says.
                try:
                    meta = json.loads(pdata)
                except ValueError:
                    continue  # half-written or broken JSON: leave both sides alone until it's fixed
                meta['id'], meta['studioAppId'] = gid, int(sid)
                fixed = json.dumps(meta, ensure_ascii=False, indent=2).encode()
                if fixed != pdata:
                    pfile.write_bytes(fixed)
                pdata = fixed
            storage_write(sid, spath, pdata, ctype)
            synced[name] = fingerprint(pdata, name)
            to_studio.append(name)
        elif sdata is not None:
            if name == 'game.json':
                meta = json.loads(sdata)
                meta['id'], meta['studioAppId'] = gid, int(sid)
                sdata = json.dumps(meta, ensure_ascii=False, indent=2).encode()
                # Both sides hold the same file from now on (the studio's copy gains studioAppId).
                storage_write(sid, spath, sdata, ctype)
            pfile.write_bytes(sdata)
            synced[name] = fingerprint(sdata, name)
            to_project.append(name)
    try:
        if requests_board.update(root, board_store(sid, gid), (link.get('name') or 'your game'), board_notify(sid, gid)):
            to_studio.append(requests_board.FILE)
    except Exception as err:  # the board must never stop the game itself from syncing
        print(f'Note: request board for {gid}: {err}', file=sys.stderr)
    # What invited editors and maintainers may use, and what they made (guest_share.py).
    shared = guest_share.run(sid, gid, link, root, DATA / 'apps' / str(sid), storage_write)
    message = first_message or ('Studio: ' + ', '.join(to_project) if to_project else 'Update ' + ', '.join(to_studio) if to_studio else 'Update game')
    committed = commit(root, message)
    if (to_studio or to_project) and OWNER_TOKEN:
        rebuild_play(link)
    # Keep the project's name in step with the game's name (owner authority only).
    name = None
    try:
        name = json.loads((root / 'game.json').read_bytes()).get('name')
    except (OSError, ValueError, AttributeError):
        pass
    renamed = False
    if name and name != link.get('name') and OWNER_TOKEN:
        call('PATCH', f"/api/projects/{link['projectId']}", json.dumps({'name': name}).encode(), token=OWNER_TOKEN)
        link['name'] = name
        renamed = True
    if synced != link.get('synced') or renamed:
        link['synced'] = synced
        storage_write(sid, f'projects/{gid}.json', json.dumps(link).encode(), 'application/json')
    return {'game': gid, 'project': link['projectId'], 'folder': str(root), 'to_studio': to_studio,
            'to_project': to_project, 'committed': committed, 'guests': shared}


def rebuild_play(link):
    """Refresh the project's Play build after the game changed, so collaborators
    never play an old version. Needs owner authority, so it runs on agent syncs
    (each studio AI change); a collaborator can also press Build."""
    try:
        call('POST', f"/api/projects/{link['projectId']}/artifacts/play/build", b'', token=OWNER_TOKEN)
    except urllib.error.HTTPError as err:
        if err.code != 404:  # 404: an older project without a Play build
            print(f'Note: could not rebuild Play: HTTP {err.code}', file=sys.stderr)
    except Exception as err:
        print(f'Note: could not rebuild Play: {err}', file=sys.stderr)


def ensure_play(link):
    """Give the project its "Play" build, so anyone invited to edit can play the game.

    The Game project type declares it (play_build.py), but Möbius only registers a
    build when its source file already exists, and game.html arrives with the first
    sync. Returns whether the project has the build."""
    if not OWNER_TOKEN:
        return None
    pid = link['projectId']
    try:
        current = json.loads(call('GET', f'/api/projects/{pid}/artifacts', token=OWNER_TOKEN) or b'{}')
        entries = current.get('artifacts', current) if isinstance(current, dict) else current
        if any(isinstance(a, dict) and a.get('id') == 'play' for a in entries or []):
            return True
        body = {'id': 'play', 'name': 'Play', 'builder': 'game', 'source': 'game.html'}
        call('POST', f'/api/projects/{pid}/artifacts', json.dumps(body).encode(), token=OWNER_TOKEN)
        return True
    except urllib.error.HTTPError as err:
        # 422: a project made before Game projects had a Play build.
        print(f'Note: could not add the Play build to project {pid}: HTTP {err.code}', file=sys.stderr)
        return False


def seed_engine(sid):
    """Keep the studio's local engine library current (a no-op when it is). Games still play without it."""
    try:
        import seed_engine
        return seed_engine.seed(sid)
    except Exception as err:  # never block the game's assistant on this
        return f'skipped: {err}'


def link_studio_chat(sid, gid, link):
    """File the game's own studio chat under its project, so the owner finds it
    with the project's chats (owner-only; people the project is shared with never
    see it). Only the chat the studio recorded for this game is linked: another
    chat that happens to run ensure stays where it is. Returns whether it is linked."""
    chat_id = os.environ.get('CHAT_ID', '')
    if not (OWNER_TOKEN and chat_id and link.get('projectId')):
        return None
    studio_chat = storage_json(sid, f'chats/{gid}.json') or {}
    if studio_chat.get('id') != chat_id:
        return None
    try:
        return call('PUT', f"/api/projects/{link['projectId']}/chats/{chat_id}/link", b'', token=OWNER_TOKEN) is not None
    except urllib.error.HTTPError as err:
        print(f'Note: could not file this chat under the project: HTTP {err.code}', file=sys.stderr)
        return False


def ensure(sid, gid):
    seed_engine(sid)
    game = storage_json(sid, f'games/{gid}.json')
    if not isinstance(game, dict):
        sys.exit(f'No game "{gid}" in Game Studio.')
    link = link_of(sid, gid)
    if link and root_of(link):
        return {**sync(sid, gid, link), 'play': ensure_play(link), 'chat': link_studio_chat(sid, gid, link)}
    link = create(sid, gid, game)
    report = sync(sid, gid, link, first_message=f"Start {link['name']}")
    return {**report, 'created': True, 'play': ensure_play(link), 'chat': link_studio_chat(sid, gid, link)}


def linked_games(sid):
    raw = call('GET', f'/api/storage/apps-list/{sid}/projects/')
    try:
        entries = (json.loads(raw) if raw else {}).get('entries') or []
    except (ValueError, AttributeError):
        entries = []
    return [e['name'][:-5] for e in entries if e.get('type') == 'file' and e.get('name', '').endswith('.json')]


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ('ensure', 'sync', 'path', 'sync-folder'):
        sys.exit(__doc__)
    if sys.argv[1] == 'sync-folder':
        # From inside a game's project folder: its game.json names the game and the studio.
        meta = json.loads((Path(sys.argv[2]) / 'game.json').read_text())
        print(json.dumps({'ok': True, **sync(str(meta['studioAppId']), meta['id'])}))
        return
    action, sid = sys.argv[1], sys.argv[2]
    gid = sys.argv[3] if len(sys.argv) > 3 else None
    if action == 'ensure':
        print(json.dumps({'ok': True, **ensure(sid, gid)}))
    elif action == 'path':
        link = link_of(sid, gid)
        root = root_of(link) if link else None
        if not root:
            sys.exit(f'Game "{gid}" has no project yet: run game_project.py ensure {sid} {gid}')
        print(root)
    else:
        games = [gid] if gid else linked_games(sid)
        print(json.dumps({'ok': True, 'games': [sync(sid, g) for g in games]}))


if __name__ == '__main__':
    main()
