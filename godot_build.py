"""Godot games for Game Studio: install the engine, start a game, build it.

  python3 godot_build.py setup APP            install Godot (if missing) and store the shared web engine
  python3 godot_build.py new APP GID [NAME]   start a game from kits/godot/starter, then build it
  python3 godot_build.py build APP GID        export the game and store it so Play shows the new version
  python3 godot_build.py where APP GID        print the game's project folder
  python3 godot_build.py undo APP GID         go back one step (each build is a step) and rebuild
  python3 godot_build.py shot APP GID OUT.png [SECONDS] [--view [--cut METRES]]  render the game in a headless
                                              browser (check the look); --view: in View mode, cut away above a height
  python3 godot_build.py look MODEL.glb OUT.png [--plain]  a model from front, three-quarter and side in the game's
                                              drawn look (playing its idle move); --plain shows its own shading,
                                              --pose rest|CLIP shows the rest pose or another move

A game's Godot project lives in /data/apps/APP/godot-src/GID (edit its .gd, .tscn and
.gdshader files there). `build` exports only the game's pack (games/GID.pck); the engine
is stored once (engine/godot-VERSION.wasm.gz and .js). The Play frame is sandboxed, so
games/GID.html is a small boot page: it asks the studio for the engine and pack, then
starts Godot from them. Errors from the export are printed; fix them and build again.
"""
import gzip
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = '4.7.2'
HERE = Path(__file__).resolve().parent
STARTER = HERE / 'kits' / 'godot' / 'starter'
BIN = Path.home() / '.local' / 'bin' / 'godot'
TEMPLATES = Path.home() / '.local' / 'share' / 'godot' / 'export_templates' / f'{VERSION}.stable'
RELEASE = f'https://github.com/godotengine/godot/releases/download/{VERSION}-stable'
BASE = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
TOKEN = os.environ.get('AGENT_TOKEN') or os.environ.get('APP_TOKEN', '')


def api(method, path, body=None, ctype='application/octet-stream'):
    req = urllib.request.Request(BASE + path, method=method, data=body, headers={
        'Authorization': 'Bearer ' + TOKEN, **({'Content-Type': ctype} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def put(app, path, data, ctype='application/octet-stream'):
    status, body = api('PUT', f'/api/storage/apps/{app}/{path}', data, ctype)
    if status >= 300:
        sys.exit(f'Could not store {path}: HTTP {status} {body[:200]!r}')


def exists(app, path):
    status, _ = api('GET', f'/api/storage/apps/{app}/{path}')
    return status == 200


def download(url, out):
    print(f'downloading {url}', flush=True)
    with urllib.request.urlopen(url, timeout=900) as res, open(out, 'wb') as f:
        shutil.copyfileobj(res, f)


def install():
    """Godot lives outside /data, so a container replacement removes it; reinstall on demand."""
    if not BIN.exists():
        with tempfile.TemporaryDirectory() as tmp:
            z = Path(tmp) / 'godot.zip'
            download(f'{RELEASE}/Godot_v{VERSION}-stable_linux.x86_64.zip', z)
            BIN.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(z) as zf:
                name = next(n for n in zf.namelist() if n.endswith('x86_64'))
                with zf.open(name) as src, open(BIN, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
            BIN.chmod(0o755)
    if not (TEMPLATES / 'web_nothreads_release.zip').exists():
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / 'templates.tpz'
            download(f'{RELEASE}/Godot_v{VERSION}-stable_export_templates.tpz', t)
            TEMPLATES.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(t) as zf:
                for n in zf.namelist():
                    if n.startswith('templates/web_') or n == 'templates/version.txt':
                        with zf.open(n) as src, open(TEMPLATES / Path(n).name, 'wb') as dst:
                            shutil.copyfileobj(src, dst)


def godot(project, *args, timeout=600):
    return subprocess.run([str(BIN), '--headless', '--path', str(project), *args],
                          capture_output=True, text=True, timeout=timeout)


def setup(app):
    install()
    if exists(app, f'engine/godot-{VERSION}.wasm.gz') and exists(app, f'engine/godot-{VERSION}.js'):
        print('engine already stored')
        return
    with zipfile.ZipFile(TEMPLATES / 'web_nothreads_release.zip') as zf:
        wasm = zf.read('godot.wasm')
        js = zf.read('godot.js')
    put(app, f'engine/godot-{VERSION}.wasm.gz', gzip.compress(wasm, 9))
    put(app, f'engine/godot-{VERSION}.js', js, 'text/javascript')
    print(f'stored engine: {len(wasm) // 1_000_000} MB, compressed for download')


def folder(app, gid):
    return Path('/data/apps') / str(app) / 'godot-src' / gid


BOOT = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__</title><!-- build __STAMP__ --><meta name="studio-pck" content="__PCK__">
<style>html,body{margin:0;height:100%;overflow:hidden;background:#0b1020;touch-action:none}canvas{display:block;width:100%;height:100%;outline:none}
#gd-load{position:fixed;inset:0;display:grid;place-items:center;color:#fff;font:600 16px system-ui,sans-serif}</style></head>
<body><canvas id="canvas" tabindex="0"></canvas><div id="gd-load">Loading…</div><script>
(() => {
  const say = (type, extra) => parent.postMessage(Object.assign({ type }, extra || {}), '*');
  const fail = (err) => { const l = document.getElementById('gd-load'); if (l) l.textContent = 'This game could not start.'; say('studio:error', { message: String(err && err.message || err), detail: 'Godot start-up' }); };
  addEventListener('message', async (e) => {
    const d = e.data; if (!d || d.type !== 'godot:files') return;
    try {
      const wasm = await new Response(d.wasmGz.stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
      const pck = await d.pck.arrayBuffer();
      const files = { 'index.wasm': [wasm, 'application/wasm'], 'index.pck': [pck, 'application/octet-stream'] };
      const realFetch = window.fetch.bind(window);
      window.fetch = (url, init) => { const f = files[String(url).split('?')[0].split('/').pop()]; return f ? Promise.resolve(new Response(f[0], { headers: { 'Content-Type': f[1] } })) : realFetch(url, init); };
      // Audio worklets load with addModule, which bypasses fetch. Safari only accepts them from a
      // real address in this sandboxed frame, so use Game Studio's served copies.
      if (window.AudioWorklet && d.assetBase) {
        const add = AudioWorklet.prototype.addModule;
        AudioWorklet.prototype.addModule = function (path, opts) {
          const m = String(path).match(/index\.(audio(?:\.position)?\.worklet\.js)$/);
          return add.call(this, m ? d.assetBase + 'godot/__VERSION__/' + m[1] : path, opts);
        };
      }
      // No service worker in a sandboxed frame (WebKit throws on merely reading it).
      try { Object.defineProperty(navigator, 'serviceWorker', { value: { getRegistration: () => Promise.resolve(undefined), register: () => Promise.reject(new Error('none')) }, configurable: true }); } catch (_) {}
      window.__studioMode = d.mode || 'play';   // 'view': Game Studio's Edit view (studio_view.gd)
      window.__studioCamera = d.camera || null;  // keep the Edit view's camera across rebuilds
      window.__studioSelected = d.selected || null;
      window.__studioCut = d.cut || null;       // see-inside cut height in metres, or null
      (0, eval)(d.engineJs);
      const engine = new Engine({ executable: 'index', mainPack: 'index.pck', canvasResizePolicy: 2, focusCanvas: true, args: [],
        fileSizes: { 'index.pck': pck.byteLength, 'index.wasm': wasm.byteLength } });
      await engine.startGame();
      // let go of the engine and pack copies: phones (iPhone Safari above all) have little memory
      files['index.wasm'] = null; files['index.pck'] = null;
      const load = document.getElementById('gd-load'); if (load) load.remove();
    } catch (err) { fail(err); }
  });
  // toolbar commands from the studio (home, see inside, select), read by studio_view.gd each frame
  window.__studioInbox = [];
  addEventListener('message', (e) => { if (e.data && e.data.type === 'studio:view') window.__studioInbox.push(e.data); });
  say('godot:ready');
})();
</script></body></html>'''


def phone_textures(src):
    """Textures pulled out of imported models default to GPU-compressed copies for every
    platform (a 35 MB game for one textured shop). Store them as compact WebP instead, capped
    at 1024 px for big tiling surfaces (names with _tile) and 512 px for everything else.
    Returns True when an import setting changed (the project must be imported again)."""
    changed = False
    for imp in Path(src).rglob('*.import'):
        if '.godot' in imp.parts or imp.suffixes[-2:-1] not in (['.jpg'], ['.jpeg'], ['.png'], ['.webp']):
            continue
        text = imp.read_text()
        if 'importer="texture"' not in text:
            continue
        lim = 1024 if '_tile' in imp.name else 512
        new = re.sub(r'(?m)^compress/mode=[02]$', 'compress/mode=1', text)
        if 'compress/mode=1' in new:
            new = re.sub(r'(?m)^process/size_limit=0$', f'process/size_limit={lim}', new)
        if new != text:
            imp.write_text(new)
            changed = True
    return changed


VIEW_KIT = HERE / 'kits' / 'godot' / 'view'


def ensure_view(src):
    """Every Godot game gets Game Studio's View mode (free camera and see-inside cut-away), kept
    up to date on each build. It does nothing unless the studio's View switch is on."""
    src = Path(src)
    for f in VIEW_KIT.iterdir():
        if f.is_file():
            shutil.copy(f, src / f.name)
    proj = src / 'project.godot'
    text = proj.read_text()
    line = 'StudioView="*res://studio_view.gd"'
    if line in text:
        return
    if re.search(r'(?m)^\[autoload\]', text):
        text = re.sub(r'(?m)^\[autoload\][ \t]*\n', '[autoload]\n\n' + line + '\n', text, count=1)
    else:
        text = text.rstrip() + '\n\n[autoload]\n\n' + line + '\n'
    proj.write_text(text)


HISTORY_SKIP = ('.godot', 'build', '.history')


def _project_files(src):
    for f in sorted(Path(src).rglob('*')):
        rel = f.relative_to(src)
        if f.is_file() and rel.parts[0] not in HISTORY_SKIP and f.suffix != '.import':
            yield rel, f


def snapshot(src, keep=30):
    """Remember the project as it is (one step of the person's history). Files are stored once by
    content, so a step that changes one script costs only that script."""
    import hashlib
    hist = Path(src) / '.history'
    blobs = hist / 'blobs'
    blobs.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for rel, f in _project_files(src):
        data = f.read_bytes()
        h = hashlib.sha1(data).hexdigest()
        if not (blobs / h).exists():
            (blobs / h).write_bytes(data)
        manifest[str(rel)] = h
    steps = sorted(hist.glob('step-*.json'))
    if steps and json.loads(steps[-1].read_text()) == manifest:
        return  # nothing changed since the last step
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    (hist / f'step-{stamp}.json').write_text(json.dumps(manifest))
    for old in sorted(hist.glob('step-*.json'))[:-keep]:
        old.unlink()
    live = set()
    for st in hist.glob('step-*.json'):
        live |= set(json.loads(st.read_text()).values())
    for b in blobs.iterdir():
        if b.name not in live:
            b.unlink()


def undo(app, gid):
    """Go back one step: restore the project as it was before the last build, then rebuild."""
    src = folder(app, gid)
    hist = src / '.history'
    steps = sorted(hist.glob('step-*.json'))
    if len(steps) < 2:
        sys.exit('Nothing to undo yet.')
    prev = json.loads(steps[-2].read_text())
    for rel, f in list(_project_files(src)):
        if str(rel) not in prev:
            f.unlink()
    for rel, h in prev.items():
        dst = src / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((hist / 'blobs' / h).read_bytes())
    steps[-1].unlink()
    build(app, gid, record=False)
    print(json.dumps({'undone': gid, 'steps_left': len(steps) - 1}))


def _drop_old_packs(app, gid, keep):
    """Remove earlier builds' game files (and the old unversioned one) from storage."""
    status, body = api('GET', f'/api/storage/apps-list/{app}/games/')
    if status != 200:
        return
    try:
        entries = json.loads(body).get('entries', [])
    except Exception:
        return
    for e in entries:
        name = e.get('name', '')
        path = f'games/{name}'
        if name.startswith(f'{gid}.') and name.endswith('.pck') and path != keep:
            api('DELETE', f'/api/storage/apps/{app}/{path}')


def build(app, gid, record=True):
    install()
    src = folder(app, gid)
    if not (src / 'project.godot').exists():
        sys.exit(f'No Godot project at {src}. Start one with: python3 {__file__} new {app} {gid}')
    meta_status, meta_body = api('GET', f'/api/storage/apps/{app}/games/{gid}.json')
    meta = json.loads(meta_body) if meta_status == 200 else {'id': gid, 'name': 'Untitled game'}
    ensure_view(src)
    godot(src, '--import')
    if phone_textures(src):
        godot(src, '--import')
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'index.pck'
        r = godot(src, '--export-pack', 'Web', str(out))
        log = (r.stdout + r.stderr)
        errors = [l for l in log.splitlines() if 'ERROR' in l or 'SCRIPT ERROR' in l or 'Parse Error' in l]
        if r.returncode != 0 or not out.exists():
            print(log[-3000:])
            sys.exit('Export failed; fix the errors above and build again.')
        if errors:
            print('Warnings/errors during export (the game may not run):\n' + '\n'.join(errors[:20]))
        pck = out.read_bytes()
    # A script error does not stop an export, but the game would not start: boot it headless
    # for a moment and refuse to store a game whose scripts fail to load.
    boot = godot(src, '--quit-after', '30', timeout=180)
    boot_log = boot.stdout + boot.stderr
    script_errors = [l for l in boot_log.splitlines() if 'SCRIPT ERROR' in l or 'Parse Error' in l or 'Failed to load script' in l]
    if script_errors:
        print('\n'.join(script_errors[:20]))
        sys.exit('The game has script errors (above), so it was not stored. Fix them and build again.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    name = str(meta.get('name') or 'Game').replace('<', '').replace('&', '')
    # Devices keep a stored binary forever once read, so every build gets its own file name
    # (named in the boot page); a rebuild is then a new file every device must fetch.
    pck_path = f'games/{gid}.{stamp}.pck'
    put(app, pck_path, pck)
    put(app, f'games/{gid}.html', BOOT.replace('__VERSION__', VERSION).replace('__NAME__', name).replace('__STAMP__', stamp)
        .replace('__PCK__', pck_path).encode(), 'text/html')
    _drop_old_packs(app, gid, keep=pck_path)
    meta.update({'kind': 'godot', 'engine': f'godot-{VERSION}', 'updatedAt': datetime.now(timezone.utc).isoformat()})
    put(app, f'games/{gid}.json', json.dumps(meta).encode(), 'application/json')
    if record:
        snapshot(src)
    print(json.dumps({'built': gid, 'pack_kb': len(pck) // 1024, 'folder': str(src), 'stamp': stamp}))


def new(app, gid, name=None):
    setup(app)
    if name and not exists(app, f'games/{gid}.json'):
        put(app, f'games/{gid}.json', json.dumps({'id': gid, 'name': name, 'kind': 'godot',
            'controls': 'Move with WASD or the arrows, or drag on a touch screen.'}).encode(), 'application/json')
    dst = folder(app, gid)
    if not dst.exists():
        shutil.copytree(STARTER, dst)
        if name:
            p = dst / 'project.godot'
            p.write_text(p.read_text().replace('config/name="Godot game"', f'config/name={json.dumps(name)}'))
    build(app, gid)


def _render(project, out, seconds=12, size=(960, 600), query=''):
    """Export PROJECT to web and photograph it after SECONDS in headless Chromium. Returns console errors."""
    install()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'playwright'], check=True)
        from playwright.sync_api import sync_playwright
    subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], capture_output=True)
    import http.server, socketserver, threading, functools
    logs = []
    with tempfile.TemporaryDirectory() as tmp:
        godot(project, '--import')
        r = godot(project, '--export-release', 'Web', str(Path(tmp) / 'index.html'))
        if not (Path(tmp) / 'index.html').exists():
            print((r.stdout + r.stderr)[-3000:]); sys.exit('Export failed.')
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
        handler.log_message = lambda *a, **k: None
        with socketserver.TCPServer(('127.0.0.1', 0), handler) as httpd:
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            with sync_playwright() as p:
                b = p.chromium.launch(args=['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'])
                pg = b.new_page(viewport={'width': size[0], 'height': size[1]})
                pg.on('console', lambda m: logs.append(m.text))
                pg.goto(f'http://127.0.0.1:{httpd.server_address[1]}/index.html{query}')
                pg.wait_for_timeout(int(float(seconds) * 1000))
                pg.screenshot(path=out)
                b.close()
            httpd.shutdown()
    return [l for l in logs if ('error' in l.lower() or 'SCRIPT' in l) and 'GPU stall' not in l]


def shot(app, gid, out, seconds=12, view=False, cut=None):
    """Photograph the game itself (its main scene) in a headless browser; view=True shows it in
    View mode (cut = see-inside height in metres)."""
    ensure_view(folder(app, gid))
    q = ('?studio_view=1' + (f'&cut={cut}' if cut is not None else '')) if view else ''
    errs = _render(folder(app, gid), out, seconds, query=q)
    print(json.dumps({'shot': out, 'errors': errs[:15]}))


LOOK_GD = r'''extends Node3D
# Style check: the model three times (front, three-quarter, side) in the game's drawn look.
var plain := __PLAIN__
var pose := "__POSE__"
var focus := "__FOCUS__"
var bg := Color("__BG__")

func _ready() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = bg
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.3, 0.28, 0.36) if not plain else Color(0.55, 0.55, 0.6)
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new(); we.environment = env; add_child(we)
	var sun := DirectionalLight3D.new(); sun.rotation_degrees = Vector3(-40, -30, 0); add_child(sun)
	var scene: PackedScene = load("res://model.glb")
	var turns := [0.0, -45.0, -90.0]
	var boxes: Array[AABB] = []
	var holders: Array[Node3D] = []
	for i in 3:
		var holder := Node3D.new(); add_child(holder)
		var m: Node3D = scene.instantiate()
		holder.add_child(m)
		m.rotation_degrees.y = turns[i]
		if not plain:
			Cel.apply(m)
		_play_idle(m)
		holders.append(holder)
	await get_tree().process_frame
	await get_tree().process_frame
	var box := _aabb(holders[0])
	var w: float = max(box.size.x, box.size.z) * 1.25 + 0.2
	for i in 3:
		holders[i].position = Vector3((i - 1) * w, -box.position.y, 0)
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	var h: float = box.size.y
	cam.size = max(h * 1.12, w * 3.0 * 0.5 * 1.05)
	cam.position = Vector3(0, h * 0.5, 20)
	if focus == "head":
		# front close-up of the top of the model (the face): hide the turned copies
		holders[1].visible = false
		holders[2].visible = false
		cam.size = h * 0.24
		cam.position = Vector3(-w, h * 0.86, 20)
		for sk in holders[0].find_children("*", "Skeleton3D", true, false):
			var skel := sk as Skeleton3D
			var bi := skel.find_bone("DEF-head")
			if bi >= 0:
				var hp: Vector3 = skel.global_transform * skel.get_bone_global_pose(bi).origin
				cam.size = h * 0.2
				cam.position = Vector3(hp.x, hp.y + h * 0.06, 20)
	add_child(cam)
	cam.current = true

func _play_idle(n: Node) -> void:
	for c in n.find_children("*", "AnimationPlayer", true, false):
		var ap := c as AnimationPlayer
		var pick := ""
		if pose == "rest":
			return
		var names := ap.get_animation_list()
		for want in [pose, "Idle_Loop", "idle", "Idle"]:
			if want != "" and names.has(want):
				pick = want
				break
		if pick == "":
			for a in names:
				var l := a.to_lower()
				if l.contains("idle") and not l.contains("crouch") and pick == "":
					pick = a
		if pick != "":
			ap.get_animation(pick).loop_mode = Animation.LOOP_LINEAR
			ap.play(pick)

func _aabb(n: Node) -> AABB:
	var out := AABB()
	var first := true
	# geometry only: lights are VisualInstance3D too, and their reach would swamp the framing
	for c in n.find_children("*", "GeometryInstance3D", true, false):
		var vi := c as GeometryInstance3D
		var b := vi.global_transform * vi.get_aabb()
		if first:
			out = b; first = false
		else:
			out = out.merge(b)
	return out
'''


def look(model, out, seconds=14, plain=False, bg='#f2e6d8', pose=''):
    """Render a GLB from the front, three-quarter and side in the starter's drawn look (Cel.apply)."""
    model = Path(model).resolve()
    if not model.exists():
        sys.exit(f'No model at {model}')
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
        proj = Path(tmp) / 'look'
        shutil.copytree(STARTER, proj)
        for f in ('main.gd', 'player.gd'):
            (proj / f).unlink(missing_ok=True)
        shutil.copy(model, proj / 'model.glb')
        def gd(focus):
            return (LOOK_GD.replace('__PLAIN__', 'true' if plain else 'false').replace('__BG__', bg)
                    .replace('__POSE__', pose).replace('__FOCUS__', focus))
        (proj / 'main.gd').write_text(gd(''))
        errs = _render(proj, out, seconds, size=(1200, 600))
        # plus a close-up of the face (characters with a skeleton), so drawn features can be judged
        from model_tool import read_glb
        if not read_glb(str(model))[0].get('skins'):
            print(json.dumps({'look': str(out), 'errors': errs[:15]}))
            return
        (proj / 'main.gd').write_text(gd('head'))
        head = Path(tmp) / 'head.png'
        errs += _render(proj, str(head), seconds, size=(600, 600))
        from PIL import Image
        full, face = Image.open(out), Image.open(head)
        sheet = Image.new('RGB', (full.width + face.width, max(full.height, face.height)), bg)
        sheet.paste(full, (0, 0)); sheet.paste(face, (full.width, 0))
        sheet.save(out)
    print(json.dumps({'look': str(out), 'errors': errs[:15]}))

if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == 'setup':
        setup(a[1])
    elif len(a) >= 3 and a[0] == 'new':
        new(a[1], a[2], ' '.join(a[3:]) or None)
    elif len(a) >= 3 and a[0] == 'build':
        build(a[1], a[2])
    elif len(a) >= 4 and a[0] == 'shot':
        rest = [x for x in a[4:] if not x.startswith('--')]
        cut = a[a.index('--cut') + 1] if '--cut' in a else None
        if cut in rest: rest.remove(cut)
        shot(a[1], a[2], a[3], *(rest[:1]), view='--view' in a, cut=cut)
    elif len(a) >= 3 and a[0] == 'look':
        look(a[1], a[2], plain='--plain' in a, pose=a[a.index('--pose') + 1] if '--pose' in a else '')
    elif len(a) >= 3 and a[0] == 'undo':
        undo(a[1], a[2])
    elif len(a) >= 3 and a[0] == 'where':
        print(folder(a[1], a[2]))
    else:
        print(__doc__)
        sys.exit(2)
