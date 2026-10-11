#!/usr/bin/env python3
"""Bring playtest notes from each game's own app into Game Studio.

  python3 playtest_notes.py <studioAppId>

Players leave notes with the Note button in a game's app (player/index.jsx),
including visitors on a public link. They land in that app's private inbox,
public/notes/<id>.json, which visitors can add to but never read. Every minute
(job.sh) this copies the newest notes of every published game to studio
storage notes/<gameId>.json, where the studio shows them beside the wishes,
and tells the owner about notes that arrived since the last run.
"""
import json
import sys
from pathlib import Path

from game_project import DATA, board_notify, storage_json, storage_write

KEEP = 50


def inbox(app_id):
    folder = DATA / 'apps' / str(int(app_id)) / 'public' / 'notes'
    notes = []
    for path in sorted(folder.glob('*.json'), reverse=True)[:KEEP] if folder.is_dir() else []:
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        text = str(raw.get('text') or '').strip()[:1000] if isinstance(raw, dict) else ''
        if not text:
            continue
        name = str(raw.get('name') or '').strip()[:40] or None
        played = raw.get('playedSeconds')
        notes.append({'id': path.stem, 'text': text, 'name': name, 'at': str(raw.get('at') or '')[:40],
                      'playedSeconds': int(played) if isinstance(played, (int, float)) and played >= 0 else None})
    return notes


def collect(sid):
    studio = DATA / 'apps' / str(int(sid))
    for record_path in sorted((studio / 'published').glob('*.json')):
        gid = record_path.stem
        try:
            record = json.loads(record_path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or not record.get('appId') or record.get('target') == 'worlds':
            continue
        notes = inbox(record['appId'])
        current = storage_json(sid, f'notes/{gid}.json') or {}
        if current.get('items') == notes:
            continue
        storage_write(sid, f'notes/{gid}.json', json.dumps({'items': notes}, ensure_ascii=False).encode(), 'application/json')
        known = {n.get('id') for n in current.get('items') or []}
        fresh = [n for n in notes if n['id'] not in known]
        # The first collection for a game is not news; later notes are.
        if fresh and 'items' in current:
            first = fresh[0]
            more = f' (+{len(fresh) - 1} more)' if len(fresh) > 1 else ''
            name = record.get('name') or 'your game'
            board_notify(sid, gid)(f'Playtest note for {name}', f"{first['name'] or 'A player'}: {first['text']}{more}"[:300])


if __name__ == '__main__':
    collect(sys.argv[1] if len(sys.argv) > 1 else '12')
