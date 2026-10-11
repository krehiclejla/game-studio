#!/usr/bin/env python3
"""Find and fetch free CC0 art from kenney.nl for Game Studio.

  python3 kenney.py search WORDS... [--kind 2d|3d]   packs whose names match (e.g. "knight", "zombie", "robot")
  python3 kenney.py characters [--kind 2d|3d]        packs known to contain characters
  python3 kenney.py fetch SLUG                       summarise a pack's files (fetches only its preview pictures)
  python3 kenney.py files SLUG GLOB [--max N]        fetch the matching files, e.g. "**/*.glb" or "**/Characters/*.png"

Everything from Kenney is CC0 (public domain): free to use, change and ship.
Only the files asked for are downloaded (packzip.py reads single files out of
the pack's zip), cached in ~/.cache/game-studio/packs; the pack index in
~/.cache/game-studio/kenney-index.json (refreshed weekly).
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from packzip import Pack  # noqa: E402

INDEX = Path.home() / '.cache' / 'game-studio' / 'kenney-index.json'
UA = {'User-Agent': 'Mozilla/5.0 (MobiusGameStudio)'}
CATEGORIES = {'2d': '2D', '3d': '3D'}

# Packs with characters, checked by hand; search finds the rest.
CHARACTER_PACKS = {
    '2d': ['toon-characters', 'platformer-characters', 'modular-characters', 'shape-characters', 'animal-pack-remastered',
           'monster-builder-pack', 'robot-pack', 'platformer-art-extended-enemies', 'pixel-platformer', 'tiny-dungeon',
           'roguelike-characters', 'top-down-shooter', 'space-shooter-remastered', 'alien-ufo-pack', 'racing-pack', 'fish-pack'],
    '3d': ['animated-characters-protagonists', 'animated-characters-survivors', 'animated-characters-retro', 'mini-characters',
           'blocky-characters', 'cube-pets', 'car-kit', 'toy-car-kit', 'space-kit'],
}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf8', 'replace')


def build_index():
    packs = {}
    for kind, cat in CATEGORIES.items():
        for page in range(1, 40):
            url = f'https://kenney.nl/assets/category:{cat}' + (f'/page:{page}' if page > 1 else '')
            try:
                html = get(url)
            except urllib.error.HTTPError:
                break  # past the last page
            time.sleep(0.3)
            slugs = {s for s in re.findall(r'kenney\.nl/assets/([a-z0-9-]+)', html) if s not in ('category', 'tag', 'page')}
            new = slugs - {s for s, p in packs.items() if kind in p}
            if not new:
                break
            for slug in slugs:
                packs.setdefault(slug, [])
                if kind not in packs[slug]:
                    packs[slug].append(kind)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({'at': time.time(), 'packs': packs}))
    return packs


def index():
    try:
        data = json.loads(INDEX.read_text())
        if time.time() - data['at'] < 7 * 86400 and data['packs']:
            return data['packs']
    except (OSError, ValueError, KeyError):
        pass
    return build_index()


def summarise(pack):
    names = pack.names()
    by_ext = {}
    for n in names:
        ext = Path(n).suffix.lower() or '(none)'
        by_ext[ext] = by_ext.get(ext, 0) + 1
    folders = sorted({str(Path(n).parent) for n in names})
    previews = [str(pack.file(n)) for n in names if re.search(r'preview|sample', Path(n).name, re.I) and n.lower().endswith('.png')][:6]
    return {'dir': str(pack.root), 'files': len(names), 'by_type': dict(sorted(by_ext.items(), key=lambda kv: -kv[1])),
            'folders': folders[:60], 'previews': previews,
            'next': 'Read a preview PNG to see the pack, then fetch files with: kenney.py files SLUG "GLOB"'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['search', 'characters', 'fetch', 'files'])
    parser.add_argument('args', nargs='*')
    parser.add_argument('--kind', choices=['2d', '3d'])
    parser.add_argument('--max', type=int, default=80)
    a = parser.parse_args()

    if a.action == 'characters':
        kinds = [a.kind] if a.kind else ['2d', '3d']
        print(json.dumps({k: CHARACTER_PACKS[k] for k in kinds}, indent=1))
    elif a.action == 'search':
        words = [w.lower() for w in a.args if w.strip()]
        if not words:
            sys.exit('Give words to search for.')
        packs = index()
        hits = [(slug, kinds) for slug, kinds in packs.items()
                if (not a.kind or a.kind in kinds) and any(w.rstrip('s') in slug for w in words)]
        print(json.dumps({'matches': [{'slug': s, 'kind': k, 'page': f'https://kenney.nl/assets/{s}'} for s, k in sorted(hits)],
                          'tip': 'No match? Try broader words (animal, monster, vehicle), or kenney.py characters.'}, indent=1))
    elif a.action == 'fetch':
        if not a.args:
            sys.exit('Give a pack slug, e.g. animated-characters-1.')
        print(json.dumps(summarise(Pack(a.args[0])), indent=1))
    else:
        if len(a.args) < 2:
            sys.exit('Usage: kenney.py files SLUG GLOB')
        pack = Pack(a.args[0])
        names = pack.names(a.args[1])
        found = [str(pack.file(n)) for n in names[:a.max]]
        print(json.dumps({'count': len(names), 'files': found}, indent=1))


if __name__ == '__main__':
    main()
