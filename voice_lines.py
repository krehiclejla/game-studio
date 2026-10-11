#!/usr/bin/env python3
"""Voice lines for a game, made on this machine with Kokoro (Apache-2.0, 82M, via
kokoro-onnx, MIT). The same natural voice on every phone and computer, no
download for players. Lines are saved in the game's own art; studio.say(text,
{voice}) plays the made line when the text and voice match exactly, and falls
back to the device voice for anything else.

  python3 voice_lines.py <appId> <gameId> "hero|We did it!" "villain|You again?" ...
  python3 voice_lines.py <appId> <gameId> --file lines.json      [["hero", "We did it!"], ...]
  python3 voice_lines.py <appId> <gameId> ... --kbps 32             smaller lines (default 40)
  python3 voice_lines.py <appId> <gameId> --list                 what the game has
  python3 voice_lines.py <appId> <gameId> --remove "hero|We did it!"
  python3 voice_lines.py voices                                  every voice name
  python3 voice_lines.py try "af_bella|Hello there" OUT.mp3      one line to a file (to listen)

Voices: the studio's characters (narrator, hero, heroine, villain, robot, kid,
giant, old, fairy) or any Kokoro voice name (af_heart, am_puck, bm_george, ...;
the first letter is the language: a/b English US/UK, e Spanish, f French,
h Hindi, i Italian, j Japanese, p Portuguese, z Chinese; second letter f/m).
About half a second per line; each line is ~5 KB per second of speech.

Japanese: VOICEVOX voices (free, made for Japanese, with angry, hot-blooded and
whispering styles; reads kanji properly). Name one as vv:<style id>, optionally
tuned: vv:81,p=-0.08,s=1.1,i=1.5,r=0.9 (p pitch -0.15..0.15, s speed,
i intonation/emotion 0..2, r playback rate). `voices` lists every style.
VOICEVOX's terms require crediting each character used ("VOICEVOX:<name>");
the tool records them in the game's art as voiceCredits, so show those in
the game's credits. Its models download on first use (~60 MB each).
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_art import storage_get, storage_put_json  # noqa: E402

HOME = Path.home() / '.cache' / 'game-studio' / 'kokoro'
FILES = {
    'kokoro-v1.0.onnx': 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx',
    'voices-v1.0.bin': 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin',
}
# Studio characters -> (Kokoro voice, speaking speed, playback rate for pitch).
CHARACTERS = {
    'narrator': ('af_heart', 1.0, 1.0),
    'hero': ('am_michael', 1.05, 1.0),
    'heroine': ('af_bella', 1.05, 1.0),
    'villain': ('bm_george', 0.9, 0.88),
    'robot': ('am_echo', 1.0, 0.9),
    'kid': ('af_sky', 1.1, 1.18),
    'giant': ('am_onyx', 0.85, 0.8),
    'old': ('bm_lewis', 0.85, 0.95),
    'fairy': ('af_nicole', 1.05, 1.25),
}
LANGS = {'a': 'en-us', 'b': 'en-gb', 'e': 'es', 'f': 'fr-fr', 'h': 'hi', 'i': 'it', 'j': 'ja', 'p': 'pt-br', 'z': 'cmn'}
MAX_LINE = 400
KBPS = 40  # --kbps 24..64: lower keeps big games under the publish limit (shouts sound fine at 32)


VV_HOME = Path.home() / '.cache' / 'game-studio' / 'voicevox'
VV_RELEASE = '0.17.0'
VV_ORT = 'voicevox_onnxruntime-linux-x64-1.23.2'
VV_URLS = {
    'wheel': f'https://github.com/VOICEVOX/voicevox_core/releases/download/{VV_RELEASE}/voicevox_core-{VV_RELEASE}-cp310-abi3-manylinux_2_34_x86_64.whl',
    'ort': f'https://github.com/VOICEVOX/onnxruntime-builder/releases/download/voicevox_onnxruntime-1.23.2/{VV_ORT}.tgz',
    'dict': 'https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz',
    'models': f'https://github.com/VOICEVOX/voicevox_vvm/releases/download/{VV_RELEASE}/',
}


def vv_fetch(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        urllib.request.urlretrieve(url, str(dest) + '.part')
        os.replace(str(dest) + '.part', dest)
    return dest


def vv_styles():
    """{style id: (model file, character, style)} from the models' README table."""
    readme = vv_fetch(VV_URLS['models'] + 'README.txt', VV_HOME / 'vv' / 'models' / 'README.txt').read_text()
    out = {}
    for line in readme.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 4 and cells[0].endswith('.vvm') and cells[3].isdigit():
            out.setdefault(int(cells[3]), (cells[0], cells[1], cells[2]))
    return out


def vv_parse(voice):
    """vv:81,p=-0.08,s=1.1,i=1.5,r=0.9 -> (style id, {pitch, speed, into, rate})."""
    head, *opts = voice[3:].split(',')
    tune = {'p': 0.0, 's': 1.0, 'i': 1.0, 'r': 1.0, 'v': 1.0}
    for o in opts:
        k_, _, v = o.partition('=')
        if k_.strip() in tune:
            tune[k_.strip()] = float(v)
    return int(head), tune


class Voicevox:
    """Loads VOICEVOX once; each voice model is loaded on demand (one at a time
    keeps memory near 400 MB)."""

    def __init__(self):
        import importlib.util
        import tarfile
        if importlib.util.find_spec('voicevox_core') is None:
            whl = vv_fetch(VV_URLS['wheel'], VV_HOME / VV_URLS['wheel'].rsplit('/', 1)[1])
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--user', str(whl)], check=True)
        root = VV_HOME / 'vv'
        for name, folder in (('ort', VV_ORT), ('dict', 'open_jtalk_dic_utf_8-1.11')):
            if not (root / folder).exists():
                tgz = vv_fetch(VV_URLS[name], VV_HOME / VV_URLS[name].rsplit('/', 1)[1])
                with tarfile.open(tgz) as t:
                    t.extractall(root, filter='data')
                tgz.unlink()
        from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer
        ort = Onnxruntime.load_once(filename=str(next((root / VV_ORT / 'lib').glob('libvoicevox_onnxruntime.so*'))))
        self.syn = Synthesizer(ort, OpenJtalk(str(root / 'open_jtalk_dic_utf_8-1.11')), cpu_num_threads=min(4, os.cpu_count() or 4))
        self.styles = vv_styles()
        self.loaded = None

    def use(self, vvm):
        from voicevox_core.blocking import VoiceModelFile
        if self.loaded and self.loaded[0] == vvm:
            return
        if self.loaded:
            self.syn.unload_voice_model(self.loaded[1])
        path = vv_fetch(VV_URLS['models'] + vvm, VV_HOME / 'vv' / 'models' / vvm)
        with VoiceModelFile.open(path) as m:
            self.syn.load_voice_model(m)
            self.loaded = (vvm, m.id)

    def credit(self, voice):
        return 'VOICEVOX:' + self.styles[vv_parse(voice)[0]][1]

    def speak(self, voice, text):
        """Return (mono float samples, sample rate, playback rate)."""
        import io
        import wave
        import numpy as np
        sid, tune = vv_parse(voice)
        if sid not in self.styles:
            sys.exit(f'Unknown VOICEVOX style {sid} (run: voice_lines.py voices).')
        self.use(self.styles[sid][0])
        q = self.syn.create_audio_query(text, sid)
        q.pitch_scale, q.speed_scale, q.intonation_scale = tune['p'], tune['s'], tune['i']
        q.pre_phoneme_length, q.post_phoneme_length = 0.03, 0.08
        with wave.open(io.BytesIO(self.syn.synthesis(q, sid))) as w:
            sr = w.getframerate()
            samples = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype('float32') / 32768
        peak = float(np.abs(samples).max() or 1)
        return samples * (0.95 * tune['v'] / peak), sr, tune['r']


def key(voice, text):
    # Must match lineKey() in gameRuntime.js.
    return f"{voice or 'narrator'}|{' '.join(str(text).split())[:MAX_LINE]}"


def engine():
    need = [p for m, p in (('kokoro_onnx', 'kokoro-onnx'), ('lameenc', 'lameenc')) if __import__('importlib').util.find_spec(m) is None]
    if need:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', *need], check=True)
    HOME.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        if not (HOME / name).exists():
            urllib.request.urlretrieve(url, HOME / (name + '.part'))
            os.replace(HOME / (name + '.part'), HOME / name)
    import onnxruntime as ort
    from kokoro_onnx import Kokoro
    o = ort.SessionOptions()
    # This machine has 8 cores; the default of one thread per host CPU is ~6x slower.
    o.intra_op_num_threads = min(8, os.cpu_count() or 8)
    o.inter_op_num_threads = 1
    return Kokoro.from_session(ort.InferenceSession(str(HOME / 'kokoro-v1.0.onnx'), o, providers=['CPUExecutionProvider']), str(HOME / 'voices-v1.0.bin'))


class Engines:
    """Starts Kokoro and VOICEVOX only when a line needs them."""

    def __init__(self):
        self._k = self._vv = None

    @property
    def kokoro(self):
        self._k = self._k or engine()
        return self._k

    @property
    def vv(self):
        self._vv = self._vv or Voicevox()
        return self._vv


def speak(eng, voice, text):
    """Return (mp3 bytes, playback rate)."""
    import lameenc
    import numpy as np
    if voice.startswith('vv:'):
        samples, sr, rate = eng.vv.speak(voice, text)
    else:
        k = eng.kokoro
        kv, speed, rate = CHARACTERS.get(voice, (voice, 1.0, 1.0))
        if kv not in k.get_voices():
            sys.exit(f'Unknown voice "{voice}". Characters: {", ".join(CHARACTERS)}; a Kokoro voice; or vv:<id> (run: voice_lines.py voices).')
        samples, sr = k.create(text, voice=kv, speed=speed, lang=LANGS.get(kv[0], 'en-us'))
    enc = lameenc.Encoder()
    enc.set_bit_rate(KBPS)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
    return enc.encode(pcm) + enc.flush(), rate


def parse(items):
    out = []
    for item in items:
        if isinstance(item, (list, tuple)):
            voice, text = item
        elif '|' in str(item):
            voice, text = str(item).split('|', 1)
        else:
            voice, text = 'narrator', item
        text = ' '.join(str(text).split())[:MAX_LINE]
        if text:
            out.append((voice.strip() or 'narrator', text))
    return out


def main():
    import base64
    global KBPS
    args = sys.argv[1:]
    if '--kbps' in args:
        i = args.index('--kbps'); KBPS = int(args[i + 1]); del args[i:i + 2]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        return
    if args[0] == 'voices':
        k = engine()
        vv = {f'vv:{i}': f'{c} / {st}' for i, (_, c, st) in sorted(vv_styles().items())}
        print(json.dumps({'characters': {n: v[0] for n, v in CHARACTERS.items()}, 'kokoro': k.get_voices(), 'voicevox': vv}, indent=1, ensure_ascii=False))
        return
    if args[0] == 'try':
        (voice, text), = parse([args[1]])
        mp3, rate = speak(Engines(), voice, text)
        Path(args[2]).write_bytes(mp3)
        print(json.dumps({'ok': True, 'out': args[2], 'rate': rate}))
        return
    app_id, game_id, rest = args[0], args[1], args[2:]
    path = f'games/{game_id}.art.json'
    art = storage_get(app_id, path) or {}
    voices = dict(art.get('voices') or {})
    if rest[:1] == ['--list']:
        print(json.dumps({'lines': sorted(voices)}, indent=1))
        return
    if rest[:1] == ['--remove']:
        gone = [k_ for k_ in (key(v, t) for v, t in parse(rest[1:])) if voices.pop(k_, None)]
        art['voices'] = voices
        storage_put_json(app_id, path, art)
        print(json.dumps({'ok': True, 'removed': gone}))
        return
    items = json.loads(Path(rest[1]).read_text()) if rest[:1] == ['--file'] else rest
    lines = parse(items)
    if not lines:
        sys.exit('No lines given. Use "voice|text".')
    eng = Engines()
    made = []
    credits = set(art.get('voiceCredits') or [])
    # VOICEVOX lines grouped by model file, so each model loads once.
    order = lambda vt: (vt[0].startswith('vv:'), eng.vv.styles[vv_parse(vt[0])[0]][0] if vt[0].startswith('vv:') else '')
    for voice, text in sorted(lines, key=order):
        mp3, rate = speak(eng, voice, text)
        if voice.startswith('vv:'):
            credits.add(eng.vv.credit(voice))
        entry = {'dataUrl': 'data:audio/mpeg;base64,' + base64.b64encode(mp3).decode()}
        if rate != 1.0:
            entry['rate'] = rate
        voices[key(voice, text)] = entry
        made.append({'key': key(voice, text), 'kb': round(len(mp3) / 1024, 1)})
    art['voices'] = voices
    if credits:
        art['voiceCredits'] = sorted(credits)
    storage_put_json(app_id, path, art)
    print(json.dumps({'ok': True, 'game': game_id, 'made': made, 'total_lines': len(voices), 'credits': sorted(credits),
                      'next': "In the game call studio.say(TEXT, { voice: VOICE }) with exactly the same text and voice (spacing may differ)."}, indent=1))


if __name__ == '__main__':
    main()
