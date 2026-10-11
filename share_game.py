#!/usr/bin/env python3
"""Give one game a public play link: anyone with it plays a fresh game.

  python3 share_game.py <studioAppId> <gameId>

Publishes the game's own app (so it has the current game and the player that
starts visitors fresh), turns on its public link, and records the link in the
studio's storage at published/<gameId>.json ("playUrl"), where the studio shows
it. Players on the link never see the owner's saves, chats or files, and their
own progress lasts while their page is open. Later publishes keep the public
copy up to date (publish_game.py refreshes it while "playUrl" is set).

  python3 share_game.py <studioAppId> <gameId> --stop    turn the link off

Needs a Möbius agent run (API_BASE_URL, AGENT_TOKEN; publishing applies the app).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from build_art import api, storage_get, storage_put_json

HERE = Path(__file__).resolve().parent


def public_origin():
    origin = os.environ.get('FRONTEND_ORIGIN', '').rstrip('/')
    if not origin and os.environ.get('RAILWAY_PUBLIC_DOMAIN'):
        origin = 'https://' + os.environ['RAILWAY_PUBLIC_DOMAIN']
    return origin


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sid, gid = sys.argv[1], sys.argv[2]
    stop = '--stop' in sys.argv[3:]
    record = storage_get(sid, f'published/{gid}.json') or {}
    if stop:
        if record.get('appId'):
            api('DELETE', f"/api/apps/{record['appId']}/hosted-publication")
        record.pop('playUrl', None)
        storage_put_json(sid, f'published/{gid}.json', record)
        print(json.dumps({'ok': True, 'stopped': True}))
        return
    if record.get('target') == 'worlds':
        sys.exit('This game is published inside Möbius Worlds, not as its own app; share Worlds instead.')
    proc = subprocess.run([sys.executable, str(HERE / 'publish_game.py'), sid, gid, '--shared'],
                          capture_output=True, text=True, timeout=600, cwd=HERE)
    if proc.returncode:
        sys.exit('Publishing failed: ' + (proc.stdout + proc.stderr).strip()[-1500:])
    record = storage_get(sid, f'published/{gid}.json') or {}
    if not record.get('appId'):
        sys.exit('The game has no app yet: publishing did not record one.')
    app = api('PUT', f"/api/apps/{record['appId']}/hosted-publication")
    path = ((app or {}).get('hosted_publication') or {}).get('path') or f"/{record.get('slug', '')}"
    origin = public_origin()
    if not origin:
        sys.exit('Could not tell this Möbius address; the public path is ' + path)
    record['playUrl'] = origin + path
    storage_put_json(sid, f'published/{gid}.json', record)
    print(json.dumps({'ok': True, 'playUrl': record['playUrl'], 'appId': record['appId']}))


if __name__ == '__main__':
    main()
