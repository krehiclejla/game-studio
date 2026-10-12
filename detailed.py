#!/usr/bin/env python3
"""Any character or object in 3D, made on this machine (CPU, no accounts, all free):

  python3 detailed.py concept "PROMPT" OUT.png [--object|--picture [--wide]] [--seed N]
      Draw a concept with DreamShaper 8 (SD 1.5) + LCM; characters get a T-pose guide.
  python3 detailed.py local3d PICTURE.png OUT.glb [--res 192]
      BiRefNet lite cut-out -> TripoSR (MIT) with a baked 1024px texture, the sharp picture
      painted back onto the front -> simplified, JPEG-textured GLB (~40 s).
  python3 detailed.py upright RAW.glb OUT.glb [HEIGHT]
      Objects: stand it up, sit it on the ground, pack it small (gltfpack).
  python3 detailed.py rig RAW.glb OUT.glb ["Idle_Loop=idle,Walk_Loop=walk,..."] [--flip]
      Fit the Quaternius animation skeleton (smooth 'bone heat' weights) and add clips.
  python3 detailed.py cutout PICTURE.png OUT.png
      Just the transparent cut-out.
"""
import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import tempfile
import urllib.request
from pathlib import Path

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import gs_deps  # noqa: E402,F401  (reinstalls basic packages after a container replacement)
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_tool import read_glb, write_glb, add_view, view_bytes, ual_files  # noqa: E402

GAMMA = 1.5  # TripoSR vertex colours: between raw (washed out) and full sRGB (too dark)
SMOOTH_HEAT = float(os.environ.get('GS_SMOOTH_HEAT', '1.0'))  # 0 = hard nearest-bone weights
# A three-hit combo (attack, attack2, attack3), a heavy finisher, a dash attack and a dodge.
# Every character starts with the basics; fighting moves are added only when asked
# (model_tool.py add-anims, e.g. COMBAT_ANIMS for a sword fighter).
DEFAULT_ANIMS = 'Idle_Loop=idle,Walk_Loop=walk,Sprint_Loop=run,Jump_Loop=jump,Hit_Chest=hurt,Death01=die'
COMBAT_ANIMS = ('Sword_Regular_A=attack,Sword_Regular_B=attack2,Sword_Regular_C=attack3,Sword_Attack=heavy,'
                'Sword_Dash_RM=dash-attack,Roll=dodge')


DRAW_NEEDS_GB = 3.5   # bfloat16 image model + pose guide + working memory, measured on CPU


def memory_free_gb():
    """Memory this container can still use for new work: its cap minus what running programs
    hold (the disk cache does not count, the kernel frees it on demand). None if uncapped."""
    try:
        cap = open('/sys/fs/cgroup/memory.max').read().strip()
        if cap == 'max':
            return None
        stat = dict(l.split() for l in open('/sys/fs/cgroup/memory.stat'))
        return (int(cap) - int(stat.get('anon', 0))) / 2**30
    except Exception:
        return None


def check_memory_for_drawing():
    """Refuse to draw when it would not fit: running out of memory takes the whole Möbius
    container down, not just this step."""
    free = memory_free_gb()
    if free is not None and free < DRAW_NEEDS_GB:
        print(json.dumps({'ok': False, 'error': f'Not enough memory to draw on this machine: {free:.1f} GB free, drawing needs about '
                          f'{DRAW_NEEDS_GB} GB (the Möbius container is capped by its host setting MOBIUS_APP_MEM_LIMIT).',
                          'next': 'Do not retry. Make it without a drawing: 3D AI Studio text-to-3D (ai3d.py text, if it has credits), '
                                  'the free character library, shapes.py for objects, or an SVG for flat pictures.'}))
        sys.exit(3)


def concept(prompt, out, seed=None, wide=False, obj=False, picture=False, body=None, build=None, empty_hands=False,
            init=None, strength=0.55, style=None):
    """Draw a full-body T-pose concept on this machine: DreamShaper 8 (SD 1.5, OpenRAIL-M)
    with LCM-LoRA for speed and an OpenPose ControlNet that holds the T-pose. ~40 s on CPU.
    init: redraw this picture instead of starting blank (an edit that keeps the same
    character; strength 0.3 = small touch-up, 0.55 = clear change, 0.8 = nearly new).
    style: the look, in any words ("PS2 Silent Hill graphics", "claymation", "anime")."""
    # Characters read their whole (long) description in chunks (long_embeds), with the
    # style at the end; other pictures just lead with it.
    tail = f', {style} style' if style else ''
    if style and (obj or picture):
        prompt = f'{style} style, {prompt}'
    check_memory_for_drawing()
    from PIL import Image as _Image
    init_img = _Image.open(init).convert('RGB') if init else None
    import fcntl
    ensure_triposr()
    import importlib.util
    need = [pkg for mod, pkg in (('diffusers', 'diffusers==0.34.0'), ('accelerate', 'accelerate'), ('safetensors', 'safetensors'), ('peft', 'peft')) if importlib.util.find_spec(mod) is None]
    if need:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', *need], check=True)
    import torch
    from diffusers import ControlNetModel, LCMScheduler, StableDiffusionControlNetPipeline
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tpose import tpose
    with open(Path.home() / '.cache' / 'game-studio' / 'triposr.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        torch.set_num_threads(min(8, os.cpu_count() or 8))
        # Half-precision (bfloat16) weights: the Möbius container has 4 GB in total, and the
        # full-precision image model plus pose guide (~5.5 GB) no longer fits. GS_DTYPE=float32
        # restores full precision on a machine with room.
        DTYPE = torch.float32 if os.environ.get('GS_DTYPE') == 'float32' else torch.bfloat16
        VARIANT = None if DTYPE == torch.float32 else 'fp16'   # half-size files: no full-size copy while loading
        gen = torch.manual_seed(seed if seed is not None else int.from_bytes(os.urandom(2), 'big'))
        if picture:
            # Skies, backgrounds and ground textures: a plain picture.
            from diffusers import StableDiffusionPipeline
            pipe = StableDiffusionPipeline.from_pretrained('Lykon/dreamshaper-8', torch_dtype=DTYPE, variant=VARIANT, safety_checker=None)
            pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
            pipe.load_lora_weights('latent-consistency/lcm-lora-sdv1-5')
            pipe.fuse_lora()
            img = pipe(prompt, negative_prompt='text, watermark, people, characters', num_inference_steps=6, guidance_scale=1.5,
                       width=768 if wide else 512, height=512, generator=gen).images[0]
        elif body in ('fourlegs', 'wings', 'any'):
            # Non-human characters: no human pose guide; a view creature.py can read.
            from diffusers import StableDiffusionPipeline
            pipe = StableDiffusionPipeline.from_pretrained('Lykon/dreamshaper-8', torch_dtype=DTYPE, variant=VARIANT, safety_checker=None)
            pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
            pipe.load_lora_weights('latent-consistency/lcm-lora-sdv1-5')
            pipe.fuse_lora()
            view = {
                'fourlegs': ('full body {p} alone on a plain white background, standing on all four legs, three-quarter side view facing left, whole body with head, tail and all four legs visible, game character, plain white background', 768, 512),
                'wings': ('full body {p} alone on a plain white background, front view facing the viewer, wings spread wide open to both sides, whole body, symmetrical, game character, plain white background', 768, 512),
                'any': ('full body {p} alone on a plain white background, front view facing the viewer, whole body, game character, plain white background', 512, 512),
            }[body]
            neg = 'cropped, cut off, several characters, scenery, street, city, buildings, landscape, ground, shadow, text, human, person'
            if init_img is not None:
                from diffusers import StableDiffusionImg2ImgPipeline
                pipe = StableDiffusionImg2ImgPipeline(**pipe.components)
                pe, ne = long_embeds(pipe, view[0].format(p=prompt) + tail, neg)
                img = pipe(prompt_embeds=pe, negative_prompt_embeds=ne, image=init_img, strength=strength,
                           num_inference_steps=max(6, round(4 / strength)), guidance_scale=1.5, generator=gen).images[0]
            else:
                pe, ne = long_embeds(pipe, view[0].format(p=prompt) + tail, neg)
                img = pipe(prompt_embeds=pe, negative_prompt_embeds=ne,
                           num_inference_steps=6, guidance_scale=1.5, width=view[1], height=view[2], generator=gen).images[0]
        elif obj:
            # Objects (trees, coins, houses, props): one centred object, no pose guide.
            from diffusers import StableDiffusionPipeline
            pipe = StableDiffusionPipeline.from_pretrained('Lykon/dreamshaper-8', torch_dtype=DTYPE, variant=VARIANT, safety_checker=None)
            pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
            pipe.load_lora_weights('latent-consistency/lcm-lora-sdv1-5')
            pipe.fuse_lora()
            img = pipe(f'{prompt}, isolated on a white background, full view, game asset, 3D render',
                       negative_prompt='cropped, cut off, touching the edges, close-up, several objects, landscape, scenery, ground, grass, floor, horizon, shadow, text', num_inference_steps=6, guidance_scale=1.5,
                       width=512, height=512, generator=gen).images[0]
        else:
            cn = ControlNetModel.from_pretrained('lllyasviel/control_v11p_sd15_openpose', torch_dtype=DTYPE, variant=VARIANT)
            pipe = StableDiffusionControlNetPipeline.from_pretrained('Lykon/dreamshaper-8', controlnet=cn, torch_dtype=DTYPE, variant=VARIANT, safety_checker=None)
            pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
            pipe.load_lora_weights('latent-consistency/lcm-lora-sdv1-5')
            pipe.fuse_lora()
            from tpose import BUILD_WORDS
            cw = 640 if build in ('heavy', 'huge') else 512  # broad bodies need room for their hands
            words = BUILD_WORDS.get(build or 'average', '')
            hands = ', empty open hands, holding nothing' if empty_hands else ''
            # Fitted sleeves: the rig lowers the T-posed arms, and any cloth hanging under
            # them (kimono or wizard sleeves, capes) swings into the shoulders and back
            # and piles up as a hump. Tight sleeves keep the body human from every side.
            full = (f'full body game character alone on a plain white background, {prompt}, {words}{hands}, fitted sleeves close to the arms, '
                    f'standing in a T-pose, arms straight out to the sides, front view, whole body head to feet, plain white background{tail}')
            # The pose guide sets proportions; a little slack lets the body's bulk follow the words.
            neg = ('cropped, cut off, multiple people, scenery, street, city, buildings, landscape, room, wooden wall, floor, puddle, shadow, extra limbs, '
                   'wide sleeves, flowing sleeves, hanging sleeves, cape, cloak, drapery under the arms'
                   + ('' if build in ('slim', 'lanky') else ', skinny, thin waist, narrow waist')
                   + (', weapon, sword, club, staff, spear, katana, sheath, scabbard, holding an object' if empty_hands else ''))
            if init_img is not None:
                # An edit: redraw the current picture, same size, the pose guide still holding the T-pose.
                from diffusers import StableDiffusionControlNetImg2ImgPipeline
                pipe = StableDiffusionControlNetImg2ImgPipeline(**pipe.components)
                w, h = init_img.size
                pe, ne = long_embeds(pipe, full, neg)
                img = pipe(prompt_embeds=pe, negative_prompt_embeds=ne, image=init_img, control_image=tpose(w=w, h=h, build=build or 'average'), strength=strength,
                           num_inference_steps=max(6, round(4 / strength)), guidance_scale=1.5, controlnet_conditioning_scale=0.85,
                           generator=gen).images[0]
            else:
                pe, ne = long_embeds(pipe, full, neg)
                img = pipe(prompt_embeds=pe, negative_prompt_embeds=ne, image=tpose(w=cw, build=build or 'average'), num_inference_steps=6, guidance_scale=1.5,
                           controlnet_conditioning_scale=0.85, width=cw, height=768, generator=gen).images[0]
    img.save(out)
    print(json.dumps({'ok': True, 'out': str(out), 'next': 'Read it: the right character and style, a clean T-pose, nothing cut off. Redraw with another --seed if not.'}))


def long_embeds(pipe, prompt, negative):
    """Prompt embeddings for text of any length: the text model reads 75 tokens at a
    time, so read the text in 75-token chunks and join them (the picture model takes any
    length). The negative text is padded to the same number of chunks."""
    import torch
    tok, enc = pipe.tokenizer, pipe.text_encoder

    def chunks(text):
        ids = tok(text, truncation=False, add_special_tokens=False).input_ids
        return [ids[i:i + 75] for i in range(0, len(ids), 75)] or [[]]

    pos, neg = chunks(prompt), chunks(negative)
    n = max(len(pos), len(neg))
    pos, neg = pos + [[]] * (n - len(pos)), neg + [[]] * (n - len(neg))

    def embed(parts):
        rows = [[tok.bos_token_id, *c, tok.eos_token_id] + [tok.pad_token_id] * (75 - len(c)) for c in parts]
        with torch.no_grad():
            return torch.cat([enc(torch.tensor([r]))[0] for r in rows], dim=1)
    return embed(pos), embed(neg)


# ---------- picture -> 3D on this machine (TripoSR, MIT, CPU) ----------
TRIPOSR = Path.home() / '.cache' / 'game-studio' / 'TripoSR'


BLENDER_VERSION = '5.2.2'
BLENDER_DIR = Path.home() / '.cache' / 'game-studio' / 'blender'
BLENDER = BLENDER_DIR / f'blender-{BLENDER_VERSION}-linux-x64' / 'blender'
BLENDER_LIBS = ['libsm6', 'libice6', 'libgl1', 'libxkbcommon0', 'libxi6', 'libxrender1', 'libxxf86vm1', 'libxfixes3', 'libegl1']


def ensure_blender():
    """Blender (GPL, free) for the clean-up step: downloaded once into the cache.
    Returns its path, or None when it can't be set up here (the step is then skipped)."""
    if not BLENDER.exists():
        import tarfile
        BLENDER_DIR.mkdir(parents=True, exist_ok=True)
        archive = BLENDER_DIR / 'blender.tar.xz'
        major = '.'.join(BLENDER_VERSION.split('.')[:2])
        # blender.org refuses Python's default user agent (HTTP 403).
        req = urllib.request.Request(f'https://download.blender.org/release/Blender{major}/blender-{BLENDER_VERSION}-linux-x64.tar.xz',
                                     headers={'User-Agent': 'Mozilla/5.0 (MobiusGameStudio)'})
        with urllib.request.urlopen(req, timeout=600) as res, open(archive, 'wb') as f:
            shutil.copyfileobj(res, f)
        with tarfile.open(archive, 'r:xz') as tar:  # Python's own xz: this machine has no xz tool
            tar.extractall(BLENDER_DIR, filter='tar')
        archive.unlink()
    if subprocess.run([str(BLENDER), '-b', '--version'], capture_output=True).returncode:
        # Missing system libraries (a fresh container): install them if this machine allows it.
        # A fresh container has empty package lists, so refresh them first.
        subprocess.run(['sudo', '-n', 'apt-get', 'update', '-q'], capture_output=True)
        subprocess.run(['sudo', '-n', 'apt-get', 'install', '-y', '-q', *BLENDER_LIBS], capture_output=True)
        if subprocess.run([str(BLENDER), '-b', '--version'], capture_output=True).returncode:
            return None
    return BLENDER


def blender_clean(raw, out):
    """Smooth, closed, lump-free surface with the colours re-baked (blender_clean.py).
    Returns True when OUT was written; on any problem the caller keeps the raw model."""
    try:
        blender = ensure_blender()
    except Exception as err:  # no network, disk full...
        print(f'Blender clean-up skipped: {err}', file=sys.stderr)
        return False
    if not blender:
        print('Blender clean-up skipped: Blender cannot run on this machine.', file=sys.stderr)
        return False
    script = Path(__file__).resolve().parent / 'blender_clean.py'
    proc = subprocess.run([str(blender), '-b', '--python', str(script), '--', str(raw), str(out)],
                          capture_output=True, text=True, timeout=600)
    if 'CLEAN_OK' not in proc.stdout or not Path(out).exists():
        print('Blender clean-up skipped: ' + (proc.stderr or proc.stdout)[-400:], file=sys.stderr)
        return False
    return True


def ensure_triposr():
    if not (TRIPOSR / 'run.py').exists():
        subprocess.run(['git', 'clone', '-q', 'https://github.com/VAST-AI-Research/TripoSR.git', str(TRIPOSR)], check=True)
        iso = TRIPOSR / 'tsr' / 'models' / 'isosurface.py'
        iso.write_text(iso.read_text().replace('from torchmcubes import marching_cubes\n', '''try:
    from torchmcubes import marching_cubes
except ImportError:  # CPU fallback: scikit-image, in torchmcubes' (z, y, x) order
    from skimage.measure import marching_cubes as _sk_mc

    def marching_cubes(vol, level):
        v, f, _, _ = _sk_mc(vol.cpu().numpy(), level)
        return torch.from_numpy(v[:, ::-1].copy()).float(), torch.from_numpy(f[:, ::-1].copy().astype('int64'))
'''))
    # Texture baking normally needs OpenGL; this container has none, so bake on the CPU.
    bake = TRIPOSR / 'tsr' / 'bake_texture.py'
    shutil.copy(Path(__file__).resolve().parent / 'tsr_raster.py', TRIPOSR / 'tsr' / 'cpu_raster.py')
    if 'cpu_raster' not in bake.read_text():
        bake.write_text(bake.read_text().replace('import moderngl\n', '').replace(
            '    positions_texture = rasterize_position_atlas(',
            '    from .cpu_raster import rasterize_position_atlas as cpu_raster\n    positions_texture = cpu_raster('))
    import importlib.util
    if importlib.util.find_spec('torch') is None:  # check without loading it: memory is tight
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--index-url', 'https://download.pytorch.org/whl/cpu', 'torch', 'torchvision'], check=True)
    import importlib.util
    need = [pkg for mod, pkg in (('omegaconf', 'omegaconf'), ('einops', 'einops'), ('transformers', 'transformers<5'), ('trimesh', 'trimesh'),
                                 ('xatlas', 'xatlas'), ('huggingface_hub', 'huggingface-hub'), ('skimage', 'scikit-image'), ('moderngl', 'moderngl'),
                                 ('imageio', 'imageio'), ('rembg', 'rembg')) if importlib.util.find_spec(mod) is None]
    if need:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', *need], check=True)


BIREFNET = Path.home() / '.rembg' / 'models' / 'birefnet-general-lite' / 'birefnet-general-lite.onnx'
BIREFNET_URL = 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx'


def cutout(png, out):
    """Cut the subject out with BiRefNet lite (MIT): clean edges, keeps holes and leaves right."""
    import onnxruntime as ort
    from PIL import Image
    if not BIREFNET.exists():
        BIREFNET.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(BIREFNET_URL, str(BIREFNET) + '.part')
        os.replace(str(BIREFNET) + '.part', BIREFNET)
    o = ort.SessionOptions()
    o.enable_cpu_mem_arena = False  # keeps the peak near 6.5 GB (the default runs out of memory)
    o.enable_mem_pattern = False
    o.intra_op_num_threads = min(8, os.cpu_count() or 8)
    o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    s = ort.InferenceSession(str(BIREFNET), o, providers=['CPUExecutionProvider'])
    im = Image.open(png).convert('RGB')
    x = (np.asarray(im.resize((1024, 1024), Image.BICUBIC)).astype('f4') / 255 - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    y = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype('f4')})[0]
    mask = Image.fromarray((255 / (1 + np.exp(-y[0, 0]))).astype('u1')).resize(im.size, Image.BICUBIC)
    im = im.convert('RGBA')
    im.putalpha(mask)
    im.save(out)


def prepare(png, out):
    """Cut the subject out and frame it the way TripoSR expects."""
    from PIL import Image
    cut_png = Path(out).with_name('cut.png')
    # Its own process, so its memory is free again before the 3D step starts.
    proc = subprocess.run([sys.executable, __file__, 'cutout', str(png), str(cut_png)], capture_output=True, text=True, timeout=600)
    if proc.returncode or not cut_png.exists():
        # Out of memory (another job running): the smaller, rougher cut-out still works.
        from rembg import remove, new_session
        cut = remove(Image.open(png).convert('RGB'), session=new_session('isnet-general-use'))
    else:
        cut = Image.open(cut_png)
    a = np.array(cut).astype('f4') / 255
    ys, xs = np.where(a[..., 3] > 0.5)
    if not len(ys):
        sys.exit('No character found in the picture.')
    crop = cut.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    w, h = crop.size
    side = int(max(w, h) / 0.85)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(crop, ((side - w) // 2, (side - h) // 2))
    c = np.array(canvas).astype('f4') / 255
    rgb = c[..., :3] * c[..., 3:4] + 0.5 * (1 - c[..., 3:4])
    Image.fromarray((rgb * 255).astype('uint8')).save(out)
    Image.fromarray((c[..., 3] * 255).astype('uint8')).save(Path(out).with_name('alpha.png'))


def drop_floaters(m, keep=0.03):
    """Remove small pieces floating free of the model (bits of a chain, a rope or
    a stray shadow that picture-to-3D turns into specks in the air). Keeps every
    piece with at least KEEP of the biggest piece's triangles."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    # Pieces by position: texture seams split the surface into separately
    # numbered patches that still touch, and those must count as one piece.
    _, weld = np.unique(np.round(np.asarray(m.vertices) / 1e-5).astype('i8'), axis=0, return_inverse=True)
    f = weld.reshape(-1)[np.asarray(m.faces)]
    n = int(f.max()) + 1
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]]])
    graph = sp.coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    _, vlabel = connected_components(graph, directed=False)
    labels = vlabel[f[:, 0]]
    sizes = np.bincount(labels)
    if len(sizes) < 2:
        return 0
    small = sizes[labels] < keep * sizes.max()
    # A separate piece that sits wholly behind the model's middle (TripoSR looks from
    # +X) was never in the picture: the front view can't show it, so it is invented.
    main = int(np.argmax(sizes))
    V = np.asarray(m.vertices)
    fx = V[np.asarray(m.faces)].mean(1)[:, 0]
    middle = float(np.median(fx[labels == main]))
    for piece in range(len(sizes)):
        if piece != main and fx[labels == piece].max() < middle:
            small |= labels == piece
    if small.any():
        m.update_faces(~small)
        m.remove_unreferenced_vertices()
    return int(len(np.unique(labels[small])))


def local3d(png, out, res=192, project=True):
    import fcntl
    ensure_triposr()
    work = Path(tempfile.mkdtemp(prefix='tsr-', dir=os.environ.get('TMPDIR')))
    prepped = work / 'in.png'
    (work / 'out' / '0').mkdir(parents=True)
    # One generation at a time: each step needs most of this machine's memory.
    with open(Path.home() / '.cache' / 'game-studio' / 'triposr.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prepare(png, prepped)
        env = {**os.environ, 'OMP_NUM_THREADS': str(min(8, os.cpu_count() or 8))}
        # --bake-texture: a real 1024px texture instead of per-corner colours (much sharper, true colours).
        proc = subprocess.run([sys.executable, 'run.py', str(prepped), '--no-remove-bg', '--device', 'cpu', '--output-dir', str(work / 'out'),
                               '--model-save-format', 'obj', '--bake-texture', '--texture-resolution', '1024', '--mc-resolution', str(res)],
                              cwd=TRIPOSR, env=env, capture_output=True, text=True, timeout=900)
    mesh, tex = work / 'out' / '0' / 'mesh.obj', work / 'out' / '0' / 'texture.png'
    if proc.returncode or not mesh.exists():
        sys.exit('3D generation failed: ' + (proc.stderr or proc.stdout)[-600:])
    import trimesh
    from PIL import Image
    m = trimesh.load(mesh, process=False, force='mesh')
    drop_floaters(m)
    texture = Image.open(tex).convert('RGB')
    if project:
        # TripoSR's colours are a blurry guess; paint the sharp picture back onto
        # everything that faces its camera (faces, patterns, small details).
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from tsr_raster import front_project
        sharp = front_project(np.asarray(m.vertices, 'f8'), np.asarray(m.faces), np.asarray(m.visual.uv, 'f8'),
                              np.asarray(texture).astype('f8') / 255, np.asarray(Image.open(prepped).convert('RGB')).astype('f8') / 255,
                              np.asarray(Image.open(work / 'alpha.png')).astype('f8') / 255)
        texture = Image.fromarray((sharp * 255).clip(0, 255).astype('uint8'))
    mat = trimesh.visual.material.PBRMaterial(baseColorTexture=texture, metallicFactor=0.0, roughnessFactor=0.9)
    m.visual = trimesh.visual.TextureVisuals(uv=m.visual.uv, material=mat)
    m.export(work / 'textured.glb', file_type='glb')
    # Half the triangles (TripoSR is very dense) and a JPEG texture: about a third of the size, same look.
    shrink(work / 'textured.glb', out, simplify=0.5, quantize=False)
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': Path(out).stat().st_size, 'next': f'rig it: detailed.py rig {out} RIGGED.glb'}))


def studio_app_id():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from studio_app import app_id
    return app_id()


def hf_token():
    """The owner's Hugging Face key: Game Studio's app secret 'hf-token' (or HF_TOKEN)."""
    if os.environ.get('HF_TOKEN'):
        return os.environ['HF_TOKEN']
    base = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
    token = os.environ.get('AGENT_TOKEN') or os.environ.get('APP_TOKEN')
    req = urllib.request.Request(f'{base}/api/apps/{studio_app_id()}/secrets/hf-token',
                                 headers={'Authorization': f'Bearer {token}'})
    try:
        return urllib.request.urlopen(req, timeout=20).read().decode().strip()
    except Exception:
        return None


def online3d(png, out, seed=1):
    """Picture -> textured 3D model with TRELLIS (MIT, Microsoft) on Hugging Face, using
    the owner's free key. It builds the whole object (back, sides, clothing) instead of
    guessing from the front, so there are no holes or hanging bits. About 1-2 minutes.
    The model comes out standing up (+Y up), metres roughly 1 tall; rig() rescales it."""
    token = hf_token()
    if not token:
        sys.exit('No Hugging Face key is saved yet: ask the person to add it in Game Studio.')
    from gradio_client import Client, handle_file
    from gradio_client.exceptions import AppError
    last = None
    for attempt in range(2):
        try:
            client = Client('trellis-community/TRELLIS', token=token, verbose=False)
            client.predict(api_name='/start_session')
            prepped = client.predict(image=handle_file(str(png)), api_name='/preprocess_image')
            result = client.predict(image=handle_file(prepped), multiimages=[], seed=seed, ss_guidance_strength=7.5,
                                    ss_sampling_steps=12, slat_guidance_strength=3.0, slat_sampling_steps=12,
                                    multiimage_algo='stochastic', mesh_simplify=0.95, texture_size=1024,
                                    api_name='/generate_and_extract_glb')
            glb = next(r for r in result if isinstance(r, str) and r.endswith('.glb')) if isinstance(result, (list, tuple)) else result
            if isinstance(glb, dict):
                glb = glb.get('value') or glb.get('path')
            shutil.copy(glb, out)
            print(json.dumps({'ok': True, 'out': str(out), 'bytes': Path(out).stat().st_size,
                              'next': f'rig it: detailed.py rig {out} RIGGED.glb --no-body'}))
            return
        except AppError as err:
            last = str(err)
            if 'quota' in last.lower():
                sys.exit('The free Hugging Face GPU time for today is used up; try again later (it refills daily).')
        except Exception as err:  # the space was waking up or busy: one more try
            last = str(err)
        time.sleep(10)
    sys.exit(f'The online 3D generator failed: {last}'[:500])


def weapon(raw, out, length=1.0, grip=0.12, flip_ends=False):
    """Turn a picture-to-3D weapon (drawn standing up, handle at the bottom) into a
    holdable item: blade/head along +Y, its flat side facing X, the grip point at the
    origin, LENGTH metres long (a person is 1.8). model_tool.py equip puts it in a hand."""
    import trimesh
    scene = trimesh.load(raw, force='scene')
    parts = [g for g in scene.dump() if isinstance(g, trimesh.Trimesh)]
    mesh = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
    mesh.apply_transform(np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, 1]], 'f8'))
    # Long axis -> +Y (blade/head up), the handle end being the one drawn on the left
    # (-X here); the thinnest direction -> X (a blade's flat side faces sideways).
    V = np.asarray(mesh.vertices)
    _, _, vt = np.linalg.svd(V - V.mean(0), full_matrices=False)
    long_, mid, thin = vt[0], vt[1], vt[2]
    if long_[0] < 0:
        long_ = -long_
    if flip_ends:
        long_ = -long_
    R = np.array([thin, long_, mid])
    if np.linalg.det(R) < 0:
        R[2] = -R[2]
    T = np.eye(4)
    T[:3, :3] = R
    mesh.apply_transform(T)
    lo, hi = mesh.bounds
    mesh.apply_translation([0, -lo[1], 0])
    mesh.apply_scale(length / max(hi[1] - lo[1], 1e-6))
    V = np.asarray(mesh.vertices)
    gy = grip * length
    band = V[np.abs(V[:, 1] - gy) < 0.04 * length]
    centre = band.mean(0) if len(band) >= 3 else V.mean(0)
    mesh.apply_translation([-centre[0], -gy, -centre[2]])
    mesh.fix_normals()
    work = Path(tempfile.mkdtemp(prefix='weapon-', dir=os.environ.get('TMPDIR')))
    mesh.export(work / 'w.glb', file_type='glb')
    shrink(work / 'w.glb', out, quantize=False)
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': Path(out).stat().st_size, 'length': length, 'grip': grip,
                      'next': f'Save it as an asset (model_tool.py asset ... --glb {out}) and put it in a hand: model_tool.py equip CHAR.glb {out} OUT.glb'}))


GLTFPACK = Path.home() / '.cache' / 'game-studio' / 'node' / 'node_modules' / '.bin' / 'gltfpack'


def shrink(src, out, simplify=None, quantize=True):
    """JPEG textures, then gltfpack (MIT): optional simplification, and packed numbers
    (KHR_mesh_quantization, which three.js reads with no extra setup). Leave quantize off
    for files our own tools edit later (rigging, adding clips)."""
    import io
    from PIL import Image
    from model_tool import compact
    g, b = read_glb(src)
    b = bytearray(b)
    for img in g.get('images', []):
        if img.get('mimeType') == 'image/jpeg' or 'bufferView' not in img:
            continue
        pil = Image.open(io.BytesIO(view_bytes(g, b, img['bufferView'])))
        if pil.mode in ('RGBA', 'LA') and pil.getchannel('A').getextrema()[0] < 250:
            continue  # real transparency: keep the PNG
        buf = io.BytesIO()
        pil.convert('RGB').save(buf, 'JPEG', quality=85, optimize=True)
        img['bufferView'] = add_view(g, b, buf.getvalue())
        img['mimeType'] = 'image/jpeg'
    tmp = Path(out).with_suffix('.jpg.glb')
    write_glb(tmp, g, compact(g, b))
    if not GLTFPACK.exists():
        subprocess.run(['npm', 'install', '--silent', '--prefix', str(GLTFPACK.parents[2]), 'gltfpack'], check=True, timeout=300)
    cmd = [str(GLTFPACK), '-i', str(tmp), '-o', str(out), '-kn', '-km']
    if simplify:
        cmd += ['-si', str(simplify)]
    if not quantize:
        cmd.append('-noq')
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode or not Path(out).exists():
        shutil.copy(tmp, out)  # gltfpack missing or failed: the JPEG version is still smaller
    tmp.unlink(missing_ok=True)


def upright(raw, out, height=1.0):
    """Stand a TripoSR object up (its up is Z), size it, sit it on the ground, then pack it small."""
    import trimesh
    scene = trimesh.load(raw, force='scene')
    parts = [g for g in scene.dump() if isinstance(g, trimesh.Trimesh)]
    mesh = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
    mesh.apply_transform(np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, 1]], dtype='f8'))
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    mesh.apply_scale(height / max(hi[1] - lo[1], 1e-6))
    mesh.fix_normals()
    work = Path(tempfile.mkdtemp(prefix='upright-', dir=os.environ.get('TMPDIR')))
    mesh.export(work / 'up.glb', file_type='glb')
    shrink(work / 'up.glb', out)
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': Path(out).stat().st_size, 'height': height}))


# ---------- rigging ----------

def accessor_array(g, b, i):
    acc = g['accessors'][i]
    comps = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[acc['type']]
    dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1', 5122: '<i2', 5120: 'i1'}[acc['componentType']]
    view = g['bufferViews'][acc['bufferView']]
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    stride = view.get('byteStride')
    size = np.dtype(dtype).itemsize * comps
    if stride and stride != size:
        rows = [np.frombuffer(bytes(b[start + k * stride:start + k * stride + size]), dtype=dtype) for k in range(acc['count'])]
        arr = np.stack(rows)
    else:
        arr = np.frombuffer(bytes(b[start:start + size * acc['count']]), dtype=dtype).reshape(acc['count'], comps) if comps > 1 else np.frombuffer(bytes(b[start:start + size * acc['count']]), dtype=dtype)
    if acc.get('normalized') and acc['componentType'] != 5126:
        arr = arr.astype('f4') / {5121: 255, 5123: 65535, 5120: 127, 5122: 32767}[acc['componentType']]
    return arr.astype('f4') if acc['componentType'] == 5126 else arr


def node_matrix(n):
    if 'matrix' in n:
        return np.array(n['matrix'], dtype='f8').reshape(4, 4).T
    t = np.array(n.get('translation', [0, 0, 0]), dtype='f8')
    x, y, z, w = n.get('rotation', [0, 0, 0, 1])
    s = np.array(n.get('scale', [1, 1, 1]), dtype='f8')
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def world_matrices(g):
    parent = {}
    for i, n in enumerate(g.get('nodes', [])):
        for c in n.get('children', []):
            parent[c] = i
    cache = {}

    def world(i):
        if i not in cache:
            m = node_matrix(g['nodes'][i])
            cache[i] = world(parent[i]) @ m if i in parent else m
        return cache[i]
    return world, parent


def mat_to_trs(m):
    t = m[:3, 3].copy()
    sx, sy, sz = np.linalg.norm(m[:3, 0]), np.linalg.norm(m[:3, 1]), np.linalg.norm(m[:3, 2])
    r = m[:3, :3] / np.array([sx, sy, sz])
    tr = np.trace(r)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, 0.25 * s]
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = [0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s]
    elif r[1, 1] > r[2, 2]:
        s = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = [(r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s]
    else:
        s = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = [(r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s, (r[1, 0] - r[0, 1]) / s]
    return t.tolist(), [float(v) for v in q], [float(sx), float(sy), float(sz)]


FILL_DEPTH = os.environ.get('GS_FILL_DEPTH', '1') != '0'


def fill_depth(prims, H=1.8):
    """Deepen slices that are much flatter (front to back) than a body is.

    Model is standing, 1.8 tall, centred, facing +Z. Per 3 cm slice: legs are measured
    one at a time (a leg is about as deep as wide), the torso against ~60% of its
    width (tapering to ~30% at the shoulder line, arms included), the head against ~85%. Arms held out in the T-pose are left alone. Only
    ever deepens, never flattens, and changes smoothly from slice to slice."""
    from scipy.ndimage import gaussian_filter1d
    pos = np.concatenate([p[1] for p in prims])
    y, x, z = pos[:, 1], pos[:, 0], pos[:, 2]
    waist = np.abs(x[(y > 0.42 * H) & (y < 0.55 * H)])
    core = max(float(np.percentile(waist, 97)) * 1.35 if len(waist) else 0.2, 0.12)
    edges = np.arange(0, H + 0.03, 0.03)
    n = len(edges) - 1
    fac = np.ones(n)
    ctr = np.zeros(n)
    slices = [(y >= edges[i]) & (y < edges[i + 1]) & (np.abs(x) < core) for i in range(n)]
    width = np.array([np.percentile(x[m], 98) - np.percentile(x[m], 2) if m.sum() >= 12 else 0.0 for m in slices])
    # Where the neck starts: the first slice above the shoulders that is much narrower
    # than them. Shoulder height differs per character, and treating a broad shoulder
    # slice as head (as deep as wide) swells the upper back into a hump.
    mids = (edges[:-1] + edges[1:]) / 2
    band = np.flatnonzero((mids > 0.65 * H) & (mids < 0.92 * H))
    neck = 0.84 * H
    if len(band) and width[band].max() > 0:
        top = band[np.argmax(width[band])]
        narrow = [i for i in range(top, n) if 0 < width[i] < 0.55 * width[top]]
        if narrow:
            neck = edges[narrow[0]]
    for i in range(n):
        m = slices[i]
        if m.sum() < 12:
            continue
        ys = mids[i]
        ctr[i] = float(np.median(z[m]))
        if ys < 0.45 * H:
            parts, target = [m & (x < 0), m & (x >= 0)], 0.85  # each leg (or each half of a robe)
        elif ys < neck:
            # Chest and belly are ~60% as deep as wide, but the shoulder line is broad
            # and thin, and in a T-pose the arms count toward its width too (~30%):
            # holding it to 60% pushes a hump out behind the shoulders.
            parts, target = [m], 0.6 - 0.3 * float(np.clip((ys - (neck - 0.14 * H)) / (0.12 * H), 0, 1))
        else:
            parts, target = [m], 0.85
        need = 1.0
        for part in parts:
            if part.sum() < 8:
                continue
            w = np.percentile(x[part], 98) - np.percentile(x[part], 2)
            d = np.percentile(z[part], 98) - np.percentile(z[part], 2)
            if d > 1e-4:
                need = max(need, target * w / d)
        fac[i] = min(need, 1.8)
    # Smooth within the body and within the head separately, so a flat head's large
    # correction never bleeds down into the shoulders (or the shoulders' into the neck).
    k = int(np.searchsorted(mids, neck))
    fac = np.maximum(1.0, np.concatenate([gaussian_filter1d(fac[:k], 1.5, mode='nearest') if k else fac[:0],
                                          gaussian_filter1d(fac[k:], 1.5, mode='nearest') if k < n else fac[:0]]))
    known = ctr != 0
    if known.any():
        ctr = np.interp(np.arange(n), np.flatnonzero(known), ctr[known])
    out = []
    for p, q, nor in prims:
        q = q.copy()
        idx = np.clip(((q[:, 1]) / 0.03).astype(int), 0, n - 1)
        # Full effect on the body, fading out toward arms held out to the sides.
        wx = np.clip((core * 1.25 - np.abs(q[:, 0])) / (core * 0.25), 0, 1)
        f = 1 + (fac[idx] - 1) * wx
        q[:, 2] = ctr[idx] + (q[:, 2] - ctr[idx]) * f
        out.append((p, q, None))  # normals are rebuilt from the reshaped triangles
    return out


def rig(raw, out, anims, flip_front=False, body=None, yup=False):
    src, sbin = read_glb(raw)
    plain = (len(src.get('meshes', [])) == 1 and not src.get('skins') and len(src.get('materials', [])) <= 1
             and len(src['meshes'][0].get('primitives', [])) == 1)
    # A picture-to-3D person (one plain textured mesh, no skeleton) gets a real human
    # body under it (body_base.py): its guessed body is thin, lumpy and oddly armed.
    # Imports keep their own body. body='guess' (--no-body, or GS_BODY=0) uses the guess.
    if body is None:
        body = 'human' if plain and os.environ.get('GS_BODY', '1') != '0' else 'guess'
    # Otherwise a plain model first goes through Blender: a smooth, closed surface without
    # invented lumps on the back. GS_BLENDER=0 skips it.
    if body == 'guess' and plain and os.environ.get('GS_BLENDER', '1') != '0':
        cleaned = Path(tempfile.mkdtemp(prefix='clean-', dir=os.environ.get('TMPDIR'))) / 'clean.glb'
        if blender_clean(raw, cleaned):
            src, sbin = read_glb(cleaned)
    lib_path = ual_files()['ual1']
    lib, lbin = read_glb(lib_path)

    # 1. The model's triangles in world space (all mesh primitives, baked transforms).
    world, _ = world_matrices(src)
    prims = []
    for ni, n in enumerate(src.get('nodes', [])):
        if 'mesh' not in n:
            continue
        m = world(ni)
        for p in src['meshes'][n['mesh']]['primitives']:
            pos = accessor_array(src, sbin, p['attributes']['POSITION']).astype('f8')
            pos = (np.c_[pos, np.ones(len(pos))] @ m.T)[:, :3]
            nor = accessor_array(src, sbin, p['attributes']['NORMAL']).astype('f8') @ m[:3, :3].T if 'NORMAL' in p['attributes'] else None
            prims.append((p, pos, nor))
    if not prims:
        sys.exit('The model has no meshes.')
    allpos = np.concatenate([p[1] for p in prims])

    # 2. Stand it up: the tallest axis becomes Y (up), the arm span X, the thinnest Z (front).
    ext = allpos.max(0) - allpos.min(0)
    up, span, depth = [int(i) for i in np.argsort(-ext)]
    if yup:
        # 3D AI Studio models already stand up (+Y). Squat or long-armed characters can be
        # wider than they are tall, which would fool the tallest-axis guess. They also face
        # the other way from what this skeleton expects, so --yup turns them round
        # (--flip turns them back).
        up = 1
        span, depth = (0, 2) if ext[0] >= ext[2] else (2, 0)
        flip_front = not flip_front
    rot = np.zeros((3, 3))
    rot[0, span] = 1
    rot[1, up] = 1
    rot[2, depth] = 1
    if np.linalg.det(rot) < 0:
        rot[2] *= -1
    pos_all = allpos @ rot.T
    # Head on top: in a T-pose the widest slice (the arms) sits above the middle.
    yy = pos_all[:, 1]
    wide = pos_all[np.abs(pos_all[:, 0] - np.median(pos_all[:, 0])) > 0.35 * (pos_all[:, 0].max() - pos_all[:, 0].min())]
    if not yup and len(wide) > 20 and np.median(wide[:, 1]) < (yy.min() + yy.max()) / 2:
        rot = np.diag([1, -1, -1]) @ rot
    if flip_front:
        rot = np.diag([-1, 1, -1]) @ rot
    prims = [(p, pos @ rot.T, None if nor is None else nor @ rot.T) for p, pos, nor in prims]
    allpos = np.concatenate([p[1] for p in prims])
    lo, hi = allpos.min(0), allpos.max(0)
    height = hi[1] - lo[1]
    scale = 1.8 / height
    center = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    prims = [(p, (pos - center) * scale, nor) for p, pos, nor in prims]
    allpos = np.concatenate([p[1] for p in prims])

    # 2b. Picture-to-3D sees only the front, so bodies come out too flat front to
    # back (thin waists). Give each slice of the body a natural depth.
    if FILL_DEPTH and body == 'guess':
        prims = fill_depth(prims)
        allpos = np.concatenate([p[1] for p in prims])

    # 3. Fit the skeleton to the body: arm line height, arm reach, hip height.
    ljoints = lib['skins'][0]['joints']
    lworld, lparent = world_matrices(lib)
    names = {j: lib['nodes'][j]['name'] for j in ljoints}
    rest = {j: lworld(j) for j in ljoints}
    pos0 = {j: rest[j][:3, 3].copy() for j in ljoints}
    y = allpos[:, 1]
    x = allpos[:, 0]
    arms = allpos[(np.abs(x) > 0.45) & (y > 0.9)]
    arm_y = float(np.median(arms[:, 1])) if len(arms) > 20 else 1.44
    reach = float(np.percentile(np.abs(arms[:, 0]), 97)) if len(arms) > 20 else 0.82
    hand_x = max(0.45, reach - 0.1)
    s_arm = hand_x / 0.739
    target = {}
    for j in ljoints:
        n = names[j]
        p = pos0[j].copy()
        is_arm = any(k in n for k in ('shoulder', 'upper_arm', 'forearm', 'hand', 'f_', 'thumb'))
        if is_arm:
            p[0] = p[0] * s_arm
            p[1] = p[1] - 1.441 + arm_y
        else:
            # Body joints scale with the shoulder line, so short or tall bodies line up.
            p[1] = p[1] * (arm_y / 1.441)
        target[j] = p
    # Legs: stand them where the character's legs are (the drawing's stance), measured
    # per side at knee and ankle height, so the body and the model's legs line up.
    by_name0 = {names[j]: j for j in ljoints}
    for sd, sign in (('L', 1), ('R', -1)):
        knee, ankle = target[by_name0[f'DEF-shin.{sd}']], target[by_name0[f'DEF-foot.{sd}']]
        fitted = {}
        for key, joint in (('knee', knee), ('ankle', ankle)):
            band = allpos[(np.abs(allpos[:, 1] - joint[1]) < 0.04) & (np.sign(allpos[:, 0]) == sign) & (np.abs(allpos[:, 0]) < 0.4)]
            if len(band) > 20:
                fitted[key] = np.array([np.median(band[:, 0]), joint[1], np.median(band[:, 2])])
        if not fitted:
            continue
        k = fitted.get('knee', fitted.get('ankle'))
        a = fitted.get('ankle', k)
        for j in ljoints:
            n = names[j]
            if not n.endswith(f'.{sd}') or not any(w in n for w in ('thigh', 'shin', 'foot', 'toe', 'heel')):
                continue
            upper = 'thigh' in n or 'shin' in n
            ref, was = (k, knee) if upper else (a, ankle)
            shift = np.array([ref[0] - was[0], 0, (ref[2] - was[2]) * (0 if 'thigh' in n else 1)])
            target[j] = target[j] + np.clip(shift, -0.15, 0.15)
    # Keep the skeleton's hierarchy consistent: new worlds keep rest rotations, move translations.
    new_world = {}
    for j in ljoints:
        m = rest[j].copy()
        m[:3, 3] = target[j]
        new_world[j] = m

    # 3b. A real human body fitted to the character, with its clothes and colours.
    body_weights = None
    if body == 'human':
        import body_base
        src, sbin, prims, body_weights = body_base.fit(prims, src, sbin, lib, lbin, ljoints, names, new_world, target)

    # 4. Skin: each vertex to the two nearest bone segments (limbs never cross the midline).
    main = ['DEF-hips', 'DEF-spine.001', 'DEF-spine.002', 'DEF-spine.003', 'DEF-neck', 'DEF-head']
    for sd in ('L', 'R'):
        main += [f'DEF-shoulder.{sd}', f'DEF-upper_arm.{sd}', f'DEF-forearm.{sd}', f'DEF-hand.{sd}', f'DEF-thigh.{sd}', f'DEF-shin.{sd}', f'DEF-foot.{sd}', f'DEF-toe.{sd}']
    by_name = {names[j]: j for j in ljoints}
    child = {'DEF-hips': 'DEF-spine.001', 'DEF-spine.001': 'DEF-spine.002', 'DEF-spine.002': 'DEF-spine.003', 'DEF-spine.003': 'DEF-neck', 'DEF-neck': 'DEF-head'}
    for sd in ('L', 'R'):
        child.update({f'DEF-shoulder.{sd}': f'DEF-upper_arm.{sd}', f'DEF-upper_arm.{sd}': f'DEF-forearm.{sd}', f'DEF-forearm.{sd}': f'DEF-hand.{sd}',
                      f'DEF-thigh.{sd}': f'DEF-shin.{sd}', f'DEF-shin.{sd}': f'DEF-foot.{sd}', f'DEF-foot.{sd}': f'DEF-toe.{sd}'})
    segs = []
    for nme in main:
        a = target[by_name[nme]]
        if nme in child:
            b = target[by_name[child[nme]]]
        elif 'head' in nme:
            b = a + np.array([0, 0.3, 0])
        elif 'hand' in nme:
            b = a + np.array([0.15 if nme.endswith('L') else -0.15, 0, 0])
        else:
            b = a + np.array([0, 0, 0.1])
        side = 1 if nme.endswith('.L') else -1 if nme.endswith('.R') else 0
        segs.append((ljoints.index(by_name[nme]), a, b, side))
    joint_index = {j: k for k, j in enumerate(ljoints)}

    neck_y = target[by_name['DEF-neck']][1]
    head_i = ljoints.index(by_name['DEF-head'])

    def weights_for(pos):
        n = len(pos)
        d = np.full((n, len(segs)), 1e9)
        for k, (_, a, b, side) in enumerate(segs):
            ab = b - a
            t = np.clip(((pos - a) @ ab) / (ab @ ab), 0, 1)
            dist = np.linalg.norm(pos - (a + t[:, None] * ab), axis=1)
            if side:
                dist = np.where((np.sign(pos[:, 0]) == side) | (np.abs(pos[:, 0]) < 0.03), dist, 1e9)
            d[:, k] = dist
        # Out past the shoulders (sleeves, cuffs, anything held out in the T-pose) belongs to that arm.
        sh = abs(target[by_name['DEF-upper_arm.L']][0]) + 0.02
        arm_cols = [k for k, sg in enumerate(segs) if any(t in names[ljoints[sg[0]]] for t in ('upper_arm', 'forearm', 'hand'))]
        other = [k for k in range(len(segs)) if k not in arm_cols]
        # Only near arm height: a holster, pouch or sword hanging at the hip also sticks
        # out past the shoulders' width, but it belongs to the body, not the arm (bound
        # to the arm it swings up behind the back when the arms come down).
        outside = (np.abs(pos[:, 0]) > sh) & (pos[:, 1] > arm_y - 0.25)
        d[np.ix_(outside, other)] = 1e9
        order = np.argsort(d, axis=1)[:, :2]
        d1 = np.take_along_axis(d, order, 1)
        w = 1 / np.maximum(d1, 1e-4) ** 4
        w = w / w.sum(1, keepdims=True)
        J = np.zeros((n, 4), dtype='u1')
        W = np.zeros((n, 4), dtype='f4')
        J[:, :2] = np.array([segs[k][0] for k in range(len(segs))], dtype='u1')[order]
        W[:, :2] = w
        # Everything above the neck (head, hair, hats, helmets) moves with the head only.
        # (Arms in a T-pose sit at neck height, so only the middle, or clearly above the shoulders.)
        shoulder_x = abs(target[by_name['DEF-upper_arm.L']][0]) + 0.02
        above = (pos[:, 1] > neck_y + 0.03) & ((np.abs(pos[:, 0]) < shoulder_x) | (pos[:, 1] > arm_y + 0.18))
        J[above] = 0
        W[above] = 0
        J[above, 0] = head_i
        W[above, 0] = 1
        return J, W

    def smooth(pos, tri, J, W):
        """Blender-style 'bone heat': diffuse the nearest-bone weights over the surface so
        elbows, knees and shoulders bend smoothly instead of creasing. Solves
        (L + H) w = H w0 per bone, where H pulls each point toward its own nearest bones."""
        import scipy.sparse as sp
        from scipy.sparse.linalg import splu
        _, first, inv = np.unique(np.round(pos / 1e-5).astype('i8'), axis=0, return_index=True, return_inverse=True)
        inv = inv.reshape(-1)
        u = len(first)
        up = pos[first]
        cols = sorted(set(J[W > 0].tolist()))
        w0 = np.zeros((u, len(cols)))
        ci = {c: k for k, c in enumerate(cols)}
        for s in range(4):
            m = W[:, s] > 0
            np.add.at(w0, (inv[m], [ci[c] for c in J[m, s]]), W[m, s])
        w0 /= np.maximum(w0.sum(1, keepdims=True), 1e-9)
        t = inv[tri]
        e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
        e = e[e[:, 0] != e[:, 1]]
        A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(u, u)).tocsr()
        A = ((A + A.T) > 0).astype('f8')
        mean_edge = float(np.mean(np.linalg.norm(up[e[:, 0]] - up[e[:, 1]], axis=1)))
        L = (sp.diags(np.asarray(A.sum(1)).ravel()) - A) / mean_edge ** 2
        # Heat from the nearest bone: strong close to a bone, weak far away.
        d = np.full(u, 1e9)
        for _, a, b_, _s in segs:
            ab = b_ - a
            tt = np.clip(((up - a) @ ab) / (ab @ ab), 0, 1)
            d = np.minimum(d, np.linalg.norm(up - (a + tt[:, None] * ab), axis=1))
        H = SMOOTH_HEAT / np.maximum(d, 0.02) ** 2
        lu = splu((L + sp.diags(H)).tocsc())
        w = np.clip(lu.solve(H[:, None] * w0), 0, None)
        if w.shape[1] < 4:  # a part touched by fewer than 4 bones (face paint, hair): pad
            pad = 4 - w.shape[1]
            w = np.concatenate([w, np.zeros((u, pad))], axis=1)
            cols = cols + [cols[0]] * pad
        # Keep the four strongest bones per point.
        top = np.argsort(-w, axis=1)[:, :4]
        tw = np.take_along_axis(w, top, 1)
        tw /= np.maximum(tw.sum(1, keepdims=True), 1e-9)
        J2 = np.array(cols, dtype='u1')[top][inv]
        W2 = tw.astype('f4')[inv]
        # The head pinning (hats, hair) stays hard.
        pinned = (W[:, 0] == 1) & (J[:, 0] == head_i)
        J2[pinned], W2[pinned] = J[pinned], W[pinned]
        return J2, W2

    # 5. Assemble: the model's meshes (textures kept) + the fitted skeleton + clips.
    g = json.loads(json.dumps(src))
    b = bytearray(sbin)
    for key in ('skins', 'animations'):
        g.pop(key, None)
    base_nodes = len(g['nodes'])
    # Copy the library's skeleton nodes.
    remap = {}
    order_nodes = []

    def collect(i):
        if i in remap:
            return
        remap[i] = base_nodes + len(order_nodes)
        order_nodes.append(i)
        for c in lib['nodes'][i].get('children', []):
            if c in ljoints or any(c2 in ljoints for c2 in lib['nodes'][c].get('children', [])) or 'mesh' not in lib['nodes'][c]:
                if 'mesh' not in lib['nodes'][c]:
                    collect(c)
    roots = [j for j in ljoints if lparent.get(j) not in ljoints]
    top = roots[0]
    while top in lparent and 'mesh' not in lib['nodes'][lparent[top]]:
        top = lparent[top]
        if top not in lparent:
            break
    collect(top)
    for i in order_nodes:
        n = lib['nodes'][i]
        new = {'name': n.get('name', f'n{i}')}
        kids = [remap[c] for c in n.get('children', []) if c in remap]
        if kids:
            new['children'] = kids
        if i in ljoints:
            parent_world = new_world[lparent[i]] if lparent.get(i) in ljoints else (lworld(lparent[i]) if i in lparent else np.eye(4))
            local = np.linalg.inv(parent_world) @ new_world[i]
            t, q, s = mat_to_trs(local)
            new.update({'translation': t, 'rotation': q, 'scale': s})
        else:
            for k in ('translation', 'rotation', 'scale', 'matrix'):
                if k in n:
                    new[k] = n[k]
        g['nodes'].append(new)
    ibm = np.stack([np.linalg.inv(new_world[j]).T.astype('f4') for j in ljoints])
    ibm_view = add_view(g, b, ibm.tobytes())
    g['accessors'].append({'bufferView': ibm_view, 'componentType': 5126, 'count': len(ljoints), 'type': 'MAT4'})
    g['skins'] = [{'joints': [remap[j] for j in ljoints], 'inverseBindMatrices': len(g['accessors']) - 1, 'skeleton': remap[top]}]

    # One skinned mesh node holding every primitive, positions baked to the fitted space.
    new_prims = []
    for pi, (p, pos, nor) in enumerate(prims):
        if body_weights is not None:
            J, W = body_weights[pi]
        else:
            J, W = weights_for(pos)
        if body_weights is None and SMOOTH_HEAT and 'indices' in p:
            J, W = smooth(pos, accessor_array(src, sbin, p['indices']).reshape(-1, 3).astype('i8'), J, W)
        q = dict(p)
        q['attributes'] = dict(p['attributes'])
        pv = add_view(g, b, pos.astype('f4').tobytes())
        g['accessors'].append({'bufferView': pv, 'componentType': 5126, 'count': len(pos), 'type': 'VEC3', 'min': pos.min(0).tolist(), 'max': pos.max(0).tolist()})
        q['attributes']['POSITION'] = len(g['accessors']) - 1
        if nor is None and 'indices' in p:
            # No normals (e.g. TripoSR): smooth ones from the triangles.
            tri = accessor_array(src, sbin, p['indices']).reshape(-1, 3).astype('i8')
            fn = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
            nor = np.zeros_like(pos)
            for k in range(3):
                np.add.at(nor, tri[:, k], fn)
        if 'COLOR_0' in p['attributes'] and not src.get('materials'):
            # Vertex colours stored as sRGB bytes (TripoSR): convert to linear, as glTF expects.
            col = accessor_array(src, sbin, p['attributes']['COLOR_0'])
            lin = np.clip(col, 0, 1)
            lin[:, :3] = lin[:, :3] ** GAMMA
            cv = add_view(g, b, (np.round(lin * 255)).astype('u1').tobytes())
            g['accessors'].append({'bufferView': cv, 'componentType': 5121, 'normalized': True, 'count': len(lin), 'type': 'VEC4'})
            q['attributes']['COLOR_0'] = len(g['accessors']) - 1
        if nor is not None:
            nn = nor / np.maximum(np.linalg.norm(nor, axis=1, keepdims=True), 1e-9)
            nv = add_view(g, b, nn.astype('f4').tobytes())
            g['accessors'].append({'bufferView': nv, 'componentType': 5126, 'count': len(nn), 'type': 'VEC3'})
            q['attributes']['NORMAL'] = len(g['accessors']) - 1
        jv = add_view(g, b, J.tobytes())
        g['accessors'].append({'bufferView': jv, 'componentType': 5121, 'count': len(J), 'type': 'VEC4'})
        q['attributes']['JOINTS_0'] = len(g['accessors']) - 1
        wv = add_view(g, b, (np.round(W * 255)).astype('u1').tobytes())
        g['accessors'].append({'bufferView': wv, 'componentType': 5121, 'normalized': True, 'count': len(W), 'type': 'VEC4'})
        q['attributes']['WEIGHTS_0'] = len(g['accessors']) - 1
        new_prims.append(q)
    g['meshes'] = [{'name': 'character', 'primitives': new_prims}]
    g['nodes'].append({'name': 'character', 'mesh': 0, 'skin': 0})
    mesh_node = len(g['nodes']) - 1
    for n in g['nodes'][:base_nodes]:
        n.pop('mesh', None)
    g['scenes'] = [{'name': 'character', 'nodes': [remap[top], mesh_node]}]
    g['scene'] = 0

    # 6. Animations: library clips, rotations only (plus hip height), so fitted proportions hold.
    wanted = [tuple((x.split('=') + [''])[:2]) for x in (anims or DEFAULT_ANIMS).split(',') if x.strip()]
    lib_anims = {a['name']: a for a in lib.get('animations', [])}
    # Clips from the library's second half (sword combos, blocks, dashes) are brought
    # over after rigging; both halves use the same skeleton names.
    from model_tool import clip_table
    table = clip_table()
    later = [(f, t) for f, t in wanted if f not in lib_anims and f in table]
    missing = [f for f, _ in wanted if f not in lib_anims and f not in table]
    if missing:
        sys.exit(f'Unknown library clip(s): {", ".join(missing)} (see model_tool.py library).')
    wanted = [(f, t) for f, t in wanted if f in lib_anims]
    g['animations'] = []
    hips = by_name['DEF-hips']
    for frm, to in wanted:
        a = lib_anims[frm]
        samplers, channels = [], []
        for ch in a['channels']:
            node = ch['target']['node']
            if node not in remap or not (node in ljoints or node == top):
                continue
            nm = lib['nodes'][node].get('name', '')
            if 'f_' in nm or 'thumb' in nm:
                continue
            if ch['target']['path'] != 'rotation' and node != hips:
                continue
            sm = a['samplers'][ch['sampler']]
            new_sm = {}
            for key in ('input', 'output'):
                acc = dict(lib['accessors'][sm[key]])
                acc['bufferView'] = add_view(g, b, view_bytes(lib, lbin, acc['bufferView']))
                g['accessors'].append(acc)
                new_sm[key] = len(g['accessors']) - 1
            new_sm['interpolation'] = sm.get('interpolation', 'LINEAR')
            samplers.append(new_sm)
            channels.append({'sampler': len(samplers) - 1, 'target': {'node': remap[node], 'path': ch['target']['path']}})
        g['animations'].append({'name': to or frm, 'samplers': samplers, 'channels': channels})

    # Drop buffer data nothing references any more (the source's old geometry).
    used = set()
    for m in g['meshes']:
        for p in m['primitives']:
            used.update(p['attributes'].values())
            if 'indices' in p:
                used.add(p['indices'])
    used.add(g['skins'][0]['inverseBindMatrices'])
    for a in g['animations']:
        for s in a['samplers']:
            used.update((s['input'], s['output']))
    for img in g.get('images', []):
        if 'bufferView' in img:
            used.add(('view', img['bufferView']))
    acc_map, new_acc, view_map, new_views, chunks, length = {}, [], {}, [], [], 0

    def keep_view(vi):
        nonlocal length
        if vi not in view_map:
            v = g['bufferViews'][vi]
            data = bytes(b[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']])
            pad = (4 - length % 4) % 4
            if pad:
                chunks.append(b'\0' * pad)
                length += pad
            nv = {k: val for k, val in v.items() if k != 'byteOffset'}
            nv['byteOffset'] = length
            chunks.append(data)
            length += len(data)
            new_views.append(nv)
            view_map[vi] = len(new_views) - 1
        return view_map[vi]
    for i in sorted(x for x in used if isinstance(x, int)):
        acc = dict(g['accessors'][i])
        acc['bufferView'] = keep_view(acc['bufferView'])
        acc_map[i] = len(new_acc)
        new_acc.append(acc)
    for img in g.get('images', []):
        if 'bufferView' in img:
            img['bufferView'] = keep_view(img['bufferView'])
    for m in g['meshes']:
        for p in m['primitives']:
            p['attributes'] = {k: acc_map[v] for k, v in p['attributes'].items()}
            if 'indices' in p:
                p['indices'] = acc_map[p['indices']]
            p.pop('targets', None)
    g['skins'][0]['inverseBindMatrices'] = acc_map[g['skins'][0]['inverseBindMatrices']]
    for a in g['animations']:
        for s in a['samplers']:
            s['input'], s['output'] = acc_map[s['input']], acc_map[s['output']]
    g['accessors'], g['bufferViews'] = new_acc, new_views
    size = write_glb(out, g, bytearray(b''.join(chunks)))
    if later:
        import contextlib
        import io as _io
        from model_tool import add_anims
        with contextlib.redirect_stdout(_io.StringIO()):
            add_anims(out, out, ','.join(f'{f}={t or f}' for f, t in later))
        size = Path(out).stat().st_size
        g['animations'] += [{'name': t or f} for f, t in later]
    # Closed fists on both hands, so held items are gripped rather than lying on an open palm.
    from model_tool import fists
    fg, fb = read_glb(out)
    if fists(fg):
        size = write_glb(out, fg, fb)
    print(json.dumps({'ok': True, 'out': str(out), 'bytes': size, 'arm_height': round(arm_y, 3), 'reach': round(reach, 3),
                      'animations': [a['name'] for a in g['animations']],
                      'next': 'Render idle/walk/attack with model_tool.py render and Read them. Over 3 MB: rebuild the model with a lower texture size.'}))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['concept', 'local3d', 'online3d', 'upright', 'rig', 'cutout', 'weapon'])
    p.add_argument('args', nargs='+')
    p.add_argument('--seed', type=int)
    p.add_argument('--wide', action='store_true')
    p.add_argument('--res', type=int, default=192, help='local3d detail (160 for props keeps files small)')
    p.add_argument('--picture', action='store_true', help='concept: a plain picture (sky, background, ground texture); add --wide for 768x512')
    p.add_argument('--body', choices=['humanoid', 'fourlegs', 'wings', 'any'], help='concept: a non-human character (four legs, wings, or any other shape); humanoid is the default T-pose')
    p.add_argument('--build', choices=['slim', 'average', 'heavy', 'huge', 'small', 'lanky'], help='concept (humanoid): body build; changes the pose guide proportions and bulk')
    p.add_argument('--object', action='store_true', help='concept: one object (tree, coin, house) instead of a T-pose character')
    p.add_argument('--flip', action='store_true', help='rig: turn the model to face the other way; weapon: swap which end is the handle')
    p.add_argument('--yup', action='store_true', help='rig: a 3D AI Studio model: it already stands up along +Y (kept instead of guessing from the tallest side) and is turned to face forward (--flip reverses that)')
    p.add_argument('--no-body', action='store_true', help='rig: keep the picture-to-3D body instead of fitting a real human body under it')
    p.add_argument('--length', type=float, default=1.0, help='weapon: its length in metres (a person is 1.8; katana 1.0, club 1.3, spear 2.2, dagger 0.4)')
    p.add_argument('--grip', type=float, default=0.12, help='weapon: where the hand holds it, as a fraction of its length from the bottom (swords/clubs 0.12, spears/staffs 0.4)')
    p.add_argument('--empty-hands', action='store_true', help='concept (humanoid): draw no weapon or held item (a weapon is made separately and equipped)')
    p.add_argument('--no-project', action='store_true', help="local3d: keep TripoSR's own colours (skip painting the picture onto the front)")
    p.add_argument('--init', help='concept: edit this picture instead of drawing from nothing (keeps the same character)')
    p.add_argument('--strength', type=float, default=0.55, help='concept --init: how much may change (0.3 small touch-up, 0.55 clear change, 0.8 nearly new)')
    p.add_argument('--style', help='concept: the look in any words, e.g. "PS2 Silent Hill graphics", "claymation", "anime"')
    a = p.parse_args()
    if a.action == 'concept':
        concept(a.args[0], a.args[1], a.seed, a.wide, a.object, a.picture, a.body, a.build, a.empty_hands,
                a.init, a.strength, a.style)
    elif a.action == 'upright':
        upright(a.args[0], a.args[1], float(a.args[2]) if len(a.args) > 2 else 1.0)
    elif a.action == 'online3d':
        online3d(a.args[0], a.args[1], a.seed or 1)
    elif a.action == 'local3d':
        local3d(a.args[0], a.args[1], a.res, not a.no_project)
    elif a.action == 'cutout':
        cutout(a.args[0], a.args[1])
    elif a.action == 'weapon':
        weapon(a.args[0], a.args[1], a.length, a.grip, a.flip)
    else:
        rig(a.args[0], a.args[1], a.args[2] if len(a.args) > 2 else None, a.flip, 'guess' if a.no_body else None, a.yup)


if __name__ == '__main__':
    main()
