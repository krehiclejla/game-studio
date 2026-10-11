#!/usr/bin/env python3
"""Take single files out of a free asset pack without downloading the whole pack.

A zip keeps its table of contents at the end of the file, so one small ranged
request lists every file in a pack and one more fetches just the file wanted.
Kenney packs (kenney.nl, CC0) are named by slug; any other zip by its URL.
Servers that ignore ranges get one whole download, kept in the cache.

  python3 packzip.py files SLUG_OR_URL [GLOB] [--max N]   list a pack's files (no download)
  python3 packzip.py get SLUG_OR_URL GLOB [--max N]        fetch matching files; prints their local paths

GLOB matches paths inside the pack ("**/*.ogg", "**/footstep_grass_*",
"Audio/{click,switch}_*.ogg"). Files are cached in ~/.cache/game-studio/packs
(outside app storage), so asking again costs nothing.
"""
import argparse
import fnmatch
import json
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

CACHE = Path.home() / '.cache' / 'game-studio' / 'packs'
UA = {'User-Agent': 'MobiusGameStudio/1.0 (+https://github.com/mobius-os)'}
TAIL = 64 * 1024
MAX_FILE = 64 * 1024 * 1024
INDEX_DAYS = 30


def _request(url, headers=None, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=timeout)


def _range(url, spec):
    """(status, total size or None, bytes) for a Range request such as 'bytes=-65536'."""
    with _request(url, {'Range': spec}) as res:
        body = res.read(MAX_FILE + 1)
        total = (res.headers.get('Content-Range') or '').rsplit('/', 1)[-1]
        return res.status, int(total) if total.isdigit() else None, body


def expand_braces(pattern):
    """Expand shell-style {a,b,c} alternatives (fnmatch has none)."""
    match = re.search(r'\{([^{}]*)\}', pattern)
    if not match:
        return [pattern]
    head, tail = pattern[:match.start()], pattern[match.end():]
    return [p for option in match.group(1).split(',') for p in expand_braces(head + option + tail)]


def matches(name, pattern):
    pats = expand_braces(pattern)
    # "**/x" also matches "x" at the top of the pack.
    pats += [p[3:] for p in pats if p.startswith('**/')]
    return any(fnmatch.fnmatch(name, p) for p in pats)


def kenney_url(slug):
    """The download link on a Kenney pack page."""
    page = _request(f'https://kenney.nl/assets/{slug}', timeout=30).read().decode('utf8', 'replace')
    found = re.search(r'https://kenney\.nl/media/pages/assets/[^"\'\s]+\.zip', page)
    if not found:
        raise SystemExit(f'Could not find the download for Kenney pack "{slug}".')
    return found.group(0)


class Pack:
    """One remote zip: its file list and any single file from it, cached on this machine."""

    def __init__(self, ref):
        self.ref = ref
        self.is_url = ref.startswith(('http://', 'https://'))
        key = re.sub(r'[^a-z0-9._-]+', '-', ref.lower().split('://', 1)[-1]).strip('-')[:120] if self.is_url else ref
        self.root = CACHE / key
        self._index = None

    # --- table of contents ---------------------------------------------------
    def _load_index(self):
        path = self.root / '.index.json'
        try:
            data = json.loads(path.read_text())
            if time.time() - data['at'] < INDEX_DAYS * 86400:
                return data
        except (OSError, ValueError, KeyError):
            pass
        url = self.ref if self.is_url else kenney_url(self.ref)
        data = {'at': time.time(), 'url': url, 'ranged': True, 'members': self._read_directory(url)}
        if data['members'] is None:
            data.update(ranged=False, members=self._whole(url))
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return data

    def _read_directory(self, url):
        status, total, tail = _range(url, f'bytes=-{TAIL}')
        if status != 206 or not total:
            return None
        end = tail.rfind(b'PK\x05\x06')
        if end < 0:
            raise SystemExit(f'{url} is not a zip file.')
        size, offset = struct.unpack('<II', tail[end + 12:end + 20])
        if offset == 0xFFFFFFFF:
            return None  # zip64: rare for game packs; read it whole
        start = offset - (total - len(tail))
        directory = tail[start:start + size] if start >= 0 else _range(url, f'bytes={offset}-{offset + size - 1}')[2]
        members, p = {}, 0
        while p + 46 <= len(directory) and directory[p:p + 4] == b'PK\x01\x02':
            method, = struct.unpack('<H', directory[p + 10:p + 12])
            crc, packed, unpacked = struct.unpack('<III', directory[p + 16:p + 28])
            name_len, extra_len, comment_len = struct.unpack('<HHH', directory[p + 28:p + 34])
            local, = struct.unpack('<I', directory[p + 42:p + 46])
            name = directory[p + 46:p + 46 + name_len].decode('utf-8', 'replace')
            if not name.endswith('/') and '__MACOSX' not in name:
                members[name] = [method, crc, packed, unpacked, local]
            p += 46 + name_len + extra_len + comment_len
        return members

    def _whole(self, url):
        """The server ignores ranges: unpack the zip once into the cache."""
        import io
        import zipfile
        with _request(url, timeout=600) as res:
            data = res.read()
        members = {}
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir() or '__MACOSX' in info.filename:
                    continue
                target = self._safe(info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
                members[info.filename] = [0, info.CRC, info.compress_size, info.file_size, -1]
        return members

    @property
    def index(self):
        if self._index is None:
            self._index = self._load_index()
        return self._index

    def names(self, pattern=None):
        names = sorted(self.index['members'])
        return [n for n in names if matches(n, pattern)] if pattern else names

    def size(self, name):
        return self.index['members'][name][3]

    # --- single files --------------------------------------------------------
    def _safe(self, name):
        target = (self.root / name).resolve()
        if self.root.resolve() not in target.parents:
            raise SystemExit(f'Refusing an unsafe path in the pack: {name}')
        return target

    def file(self, name):
        """A local path to one file of the pack, fetched on first use."""
        target = self._safe(name)
        if target.is_file():
            return target
        if name not in self.index['members']:
            raise SystemExit(f'{name} is not in pack {self.ref}.')
        method, crc, packed, unpacked, local = self.index['members'][name]
        if local < 0:
            raise SystemExit(f'{name} is missing from the cached copy of {self.ref}; delete {self.root} and retry.')
        if unpacked > MAX_FILE:
            raise SystemExit(f'{name} is too large ({unpacked / 1e6:.0f} MB).')
        head = 30 + len(name.encode()) + 1024  # the local header's extra field can differ in length
        status, _, chunk = _range(self.index['url'], f'bytes={local}-{local + head + packed}')
        if status != 206 or chunk[:4] != b'PK\x03\x04':
            raise SystemExit(f'Could not read {name} from {self.ref} (the server stopped allowing partial downloads).')
        name_len, extra_len = struct.unpack('<HH', chunk[26:30])
        data = chunk[30 + name_len + extra_len:30 + name_len + extra_len + packed]
        if method == 8:
            data = zlib.decompressobj(-15).decompress(data)
        elif method != 0:
            raise SystemExit(f'{name} uses a compression this tool cannot read.')
        if zlib.crc32(data) & 0xFFFFFFFF != crc:
            raise SystemExit(f'{name} failed its checksum; try again.')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self._companions(name, data)
        return target

    def _companions(self, name, data):
        """A glTF model names its textures (and .gltf its buffers) as sibling files: fetch those too."""
        lower = name.lower()
        if not lower.endswith(('.glb', '.gltf')):
            return
        try:
            if lower.endswith('.glb'):
                length, = struct.unpack('<I', data[12:16])
                doc = json.loads(data[20:20 + length])
            else:
                doc = json.loads(data)
        except (ValueError, struct.error):
            return
        import posixpath
        import urllib.parse
        folder = posixpath.dirname(name)
        for item in (doc.get('images') or []) + (doc.get('buffers') or []):
            uri = item.get('uri') or ''
            if not uri or uri.startswith('data:') or '://' in uri:
                continue
            ref = posixpath.normpath(posixpath.join(folder, urllib.parse.unquote(uri)))
            if ref in self.index['members']:
                self.file(ref)

    def files(self, pattern, limit=None):
        """Local paths of every pack file matching the glob, fetching only those."""
        names = self.names(pattern)
        if not names:
            print(f'  warning: no files in {self.ref} match {pattern}', file=sys.stderr)
        return [self.file(n) for n in names[:limit]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['files', 'get'])
    parser.add_argument('pack')
    parser.add_argument('glob', nargs='?')
    parser.add_argument('--max', type=int, default=200)
    a = parser.parse_args()
    pack = Pack(a.pack)
    if a.action == 'files':
        names = pack.names(a.glob)
        print(json.dumps({'pack': a.pack, 'count': len(names),
                          'files': [{'name': n, 'kb': round(pack.size(n) / 1024, 1)} for n in names[:a.max]],
                          **({'more': len(names) - a.max} if len(names) > a.max else {})}, indent=1))
    else:
        if not a.glob:
            sys.exit('Give a GLOB of the files to fetch, e.g. "**/*.ogg".')
        print(json.dumps({'pack': a.pack, 'files': [str(p) for p in pack.files(a.glob, a.max)]}, indent=1))


if __name__ == '__main__':
    main()
