"""A real human body under a picture-to-3D character.

Picture-to-3D (TripoSR) sees only the front, so the body it guesses is thin from the
side, lumpy at the back and oddly shaped around the arms. For a humanoid we instead
take the animation library's rigged mannequin (a proper human body, T-pose, the same
53-bone skeleton the clips drive), fit it to the character, and keep from the guess
only what sticks out from that body (hat brims, holsters, skirts, big boots):

1. Proportions: the mannequin follows the skeleton fitted to the character (rig()).
2. Build: each bone's flesh is scaled to the character's thickness seen from the
   front (per quarter of the bone), and its depth follows at a gentler rate.
3. Clothes: parts of the guessed model more than CLOTH_GAP outside the fitted body.
4. Colours: baked from the guessed model onto body + clothes (blender_bake.py).
5. Skin weights: the mannequin's own for the body; each clothing point takes the
   weights of the nearest body point.

detailed.rig(..., body='human') calls fit(); it returns the new model in rig()'s
standing space plus its skin weights.
"""
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import gs_deps  # noqa: E402,F401  (reinstalls basic packages after a container replacement)
import numpy as np

REMESH_VOXEL = 0.012  # metres: body and clothes fused into one closed surface at this detail
HUG = 0.05  # metres: torso clothing is pulled in to at most this far from the body
CLOTH_GAP = 0.02  # metres outside the body before a guessed part counts as clothing
CLOTH_GAP_LEG = 0.1  # on the legs: only a skirt, robe or coat hem stands this far clear
MAIN = ['DEF-hips', 'DEF-spine.001', 'DEF-spine.002', 'DEF-spine.003', 'DEF-neck', 'DEF-head'] + [
    f'DEF-{b}.{s}' for s in 'LR' for b in ('shoulder', 'upper_arm', 'forearm', 'hand', 'thigh', 'shin', 'foot', 'toe')]
CHILD = {'DEF-hips': 'DEF-spine.001', 'DEF-spine.001': 'DEF-spine.002', 'DEF-spine.002': 'DEF-spine.003',
         'DEF-spine.003': 'DEF-neck', 'DEF-neck': 'DEF-head'}
for _s in 'LR':
    CHILD.update({f'DEF-shoulder.{_s}': f'DEF-upper_arm.{_s}', f'DEF-upper_arm.{_s}': f'DEF-forearm.{_s}',
                  f'DEF-forearm.{_s}': f'DEF-hand.{_s}', f'DEF-thigh.{_s}': f'DEF-shin.{_s}',
                  f'DEF-shin.{_s}': f'DEF-foot.{_s}', f'DEF-foot.{_s}': f'DEF-toe.{_s}'})
# How much each part may be widened or narrowed to match the character.
LIMITS = {'head': (0.9, 1.2), 'neck': (0.85, 1.4), 'hand': (0.8, 1.3), 'toe': (0.8, 1.4), 'foot': (0.8, 1.5)}
DEFAULT_LIMIT = (0.75, 1.8)


def _segments(names, target):
    """(name, start, end, side) per main bone, positioned on the fitted skeleton."""
    by = {n: j for j, n in names.items()}
    segs = []
    for n in MAIN:
        a = target[by[n]]
        if n in CHILD:
            b = target[by[CHILD[n]]]
        elif 'head' in n:
            b = a + np.array([0, 0.25, 0])
        elif 'hand' in n:
            b = a + np.array([0.12 if n.endswith('L') else -0.12, 0, 0])
        else:
            b = a + np.array([0, 0, 0.1])
        segs.append((n, a, b, 1 if n.endswith('.L') else -1 if n.endswith('.R') else 0))
    return segs


def _nearest_segment(P, segs):
    """Index of the nearest bone segment per point (limbs stay on their own side), and t along it."""
    best = np.full(len(P), 1e9)
    idx = np.zeros(len(P), int)
    tt = np.zeros(len(P))
    for k, (_, a, b, side) in enumerate(segs):
        ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(P - (a + t[:, None] * ab), axis=1)
        if side:
            d = np.where((np.sign(P[:, 0]) == side) | (np.abs(P[:, 0]) < 0.03), d, 1e9)
        better = d < best
        best[better], idx[better], tt[better] = d[better], k, t[better]
    return idx, tt, best


def _front_radius(P, seg):
    """Distance from the bone as seen from the front (depth ignored)."""
    _, a, b, _ = seg
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    off = P - (a + t[:, None] * ab)
    return np.hypot(off[:, 0], off[:, 1]), t


def _mannequin(lib, lbin, dt):
    """The library mannequin: positions, triangles and skin (joint indices into the skin's joint list)."""
    node = next(n for n in lib['nodes'] if 'mesh' in n and 'skin' in n)
    mesh = lib['meshes'][node['mesh']]
    P, F, J, W = [], [], [], []
    for p in mesh['primitives']:
        base = sum(len(x) for x in P)
        P.append(dt.accessor_array(lib, lbin, p['attributes']['POSITION']).astype('f8'))
        F.append(dt.accessor_array(lib, lbin, p['indices']).reshape(-1, 3).astype('i8') + base)
        J.append(dt.accessor_array(lib, lbin, p['attributes']['JOINTS_0']).astype('i8'))
        w = dt.accessor_array(lib, lbin, p['attributes']['WEIGHTS_0']).astype('f8')
        W.append(w / np.maximum(w.sum(1, keepdims=True), 1e-9))
    skin = lib['skins'][node['skin']]
    ibm = dt.accessor_array(lib, lbin, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
    return np.concatenate(P), np.concatenate(F), np.concatenate(J), np.concatenate(W), skin['joints'], ibm


def _weld(P, F, tol=1e-5):
    _, first, inv = np.unique(np.round(P / tol).astype('i8'), axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    return first, inv


def fit(prims, src, sbin, lib, lbin, ljoints, names, new_world, target, workdir=None):
    """Return (glb dict, binary, prims, weights) for the fitted body + clothes, ready for rig()'s assembly."""
    import trimesh
    from PIL import Image
    import detailed as dt

    work = Path(workdir or tempfile.mkdtemp(prefix='body-', dir=os.environ.get('TMPDIR')))

    # The character as rig() stood it up: one textured mesh.
    CP, CF, CUV = [], [], []
    for p, pos, _ in prims:
        base = sum(len(x) for x in CP)
        CP.append(pos)
        CF.append(dt.accessor_array(src, sbin, p['indices']).reshape(-1, 3).astype('i8') + base)
        CUV.append(dt.accessor_array(src, sbin, p['attributes']['TEXCOORD_0']).astype('f8')
                   if 'TEXCOORD_0' in p['attributes'] else np.zeros((len(pos), 2)))
    CP, CF, CUV = np.concatenate(CP), np.concatenate(CF), np.concatenate(CUV)
    CUV[:, 1] = 1 - CUV[:, 1]  # glTF counts v from the top, trimesh from the bottom (it flips back on export)
    image = None
    if src.get('images'):
        view = src['bufferViews'][src['images'][0]['bufferView']]
        start = view.get('byteOffset', 0)
        image = Image.open(io.BytesIO(bytes(sbin[start:start + view['byteLength']]))).convert('RGB')
    char = trimesh.Trimesh(CP, CF, process=False)
    if image is not None:
        char.visual = trimesh.visual.TextureVisuals(uv=CUV, material=trimesh.visual.material.PBRMaterial(
            baseColorTexture=image, metallicFactor=0.0, roughnessFactor=0.9))  # unspecified metal = 1 in glTF: a black bake
    char.export(work / 'character.glb')

    # 1. The mannequin, moved onto the fitted skeleton (linear blend skinning).
    MP, MF, MJ, MW, mjoints, ibm = _mannequin(lib, lbin, dt)
    move = np.stack([new_world[j] @ ibm[k] for k, j in enumerate(mjoints)])
    H = np.c_[MP, np.ones(len(MP))]
    M1 = np.zeros_like(MP)
    for s in range(MJ.shape[1]):
        M1 += MW[:, s:s + 1] * np.einsum('nij,nj->ni', move[MJ[:, s]], H)[:, :3]

    # 2. Thickness per bone quarter, from the character's front silhouette.
    segs = _segments(names, target)
    cseg, ct, _ = _nearest_segment(CP, segs)
    mseg, mt, _ = _nearest_segment(M1, segs)
    bins = 4
    scale = np.ones((len(segs), bins))
    for k, seg in enumerate(segs):
        cr, _ = _front_radius(CP[cseg == k], seg)
        mr, _ = _front_radius(M1[mseg == k], seg)
        cb = np.minimum((ct[cseg == k] * bins).astype(int), bins - 1)
        mb = np.minimum((mt[mseg == k] * bins).astype(int), bins - 1)
        kind = next((key for key in LIMITS if key in seg[0]), None)
        lo, hi = LIMITS.get(kind, DEFAULT_LIMIT)
        for q in range(bins):
            c, m = cr[cb == q], mr[mb == q]
            if len(c) >= 15 and len(m) >= 5 and np.percentile(m, 85) > 1e-3:
                scale[k, q] = np.clip(np.percentile(c, 85) / np.percentile(m, 85), lo, hi)
        # A gentle blend between quarters so the surface doesn't step.
        scale[k] = np.convolve(np.pad(scale[k], 1, mode='edge'), [0.25, 0.5, 0.25], mode='valid')
    s_at = lambda k, t: np.interp(t * bins - 0.5, np.arange(bins), scale[k])
    M2 = M1.copy()
    for k, seg in enumerate(segs):
        sel = mseg == k
        if not sel.any():
            continue
        _, a, b, _ = seg
        ab = b - a
        P = M1[sel]
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        on = a + t[:, None] * ab
        off = P - on
        s = s_at(k, t)[:, None]
        # Width follows the character fully; depth follows more gently (the front view can't see it).
        grow = np.c_[s[:, 0], s[:, 0], s[:, 0] ** 0.6]
        M2[sel] = on + off * grow
    # Smooth the seams between bones (a few averaging passes over welded neighbours).
    first, inv = _weld(M2, MF)
    U = M2[first].copy()
    e = inv[MF]
    edges = np.concatenate([e[:, [0, 1]], e[:, [1, 2]], e[:, [2, 0]]])
    for _ in range(3):
        acc = np.zeros_like(U)
        cnt = np.zeros(len(U))
        np.add.at(acc, edges[:, 0], U[edges[:, 1]])
        np.add.at(cnt, edges[:, 0], 1)
        U = 0.5 * U + 0.5 * acc / np.maximum(cnt, 1)[:, None]
    M2 = U[inv]
    # The head stays the character's own (face, hair, hat are what make it recognisable,
    # and the guess gets them right from the front): the body ends partway up the neck.
    by = {n: j for j, n in names.items()}
    neck_y, head_y = target[by['DEF-neck']][1], target[by['DEF-head']][1]
    cut = neck_y + 0.5 * (head_y - neck_y)
    # Either side of the middle: the neck's width (not collars or shoulders) up to the skull's
    # base, and wider above it for hat brims and big hair.
    above = lambda P: (P[:, 1] > cut) & (np.abs(P[:, 0]) < np.where(P[:, 1] > head_y + 0.13, 0.3, 0.09))
    body = trimesh.Trimesh(M2, MF[~((M2[:, 1] > cut) & (np.abs(M2[:, 0]) < 0.12))[MF].all(1)], process=False)

    # 3. Clothes: parts of the guess clearly outside the body.
    # Distance to a dense sample of the body's surface (5 mm apart) is plenty here.
    from scipy.spatial import cKDTree
    samples, sface = trimesh.sample.sample_surface_even(body, 80000, radius=0.004, seed=1)
    dist, near = cKDTree(samples).query(CP)
    outward = np.einsum('ij,ij->i', CP - samples[near], body.face_normals[sface[near]]) > 0
    outside = outward & (dist > CLOTH_GAP)
    # Nothing on the arms: they are fitted to the sleeves already, and a loose sleeve
    # piece bound to the chest would stick out when the arms come down.
    on_arm = np.isin(cseg, [k for k, sg in enumerate(segs) if any(w in sg[0] for w in ('shoulder', 'upper_arm', 'forearm', 'hand'))])
    # Around the shoulders too (collars and shoulder pads would stay up when the arms drop).
    arm_line = target[by['DEF-upper_arm.L']][1]
    on_arm |= (CP[:, 1] > arm_line - 0.12) & (np.abs(CP[:, 0]) > 0.14)
    # On the legs only what stands well clear of them (a skirt or a coat's hem), never
    # the guessed legs themselves: a second, slightly offset pair of legs.
    on_leg = np.isin(cseg, [k for k, sg in enumerate(segs) if any(w in sg[0] for w in ('thigh', 'shin', 'foot', 'toe'))])
    outside &= ~on_leg | (dist > CLOTH_GAP_LEG)
    # Around the neck, nothing but the head itself: a guessed collar there turns into
    # spikes by the face (it is painted onto the body instead).
    on_neck = np.isin(cseg, [k for k, sg in enumerate(segs) if sg[0] in ('DEF-neck', 'DEF-head')])
    outside &= ~on_neck
    keep = ((outside & ~on_arm) | above(CP))[CF].all(1)
    # Clothing around the chest, belly and back hugs the body: a coat or cloak the
    # guess left standing off the back would otherwise hang like a loose board.
    on_torso = np.isin(cseg, [k for k, sg in enumerate(segs) if sg[0].startswith('DEF-spine') or sg[0] == 'DEF-hips'])
    far = on_torso & (dist > HUG) & ~above(CP)
    if far.any():
        CP = CP.copy()
        pull = (CP[far] - samples[near[far]]) / np.maximum(dist[far], 1e-6)[:, None]
        CP[far] = samples[near[far]] + pull * HUG
    cloth = trimesh.Trimesh(CP, CF[keep], process=False)
    cloth.remove_unreferenced_vertices()
    if len(cloth.faces):
        dt.drop_floaters(cloth, keep=0.05)  # scraps along the body's edge are not clothing
    if len(cloth.faces):
        cloth.export(work / 'clothes.glb')  # kept for inspection
    # Two parts for Blender: the body and its clothes, fused into one closed surface,
    # and the character's own head (hair, hats, faces), kept as drawn.
    head_face = above(CP)[CF].all(1) & keep
    parts = trimesh.util.concatenate([body, cloth]) if len(cloth.faces) else body
    scene = trimesh.Scene()
    if len(cloth.faces):
        headless = trimesh.Trimesh(CP, CF[keep & ~head_face], process=False)
        headless.remove_unreferenced_vertices()
        parts = trimesh.util.concatenate([body, headless]) if len(headless.faces) else body
    scene.add_geometry(parts, node_name='fuse', geom_name='fuse')
    if head_face.any():
        head = trimesh.Trimesh(CP, CF[head_face], process=False)
        head.remove_unreferenced_vertices()
        scene.add_geometry(head, node_name='keep', geom_name='keep')
    scene.export(work / 'fitted.glb')

    # 4. Colours from the guess onto body + clothes.
    blender = dt.ensure_blender()
    if not blender:
        raise RuntimeError('Blender is needed to paint the body.')
    script = Path(__file__).resolve().parent / 'blender_bake.py'
    # Rays start well outside the body: loose clothes (baggy jeans, a coat) sit several
    # centimetres out, and a ray starting inside them misses and paints black.
    proc = subprocess.run([str(blender), '-b', '--python', str(script), '--', str(work / 'character.glb'),
                           str(work / 'fitted.glb'), str(work / 'baked.glb'), '--cage', '0.14', '--ray', '0.3',
                           # One closed surface: no gaps between body and clothes, no loose flaps.
                           '--remesh', str(REMESH_VOXEL), '--faces', '24000'],
                          capture_output=True, text=True, timeout=900)
    if 'BAKE_OK' not in proc.stdout:
        raise RuntimeError('Painting the body failed: ' + (proc.stderr or proc.stdout)[-400:])
    g, b = dt.read_glb(work / 'baked.glb')

    # 5. Skin weights: the mannequin's for the body, the nearest body point's for clothes.
    from scipy.spatial import cKDTree
    body_w = np.zeros((len(M2), 4), 'f8')
    body_j = np.zeros((len(M2), 4), 'i8')
    k = min(4, MJ.shape[1])
    order = np.argsort(-MW, axis=1)[:, :k]
    body_j[:, :k] = np.take_along_axis(MJ, order, 1)
    body_w[:, :k] = np.take_along_axis(MW, order, 1)
    body_w /= np.maximum(body_w.sum(1, keepdims=True), 1e-9)
    # mjoints are node ids in the library; rig() writes the skin in ljoints order.
    to_skin = np.array([ljoints.index(j) for j in mjoints])
    body_j = to_skin[body_j]
    tree = cKDTree(M2)
    world, _ = dt.world_matrices(g)
    out_prims, weights = [], []
    for ni, n in enumerate(g.get('nodes', [])):
        if 'mesh' not in n:
            continue
        m = world(ni)
        for p in g['meshes'][n['mesh']]['primitives']:
            pos = dt.accessor_array(g, b, p['attributes']['POSITION']).astype('f8')
            pos = (np.c_[pos, np.ones(len(pos))] @ m.T)[:, :3]
            nor = dt.accessor_array(g, b, p['attributes']['NORMAL']).astype('f8') @ m[:3, :3].T if 'NORMAL' in p['attributes'] else None
            _, near = tree.query(pos)
            out_prims.append((p, pos, nor))
            weights.append((body_j[near].astype('u1'), body_w[near].astype('f4')))
    return g, b, out_prims, weights
