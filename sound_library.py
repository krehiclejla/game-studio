#!/usr/bin/env python3
"""Real sound effects and music for Game Studio, all CC0 (public domain: free to use,
change and ship, no credit required).

Sources
  kenney  Kenney's audio packs (kenney.nl): impacts and footsteps, UI clicks, RPG,
          sci-fi, casino, digital, voice-overs, music jingles. Read one file at a time.
  oga     OpenGameArt (opengameart.org) entries offered as CC0: music tracks,
          ambiences and sound effects. The site asks for 10 s between requests,
          so each OpenGameArt step may wait a few seconds.

  python3 sound_library.py search WORDS... [--music | --sfx] [--max N]
      Find sounds. Prints ids such as "kenney:impact-sounds/Audio/footstep_grass_000.ogg"
      or "oga:another-august", with titles and variants. Use one or two plain words
      ("footstep grass", "sword", "calm forest", "boss battle"); retry with fewer
      words when nothing comes back.
  python3 sound_library.py add APP_ID ID NAME (--game GAME_ID | --shared) [--music] [--file NAME] [--seconds S]
      Download, convert to MP3 (plays on every phone), trim and level it, and save it as NAME:
      --game puts it in that game's own art, --shared in the Assets tab for every game.
      --music keeps it whole as a looping track (studio.music); otherwise it is a
      one-shot effect (studio.sound), mono, silence trimmed, at most 12 s.
      --file picks one file of an OpenGameArt entry that has several (or a zip);
      --seconds shortens a long track (fades out at the end).
  python3 sound_library.py list APP_ID [--game GAME_ID]
  python3 sound_library.py remove APP_ID NAME (--game GAME_ID | --shared)

In a game: studio.sound('NAME') (optional { volume, rate }), studio.music('NAME')
(optional { volume: 0.5, loop: true, fade: 0.8 }), studio.stopMusic().
Keep music under about 3 MB (a 3-minute track); the tool says when a track is too big.
"""
import argparse
import base64
import html
import io
import json
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gs_deps  # noqa: E402,F401
from build_art import api, storage_get, storage_put_json  # noqa: E402
from packzip import Pack  # noqa: E402

CACHE = Path.home() / '.cache' / 'game-studio'
UA = {'User-Agent': 'MobiusGameStudio/1.0 (+https://github.com/mobius-os)'}
OGA = 'https://opengameart.org'
OGA_CC0 = '4'
OGA_TYPES = {'music': '12', 'sfx': '13'}
OGA_GAP = 10.5                         # robots.txt: Crawl-delay 10
KENNEY_AUDIO = ['casino-audio', 'digital-audio', 'impact-sounds', 'interface-sounds', 'music-jingles',
                'rpg-audio', 'sci-fi-sounds', 'ui-audio', 'voiceover-pack', 'voiceover-pack-fighter']
AUDIO_EXT = ('.ogg', '.mp3', '.wav', '.flac')
SFX_SECONDS = 12
MUSIC_MAX_BYTES = 3_000_000
MP3_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)
NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_]{0,39}$')


def out(value):
    print(json.dumps(value, indent=1, ensure_ascii=False))


def fail(message, **extra):
    out({'ok': False, 'error': message, **extra})
    sys.exit(2)


# ---------- fetching ----------

def oga_get(url, binary=False, limit=80_000_000):
    """One polite request to OpenGameArt (at most one every 10 s, across runs)."""
    stamp = CACHE / 'oga-last-request'
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        wait = float(stamp.read_text()) + OGA_GAP - time.time()
        if wait > 0:
            time.sleep(min(wait, OGA_GAP))
    except (OSError, ValueError):
        pass
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as res:
            data = res.read(limit + 1)
    finally:
        stamp.write_text(str(time.time()))
    if len(data) > limit:
        fail(f'That file is larger than {limit // 1_000_000} MB.')
    return data if binary else data.decode('utf8', 'replace')


def text(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()


# ---------- Kenney ----------

def kenney_packs():
    """Kenney's audio packs, from its Audio category (checked monthly)."""
    path = CACHE / 'kenney-audio.json'
    try:
        data = json.loads(path.read_text())
        if time.time() - data['at'] < 30 * 86400 and data['packs']:
            return data['packs']
    except (OSError, ValueError, KeyError):
        pass
    try:
        page = urllib.request.urlopen(urllib.request.Request('https://kenney.nl/assets/category:Audio', headers=UA),
                                      timeout=30).read().decode('utf8', 'replace')
        packs = sorted({s for s in re.findall(r'kenney\.nl/assets/([a-z0-9-]+)', page)
                        if s not in ('category', 'tag', 'page', 'series')}) or KENNEY_AUDIO
    except OSError:
        packs = KENNEY_AUDIO
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'at': time.time(), 'packs': packs}))
    return packs


def words_of(value):
    return [w.rstrip('s') for w in re.split(r'[^a-z0-9]+', value.lower()) if w]


def kenney_search(words, kind, limit):
    groups = {}
    for slug in kenney_packs():
        if kind == 'music' and slug != 'music-jingles':
            continue
        if kind == 'sfx' and slug == 'music-jingles':
            continue
        try:
            names = [n for n in Pack(slug).names() if n.lower().endswith(AUDIO_EXT)]
        except (OSError, SystemExit) as err:
            print(f'  note: Kenney pack {slug} could not be read ({err})', file=sys.stderr)
            continue
        for name in names:
            stem = re.sub(r'[_ -]?\d+$', '', Path(name).stem)
            key = (slug, str(Path(name).parent), stem)
            groups.setdefault(key, []).append(name)
    hits = []
    for (slug, folder, stem), names in groups.items():
        hay = set(words_of(f'{slug} {folder} {stem}'))
        score = sum(1 for w in words if w in hay or any(h.startswith(w) for h in hay if len(w) > 3))
        if score:
            hits.append((score, slug, stem, sorted(names)))
    hits.sort(key=lambda h: (-h[0], h[1], h[2]))
    return [{'id': f'kenney:{slug}/{names[0]}', 'title': stem.replace('_', ' '), 'source': f'Kenney {slug}',
             'kind': 'music' if slug == 'music-jingles' else 'sfx',
             **({'variants': [f'kenney:{slug}/{n}' for n in names[1:6]], 'variant_count': len(names)} if len(names) > 1 else {})}
            for score, slug, stem, names in hits[:limit]]


# ---------- OpenGameArt ----------

def oga_search(words, kind, limit):
    params = [('keys', ' '.join(words)), ('field_art_type_tid[]', OGA_TYPES[kind]),
              ('field_art_licenses_tid[]', OGA_CC0), ('sort_by', 'count'), ('sort_order', 'DESC'),
              ('items_per_page', '24')]
    page = oga_get(f'{OGA}/art-search-advanced?' + urllib.parse.urlencode(params))
    found = []
    for chunk in re.split(r'<div class="views-row views-row-\d+[^"]*">', page)[1:]:
        link = re.search(r'class="art-preview-title"><a href="/content/([^"?#/]+)">(.*?)</a>', chunk, re.S)
        if not link:
            continue
        mp3 = re.search(r"data-mp3-url='([^']*)'", chunk)
        found.append({'id': f'oga:{link.group(1)}', 'title': text(link.group(2)), 'source': 'OpenGameArt',
                      'kind': kind, 'page': f'{OGA}/content/{link.group(1)}',
                      **({'file': urllib.parse.unquote(mp3.group(1).rsplit('/', 1)[-1])} if mp3 and mp3.group(1) else {})})
    return found[:limit]


def oga_entry(slug):
    page = oga_get(f'{OGA}/content/{slug}')

    def field(name):
        m = re.search(r'<div class="field field-name-' + re.escape(name) + r'[\s"].*?(?=<div class="field field-name-|<ul class="links|$)', page, re.S)
        return m.group(0) if m else ''
    title = re.search(r'field-name-title.*?<h2>(.*?)</h2>', page, re.S)
    author = re.search(r'<a href="/users/[^"]+"[^>]*>(.*?)</a>', field('author-submitter'), re.S)
    licenses = [text(n) for n in re.findall(r"<div class='license-name'>(.*?)</div>", field('field-art-licenses'), re.S)]
    files = []
    for url, kind, name in re.findall(r'<a href="(https://[^"]+)" type="([^"]*)"[^>]*>(.*?)</a>', field('field-art-files'), re.S):
        if urllib.parse.urlsplit(url).hostname == 'opengameart.org':
            size = re.search(r'length=(\d+)', kind)
            files.append({'name': text(name) or url.rsplit('/', 1)[-1], 'url': url, 'size': int(size.group(1)) if size else None})
    return {'title': text(title.group(1)) if title else slug, 'author': text(author.group(1)) if author else 'unknown',
            'licenses': licenses, 'files': files, 'page': f'{OGA}/content/{slug}'}


# ---------- audio processing ----------

def decode(data, suffix):
    import numpy as np
    import soundfile as sf
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            audio, rate = sf.read(tmp.name, dtype='float32', always_2d=True)
        except Exception as err:  # noqa: BLE001 - libsndfile raises several types
            fail(f'Could not read that audio file ({err}).')
    if rate not in MP3_RATES:
        from scipy.signal import resample_poly
        audio = resample_poly(audio, 44100, rate, axis=0).astype('float32')
        rate = 44100
    return np.asarray(audio), rate


def prepare(audio, rate, music, seconds):
    import numpy as np
    if audio.shape[1] > 2:
        audio = audio[:, :2]
    if not music:
        audio = audio.mean(axis=1, keepdims=True)
        loud = np.flatnonzero(np.abs(audio[:, 0]) > 10 ** (-50 / 20))
        if loud.size:
            pad = int(rate * 0.01)
            audio = audio[max(0, loud[0] - pad):loud[-1] + pad]
    limit = seconds or (None if music else SFX_SECONDS)
    if limit and audio.shape[0] > limit * rate:
        audio = audio[:int(limit * rate)].copy()
        fade = min(audio.shape[0], int(rate * (2.0 if music else 0.05)))
        audio[-fade:] *= np.linspace(1, 0, fade, dtype='float32')[:, None]
    peak = float(np.abs(audio).max()) or 1.0
    if music:
        rms = float(np.sqrt(np.mean(audio ** 2))) or 1.0
        gain = min(10 ** (-18 / 20) / rms, 10 ** (-1 / 20) / peak)
    else:
        gain = 10 ** (-1 / 20) / peak
    return (audio * gain).astype('float32')


def mp3(audio, rate, music):
    import soundfile as sf
    for level in ((0.7, 0.9) if music else (0.5,)):
        buf = io.BytesIO()
        sf.write(buf, audio, rate, format='MP3', subtype='MPEG_LAYER_III', compression_level=level, bitrate_mode='VARIABLE')
        data = buf.getvalue()
        if not music or len(data) <= MUSIC_MAX_BYTES:
            return data
    seconds = audio.shape[0] / rate
    fail(f'The track is {len(data) / 1e6:.1f} MB as MP3 ({seconds:.0f} s); games stay fast under {MUSIC_MAX_BYTES / 1e6:.0f} MB.',
         next=f'Pick a shorter track, or add --seconds {int(seconds * MUSIC_MAX_BYTES / len(data)) - 5} to shorten this one.')


# ---------- add / list / remove ----------

def fetch(ident, file_name):
    """(bytes, file suffix, credit, provenance) for a search id."""
    source, _, ref = ident.partition(':')
    if source == 'kenney':
        slug, _, member = ref.partition('/')
        pack = Pack(slug)
        if member not in pack.names():
            fail(f'{member} is not in Kenney pack {slug}.', next=f'python3 packzip.py files {slug} "**/*.ogg"')
        title = slug.replace('-', ' ').title()
        return (pack.file(member).read_bytes(), Path(member).suffix.lower(), f'{title} by Kenney (CC0)',
                {'source': 'kenney', 'pack': slug, 'file': member, 'url': f'https://kenney.nl/assets/{slug}', 'license': 'CC0-1.0'})
    if source == 'oga':
        entry = oga_entry(ref)
        if not any(name.strip().upper() == 'CC0' for name in entry['licenses']):
            fail(f'"{entry["title"]}" is not offered as CC0 ({", ".join(entry["licenses"]) or "no licence shown"}); choose another.')
        files = entry['files']
        if file_name:
            files = [f for f in files if file_name.lower() in f['name'].lower()]
        audio = [f for f in files if f['name'].lower().endswith(AUDIO_EXT)]
        zips = [f for f in files if f['name'].lower().endswith('.zip')]
        credit = f'"{entry["title"]}" by {entry["author"]} (CC0), {entry["page"]}'
        prov = {'source': 'opengameart', 'title': entry['title'], 'author': entry['author'], 'url': entry['page'], 'license': 'CC0-1.0'}
        if not audio and zips and len(zips) == 1:
            pack = Pack(zips[0]['url'])
            inside = [n for n in pack.names() if n.lower().endswith(AUDIO_EXT)]
            pick = [n for n in inside if not file_name or file_name.lower() in n.lower()]
            if len(pick) != 1:
                fail(f'"{entry["title"]}" is a zip of {len(inside)} sounds; choose one with --file.',
                     files=inside[:60])
            return pack.file(pick[0]).read_bytes(), Path(pick[0]).suffix.lower(), credit, {**prov, 'file': pick[0]}
        if not audio:
            fail(f'"{entry["title"]}" has no single audio file to use.', files=[f['name'] for f in entry['files']])
        if len(audio) > 1 and not file_name:
            # Prefer the most playable format of the first track when an entry offers several.
            order = {'.mp3': 0, '.ogg': 1, '.flac': 2, '.wav': 3}
            stems = {Path(f['name']).stem for f in audio}
            if len(stems) > 1:
                fail(f'"{entry["title"]}" has several tracks; choose one with --file.', files=[f['name'] for f in audio])
            audio.sort(key=lambda f: order.get(Path(f['name']).suffix.lower(), 9))
        chosen = audio[0]
        return oga_get(chosen['url'], binary=True), Path(chosen['name']).suffix.lower(), credit, {**prov, 'file': chosen['name']}
    fail(f'Unknown id {ident}; use an id printed by search (kenney:... or oga:...).')


def cmd_add(a):
    name = a.name.lower()
    if not NAME_RE.match(name):
        fail('Names are lowercase letters, digits and _, starting with a letter or digit (e.g. footstep, boss_theme).')
    if bool(a.game) == bool(a.shared):
        fail('Say where it goes: --game GAME_ID (this game only) or --shared (the Assets tab, every game).')
    data, suffix, credit, prov = fetch(a.id, a.file)
    audio, rate = decode(data, suffix)
    audio = prepare(audio, rate, a.music, a.seconds)
    encoded = mp3(audio, rate, a.music)
    seconds = round(audio.shape[0] / rate, 2)
    kind = 'music' if a.music else 'sfx'
    meta = {'kind': kind, 'seconds': seconds, 'size': len(encoded), 'credit': credit, **prov,
            'updatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    if a.game:
        path = f'games/{a.game}.art.json'
        art = storage_get(a.app, path) or {'images': {}, 'sheets': {}, 'sounds': {}, 'models': {}}
        art.setdefault('sounds', {})[name] = 'data:audio/mpeg;base64,' + base64.b64encode(encoded).decode()
        art.setdefault('credits', {})[name] = meta
        storage_put_json(a.app, path, art)
        where = f'game {a.game}'
    else:
        api('PUT', f'/api/storage/apps/{a.app}/audio/{name}.mp3', encoded, 'audio/mpeg')
        assets = storage_get(a.app, 'assets.json') or {}
        assets.setdefault('audio', {})[name] = meta
        storage_put_json(a.app, 'assets.json', assets)
        where = 'Assets (every game)'
    use = f"studio.music('{name}')" if a.music else f"studio.sound('{name}')"
    out({'ok': True, 'name': name, 'kind': kind, 'seconds': seconds, 'kb': round(len(encoded) / 1024), 'where': where,
         'credit': credit, 'use': use})


def cmd_list(a):
    shared = {k: {f: v.get(f) for f in ('kind', 'seconds', 'size', 'credit')} for k, v in ((storage_get(a.app, 'assets.json') or {}).get('audio') or {}).items()}
    result = {'shared': shared}
    if a.game:
        art = storage_get(a.app, f'games/{a.game}.art.json') or {}
        credits = art.get('credits') or {}
        result['game'] = {k: {'kb': round(len(v) * 3 / 4 / 1024), **{f: (credits.get(k) or {}).get(f) for f in ('kind', 'seconds', 'credit')}}
                          for k, v in (art.get('sounds') or {}).items()}
    out(result)


def cmd_remove(a):
    if a.game:
        path = f'games/{a.game}.art.json'
        art = storage_get(a.app, path) or {}
        if a.name not in (art.get('sounds') or {}):
            fail(f'{a.name} is not one of game {a.game}\'s sounds.')
        art['sounds'].pop(a.name, None)
        (art.get('credits') or {}).pop(a.name, None)
        storage_put_json(a.app, path, art)
    else:
        assets = storage_get(a.app, 'assets.json') or {}
        if a.name not in (assets.get('audio') or {}):
            fail(f'{a.name} is not a shared sound.')
        assets['audio'].pop(a.name, None)
        storage_put_json(a.app, 'assets.json', assets)
        api('DELETE', f'/api/storage/apps/{a.app}/audio/{a.name}.mp3')
    out({'ok': True, 'removed': a.name})


def cmd_search(a):
    words = [w for w in words_of(' '.join(a.words)) if len(w) > 1]
    if not words:
        fail('Give a word or two to search for, e.g. "footstep", "laser", "calm forest".')
    kinds = ['music'] if a.music else ['sfx'] if a.sfx else ['sfx', 'music']
    results = {'kenney': [], 'opengameart': []}
    for kind in kinds:
        results['kenney'] += kenney_search(words, kind, a.max)
    for kind in kinds:
        try:
            results['opengameart'] += oga_search(a.words, kind, a.max)
        except OSError as err:
            results['opengameart_error'] = f'OpenGameArt did not answer ({err}).'
    out({**results, 'next': 'python3 sound_library.py add APP_ID ID NAME --game GAME_ID [--music]  (or --shared)',
         **({'tip': 'Nothing found: try one broader word (hit, step, magic, rain, menu, battle, calm).'}
            if not results['kenney'] and not results['opengameart'] else {})})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('search')
    s.add_argument('words', nargs='+')
    g = s.add_mutually_exclusive_group()
    g.add_argument('--music', action='store_true')
    g.add_argument('--sfx', action='store_true')
    s.add_argument('--max', type=int, default=12)
    d = sub.add_parser('add')
    d.add_argument('app')
    d.add_argument('id')
    d.add_argument('name')
    d.add_argument('--game')
    d.add_argument('--shared', action='store_true')
    d.add_argument('--music', action='store_true')
    d.add_argument('--file')
    d.add_argument('--seconds', type=float)
    ls = sub.add_parser('list')
    ls.add_argument('app')
    ls.add_argument('--game')
    r = sub.add_parser('remove')
    r.add_argument('app')
    r.add_argument('name')
    r.add_argument('--game')
    r.add_argument('--shared', action='store_true')
    a = parser.parse_args()
    {'search': cmd_search, 'add': cmd_add, 'list': cmd_list, 'remove': cmd_remove}[a.cmd](a)


if __name__ == '__main__':
    main()
