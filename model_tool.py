#!/usr/bin/env python3
"""3D character tools for Game Studio: Kenney packs, Mixamo downloads, AI edits.

  python3 model_tool.py info MODEL.glb
      Meshes, animations, size, and whether textures are external.
  python3 model_tool.py fbx IN.fbx OUT.glb
      Convert FBX (Kenney animated packs, Mixamo downloads) to GLB.
  python3 model_tool.py pack IN.glb OUT.glb [--texture PNG]
      Make a model self-contained: embed its external textures (optionally
      replacing the first one, e.g. a recoloured skin).
  python3 model_tool.py merge-anims BASE.glb OUT.glb ANIM.glb[=name] ...
      Copy animations from other files with the same skeleton (Mixamo
      "without skin" downloads, Kenney Animations/*.fbx converted to GLB) into
      BASE, matching bones by name. "=name" renames the clip.
  python3 model_tool.py rename-anims IN.glb OUT.glb old=new ...
  python3 model_tool.py keep-anims IN.glb OUT.glb "Idle=idle,Walking_A=walk,1H_Melee_Attack_Chop=attack,Death_A=die"
      Keep only these clips (renamed) and shrink the file; use it on library characters with many clips.
  python3 model_tool.py recolor IN.glb OUT.glb "Skin=#e0b08c,Clothes=#2d3f66"
      Repaint materials by name (see info); great for colour-only models such as Quaternius's.
  python3 model_tool.py fists IN.glb OUT.glb
      Close both hands into fists (finger bones curl toward the palm; every move keeps it).
      equip does this for the holding hand by itself.
  node /data/apps/game-studio/attach.mjs joints|add ...
      Add hats, capes, weapons or gear to any rigged character, fixed to a bone.
  python3 model_tool.py library
      List the 89 free animations of the Quaternius Universal Animation Library (CC0).
  python3 model_tool.py add-anims IN.glb OUT.glb "Walk_Loop=walk,Sword_Attack=attack,Zombie_Walk_Fwd_Loop=zombie-walk"
      Retarget library animations onto any skinned humanoid (Kenney animated
      characters, Mixamo, imports). Not for rigid-part models (Kenney blocky or
      mini characters), which already have their own clips.
  python3 model_tool.py moves <appId> NAME "Dance_Loop=dance,Yes=nod,..."
      Give a gallery 3D character more moves from the library (any humanoid): adds the
      clips, saves it (the Characters tab and games see them by their new names).
  python3 model_tool.py render MODEL.glb OUT.png [--anim NAME] [--size 512]
      Render a thumbnail (a 3/4 view on a transparent background) to check it.
  python3 model_tool.py draft <appId> NAME --job ID --glb FILE [--thumb PNG] [--source kenney|import|ai] [--prompt TEXT]
      Save a 3D character design for the person to Keep, retry or change.
  python3 model_tool.py save <appId> NAME --glb FILE [--thumb PNG]
      Replace a gallery 3D character's model (after an edit).
  python3 model_tool.py keep <appId> NAME --glb FILE [--thumb PNG] [--spec SPEC.json] [--credit TEXT]
         [--source made] [--style S] [--role ROLE] [--body humanoid] [--height M] [--prompt TEXT]
      Save a finished 3D character straight into the Characters tab (like tapping Keep on a
      draft). Use it for characters made for a game, so the person can see and reuse them.
      Prints the final name (a taken name gets a number added).
  python3 model_tool.py texture MODEL.glb OUT.png
      Pull out the embedded texture to recolour it (then pack --texture).
  python3 model_tool.py asset <appId> NAME --glb FILE [--thumb PNG] [--credit TEXT] [--prompt TEXT]
      Save a 3D model (tree, rock, house, prop, vehicle) to Assets; games load it with studio.model(NAME).

Models must stay under 3 MB. Game animation names that games expect: idle,
walk, run (or sprint), jump, fall, attack, hurt, die.
"""
import argparse
from datetime import datetime, timezone
import base64
import json
import os
import re
import struct
import subprocess
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_art import api, storage_get, storage_put_json  # noqa: E402

MAX_MODEL = 3 * 1024 * 1024  # an installed game app holds ~7.5 MB: about two characters this size
BIN_DIR = Path.home() / '.cache' / 'game-studio' / 'bin'
FBX2GLTF_URL = 'https://github.com/facebookincubator/FBX2glTF/releases/download/v0.9.7/FBX2glTF-linux-x64'


# ---------- GLB read/write ----------

def read_glb(path):
    data = Path(path).read_bytes()
    if data[:4] != b'glTF':
        sys.exit(f'{path} is not a GLB file.')
    offset, gltf, binary = 12, None, b''
    while offset < len(data):
        length, kind = struct.unpack('<II', data[offset:offset + 8])
        chunk = data[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            gltf = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = bytearray(chunk)
        offset += 8 + length
    gltf.setdefault('buffers', [{'byteLength': 0}])
    return gltf, bytearray(binary)


def write_glb(path, gltf, binary):
    while len(binary) % 4:
        binary.append(0)
    gltf['buffers'] = [{'byteLength': len(binary)}]
    js = json.dumps(gltf, separators=(',', ':')).encode()
    js += b' ' * ((4 - len(js) % 4) % 4)
    out = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary))
    out += struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(binary), 0x004E4942) + bytes(binary)
    Path(path).write_bytes(out)
    return len(out)


def add_view(gltf, binary, blob):
    while len(binary) % 4:
        binary.append(0)
    view = {'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(blob)}
    binary.extend(blob)
    gltf.setdefault('bufferViews', []).append(view)
    return len(gltf['bufferViews']) - 1


def view_bytes(gltf, binary, index):
    v = gltf['bufferViews'][index]
    start = v.get('byteOffset', 0)
    return bytes(binary[start:start + v['byteLength']])


# ---------- commands ----------

def info(path):
    gltf, binary = read_glb(path)
    anims = [{'name': a.get('name'), 'channels': len(a.get('channels', []))} for a in gltf.get('animations', [])]
    mats = [m.get('name') for m in gltf.get('materials', [])]
    external = [img.get('uri') for img in gltf.get('images', []) if img.get('uri') and not img['uri'].startswith('data:')]
    print(json.dumps({'bytes': Path(path).stat().st_size, 'meshes': len(gltf.get('meshes', [])), 'skins': len(gltf.get('skins', [])),
                      'nodes': len(gltf.get('nodes', [])), 'materials': mats, 'animations': anims, 'external_textures': external}, indent=1))


def fbx2glb(src, out):
    exe = BIN_DIR / 'FBX2glTF'
    if not exe.exists():
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(urllib.request.urlopen(FBX2GLTF_URL, timeout=120).read())
        exe.chmod(0o755)
    base = str(out)[:-4] if str(out).endswith('.glb') else str(out)
    proc = subprocess.run([str(exe), '--binary', '--input', str(src), '--output', base], capture_output=True, text=True)
    if proc.returncode or not Path(base + '.glb').exists():
        sys.exit('Converting the FBX failed: ' + (proc.stderr or proc.stdout)[-800:])
    print(json.dumps({'ok': True, 'out': base + '.glb'}))


def pack(src, out, texture=None):
    gltf, binary = read_glb(src)
    folder = Path(src).parent
    for i, img in enumerate(gltf.get('images', [])):
        uri = img.get('uri')
        if texture and i == 0:
            blob, mime = Path(texture).read_bytes(), 'image/png'
        elif uri and uri.startswith('data:'):
            head, b64 = uri.split(',', 1)
            blob, mime = base64.b64decode(b64), head[5:].split(';')[0]
        elif uri:
            file = folder / uri
            if not file.exists():
                sys.exit(f'Missing texture {uri} next to {src}.')
            blob, mime = file.read_bytes(), 'image/jpeg' if file.suffix.lower() in ('.jpg', '.jpeg') else 'image/png'
        else:
            continue
        gltf['images'][i] = {'name': img.get('name', f'image{i}'), 'mimeType': mime, 'bufferView': add_view(gltf, binary, blob)}
    if texture and not gltf.get('images'):
        # Models without a texture slot (common for FBX exports) get the skin on every material.
        view = add_view(gltf, binary, Path(texture).read_bytes())
        gltf['images'] = [{'name': 'skin', 'mimeType': 'image/png', 'bufferView': view}]
        gltf['samplers'] = gltf.get('samplers') or [{'magFilter': 9729, 'minFilter': 9987}]
        gltf['textures'] = (gltf.get('textures') or []) + [{'source': 0, 'sampler': 0}]
        tex = len(gltf['textures']) - 1
        for mat in gltf.get('materials', []):
            pbr = mat.setdefault('pbrMetallicRoughness', {})
            pbr['baseColorTexture'] = {'index': tex}
            pbr['baseColorFactor'] = [1, 1, 1, 1]
            pbr['metallicFactor'] = 0
            pbr['roughnessFactor'] = 0.8
    size = write_glb(out, gltf, binary)
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': size}))


def merge_anims(base, out, extras):
    gltf, binary = read_glb(base)
    names = {n.get('name'): i for i, n in enumerate(gltf.get('nodes', [])) if n.get('name')}
    gltf.setdefault('animations', [])
    gltf.setdefault('accessors', [])
    added = []
    for spec in extras:
        path, _, rename = spec.partition('=')
        other, obin = read_glb(path)
        # FBX exports often add a one-frame "pose" clip beside the real one; skip it.
        def length(a):
            return max((other['accessors'][s['input']].get('max') or [0])[0] for s in a['samplers'])
        clips = [a for a in other.get('animations', []) if length(a) > 0.05] or other.get('animations', [])
        other['animations'] = clips
        for k, anim in enumerate(clips):
            samplers, remap = [], {}
            for s_index, sampler in enumerate(anim['samplers']):
                new = {}
                for key in ('input', 'output'):
                    acc = dict(other['accessors'][sampler[key]])
                    acc['bufferView'] = add_view(gltf, binary, view_bytes(other, obin, acc['bufferView']))
                    gltf['accessors'].append(acc)
                    new[key] = len(gltf['accessors']) - 1
                new['interpolation'] = sampler.get('interpolation', 'LINEAR')
                remap[s_index] = len(samplers)
                samplers.append(new)
            channels = []
            for ch in anim['channels']:
                node_name = other['nodes'][ch['target']['node']].get('name')
                # Mixamo prefixes bones (mixamorig:Hips vs mixamorig1:Hips); match loosely.
                target = names.get(node_name) or names.get(re.sub(r'^mixamorig\d*:', 'mixamorig:', node_name or ''))
                if target is None:
                    continue
                channels.append({'sampler': remap[ch['sampler']], 'target': {'node': target, 'path': ch['target']['path']}})
            if not channels:
                continue
            clip = rename if rename and len(other['animations']) == 1 else (anim.get('name') or Path(path).stem)
            if rename and len(other['animations']) > 1:
                clip = f'{rename}-{k}'
            gltf['animations'] = [a for a in gltf['animations'] if a.get('name') != clip]
            gltf['animations'].append({'name': clip, 'samplers': samplers, 'channels': channels})
            added.append({'name': clip, 'channels': len(channels), 'of': len(anim['channels'])})
    size = write_glb(out, gltf, binary)
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': size, 'added': added,
                      'note': 'Channels that matched no bone were skipped; if "channels" is far below "of", the skeletons differ.'}))


def rename_anims(src, out, pairs):
    gltf, binary = read_glb(src)
    mapping = dict(p.split('=', 1) for p in pairs)
    for a in gltf.get('animations', []):
        if a.get('name') in mapping:
            a['name'] = mapping[a['name']]
    write_glb(out, gltf, binary)
    print(json.dumps({'ok': True, 'animations': [a.get('name') for a in gltf.get('animations', [])]}))


RENDER_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:transparent}</style></head><body>
<script type="module">
import * as THREE from 'https://esm.sh/three@0.180.0';
import { GLTFLoader } from 'https://esm.sh/three@0.180.0/examples/jsm/loaders/GLTFLoader.js';
const size = __SIZE__;
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setSize(size, size); renderer.outputColorSpace = THREE.SRGBColorSpace; document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 2.2); sun.position.set(3, 5, 4); scene.add(sun);
const bytes = Uint8Array.from(atob('__GLB__'), (c) => c.charCodeAt(0));
new GLTFLoader().parse(bytes.buffer, '', (gltf) => {
  const root = gltf.scene; scene.add(root);
  const anim = '__ANIM__';
  const clip = gltf.animations.find((a) => a.name === anim) || gltf.animations.find((a) => /idle/i.test(a.name));
  if (clip) { const mixer = new THREE.AnimationMixer(root); mixer.clipAction(clip).play(); mixer.update(clip.duration * 0.3); }
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root); const c = box.getCenter(new THREE.Vector3()); const s = box.getSize(new THREE.Vector3());
  const r = Math.max(s.x, s.y, s.z);
  const cam = new THREE.PerspectiveCamera(30, 1, r / 100, r * 100);
  cam.position.set(c.x + r * 1.2, c.y + r * 0.12, c.z + r * 2.6); cam.lookAt(c);
  renderer.render(scene, cam); document.title = 'ready';
}, (e) => { document.title = 'error ' + e; });
</script></body></html>"""


def render(model, out, anim='idle', size=512):
    work = Path(tempfile.mkdtemp(prefix='render-', dir=os.environ.get('TMPDIR')))
    page = work / 'view.html'
    glb = base64.b64encode(Path(model).read_bytes()).decode()
    page.write_text(RENDER_PAGE.replace('__SIZE__', str(size)).replace('__GLB__', glb).replace('__ANIM__', anim or ''))
    env = {k: v for k, v in os.environ.items() if k not in ('AGENT_BROWSER_PROFILE', 'AGENT_BROWSER_SESSION')}
    base = ['agent-browser', '--session', f'render-{os.getpid()}', '--profile', str(work / 'profile')]
    run = lambda *a: subprocess.run([*base, *a], capture_output=True, text=True, timeout=90, env=env).stdout.strip()
    try:
        run('set', 'viewport', str(size), str(size))
        run('open', f'file://{page}')
        title = ''
        for _ in range(40):
            title = run('get', 'title')
            if 'ready' in title or 'error' in title:
                break
            time.sleep(0.5)
        if 'ready' not in title:
            sys.exit(f'The model did not render: {title or "timed out"}')
        data_url = run('eval', "document.querySelector('canvas').toDataURL('image/png')").strip().strip('"')
        Path(out).write_bytes(base64.b64decode(data_url.split(',', 1)[1]))
    finally:
        run('close')
    print(json.dumps({'ok': True, 'out': str(out), 'next': 'Read the PNG to check the model.'}))


def thumb_data_url(path):
    from PIL import Image
    import io
    img = Image.open(path).convert('RGBA')
    box = img.getchannel('A').getbbox()
    if box:
        img = img.crop(box)
    img.thumbnail((256, 256), Image.LANCZOS)
    canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((256 - img.width) // 2, (256 - img.height) // 2))
    buf = io.BytesIO()
    canvas.save(buf, 'PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def model_meta(path):
    gltf, _ = read_glb(path)
    external = [img for img in gltf.get('images', []) if img.get('uri') and not img['uri'].startswith('data:')]
    if external:
        sys.exit('The model still points at texture files; run "pack" first so it is self-contained.')
    size = Path(path).stat().st_size
    if size > MAX_MODEL:
        # Pack its numbers (KHR_mesh_quantization: about a third smaller, same look;
        # three.js and our own tools read it) before giving up on the size.
        from detailed import shrink
        packed = Path(tempfile.mkdtemp(dir=os.environ.get('TMPDIR'))) / 'packed.glb'
        with open(os.devnull, 'w') as quiet:
            stdout, sys.stdout = sys.stdout, quiet
            try:
                shrink(path, packed)
            finally:
                sys.stdout = stdout
        if packed.exists() and packed.stat().st_size < size:
            shutil.copy(packed, path)
            size = packed.stat().st_size
    if size > MAX_MODEL:
        sys.exit(f'The model is {size // 1024} KB; keep it under {MAX_MODEL // 1024} KB.')
    return [a.get('name') for a in gltf.get('animations', []) if a.get('name')], size


def flat_thumb(glb, out, size=384):
    """A plain three-quarter view drawn with Pillow: used where no browser can
    render (a project guest's workspace). Faces are flat-shaded and painted
    back to front."""
    import numpy as np
    import trimesh
    from PIL import Image, ImageDraw
    loaded = trimesh.load(glb, force='scene')
    parts = loaded.dump() if hasattr(loaded, 'dump') else [loaded]
    verts, faces, colors, offset = [], [], [], 0
    for mesh in parts:
        if not hasattr(mesh, 'faces') or not len(mesh.faces):
            continue
        color = (180, 180, 180)
        material = getattr(getattr(mesh, 'visual', None), 'material', None)
        factor = getattr(material, 'baseColorFactor', None)
        if factor is not None:
            factor = np.asarray(factor, float)[:3]
            # glTF colours are linear: brighten them for display (sRGB).
            linear = factor / 255 if factor.max() > 1 else factor
            color = tuple(int(c) for c in np.clip(linear, 0, 1) ** (1 / 2.2) * 255)
        verts.append(np.asarray(mesh.vertices, float))
        faces.append(np.asarray(mesh.faces) + offset)
        colors += [color] * len(mesh.faces)
        offset += len(mesh.vertices)
    if not faces:
        sys.exit('The model has no faces to draw.')
    verts, faces, colors = np.vstack(verts), np.vstack(faces), np.asarray(colors)
    yaw, pitch = np.radians(35), np.radians(22)
    ry = np.array([[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
    rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
    p = (verts - verts.mean(0)) @ ry.T @ rx.T
    span = max(np.ptp(p[:, 0]), np.ptp(p[:, 1]), 1e-6)
    xy = (p[:, :2] / span * 0.85 + 0.5) * size
    xy[:, 1] = size - xy[:, 1]
    tri = p[faces]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-9
    light = np.clip(normals @ np.array([0.4, 0.6, 0.7]), 0, 1) * 0.65 + 0.35
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i in np.argsort(tri[:, :, 2].mean(1)):
        if normals[i, 2] < 0:
            continue
        shade = tuple(int(c * light[i]) for c in colors[i]) + (255,)
        draw.polygon([tuple(pt) for pt in xy[faces[i]]], fill=shade)
    img.save(out)
    return str(out)


def ensure_thumb(glb, thumb):
    if thumb:
        return thumb
    out = Path(tempfile.mkdtemp(dir=os.environ.get('TMPDIR'))) / 'thumb.png'
    if not shutil.which('agent-browser'):
        return flat_thumb(glb, out)
    with open(os.devnull, 'w') as quiet:
        stdout, sys.stdout = sys.stdout, quiet
        try:
            render(glb, out)
        finally:
            sys.stdout = stdout
    return str(out)


def get_blob(app_id, path):
    data = api('GET', f'/api/storage/apps/{app_id}/{path}')
    if not data:
        sys.exit(f'{path} is not in the studio.')
    return data


def put_blob(app_id, path, blob, ctype='model/gltf-binary'):
    api('PUT', f'/api/storage/apps/{app_id}/{path}', blob, ctype)


def draft3d(a):
    a.glb = godot_ready(a.glb)
    if not a.job or not re.fullmatch(r'[a-z0-9]{4,40}', a.job):
        sys.exit('draft needs --job ID (the job id given in the request).')
    anims, size = model_meta(a.glb)
    put_blob(a.app_id, f'character-drafts/{a.job}.glb', Path(a.glb).read_bytes())
    record = {'id': a.job, 'name': a.name, 'kind': '3d', 'dataUrl': thumb_data_url(ensure_thumb(a.glb, a.thumb)),
              'model': f'character-drafts/{a.job}.glb', 'animations': anims, 'bytes': size,
              'source': a.source or 'kenney', 'prompt': (a.prompt or '')[:400], 'credit': a.credit or '',
              'spec': json.loads(Path(a.spec).read_text()) if a.spec else None, 'style': a.style or '', 'body': a.body or 'humanoid',
              'height': a.height, 'role': a.role, 'held': [h for h in (a.held or '').split(',') if h]}
    storage_put_json(a.app_id, f'character-drafts/{a.job}.json', record)
    kick_queue(a.app_id)
    print(json.dumps({'ok': True, 'saved': 'draft', 'name': a.name, 'animations': anims, 'bytes': size}))


ROLES = ('hero', 'enemy', 'miniboss', 'boss', 'friend', 'creature', 'vehicle')
BODIES = ('humanoid', 'fourlegs', 'wings', 'any')


def kick_queue(app_id):
    """Let the studio's server-side queue (design_queue.py) react now, not at its next minute."""
    try:
        from build_art import api
        api('POST', f'/api/apps/{app_id}/run-job', b'{}')
    except BaseException:  # the scheduled run picks it up within a minute anyway
        pass


def plan(a):
    """A request for several characters: save the cast; the studio makes one card per character."""
    if not a.job or not re.fullmatch(r'[a-z0-9]{4,40}', a.job):
        sys.exit('plan needs --job ID (the job id given in the request).')
    items = json.loads(Path(a.args[1]).read_text())
    if isinstance(items, dict):
        items = items.get('characters') or items.get('items') or []
    if not isinstance(items, list) or not 1 <= len(items) <= 12:
        sys.exit('The plan must be a JSON list of 1 to 12 characters.')
    clean, seen = [], set()
    for i, it in enumerate(items):
        name = re.sub(r'[^a-z0-9_-]+', '-', str(it.get('name', '')).lower()).strip('-')[:32]
        desc = ' '.join(str(it.get('description', '')).split())[:400]
        if not name or not desc:
            sys.exit(f'Character {i + 1} needs a "name" and a "description".')
        if name in seen:
            sys.exit(f'Two characters are both named "{name}".')
        seen.add(name)
        body = it.get('body', 'humanoid')
        role = it.get('role')
        if body not in BODIES:
            sys.exit(f'{name}: "body" must be one of {", ".join(BODIES)}.')
        if role is not None and role not in ROLES:
            sys.exit(f'{name}: "role" must be one of {", ".join(ROLES)}.')
        try:
            height = float(it.get('height', 1.8))
        except (TypeError, ValueError):
            sys.exit(f'{name}: "height" must be a number of metres.')
        build = it.get('build')
        if build is not None and build not in ('slim', 'average', 'heavy', 'huge', 'small', 'lanky'):
            sys.exit(f'{name}: "build" must be slim, average, heavy, huge, small or lanky.')
        weapon = ' '.join(str(it.get('weapon') or '').split())[:300] or None
        clean.append({'name': name, 'description': desc, 'body': body, 'height': max(0.2, min(30.0, height)), 'role': role, 'build': build, 'weapon': weapon})
    storage_put_json(a.app_id, f'character-plans/{a.job}.json', {'job': a.job, 'title': (a.prompt or '')[:120], 'characters': clean})
    kick_queue(a.app_id)
    print(json.dumps({'ok': True, 'planned': [c['name'] for c in clean],
                      'next': 'Done: the studio now makes each one as its own design card. Reply with one friendly sentence listing them; do not make any yourself.'}))


def save3d(a):
    anims, size = model_meta(a.glb)
    assets = storage_get(a.app_id, 'assets.json') or {}
    old = (assets.get('characters') or {}).get(a.name)
    if not old or old.get('kind') != '3d':
        sys.exit(f'There is no 3D character "{a.name}" in the gallery.')
    put_blob(a.app_id, f'models/{a.name}.glb', Path(a.glb).read_bytes())
    if a.spec:
        storage_put_json(a.app_id, f'character-src/{a.name}.json', json.loads(Path(a.spec).read_text()))
    assets['characters'][a.name] = {**old, 'animations': anims, 'bytes': size, 'thumb': thumb_data_url(ensure_thumb(a.glb, a.thumb)),
                                    'dataUrl': None, 'updatedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    assets['characters'][a.name]['dataUrl'] = assets['characters'][a.name]['thumb']
    assets['models'] = {**(assets.get('models') or {}), a.name: {'title': a.name, 'credit': old.get('credit') or 'Your character', 'size': size}}
    storage_put_json(a.app_id, 'assets.json', assets)
    print(json.dumps({'ok': True, 'saved': '3d', 'name': a.name, 'animations': anims, 'bytes': size}))


def texture(src, out):
    gltf, binary = read_glb(src)
    for img in gltf.get('images', []):
        if 'bufferView' in img:
            Path(out).write_bytes(view_bytes(gltf, binary, img['bufferView']))
            print(json.dumps({'ok': True, 'out': str(out), 'next': 'Edit it (e.g. recolour with Pillow), then: pack IN.glb OUT.glb --texture EDITED.png'}))
            return
    sys.exit('This model has no embedded texture (its colours are material colours).')


def add_moves(a):
    """Library moves onto a gallery character: fetch its model, retarget the clips, save it."""
    assets = storage_get(a.app_id, 'assets.json') or {}
    old = (assets.get('characters') or {}).get(a.name)
    if not old or old.get('kind') != '3d':
        sys.exit(f'There is no 3D character "{a.name}" in the gallery.')
    have = set(old.get('animations') or [])
    pairs = [p.strip() for p in a.spec_moves.split(',') if p.strip()]
    wanted = [p for p in pairs if (p.split('=', 1)[1] if '=' in p else p) not in have]
    if not wanted:
        print(json.dumps({'ok': True, 'name': a.name, 'added': [], 'note': 'it already has those moves'}))
        return
    work = Path(tempfile.mkdtemp(prefix='moves-', dir=os.environ.get('TMPDIR')))
    src, out = work / 'in.glb', work / 'out.glb'
    src.write_bytes(get_blob(a.app_id, f'models/{a.name}.glb'))
    add_anims(str(src), str(out), ','.join(wanted))
    a.glb = str(out)
    a.thumb = None
    a.spec = None
    save3d(a)


GODOT_UNSUPPORTED = ('KHR_mesh_quantization', 'EXT_meshopt_compression', 'KHR_draco_mesh_compression')


def godot_ready(glb):
    """Godot cannot read quantized or meshopt-compressed glTF (gltfpack output): re-save such a
    model as a plain GLB through Blender, which reads them. Returns the path to use."""
    g, _ = read_glb(glb)
    if not set(g.get('extensionsRequired') or []) & set(GODOT_UNSUPPORTED):
        return glb
    from blender_char import blender_bin
    out = str(Path(glb).with_suffix('')) + '.plain.glb'
    script = Path(tempfile.mkdtemp()) / 'plain.py'
    script.write_text("import bpy,sys\nbpy.ops.wm.read_factory_settings(use_empty=True)\n"
                      "a=sys.argv[sys.argv.index('--')+1:]\nbpy.ops.import_scene.gltf(filepath=a[0])\n"
                      "bpy.ops.export_scene.gltf(filepath=a[1], export_format='GLB', export_image_format='JPEG', export_image_quality=88)\n")
    subprocess.run([blender_bin(), '-b', '--factory-startup', '--python', str(script), '--', glb, out],
                   capture_output=True, timeout=600)
    if not Path(out).exists():
        sys.exit(f'{glb} uses {GODOT_UNSUPPORTED} compression, which Godot games cannot read, and could not be converted.')
    print(f'(converted a compressed glTF to a plain one so Godot games can load it)', file=sys.stderr)
    return out


def keep3d(a):
    a.glb = godot_ready(a.glb)
    """Save a finished 3D character into the Characters tab, exactly as Keep does for a draft."""
    assets = storage_get(a.app_id, 'assets.json') or {}
    chars = assets.get('characters') or {}
    name, n = a.name, 2
    while name in chars:
        name, n = f'{a.name}-{n}', n + 1
    anims, size = model_meta(a.glb)
    put_blob(a.app_id, f'models/{name}.glb', Path(a.glb).read_bytes())
    if a.spec:
        storage_put_json(a.app_id, f'character-src/{name}.json', json.loads(Path(a.spec).read_text()))
    thumb = thumb_data_url(ensure_thumb(a.glb, a.thumb))
    assets = storage_get(a.app_id, 'assets.json') or {}  # re-read just before writing
    assets['models'] = {**(assets.get('models') or {}), name: {
        'title': name, 'credit': a.credit or 'Your character', 'size': size, 'animations': anims}}
    assets['characters'] = {**(assets.get('characters') or {}), name: {
        'kind': '3d', 'body': a.body or 'humanoid', 'height': a.height, 'source': a.source or 'made',
        'credit': a.credit or '', 'role': a.role, 'held': [h for h in (a.held or '').split(',') if h], 'type': '',
        'prompt': (a.prompt or '')[:400], 'style': a.style or '', 'thumb': thumb, 'dataUrl': thumb,
        'animations': anims, 'bytes': size, 'createdAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}}
    storage_put_json(a.app_id, 'assets.json', assets)
    print(json.dumps({'ok': True, 'saved': 'character', 'name': name, 'animations': anims, 'bytes': size}))


def save_asset(a):
    a.glb = godot_ready(a.glb)
    anims, size = model_meta(a.glb)
    put_blob(a.app_id, f'models/{a.name}.glb', Path(a.glb).read_bytes())
    assets = storage_get(a.app_id, 'assets.json') or {}
    assets['models'] = {**(assets.get('models') or {}), a.name: {
        'title': a.name, 'credit': a.credit or 'Made in Game Studio', 'size': size, 'animations': anims,
        'thumb': thumb_data_url(ensure_thumb(a.glb, a.thumb)), 'prompt': (a.prompt or '')[:400]}}
    storage_put_json(a.app_id, 'assets.json', assets)
    print(json.dumps({'ok': True, 'saved': 'model', 'name': a.name, 'bytes': size, 'animations': anims}))


# ---------- Quaternius Universal Animation Library (CC0) ----------
LIBS = Path.home() / '.cache' / 'game-studio' / 'libs'
UAL = {
    'ual1': ('https://opengameart.org/sites/default/files/universal_animation_librarystandard.zip', '**/Godot/*.glb'),
    'ual2': ('https://opengameart.org/sites/default/files/universal_animation_library_2standard.zip', '**/Unreal-Godot/UAL2_Standard.glb'),
}
RETARGET = Path(__file__).resolve().parent / 'retarget.mjs'


def ual_files():
    import io
    import zipfile
    found = {}
    for key, (url, pattern) in UAL.items():
        folder = LIBS / key
        done = folder / '.complete'  # an interrupted download leaves the folder without it: fetch again
        if not done.exists():
            folder.mkdir(parents=True, exist_ok=True)
            # curl, not urllib: OpenGameArt can trickle a plain Python download for many minutes.
            res = subprocess.run(['curl', '-fsSL', '-A', 'Mozilla/5.0', '--max-time', '300', '--retry', '2', url], capture_output=True, timeout=700)
            if res.returncode != 0:
                sys.exit(f'Could not download the animation library ({url}): {res.stderr.decode(errors="replace").strip()[:200]}')
            zipfile.ZipFile(io.BytesIO(res.stdout)).extractall(folder)
            done.write_text('ok')
        hits = sorted(folder.glob(pattern))
        if hits:
            found[key] = hits[0]
    return found


def clip_table():
    table = {}
    for key, path in ual_files().items():
        gltf, _ = read_glb(path)
        for anim in gltf.get('animations', []):
            secs = max((gltf['accessors'][smp['input']].get('max') or [0])[0] for smp in anim['samplers'])
            table.setdefault(anim['name'], (key, path, round(secs, 2)))
    return table


def library():
    table = clip_table()
    print(json.dumps({'clips': {name: secs for name, (_, _, secs) in sorted(table.items())},
                      'note': '89 free CC0 humanoid animations (Quaternius Universal Animation Library 1+2). _Loop clips loop; _RM clips move the root. Add them with: add-anims IN.glb OUT.glb "Walk_Loop=walk,Sword_Attack=attack"'}, indent=1))


def add_anims(src, out, spec):
    table = clip_table()
    groups = {}
    for pair in spec.split(','):
        clip = pair.split('=')[0].strip()
        if clip not in table:
            close = [n for n in table if clip.lower().replace('_', '') in n.lower().replace('_', '')][:8]
            sys.exit(f'No clip named "{clip}". Close matches: {", ".join(close) or "none"} (run: model_tool.py library).')
        groups.setdefault(table[clip][1], []).append(pair.strip())
    current = src
    results = []
    for path, pairs in groups.items():
        proc = subprocess.run(['node', str(RETARGET), str(current), str(path), str(out), ','.join(pairs)], capture_output=True, text=True, timeout=600)
        if proc.returncode:
            sys.exit('Retargeting failed: ' + (proc.stderr or proc.stdout)[-800:])
        results.extend(json.loads(proc.stdout).get('added', []))
        current = out
    print(json.dumps({'ok': True, 'out': str(out), 'added': results, 'next': 'render OUT.glb check.png --anim NAME and Read it.'}))


def compact(gltf, binary):
    """Drop buffer data nothing references any more (after removing clips)."""
    used = set()
    for m in gltf.get('meshes', []):
        for p in m['primitives']:
            used.update(p['attributes'].values())
            if 'indices' in p:
                used.add(p['indices'])
            for t in p.get('targets', []):
                used.update(t.values())
    for sk in gltf.get('skins', []):
        if 'inverseBindMatrices' in sk:
            used.add(sk['inverseBindMatrices'])
    for a in gltf.get('animations', []):
        for smp in a['samplers']:
            used.update((smp['input'], smp['output']))
    views, acc_map, new_acc, chunks, length = {}, {}, [], [], 0
    new_views = []

    def keep(vi):
        nonlocal length
        if vi not in views:
            v = gltf['bufferViews'][vi]
            data = bytes(binary[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']])
            pad = (4 - length % 4) % 4
            if pad:
                chunks.append(b'\0' * pad)
                length += pad
            nv = {k: val for k, val in v.items() if k != 'byteOffset'}
            nv['byteOffset'] = length
            chunks.append(data)
            length += len(data)
            new_views.append(nv)
            views[vi] = len(new_views) - 1
        return views[vi]
    for i in sorted(used):
        acc = dict(gltf['accessors'][i])
        if 'bufferView' in acc:
            acc['bufferView'] = keep(acc['bufferView'])
        acc_map[i] = len(new_acc)
        new_acc.append(acc)
    for img in gltf.get('images', []):
        if 'bufferView' in img:
            img['bufferView'] = keep(img['bufferView'])
    for m in gltf.get('meshes', []):
        for p in m['primitives']:
            p['attributes'] = {k: acc_map[v] for k, v in p['attributes'].items()}
            if 'indices' in p:
                p['indices'] = acc_map[p['indices']]
            if 'targets' in p:
                p['targets'] = [{k: acc_map[v] for k, v in t.items()} for t in p['targets']]
    for sk in gltf.get('skins', []):
        if 'inverseBindMatrices' in sk:
            sk['inverseBindMatrices'] = acc_map[sk['inverseBindMatrices']]
    for a in gltf.get('animations', []):
        for smp in a['samplers']:
            smp['input'], smp['output'] = acc_map[smp['input']], acc_map[smp['output']]
    gltf['accessors'], gltf['bufferViews'] = new_acc, new_views
    return bytearray(b''.join(chunks))


def recolor(src, out, spec):
    """Repaint materials by name: "Skin=#e0b08c,Clothes=#2d3f66" (a name fragment works; "*" = all)."""
    gltf, binary = read_glb(src)
    done = []
    for pair in [x.strip() for x in spec.split(',') if x.strip()]:
        key, _, hexv = pair.partition('=')
        h = hexv.lstrip('#')
        rgb = [((int(h[i:i + 2], 16) / 255) ** 2.2) for i in (0, 2, 4)]  # sRGB hex -> linear
        for m in gltf.get('materials', []):
            if key == '*' or key.lower() in (m.get('name') or '').lower():
                m.setdefault('pbrMetallicRoughness', {})['baseColorFactor'] = rgb + [1]
                done.append(m.get('name'))
    if not done:
        sys.exit('No material matched. Materials: ' + ', '.join(m.get('name', '?') for m in gltf.get('materials', [])))
    write_glb(out, gltf, binary)
    print(json.dumps({'ok': True, 'out': str(out), 'recoloured': done,
                      'note': 'Textured materials multiply this colour with their texture; for those, edit the texture instead.'}))



def _hand_vertices(g, b, skin, ji, rest_true, ibm):
    """World positions (bind pose) of the skinned vertices that mostly follow this hand bone or
    its finger bones: the hand as it is actually modelled."""
    import numpy as np
    joints = skin['joints']
    kids = {n: g['nodes'][n].get('children', []) for n in joints}
    group, todo = set(), [joints[ji]]
    while todo:
        n = todo.pop()
        if n in group:
            continue
        group.add(n)
        todo += [c for c in kids.get(n, []) if c in kids]
    wanted = {i for i, n in enumerate(joints) if n in group}
    node = next((k for k, nd in enumerate(g['nodes']) if nd.get('skin') == 0 and 'mesh' in nd), None)
    if node is None:
        return None

    def read(a, n):
        A = g['accessors'][a]
        dt = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5122: '<i2', 5121: 'u1', 5120: 'i1'}[A['componentType']]
        view = g['bufferViews'][A['bufferView']]
        stride = view.get('byteStride') or np.dtype(dt).itemsize * n
        raw = view_bytes(g, b, A['bufferView'])
        v = np.lib.stride_tricks.as_strided(np.frombuffer(raw, dt, offset=A.get('byteOffset', 0)),
                                            shape=(A['count'], n), strides=(stride, np.dtype(dt).itemsize)).astype('f8')
        if A.get('normalized'):
            v = v / {'<u2': 65535.0, 'u1': 255.0, '<i2': 32767.0, 'i1': 127.0}.get(dt, 1.0)
        return v
    out = []
    for p in g['meshes'][g['nodes'][node]['mesh']]['primitives']:
        at = p['attributes']
        if 'JOINTS_0' not in at or 'WEIGHTS_0' not in at:
            continue
        P, J, W = read(at['POSITION'], 3), read(at['JOINTS_0'], 4).astype(int), read(at['WEIGHTS_0'], 4)
        dom = J[np.arange(len(J)), W.argmax(1)]
        sel = np.where(np.isin(dom, list(wanted)))[0]
        for k in sel:                  # where each vertex sits in the scene: its bone's rest x inverse bind
            d = dom[k]
            out.append((rest_true[d] @ ibm[d].T @ np.r_[P[k], 1.0])[:3])
    return np.array(out) if out else None


def _quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]


def _axis_quat(axis, angle):
    import numpy as np
    s = np.sin(angle / 2)
    return [float(axis[0] * s), float(axis[1] * s), float(axis[2] * s), float(np.cos(angle / 2))]


FIST = {'index': (70, 90, 60), 'middle': (75, 90, 60), 'ring': (80, 90, 60), 'pinky': (85, 90, 60), 'thumb': (25, 35, 25)}


def fists(gltf, side='both', amount=1.0):
    """Close a character's hands into fists by curling its finger bones toward the palm.
    Moves never animate finger bones, so the fist holds in every animation. Characters
    without finger bones (KayKit, Quaternius: mitten or fist hands) are left as they are.
    Returns the number of finger joints curled."""
    import numpy as np
    nodes = gltf['nodes']
    animated = {c['target']['node'] for a in gltf.get('animations', []) for c in a['channels']}
    is_left = lambda n: n.endswith(('.L', '_L', '.l', '_l', 'Left')) or 'left' in n.lower()
    is_right = lambda n: n.endswith(('.R', '_R', '.r', '_r', 'Right')) or 'right' in n.lower()
    unit = lambda v: v / max(np.linalg.norm(v), 1e-9)
    curled = 0
    for hand_side, ok in (('left', is_left), ('right', is_right)):
        if side not in ('both', hand_side):
            continue
        def chain(word):
            found = []
            for k in ('1', '2', '3'):
                i = next((i for i, n in enumerate(nodes) if word in n.get('name', '').lower() and ok(n.get('name', ''))
                          and any(t in n['name'] for t in (f'0{k}', f'.{k}', f'_{k}')) and 'mesh' not in n), None)
                found.append(i)
            return found
        chains = {w: chain(w) for w in FIST}
        if chains['index'][0] is None or chains['pinky'][0] is None:
            continue
        pos = lambda i: _node_world(gltf, i)[:3, 3]
        across = unit(pos(chains['index'][0]) - pos(chains['pinky'][0]))          # knuckle line (thumb side)
        wrist = next((i for i, n in enumerate(nodes) for c in n.get('children', []) if c == chains['middle'][0]), None)
        along = unit(pos(chains['middle'][0]) - pos(wrist)) if wrist is not None and chains['middle'][0] is not None else None
        if along is None:
            continue
        palm = np.cross(along, across) * (1 if hand_side == 'left' else -1)          # the way the palm faces
        for word, angles in FIST.items():
            for joint, deg in zip(chains[word], angles):
                if joint is None or joint in animated or (nodes[joint].get('extras') or {}).get('fist'):
                    continue                                    # animated, or already closed
                W = _node_world(gltf, joint)
                child = next(iter(nodes[joint].get('children', [])), None)
                tip = unit((pos(child) if child is not None else W[:3, 3] + along) - W[:3, 3])
                axis = across if word != 'thumb' else unit(np.cross(tip, palm))
                ang = np.radians(deg) * amount
                # Pick the direction that swings the finger toward the palm.
                R = lambda a: np.array(_node_world({'nodes': [{'rotation': _axis_quat(axis, a)}]}, 0))[:3, :3]
                if np.dot(R(ang) @ tip - tip, palm) < 0:
                    ang = -ang
                # World rotation about the joint -> the same turn in the bone's own frame.
                rot = W[:3, :3] / np.linalg.norm(W[:3, :3], axis=0)
                local_axis = unit(rot.T @ axis)
                q = nodes[joint].get('rotation', [0, 0, 0, 1])
                nodes[joint]['rotation'] = _quat_mul(q, _axis_quat(local_axis, ang))
                nodes[joint].setdefault('extras', {})['fist'] = True
                curled += 1
    return curled


def fists_file(src, out, side='both', amount=1.0):
    g, b = read_glb(src)
    n = fists(g, side, amount)
    write_glb(out, g, b)
    print(json.dumps({'ok': True, 'out': str(out), 'finger_joints_curled': n,
                      'next': 'Render it and Read it: the fingers should wrap into a fist.' if n else
                              'This character has no finger bones (mitten or fist hands); nothing to change.'}))

def _node_world(gltf, index):
    """World matrix of one node in a (static) glTF scene."""
    import numpy as np
    parent = {c: i for i, n in enumerate(gltf.get('nodes', [])) for c in n.get('children', [])}

    def local(n):
        if 'matrix' in n:
            return np.array(n['matrix'], 'f8').reshape(4, 4).T
        t = np.eye(4)
        t[:3, 3] = n.get('translation', [0, 0, 0])
        x, y, z, w = n.get('rotation', [0, 0, 0, 1])
        r = np.eye(4)
        r[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
        s = np.diag(list(n.get('scale', [1, 1, 1])) + [1])
        return t @ r @ s
    m = np.eye(4)
    while index is not None:
        m = local(gltf['nodes'][index]) @ m
        index = parent.get(index)
    return m


FIST_THROUGH = (0.0, 1.0, 0.0)   # thumb side of a lone fist bone in the rest pose


def equip(char, item, out, bone=None, palm=0.08):
    """Put a held item (weapon.glb from detailed.py weapon: grip at its origin, blade/head
    along +Y) in a character's hand. It becomes part of that bone, so every animation
    swings it. Holding the same bone again replaces what it held."""
    import numpy as np
    g, b = read_glb(char)
    w, wb = read_glb(item)
    skin = (g.get('skins') or [None])[0]
    if not skin:
        sys.exit('The character has no skeleton; rig it first.')
    names = [g['nodes'][j].get('name', '') for j in skin['joints']]
    left_name = lambda n: n.endswith(('.L', '_L', '.l', '_l', 'Left')) or 'left' in n.lower() or n.lower().startswith(('l_', 'left'))
    right_name = lambda n: n.endswith(('.R', '_R', '.r', '_r', 'Right')) or 'right' in n.lower() or n.lower().startswith(('r_', 'right'))
    helper = ('ik', 'control', 'pole', 'target', 'finger', 'thumb', 'index', 'pinky', 'middle', 'ring', 'f_')
    if bone:
        pick = [i for i, n in enumerate(names) if n == bone] or [i for i, n in enumerate(names) if bone.lower() in n.lower()]
        side_ok = left_name if pick and left_name(names[pick[0]]) else right_name
    else:
        side_ok = right_name
        # The hand bone itself: never an IK or control helper that merely has "hand" in its name.
        pick = [i for i, n in enumerate(names) if ('hand' in n.lower() or 'fist' in n.lower()) and 'slot' not in n.lower()
                and side_ok(n) and not any(h in n.lower() for h in helper)]
    if not pick:
        sys.exit(f'No bone named like "{bone or "right hand"}". Bones: {", ".join(names)}')
    ji = pick[0]
    acc = g['accessors'][skin['inverseBindMatrices']]
    ibm = np.frombuffer(view_bytes(g, b, acc['bufferView']), '<f4', count=16 * len(names), offset=acc.get('byteOffset', 0)).reshape(-1, 4, 4)
    # Bind pose in world space: the inverse bind matrices are relative to the skinned mesh's
    # node, which some exporters scale (e.g. centimetres); without it, gear comes out tiny.
    # Rest pose from the bones' own nodes (world space). This is right even when the skin's bind
    # space differs from the scene (scaled rigs, compressed files).
    rest_true = {i: _node_world(g, skin['joints'][i]) for i in range(len(names))}
    rest = {i: m.copy() for i, m in rest_true.items()}
    for i in rest:                     # keep rotations pure (drop the unit scale) for building frames
        sc = np.linalg.norm(rest[i][:3, :3], axis=0)
        rest[i][:3, :3] = rest[i][:3, :3] / np.where(sc > 0, sc, 1)
    pos = lambda i: rest[i][:3, 3]
    unit = lambda v: v / max(np.linalg.norm(v), 1e-9)

    def finger(word):
        hits = [i for i, n in enumerate(names) if word in n.lower() and side_ok(n) and any(t in n for t in ('01', '.1', '_1', '1.'))]
        return hits[0] if hits else None
    slot = next((i for i, n in enumerate(names) if 'slot' in n.lower() and side_ok(n)), None)
    index, pinky, middle = finger('index'), finger('pinky'), finger('middle')
    W = np.eye(4)
    if slot is not None:
        # KayKit-style hand slot: made for held items. Its own weapons sit with the handle along
        # the slot's +Y, the blade's edge along +X and the grip at its origin; do the same.
        ji = slot
        W[:3, :3] = rest[slot][:3, :3] @ np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)
        W[:3, 3] = pos(slot)
    elif index is not None and pinky is not None:
        # Read the grip from the hand: the handle passes through the fist toward the thumb side
        # (from the pinky knuckle to the index knuckle), the edge faces along the hand, and the
        # grip sits inside the curled fingers, just past the knuckles on the palm side.
        knuckle = pos(middle) if middle is not None else (pos(index) + pos(pinky)) / 2
        along = unit(knuckle - pos(ji))
        through = pos(index) - pos(pinky)
        through = unit(through - along * through.dot(along))
        palm_side = np.cross(along, through) * (1 if side_ok is left_name else -1)
        span, length = np.linalg.norm(pos(index) - pos(pinky)), np.linalg.norm(knuckle - pos(ji))
        W[:3, 0], W[:3, 1], W[:3, 2] = np.cross(through, along), through, along
        W[:3, 3] = knuckle + along * 0.25 * length + palm_side * 0.45 * span
    else:
        # No fingers or slot (a single fist bone): the same grip as above, with the handle
        # through the fist along FIST_THROUGH (the thumb side in the rest pose).
        jnode = skin['joints'][ji]
        parent = next((i for i, j in enumerate(skin['joints']) if jnode in g['nodes'][j].get('children', [])), None)
        along = unit(pos(ji) - pos(parent)) if parent is not None else np.array([-1.0, 0, 0])
        through = np.array(FIST_THROUGH, float)
        through = unit(through - along * through.dot(along))
        W[:3, 0], W[:3, 1], W[:3, 2] = np.cross(through, along), through, along
        W[:3, 3] = pos(ji) + along * palm
    jnode = skin['joints'][ji]
    # Grip where the hand really is. A skeleton fitted to an AI-made body can sit off the mesh
    # (e.g. knuckle bones beyond a compact, mitten-like hand), and the item would float in front
    # of the fist. If the bone-based grip is outside the mesh hand, use the hand's centre instead.
    if slot is None:
        hand_mesh = _hand_vertices(g, b, skin, ji, rest_true, ibm)
        if hand_mesh is not None and len(hand_mesh) >= 20:
            centre = hand_mesh.mean(0)
            reach = np.linalg.norm(hand_mesh - centre, axis=1)
            if np.linalg.norm(W[:3, 3] - centre) > max(np.percentile(reach, 60), 1e-4):
                W[:3, 3] = centre
    # Every piece of the item (a handle, a head, a band...), each kept where it sits.
    mesh_nodes = [i for i, n in enumerate(w['nodes']) if 'mesh' in n]
    if not mesh_nodes:
        sys.exit('The item has no mesh.')
    local = np.linalg.inv(rest_true[ji]) @ W    # relative to the bone as it really is (with any unit scale)
    # Merge the item's data into the character.
    off = {k: len(g.get(k, [])) for k in ('accessors', 'bufferViews', 'images', 'textures', 'samplers', 'materials', 'meshes')}
    while len(b) % 4:
        b.append(0)
    base = len(b)
    b.extend(wb)
    for v in w.get('bufferViews', []):
        g.setdefault('bufferViews', []).append({**v, 'buffer': 0, 'byteOffset': v.get('byteOffset', 0) + base})
    for a in w.get('accessors', []):
        g.setdefault('accessors', []).append({**a, 'bufferView': a['bufferView'] + off['bufferViews']} if 'bufferView' in a else dict(a))
    for im in w.get('images', []):
        g.setdefault('images', []).append({**im, 'bufferView': im['bufferView'] + off['bufferViews']} if 'bufferView' in im else dict(im))
    for s in w.get('samplers', []):
        g.setdefault('samplers', []).append(dict(s))
    for t in w.get('textures', []):
        nt = dict(t)
        if 'source' in nt:
            nt['source'] += off['images']
        if 'sampler' in nt:
            nt['sampler'] += off['samplers']
        g.setdefault('textures', []).append(nt)

    def retex(o):
        if isinstance(o, dict):
            return {k: (v + off['textures'] if k == 'index' and isinstance(v, int) else retex(v)) for k, v in o.items()}
        return o
    for m in w.get('materials', []):
        g.setdefault('materials', []).append(retex(m))
    for m in w.get('meshes', []):
        prims = []
        for p in m['primitives']:
            q = {**p, 'attributes': {k: v + off['accessors'] for k, v in p['attributes'].items()}}
            if 'indices' in p:
                q['indices'] = p['indices'] + off['accessors']
            if 'material' in p:
                q['material'] = p['material'] + off['materials']
            prims.append(q)
        g.setdefault('meshes', []).append({**m, 'primitives': prims})
    for ext in w.get('extensionsUsed', []):
        g.setdefault('extensionsUsed', [])
        if ext not in g['extensionsUsed']:
            g['extensionsUsed'].append(ext)
    for ext in w.get('extensionsRequired', []):
        g.setdefault('extensionsRequired', [])
        if ext not in g['extensionsRequired']:
            g['extensionsRequired'].append(ext)
    # One held item per hand: drop what any bone of this hand (hand, fist, slot, wrist) held before,
    # so re-equipping never leaves the old item behind on a neighbouring bone.
    handish = ('hand', 'fist', 'slot', 'wrist')
    for jn, nm in zip(skin['joints'], names):
        if jn == jnode or (side_ok(nm) and any(h in nm.lower() for h in handish)):
            kids = g['nodes'][jn].get('children', [])
            g['nodes'][jn]['children'] = [c for c in kids if not str(g['nodes'][c].get('name', '')).startswith('held:')]
    pieces = []
    for i in mesh_nodes:
        g['nodes'].append({'name': w['nodes'][i].get('name') or f'piece{i}', 'mesh': off['meshes'] + w['nodes'][i]['mesh'],
                           'matrix': [float(x) for x in _node_world(w, i).T.reshape(-1)]})
        pieces.append(len(g['nodes']) - 1)
    g['nodes'].append({'name': f'held:{Path(item).stem}', 'children': pieces,
                       'matrix': [float(x) for x in local.T.reshape(-1)]})
    g['nodes'][jnode].setdefault('children', []).append(len(g['nodes']) - 1)
    fists(g, 'left' if side_ok is left_name else 'right')      # the holding hand grips (no-op without finger bones)
    size = write_glb(out, g, b)
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': size, 'bone': names[ji],
                      'next': 'Render it with --anim attack and Read it: the blade should come out of the fist and swing with the arm.'}))


def keep_anims(src, out, spec):
    """Keep only the listed clips ("Idle" or "Walking_A=walk"), renamed, and shrink the file."""
    gltf, binary = read_glb(src)
    have = {a.get('name'): a for a in gltf.get('animations', [])}
    short = {re.sub(r'^.*\|', '', n or ''): n for n in have}
    kept, missing = [], []
    for pair in [x.strip() for x in spec.split(',') if x.strip()]:
        frm, _, to = pair.partition('=')
        name = frm if frm in have else short.get(frm)
        if not name:
            missing.append(frm)
            continue
        kept.append({**have[name], 'name': to or re.sub(r'^.*\|', '', name)})
    if missing:
        sys.exit(f'No clip(s) named {", ".join(missing)}. Clips: {", ".join(short)}')
    gltf['animations'] = kept
    size = write_glb(out, gltf, compact(gltf, binary))
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': size, 'animations': [a['name'] for a in kept]}))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['keep', 'info', 'fbx', 'pack', 'merge-anims', 'rename-anims', 'keep-anims', 'recolor', 'render', 'texture', 'draft', 'save', 'asset', 'library', 'add-anims', 'plan', 'equip', 'fists', 'moves'])
    p.add_argument('args', nargs='*')
    p.add_argument('--texture')
    p.add_argument('--anim', default='idle')
    p.add_argument('--size', type=int, default=512)
    p.add_argument('--job')
    p.add_argument('--glb')
    p.add_argument('--thumb')
    p.add_argument('--source')
    p.add_argument('--prompt')
    p.add_argument('--credit')
    p.add_argument('--spec', help='the build3d.mjs spec the model was built from, kept for later edits')
    p.add_argument('--style')
    p.add_argument('--held', help='draft: names of the weapon/item assets the character holds, comma separated')
    p.add_argument('--bone', help='equip: which bone holds it (default: the right hand; e.g. hand.L for the left)')
    p.add_argument('--body', choices=['humanoid', 'fourlegs', 'wings', 'any'], help='draft: the character\'s body (how its skeleton was made)')
    p.add_argument('--height', type=float, help='draft: how tall it should be in games, in metres (a person is 1.8)')
    p.add_argument('--role', choices=['hero', 'enemy', 'miniboss', 'boss', 'friend', 'creature', 'vehicle'], help='draft: its role in games')
    a = p.parse_args()
    need = {'keep': 2, 'recolor': 3, 'keep-anims': 3, 'library': 0, 'add-anims': 3, 'info': 1, 'fbx': 2, 'pack': 2, 'merge-anims': 3, 'rename-anims': 3, 'render': 2, 'texture': 2, 'draft': 2, 'save': 2, 'asset': 2, 'plan': 2, 'equip': 3, 'fists': 2, 'moves': 3}[a.action]
    if len(a.args) < need:
        sys.exit(f'{a.action} needs {need} arguments; see -h.')
    if a.action == 'library':
        library()
    elif a.action == 'add-anims':
        add_anims(a.args[0], a.args[1], a.args[2])
    elif a.action == 'recolor':
        recolor(a.args[0], a.args[1], a.args[2])
    elif a.action == 'keep-anims':
        keep_anims(a.args[0], a.args[1], a.args[2])
    elif a.action == 'info':
        info(a.args[0])
    elif a.action == 'fbx':
        fbx2glb(a.args[0], a.args[1])
    elif a.action == 'pack':
        pack(a.args[0], a.args[1], a.texture)
    elif a.action == 'merge-anims':
        merge_anims(a.args[0], a.args[1], a.args[2:])
    elif a.action == 'rename-anims':
        rename_anims(a.args[0], a.args[1], a.args[2:])
    elif a.action == 'render':
        render(a.args[0], a.args[1], a.anim, a.size)
    elif a.action == 'texture':
        texture(a.args[0], a.args[1])
    elif a.action == 'equip':
        equip(a.args[0], a.args[1], a.args[2], a.bone)
    elif a.action == 'fists':
        fists_file(a.args[0], a.args[1])
    elif a.action == 'moves':
        a.app_id, a.name, a.spec_moves = a.args[0], a.args[1], a.args[2]
        add_moves(a)
    elif a.action == 'plan':
        a.app_id = a.args[0]
        plan(a)
    else:
        a.app_id, a.name = a.args[0], a.args[1]
        if not a.glb:
            sys.exit('Give the model with --glb FILE.')
        {'draft': draft3d, 'save': save3d, 'asset': save_asset, 'keep': keep3d}[a.action](a)


if __name__ == '__main__':
    main()
