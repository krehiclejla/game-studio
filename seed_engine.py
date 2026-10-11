#!/usr/bin/env python3
"""Put the engine library (build_engine.mjs) into a Game Studio's storage.

  python3 seed_engine.py <studioAppId> [--force]

The studio reads engine/index.json and engine/<module>.mjs from its storage to
start games without fetching three.js, Phaser and friends from the web. This
builds them there when they are missing or older than build_engine.mjs; a
current library makes it a no-op. Without it games simply load from esm.sh.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('DATA_DIR', '/data'))


URL = re.compile(r'https://esm\.sh/[^\'"`)\s<>\\]+')


def game_urls(sid):
    """Every esm.sh address the studio's games import, so each one is in the library."""
    found = set()
    for page in sorted((DATA / 'apps' / str(sid) / 'games').glob('*.html')):
        try:
            found.update(URL.findall(page.read_text(errors='ignore')))
        except OSError:
            pass
    return sorted(found)


def stamp(urls):
    """Changes whenever the build script or the set of addresses to include changes."""
    digest = hashlib.sha256((HERE / 'build_engine.mjs').read_bytes())
    digest.update('\n'.join(urls).encode())
    return digest.hexdigest()[:16]


def seed(sid, force=False):
    out = DATA / 'apps' / str(sid) / 'engine'
    marker = out / 'stamp.txt'
    urls = game_urls(sid)
    if not force and marker.exists() and marker.read_text().strip() == stamp(urls) and (out / 'index.json').exists():
        return 'current'
    sys.path.insert(0, str(HERE))
    import play_build
    play_build.ensure_esbuild()
    tmp = out.with_name('engine.new')
    extra = out.with_name('engine-urls.txt')
    extra.write_text('\n'.join(urls) + '\n')
    try:
        subprocess.run(['node', str(HERE / 'build_engine.mjs'), str(tmp)], check=True,
                       env={**os.environ, 'GS_TOOLS_DIR': str(play_build.TOOLS), 'GS_EXTRA_URLS': str(extra)}, stdout=subprocess.DEVNULL)
    finally:
        extra.unlink(missing_ok=True)
    (tmp / 'stamp.txt').write_text(stamp(urls) + '\n')
    if out.exists():
        subprocess.run(['rm', '-rf', str(out)], check=True)
    tmp.rename(out)
    return 'built'


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(seed(sys.argv[1], '--force' in sys.argv))
