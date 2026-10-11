#!/usr/bin/env python3
"""Skeletons and animations for characters that are not human-shaped.

  python3 creature.py RAW.glb OUT.glb --body fourlegs|wings|any [--flip] [--height 1.0]

RAW.glb is a 3D AI Studio text-to-3D model (pass --yup: it is already Y up, facing +Z),
or an older TripoSR model (Z up, the picture's camera on +X). The model comes out standing on the ground, facing +Z (like the
humanoid rig), with the same clip names games already use:
idle, walk, run, jump, attack, hurt, die.

  fourlegs  dogs, cats, horses, wolves, dinosaurs, dragons on the ground. Drawn in a
            three-quarter view facing LEFT; four legs, spine, neck, head and tail.
  wings     birds, bats, butterflies, flying dragons. Drawn from the front with the
            wings spread; wings flap, glide and dive (walk/run = flying).
  any       every other shape: slimes, ghosts, blobs, robots on wheels, cars, plant
            monsters, fish. Drawn from the front; squash-and-stretch hops, lunges,
            wobbles and tips over.
--flip turns it around if it faces backwards in the check render.
All motion is generated here (no library), so it works for any size or shape.
"""
import argparse
import io
import json
import math
import sys
from pathlib import Path

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import gs_deps  # noqa: E402,F401  (reinstalls basic packages after a container replacement)
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_tool import add_view, write_glb  # noqa: E402

FPS = 30
# attack, attack2, attack3 chain into a combo.
CLIPS = ('idle', 'walk', 'run', 'jump', 'attack', 'attack2', 'attack3', 'hurt', 'die')
# What a new creature gets unless more is asked for (--clips): the basics. Vehicles
# only idle and drive (walk = drive, run = drive fast); no one gives a car a heavy attack.
BASIC = ('idle', 'walk', 'run', 'jump', 'hurt', 'die')
VEHICLE = ('idle', 'walk', 'run')


# ---------- quaternions ----------

def quat(axis, angle):
    axis = np.asarray(axis, 'f8')
    axis = axis / np.linalg.norm(axis)
    s = math.sin(angle / 2)
    return np.array([axis[0] * s, axis[1] * s, axis[2] * s, math.cos(angle / 2)])


def qmul(a, b):
    x1, y1, z1, w1 = a
    x2, y2, z2, w2 = b
    return np.array([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2])


def rx(a):
    return quat((1, 0, 0), a)


def ry(a):
    return quat((0, 1, 0), a)


def rz(a):
    return quat((0, 0, 1), a)


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def env(t, a, b, c, d):
    """0 before a, rises to 1 by b, holds, falls back to 0 by d."""
    if t <= a or t >= d:
        return 0.0
    if t < b:
        return ease((t - a) / (b - a))
    if t <= c:
        return 1.0
    return 1 - ease((t - c) / (d - c))


# ---------- loading ----------

def load(raw, flip, body, yup=False):
    import trimesh
    scene = trimesh.load(raw, force='scene')
    parts = [g for g in scene.dump() if isinstance(g, trimesh.Trimesh)]
    mesh = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
    # TripoSR: Z up, camera on +X  ->  Y up, camera on +Z (a front view faces +Z).
    # 3D AI Studio (text-to-3D) models are already Y up and facing +Z (--yup).
    if not yup:
        mesh.apply_transform(np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, 1]], 'f8'))
    V = np.asarray(mesh.vertices, 'f8')
    if body == 'fourlegs':
        # Drawn facing left in a three-quarter view: the body's long axis lies in the
        # ground plane; turn it so the head (the image-left end, -X) points to +Z.
        xz = V[:, [0, 2]] - V[:, [0, 2]].mean(0)
        _, _, vt = np.linalg.svd(xz, full_matrices=False)
        axis = vt[0]
        if axis[0] > 0:
            axis = -axis
        ang = math.atan2(axis[0], axis[1])  # angle from +Z toward +X
        c, s = math.cos(-ang), math.sin(-ang)
        mesh.apply_transform(np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]], 'f8'))
    if flip:
        mesh.apply_transform(np.diag([-1, 1, -1, 1]).astype('f8'))
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    return mesh


# ---------- skeletons ----------
# Each joint: name -> (parent or None, world position). Rest rotations are identity,
# so every joint's axes are the world axes (X right, Y up, Z forward).

def fourlegs_skeleton(V):
    h = V[:, 1].max()
    zmin, zmax = V[:, 2].min(), V[:, 2].max()
    L = zmax - zmin
    # Belly: the lowest height where the body covers most of its length (legs don't).
    belly = 0.45 * h
    for yy in np.linspace(0.12 * h, 0.7 * h, 30):
        sl = V[np.abs(V[:, 1] - yy) < 0.025 * h]
        if len(sl) < 20:
            continue
        occ = np.unique(((sl[:, 2] - zmin) / L * 24).astype(int).clip(0, 23)).size / 24
        if occ >= 0.6:
            belly = yy
            break
    feet = V[V[:, 1] < max(0.3 * belly, 0.04 * h)]
    if len(feet) < 8:
        feet = V[V[:, 1] < 0.15 * h]
    # Front and back feet: split at the biggest gap along the body.
    zs = np.sort(feet[:, 2])
    gaps = np.diff(zs)
    lo_i, hi_i = int(len(zs) * 0.15), int(len(zs) * 0.85)
    cut = zs[lo_i + int(np.argmax(gaps[lo_i:hi_i]))] if hi_i > lo_i + 1 else np.median(zs)
    legs = {}
    for end, sel in (('front', feet[:, 2] > cut), ('back', feet[:, 2] <= cut)):
        grp = feet[sel] if sel.sum() >= 4 else feet
        zc = float(np.median(grp[:, 2]))
        xs = grp[:, 0]
        spread = max(float(np.percentile(xs, 85) - np.percentile(xs, 15)) / 2, 0.06 * h)
        xc = float(np.median(xs))
        for side, sx in (('L', 1), ('R', -1)):
            legs[f'{end}.{side}'] = np.array([xc + sx * spread * 0.8, 0.02 * h, zc])
    top = np.percentile(V[:, 1], 97)
    spine_y = belly + (top - belly) * 0.35
    zb, zf = legs['back.L'][2], legs['front.L'][2]
    head_pts = V[V[:, 2] > zmax - 0.18 * L]
    head = head_pts.mean(0) if len(head_pts) else np.array([0, top, zmax])
    J = {
        'root': (None, np.array([0, 0, (zb + zf) / 2])),
        'hips': ('root', np.array([0, spine_y, zb])),
        'spine': ('hips', np.array([0, spine_y, (zb + zf) / 2])),
        'chest': ('spine', np.array([0, spine_y, zf])),
        'neck': ('chest', np.array([0, (spine_y + head[1]) / 2 + 0.05 * h, zf + (head[2] - zf) * 0.45])),
        'head': ('neck', np.array([0, head[1], head[2] - 0.35 * (zmax - head[2]) - 0.05 * L])),
        'tail': ('hips', np.array([0, spine_y, zb - (zb - zmin) * 0.35])),
        'tail2': ('tail', np.array([0, spine_y, zmin + 0.08 * L])),
    }
    for name, foot in legs.items():
        end, side = name.split('.')
        parent = 'chest' if end == 'front' else 'hips'
        hip = np.array([foot[0] * 0.85, belly + 0.02 * h, foot[2]])
        knee = np.array([foot[0] * 0.95, belly * 0.5, foot[2] + (0.03 if end == 'back' else -0.03) * L])
        J[f'upper.{name}'] = (parent, hip)
        J[f'lower.{name}'] = (f'upper.{name}', knee)
        J[f'foot.{name}'] = (f'lower.{name}', foot)
    tips = {'head': np.array([0, head[1], zmax]), 'tail2': np.array([0, spine_y, zmin])}
    return J, tips, {'belly': belly, 'h': h, 'L': L, 'cut': cut}


def wings_skeleton(V):
    h = V[:, 1].max()
    half = np.abs(V[:, 0]).max()
    # Body: where the shape is tall; wings: where it thins out sideways.
    cols = np.linspace(0, half, 25)
    heights = []
    for x0, x1 in zip(cols[:-1], cols[1:]):
        sl = V[(np.abs(V[:, 0]) >= x0) & (np.abs(V[:, 0]) < x1)]
        heights.append(np.ptp(sl[:, 1]) if len(sl) > 5 else 0)
    heights = np.array(heights)
    root_x = 0.2 * half
    for i, v in enumerate(heights):
        if i > 1 and v < 0.6 * heights[:2].max():
            root_x = cols[i]
            break
    root_x = float(np.clip(root_x, 0.1 * half, 0.45 * half))
    wing = V[np.abs(V[:, 0]) > root_x]
    wing_y = float(np.median(wing[:, 1])) if len(wing) else 0.6 * h
    body = V[np.abs(V[:, 0]) <= root_x]
    head_y = float(np.percentile(body[:, 1], 80)) if len(body) else 0.8 * h
    J = {
        'root': (None, np.array([0, 0, 0])),
        'body': ('root', np.array([0, wing_y, 0])),
        'head': ('body', np.array([0, head_y, 0])),
        'tail': ('body', np.array([0, max(0.02 * h, wing_y - 0.35 * h), 0])),
    }
    for side, sx in (('L', 1), ('R', -1)):
        J[f'wing.{side}'] = ('body', np.array([sx * root_x, wing_y, 0]))
        J[f'wing2.{side}'] = (f'wing.{side}', np.array([sx * (root_x + (half - root_x) * 0.5), wing_y, 0]))
    tips = {'head': np.array([0, h, 0]), 'wing2.L': np.array([half, wing_y, 0]), 'wing2.R': np.array([-half, wing_y, 0]),
            'tail': np.array([0, 0, 0])}
    return J, tips, {'h': h, 'root_x': root_x, 'half': half}


def any_skeleton(V):
    h = V[:, 1].max()
    J = {
        'root': (None, np.array([0, 0, 0])),
        'base': ('root', np.array([0, 0.02 * h, 0])),
        'mid': ('base', np.array([0, 0.4 * h, 0])),
        'top': ('mid', np.array([0, 0.75 * h, 0])),
    }
    return J, {'top': np.array([0, 1.05 * h, 0])}, {'h': h}


# ---------- skin weights ----------

def weights(V, F, J, tips, body, info):
    names = list(J)
    kids = {}
    for n, (p, _) in J.items():
        if p:
            kids.setdefault(p, []).append(n)
    segs = []
    for n in names:
        if n == 'root':
            continue
        a = J[n][1]
        if n in tips:
            b = tips[n]
        elif n in kids:
            b = np.mean([J[k][1] for k in kids[n]], 0)
        else:
            b = a + np.array([0, 0.02, 0.02])
        segs.append((names.index(n), n, a, b))
    D = np.full((len(V), len(segs)), 1e9)
    for k, (_, n, a, b) in enumerate(segs):
        ab = b - a
        t = np.clip(((V - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        D[:, k] = np.linalg.norm(V - (a + t[:, None] * ab), axis=1)
    h = info['h']
    if body == 'fourlegs':
        low = V[:, 1] < info['belly'] - 0.04 * h
        for k, (_, n, a, b) in enumerate(segs):
            if '.' in n:
                end, side = n.split('.')[1:]
                sx = 1 if side == 'L' else -1
                zc = (J['upper.front.L'][1][2] + J['upper.front.R'][1][2]) / 2 if end == 'front' else (J['upper.back.L'][1][2] + J['upper.back.R'][1][2]) / 2
                xc = (J[f'upper.{end}.L'][1][0] + J[f'upper.{end}.R'][1][0]) / 2
                wrong = (np.sign(V[:, 0] - xc) != sx) | ((V[:, 2] > info['cut']) != (end == 'front'))
                D[wrong, k] = 1e9
            elif low.any():
                D[low, k] = 1e9  # below the belly is legs only
    elif body == 'wings':
        rx_ = info['root_x']
        for k, (_, n, a, b) in enumerate(segs):
            if n.startswith('wing'):
                sx = 1 if n.endswith('L') else -1
                D[(np.sign(V[:, 0]) != sx) | (np.abs(V[:, 0]) < rx_ * 0.8), k] = 1e9
            else:
                D[np.abs(V[:, 0]) > rx_ * 1.2, k] = 1e9
    order = np.argsort(D, 1)[:, :2]
    d = np.take_along_axis(D, order, 1)
    w = 1 / np.maximum(d, 1e-4) ** 4
    w /= w.sum(1, keepdims=True)
    W0 = np.zeros((len(V), len(names)))
    joint_of = np.array([s[0] for s in segs])
    np.put_along_axis(W0, joint_of[order], w, 1)
    return smooth(V, F, W0, np.min(D, 1))


def smooth(V, F, W0, dist, heat=1.0):
    """Bone heat (as in detailed.py rig): diffuse weights over the surface for soft bends."""
    import scipy.sparse as sp
    from scipy.sparse.linalg import splu
    _, first, inv = np.unique(np.round(V / 1e-5).astype('i8'), axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    u = len(first)
    w0 = np.zeros((u, W0.shape[1]))
    np.add.at(w0, inv, W0)
    w0 /= np.maximum(w0.sum(1, keepdims=True), 1e-9)
    t = inv[F]
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    e = e[e[:, 0] != e[:, 1]]
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(u, u)).tocsr()
    A = ((A + A.T) > 0).astype('f8')
    up = V[first]
    mean_edge = float(np.mean(np.linalg.norm(up[e[:, 0]] - up[e[:, 1]], axis=1))) or 1e-3
    L = (sp.diags(np.asarray(A.sum(1)).ravel()) - A) / mean_edge ** 2
    d = np.zeros(u)
    np.maximum.at(d, inv, dist)
    H = heat / np.maximum(d, 0.02) ** 2
    lu = splu((L + sp.diags(H)).tocsc())
    w = np.clip(lu.solve(H[:, None] * w0), 0, None)
    top = np.argsort(-w, 1)[:, :4]
    tw = np.take_along_axis(w, top, 1)
    tw /= np.maximum(tw.sum(1, keepdims=True), 1e-9)
    return top[inv].astype('u1'), tw[inv].astype('f4')


# ---------- animation ----------
# Each clip: (seconds, looping, fn(t) -> {joint: {'r': quat, 't': offset, 's': scale}}).

def fourlegs_clips(J, info):
    h = info['h']
    legs = [n.split('.', 1)[1] for n in J if n.startswith('upper.')]
    # Diagonal pairs move together at a trot; a gallop pairs front and back.
    trot = {'front.L': 0, 'back.R': 0, 'front.R': math.pi, 'back.L': math.pi}
    gallop = {'front.L': 0, 'front.R': 0.5, 'back.L': math.pi, 'back.R': math.pi + 0.5}

    def gait(t, period, phases, swing, lift, bob, lean=0.0):
        out = {}
        w = 2 * math.pi * t / period
        for leg in legs:
            ph = w + phases[leg]
            out[f'upper.{leg}'] = {'r': rx(-swing * math.sin(ph))}
            bend = lift * max(0.0, math.cos(ph))
            out[f'lower.{leg}'] = {'r': rx(bend if leg.startswith('back') else -bend)}
        out['root'] = {'t': [0, bob * h * abs(math.sin(w)), 0]}
        out['spine'] = {'r': rx(lean * math.sin(2 * w))}
        out['head'] = {'r': rx(0.08 * math.sin(2 * w + 1))}
        out['tail'] = {'r': ry(0.25 * math.sin(w))}
        out['tail2'] = {'r': ry(0.3 * math.sin(w - 0.8))}
        return out

    def idle(t):
        w = 2 * math.pi * t / 3.0
        return {'chest': {'r': rx(0.02 * math.sin(w))}, 'spine': {'s': [1 + 0.015 * math.sin(w), 1 + 0.02 * math.sin(w), 1]},
                'neck': {'r': ry(0.15 * math.sin(w / 1.5))}, 'head': {'r': rx(0.05 * math.sin(w + 1))},
                'tail': {'r': ry(0.2 * math.sin(w * 1.5))}, 'tail2': {'r': ry(0.25 * math.sin(w * 1.5 - 0.7))}}

    def jump(t):
        crouch = env(t, 0.0, 0.2, 0.22, 0.35) + env(t, 0.75, 0.85, 0.87, 1.0) * 0.7
        air = env(t, 0.3, 0.5, 0.55, 0.8)
        out = {'root': {'t': [0, -0.12 * h * crouch + 0.45 * h * air, 0]},
               'chest': {'r': rx(-0.2 * air)}, 'head': {'r': rx(-0.15 * air)}, 'tail': {'r': rx(-0.4 * air)}}
        for leg in legs:
            sgn = 1 if leg.startswith('back') else -1
            out[f'upper.{leg}'] = {'r': rx(sgn * -0.35 * crouch + (0.5 if leg.startswith('back') else -0.5) * air)}
            out[f'lower.{leg}'] = {'r': rx(sgn * 0.7 * crouch)}
        return out

    def attack(t):
        wind = env(t, 0.0, 0.25, 0.3, 0.4)
        hit = env(t, 0.3, 0.45, 0.55, 0.85)
        out = {'root': {'t': [0, 0.03 * h * hit, (-0.06 * wind + 0.18 * hit) * info['L']]},
               'chest': {'r': rx(0.12 * wind - 0.1 * hit)}, 'neck': {'r': rx(-0.3 * wind + 0.45 * hit)},
               'head': {'r': rx(-0.25 * hit)}, 'tail': {'r': rx(-0.3 * hit)}}
        for side in ('L', 'R'):
            out[f'upper.front.{side}'] = {'r': rx(-0.5 * hit)}
            out[f'upper.back.{side}'] = {'r': rx(0.2 * wind)}
        return out

    def hurt(t):
        k = env(t, 0.0, 0.08, 0.15, 0.5)
        return {'root': {'t': [0, 0, -0.08 * info['L'] * k]}, 'chest': {'r': rx(-0.2 * k)}, 'neck': {'r': rx(-0.3 * k)},
                'head': {'r': rx(-0.2 * k)}, 'tail': {'r': rx(0.3 * k)}}

    def die(t):
        k = ease(t / 0.9)
        out = {'root': {'r': rz(1.45 * k), 't': [0.0, 0.05 * h * k, 0]}, 'neck': {'r': rx(0.35 * k)}, 'tail': {'r': ry(0.3 * k)}}
        for leg in legs:
            out[f'upper.{leg}'] = {'r': rx((-0.3 if leg.startswith('front') else 0.3) * k)}
        return out

    return {
        'idle': (3.0, True, idle),
        'walk': (1.0, True, lambda t: gait(t, 1.0, trot, 0.35, 0.5, 0.02)),
        'run': (0.55, True, lambda t: gait(t, 0.55, gallop, 0.6, 0.8, 0.06, 0.08)),
        'jump': (1.0, False, jump),
        'attack': (0.9, False, attack),
        'attack2': (0.7, False, lambda t: {'upper.front.R': {'r': rx(-1.1 * env(t, 0, 0.25, 0.3, 0.55))}, 'lower.front.R': {'r': rx(0.6 * env(t, 0, 0.2, 0.25, 0.45))},
                                           'chest': {'r': qmul(rz(-0.15 * env(t, 0, 0.25, 0.35, 0.6)), rx(-0.15 * env(t, 0, 0.25, 0.35, 0.6)))}, 'neck': {'r': ry(0.3 * env(t, 0.1, 0.3, 0.4, 0.65))}}),
        'attack3': (1.1, False, lambda t: {'root': {'t': [0, 0.4 * h * env(t, 0.2, 0.45, 0.5, 0.75), 0.6 * info['L'] * env(t, 0.2, 0.6, 0.8, 1.1)]},
                                           'chest': {'r': rx(-0.35 * env(t, 0.2, 0.4, 0.5, 0.7))}, 'neck': {'r': rx(0.4 * env(t, 0.5, 0.65, 0.75, 1.0))},
                                           **{f'upper.{l}': {'r': rx((-0.8 if l.startswith('front') else 0.6) * env(t, 0.25, 0.45, 0.55, 0.8))} for l in legs}}),
        'hurt': (0.5, False, hurt),
        'die': (1.2, False, die),
    }


def wings_clips(J, info):
    h = info['h']

    def flap(t, rate, amp, pitch=0.0, bob=0.05, rise=0.0):
        w = 2 * math.pi * t * rate
        a = amp * math.sin(w)
        return {'wing.L': {'r': rz(a)}, 'wing.R': {'r': rz(-a)},
                'wing2.L': {'r': rz(0.5 * amp * math.sin(w - 0.9))}, 'wing2.R': {'r': rz(-0.5 * amp * math.sin(w - 0.9))},
                'root': {'t': [0, h * (rise + bob * math.sin(w + math.pi / 2)), 0]}, 'body': {'r': rx(pitch)},
                'tail': {'r': rx(0.1 * math.sin(w + 1))}}

    def jump(t):
        out = flap(t, 3.0, 0.7, -0.1, 0.03, 0.4 * env(t, 0.0, 0.35, 0.65, 1.0))
        return out

    def attack(t):
        k = env(t, 0.0, 0.3, 0.45, 0.8)
        return {'body': {'r': rx(0.6 * k)}, 'root': {'t': [0, -0.05 * h * k, 0.35 * h * k]},
                'wing.L': {'r': qmul(rz(0.3 * k), ry(0.5 * k))}, 'wing.R': {'r': qmul(rz(-0.3 * k), ry(-0.5 * k))},
                'head': {'r': rx(-0.3 * k)}}

    def hurt(t):
        k = env(t, 0.0, 0.08, 0.15, 0.5)
        return {'body': {'r': rx(-0.35 * k)}, 'root': {'t': [0, 0, -0.1 * h * k]},
                'wing.L': {'r': rz(0.6 * k)}, 'wing.R': {'r': rz(-0.6 * k)}}

    def die(t):
        k = ease(t / 1.0)
        return {'wing.L': {'r': rz(-0.9 * k)}, 'wing.R': {'r': rz(0.9 * k)}, 'wing2.L': {'r': rz(-0.6 * k)}, 'wing2.R': {'r': rz(0.6 * k)},
                'root': {'r': rz(1.4 * k), 't': [0, 0.05 * h * k, 0]}}

    return {
        'idle': (1.0, True, lambda t: flap(t, 2.0, 0.45)),
        'walk': (0.5, True, lambda t: flap(t, 4.0, 0.6, 0.2)),
        'run': (0.4, True, lambda t: flap(t, 5.0, 0.75, 0.4)),
        'jump': (1.0, False, jump),
        'attack': (0.8, False, attack),
        'attack2': (0.7, False, lambda t: {'wing.L': {'r': rz(0.9 * math.sin(math.pi * 2 * t / 0.35))}, 'wing.R': {'r': rz(-0.9 * math.sin(math.pi * 2 * t / 0.35))},
                                           'body': {'r': rx(-0.3 * env(t, 0, 0.2, 0.5, 0.7))}, 'root': {'t': [0, 0, 0.2 * h * env(t, 0, 0.3, 0.5, 0.7)]}}),
        'attack3': (1.0, False, lambda t: {'body': {'r': rx(0.9 * env(t, 0.1, 0.4, 0.6, 0.9))}, 'root': {'t': [0, 0.3 * h * env(t, 0, 0.25, 0.3, 0.45) - 0.1 * h * env(t, 0.45, 0.55, 0.7, 0.9), 0.5 * h * env(t, 0.3, 0.55, 0.7, 1.0)]},
                                           'wing.L': {'r': rz(-0.4 * env(t, 0.3, 0.45, 0.7, 0.9))}, 'wing.R': {'r': rz(0.4 * env(t, 0.3, 0.45, 0.7, 0.9))}}),
        'hurt': (0.5, False, hurt),
        'die': (1.2, False, die),
    }


def any_clips(J, info):
    h = info['h']

    def squash(s):
        return [1 / math.sqrt(s), s, 1 / math.sqrt(s)]

    def idle(t):
        w = 2 * math.pi * t / 2.0
        return {'base': {'s': squash(1 + 0.035 * math.sin(w))}, 'top': {'r': ry(0.12 * math.sin(w / 2))},
                'mid': {'r': rz(0.03 * math.sin(w))}}

    def hop(t, period, height, lean, waddle):
        p = (t / period) % 1
        up = math.sin(math.pi * p)
        land = max(0.0, 1 - p / 0.15) + max(0.0, (p - 0.9) / 0.1)
        return {'root': {'t': [0, height * h * up, 0]}, 'base': {'s': squash(1 - 0.12 * land + 0.06 * up), 'r': rz(waddle * math.sin(2 * math.pi * p))},
                'mid': {'r': rx(lean)}, 'top': {'r': rx(0.5 * lean * math.sin(2 * math.pi * p))}}

    def jump(t):
        crouch = env(t, 0.0, 0.2, 0.22, 0.32) + 0.8 * env(t, 0.78, 0.86, 0.88, 1.0)
        air = env(t, 0.28, 0.5, 0.56, 0.82)
        return {'root': {'t': [0, 0.6 * h * air, 0]}, 'base': {'s': squash(1 - 0.28 * crouch + 0.15 * air)}}

    def attack(t):
        wind = env(t, 0.0, 0.25, 0.3, 0.4)
        hit = env(t, 0.3, 0.42, 0.55, 0.85)
        return {'root': {'t': [0, 0, (0.3 * hit - 0.05 * wind) * h]}, 'base': {'s': squash(1 - 0.12 * wind + 0.1 * hit)},
                'mid': {'r': rx(-0.25 * wind + 0.4 * hit)}, 'top': {'r': rx(0.2 * hit)}}

    def hurt(t):
        k = env(t, 0.0, 0.08, 0.15, 0.5)
        return {'base': {'s': squash(1 - 0.2 * k)}, 'mid': {'r': rx(-0.35 * k)}, 'root': {'t': [0, 0, -0.1 * h * k]}}

    def die(t):
        k = ease(t / 0.9)
        return {'base': {'r': rz(1.45 * k), 's': squash(1 - 0.15 * k)}, 'root': {'t': [0.35 * h * k, 0, 0]}}

    return {
        'idle': (2.0, True, idle),
        'walk': (0.6, True, lambda t: hop(t, 0.6, 0.08, 0.1, 0.08)),
        'run': (0.4, True, lambda t: hop(t, 0.4, 0.14, 0.2, 0.05)),
        'jump': (1.0, False, jump),
        'attack': (0.8, False, attack),
        'attack2': (0.8, False, lambda t: {'base': {'r': ry(2 * math.pi * ease(t / 0.6)), 's': squash(1 + 0.1 * env(t, 0, 0.3, 0.4, 0.7))}}),
        'attack3': (1.0, False, lambda t: {'root': {'t': [0, 0.5 * h * env(t, 0.1, 0.4, 0.45, 0.6), 0.15 * h * env(t, 0.1, 0.4, 0.6, 1.0)]},
                                           'base': {'s': squash(1 - 0.35 * env(t, 0.55, 0.62, 0.7, 0.95) - 0.15 * env(t, 0, 0.1, 0.12, 0.2))}}),
        'hurt': (0.5, False, hurt),
        'die': (1.0, False, die),
    }


# ---------- writing ----------

def build(mesh, J, joints, weights_, clips, out, wanted=CLIPS):
    import trimesh
    from PIL import Image
    names = list(J)
    V = np.asarray(mesh.vertices, 'f4')
    F = np.asarray(mesh.faces, 'u4')
    N = np.asarray(mesh.vertex_normals, 'f4')
    g = {'asset': {'version': '2.0', 'generator': 'Game Studio creature.py'}, 'scene': 0, 'accessors': [], 'bufferViews': [], 'nodes': []}
    b = bytearray()

    def acc(arr, ctype, typ, normalized=False, minmax=False, target=None):
        view = add_view(g, b, np.ascontiguousarray(arr).tobytes())
        if target:
            g['bufferViews'][view]['target'] = target
        a = {'bufferView': view, 'componentType': ctype, 'count': len(arr), 'type': typ}
        if normalized:
            a['normalized'] = True
        if minmax:
            a['min'] = np.asarray(arr).min(0).reshape(-1).tolist()
            a['max'] = np.asarray(arr).max(0).reshape(-1).tolist()
        g['accessors'].append(a)
        return len(g['accessors']) - 1

    attrs = {'POSITION': acc(V, 5126, 'VEC3', minmax=True, target=34962), 'NORMAL': acc(N, 5126, 'VEC3', target=34962),
             'JOINTS_0': acc(joints, 5121, 'VEC4', target=34962), 'WEIGHTS_0': acc(np.round(weights_ * 255).astype('u1'), 5121, 'VEC4', normalized=True, target=34962)}
    prim = {'attributes': attrs, 'indices': acc(F.reshape(-1), 5125, 'SCALAR', target=34963)}
    vis = mesh.visual
    material = {'pbrMetallicRoughness': {'metallicFactor': 0.0, 'roughnessFactor': 0.9}}
    img = None
    if isinstance(vis, trimesh.visual.TextureVisuals) and vis.uv is not None:
        uv = np.asarray(vis.uv, 'f4').copy()
        uv[:, 1] = 1 - uv[:, 1]
        attrs['TEXCOORD_0'] = acc(uv, 5126, 'VEC2', target=34962)
        m = vis.material
        img = getattr(m, 'baseColorTexture', None) or getattr(m, 'image', None)
    elif getattr(vis, 'vertex_colors', None) is not None and len(vis.vertex_colors):
        attrs['COLOR_0'] = acc(np.asarray(vis.vertex_colors, 'u1'), 5121, 'VEC4', normalized=True, target=34962)
    if img is not None:
        buf = io.BytesIO()
        Image.fromarray(np.asarray(img.convert('RGB'))).save(buf, 'JPEG', quality=85, optimize=True)
        g['images'] = [{'bufferView': add_view(g, b, buf.getvalue()), 'mimeType': 'image/jpeg'}]
        g['samplers'] = [{'magFilter': 9729, 'minFilter': 9987}]
        g['textures'] = [{'source': 0, 'sampler': 0}]
        material['pbrMetallicRoughness']['baseColorTexture'] = {'index': 0}
    g['materials'] = [material]
    prim['material'] = 0
    g['meshes'] = [{'name': 'creature', 'primitives': [prim]}]

    for n in names:
        parent, pos = J[n]
        local = pos - (J[parent][1] if parent else 0)
        g['nodes'].append({'name': n, 'translation': [float(x) for x in local]})
    for n in names:
        kids = [names.index(k) for k, (p, _) in J.items() if p == n]
        if kids:
            g['nodes'][names.index(n)]['children'] = kids
    ibm = np.stack([np.linalg.inv(np.block([[np.eye(3), J[n][1].reshape(3, 1)], [np.zeros((1, 3)), np.ones((1, 1))]])).T.astype('f4') for n in names])
    g['skins'] = [{'joints': list(range(len(names))), 'inverseBindMatrices': acc(ibm, 5126, 'MAT4'), 'skeleton': 0}]
    g['nodes'].append({'name': 'creature', 'mesh': 0, 'skin': 0})
    g['scenes'] = [{'name': 'creature', 'nodes': [0, len(names)]}]

    g['animations'] = []
    for clip in wanted:
        seconds, _, fn = clips[clip]
        times = np.arange(0, seconds + 1e-6, 1 / FPS).astype('f4')
        frames = [fn(float(t)) for t in times]
        tin = acc(times, 5126, 'SCALAR', minmax=True)
        samplers, channels = [], []
        for n in names:
            for key, path, rest in (('r', 'rotation', [0, 0, 0, 1]), ('t', 'translation', None), ('s', 'scale', [1, 1, 1])):
                if not any(key in f.get(n, {}) for f in frames):
                    continue
                vals = []
                for f in frames:
                    v = f.get(n, {}).get(key)
                    if path == 'translation':
                        base = J[n][1] - (J[J[n][0]][1] if J[n][0] else 0)
                        vals.append(base + (np.asarray(v) if v is not None else 0))
                    else:
                        vals.append(np.asarray(v if v is not None else rest, 'f8'))
                arr = np.asarray(vals, 'f4')
                if path == 'rotation':
                    arr /= np.linalg.norm(arr, axis=1, keepdims=True)
                samplers.append({'input': tin, 'output': acc(arr, 5126, 'VEC4' if path == 'rotation' else 'VEC3'), 'interpolation': 'LINEAR'})
                channels.append({'sampler': len(samplers) - 1, 'target': {'node': names.index(n), 'path': path}})
        g['animations'].append({'name': clip, 'samplers': samplers, 'channels': channels})
    return write_glb(out, g, b)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('raw')
    p.add_argument('out')
    p.add_argument('--body', choices=['fourlegs', 'wings', 'any'], required=True)
    p.add_argument('--flip', action='store_true')
    p.add_argument('--yup', action='store_true', help='the model is already Y up, facing +Z (3D AI Studio text-to-3D)')
    p.add_argument('--height', type=float, default=1.0, help='height in metres (a person is 1.8)')
    p.add_argument('--vehicle', action='store_true', help='a vehicle: only idle, walk (drive) and run (drive fast)')
    p.add_argument('--clips', help=f'comma list from {",".join(CLIPS)} (default: the basics)')
    a = p.parse_args()
    mesh = load(a.raw, a.flip, a.body, a.yup)
    mesh.apply_scale(a.height / max(mesh.bounds[1][1], 1e-6))
    V = np.asarray(mesh.vertices, 'f8')
    J, tips, info = {'fourlegs': fourlegs_skeleton, 'wings': wings_skeleton, 'any': any_skeleton}[a.body](V)
    joints, w = weights(V, np.asarray(mesh.faces), J, tips, a.body, info)
    clips = {'fourlegs': fourlegs_clips, 'wings': wings_clips, 'any': any_clips}[a.body](J, info)
    import tempfile
    from detailed import shrink
    tmp = Path(tempfile.mkdtemp(prefix='creature-')) / 'full.glb'
    wanted = [c for c in (a.clips.split(',') if a.clips else VEHICLE if a.vehicle else BASIC) if c in CLIPS]
    build(mesh, J, joints, w, clips, tmp, wanted)
    shrink(tmp, a.out)  # packed numbers + JPEG: about half the size, three.js reads it as is
    size = Path(a.out).stat().st_size
    print(json.dumps({'ok': True, 'out': a.out, 'bytes': size, 'body': a.body, 'animations': wanted,
                      'next': 'Render idle, walk and attack with model_tool.py render and Read them; if it faces backwards, rerun with --flip.'}))


if __name__ == '__main__':
    main()
