#!/usr/bin/env python3
"""Edit a rigged 3D character in Blender with a short script; its skeleton and every
animation are kept. Best on library characters (library.py), which have clean parts.

  python3 blender_edit.py IN.glb OUT.glb EDIT.py     run EDIT.py on the character, save OUT.glb
  python3 blender_edit.py IN.glb --info              parts, materials, colours and bones

EDIT.py is plain Python run inside Blender (bpy is available) with these helpers.
TARGET is a part (mesh) name such as "Barbarian_Hat", or "material:NAME" for characters
made of one mesh with colour materials (Quaternius: "material:Skin", "material:Shirt").
Names match exactly first, then as a case-insensitive part of the name.

  info()                          print parts, materials, their main colours, and bones
  colors(TARGET)                  the main colours in a target, most used first: [('#4a6fa5', 0.42), ...]
  recolor(TARGET, '#8b1e1e')      repaint a target in one colour, keeping its light and dark shading
  recolor(TARGET, {'#4a6fa5': '#8b1e1e', '#e3c9a0': '#c89878'}, tol=0.15)
                                  swap only those colours (close matches within tol, 0-1)
  scale(TARGET, 1.3, about='head')          resize a part around a bone (a bigger head, a smaller hat);
                                            factor can be (x, y, z) in the character's own axes
  thicken(factor, targets=None)   bulkier (1.2) or skinnier (0.85) limbs and body, around the bones,
                                  so animations still fit; targets limits it to some parts
  move(TARGET, (x, y, z))         shift a part in metres (x right, y up, z forward)
  remove(TARGET)                  delete a part (a helmet, a cape) or the faces of one material
  borrow(OTHER.glb, PART)         take a part from another character with the same skeleton
                                  (any KayKit character to any other: a Knight_Helmet on the Barbarian)
  attach(ITEM.glb, bone, at=(0, 0, 0), turn=(0, 0, 0), size=1.0)
                                  fix worn gear (a hat, pack or beard built with shapes.py) to a bone;
                                  at is in metres from the bone, turn in degrees. It keeps the angle it
                                  has in the T-pose, so put held weapons and tools in the hand with
                                  model_tool.py equip instead (it lines them up with the fist).
  grime(amount=0.5)               darker, dirtier, less saturated colours on everything (gritty looks)
  bounds(TARGET), bone(NAME)      measure a part or find a bone (x right, y up, z forward), to size gear

Anything EDIT.py prints comes back in the result's "printed" list.
Check the result: python3 model_tool.py render OUT.glb a.png --anim idle (and walk, attack),
Read it, and iterate on EDIT.py. The input file is never changed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

RUNNER = r'''
import bpy, bmesh, sys, os, json, math, colorsys, traceback
from mathutils import Vector, Matrix, Euler
import numpy as np

ARGS = json.loads(sys.argv[sys.argv.index('--') + 1])
import builtins
def say(*a):
    # Blender's own output is noisy; lines marked SAY reach the person running the edit.
    builtins.print('SAY ' + ' '.join(str(x) for x in a), flush=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=ARGS['src'])
rig = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
# Edit in the neutral (rest) pose: the importer leaves a move applied, and gear parented to
# a posed bone would then sit wrong once the moves play.
for _o in bpy.data.objects:
    if _o.animation_data:
        _o.animation_data.action = None
if rig:
    rig.data.pose_position = 'REST'
    bpy.context.view_layer.update()
# World up is Blender's Z; the helpers speak in the character's axes: x right, y up, z forward.
def _w(v):
    return Vector((v[0], -v[2], v[1]))

def _meshes():
    shapes = {pb.custom_shape for pb in rig.pose.bones if pb.custom_shape} if rig else set()
    return [o for o in bpy.data.objects if o.type == 'MESH' and o not in shapes]

def _find(target):
    """(object, material index or None) pairs for a target."""
    if target.startswith('material:'):
        name = target[9:]
        out = []
        for o in _meshes():
            for i, s in enumerate(o.material_slots):
                if s.material and (s.material.name == name or name.lower() in s.material.name.lower()):
                    out.append((o, i))
        if not out:
            raise ValueError(f'No material like "{name}". Materials: ' + ', '.join(sorted({s.material.name for o in _meshes() for s in o.material_slots if s.material})))
        return out
    exact = [o for o in _meshes() if o.name == target]
    hits = exact or [o for o in _meshes() if target.lower() in o.name.lower()]
    if not hits:
        raise ValueError(f'No part like "{target}". Parts: ' + ', '.join(o.name for o in _meshes()))
    return [(o, None) for o in hits]

def _verts(o, mat):
    if mat is None:
        return list(range(len(o.data.vertices)))
    return sorted({v for p in o.data.polygons if p.material_index == mat for v in p.vertices})

def _bone_world(name):
    if not rig:
        raise ValueError('This model has no skeleton.')
    b = rig.data.bones.get(name) or next((x for x in rig.data.bones if name.lower() in x.name.lower()), None)
    if b is None:
        raise ValueError(f'No bone like "{name}". Bones: ' + ', '.join(x.name for x in rig.data.bones if x.use_deform))
    return b, rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local

# Texture pixels arrive as screen (sRGB) values; material colours are linear.
def _hex(c, linear=False):
    return '#%02x%02x%02x' % tuple(int(round(max(0, min(1, x)) ** (1 / 2.2 if linear else 1) * 255)) for x in c[:3])

def _rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])

def _lin(h):
    return _rgb(h) ** 2.2

def _bsdf(mat):
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat and mat.use_nodes else None

def _image(mat):
    return next((n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), None) if mat and mat.use_nodes else None

def _own_material(o, idx):
    """Give this part its own copy of a (shared) material and image, so edits stay on it."""
    slot = o.material_slots[idx]
    mat = slot.material.copy()
    img = _image(mat)
    if img is not None:
        new = img.copy()
        new.pack()
        for n in mat.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image == img:
                n.image = new
    slot.link = 'OBJECT'
    slot.material = mat
    return mat

def _uv_mask(o, mat_index, w, h):
    """Pixels of the texture covered by this part's faces (optionally one material)."""
    mask = np.zeros((h, w), bool)
    uv = o.data.uv_layers.active
    if uv is None:
        return mask
    for p in o.data.polygons:
        if mat_index is not None and p.material_index != mat_index:
            continue
        pts = [uv.data[li].uv for li in p.loop_indices]
        for k in range(1, len(pts) - 1):
            tri = np.array([[pts[0].x * w, pts[0].y * h], [pts[k].x * w, pts[k].y * h], [pts[k + 1].x * w, pts[k + 1].y * h]])
            x0, y0 = np.floor(tri.min(0)).astype(int) - 1
            x1, y1 = np.ceil(tri.max(0)).astype(int) + 1
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
            if x1 < x0 or y1 < y0:
                continue
            X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = tri
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-12:
                mask[y0:y1 + 1, x0:x1 + 1] |= (np.abs(X - ax) < 1) & (np.abs(Y - ay) < 1)
                continue
            l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / d
            l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / d
            l3 = 1 - l1 - l2
            e = -0.02
            mask[y0:y1 + 1, x0:x1 + 1] |= (l1 >= e) & (l2 >= e) & (l3 >= e)
    return mask

def _pixels(img):
    w, h = img.size
    return np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4), w, h

def colors(target, top=8):
    """Main colours in a target, most used first."""
    tally = {}
    for o, mi in _find(target):
        idxs = [mi] if mi is not None else range(len(o.material_slots))
        for i in idxs:
            mat = o.material_slots[i].material
            img = _image(mat)
            if img is not None:
                px, w, h = _pixels(img)
                m = _uv_mask(o, i if len(o.material_slots) > 1 else None, w, h)
                cols = px[m][:, :3]
                if len(cols):
                    q = np.round(cols * 24) / 24
                    u, n = np.unique(q, axis=0, return_counts=True)
                    for c, k in zip(u, n):
                        tally[_hex(c)] = tally.get(_hex(c), 0) + int(k)
            elif _bsdf(mat):
                h = _hex(_bsdf(mat).inputs['Base Color'].default_value, linear=True)
                tally[h] = tally.get(h, 0) + len(_verts(o, i))
    total = sum(tally.values()) or 1
    return [(c, round(n / total, 3)) for c, n in sorted(tally.items(), key=lambda x: -x[1])[:top]]

def recolor(target, to, tol=0.15):
    """Repaint a target in one colour, or swap {old: new} colours in it."""
    for o, mi in _find(target):
        idxs = [mi] if mi is not None else range(len(o.material_slots))
        for i in idxs:
            if not o.material_slots[i].material:
                continue
            mat = _own_material(o, i)
            img = _image(mat)
            if img is None:
                b = _bsdf(mat)
                cur = np.array(b.inputs['Base Color'].default_value[:3])
                if isinstance(to, str):
                    new = _lin(to)
                else:
                    new = next((_lin(n) for old, n in to.items() if np.abs(_rgb(old) - cur ** (1 / 2.2)).max() <= tol), None)
                if new is not None:
                    b.inputs['Base Color'].default_value = (*new, 1.0)
                continue
            px, w, h = _pixels(img)
            m = _uv_mask(o, i if len(o.material_slots) > 1 else None, w, h)
            rgb = px[..., :3]
            if isinstance(to, str):
                sel = m
                base = rgb[sel]
                lum = base.mean(1, keepdims=True)
                ref = np.median(lum) or 1e-3
                rgb[sel] = np.clip(_rgb(to)[None, :] * (lum / ref), 0, 1)
            else:
                for old, new in to.items():
                    sel = m & (np.abs(rgb - _rgb(old)).max(-1) <= tol)
                    rgb[sel] = np.clip(rgb[sel] - _rgb(old) + _rgb(new), 0, 1)
            px[..., :3] = rgb
            img.pixels[:] = px.ravel()
            img.update()
            img.pack()

def scale(target, factor, about=None):
    """Resize a part around a bone (or its own centre)."""
    f = Vector(factor if isinstance(factor, (tuple, list)) else (factor,) * 3)
    fw = Vector((abs(_w(f)[0]), abs(_w(f)[1]), abs(_w(f)[2])))
    for o, mi in _find(target):
        vs = _verts(o, mi)
        M = o.matrix_world
        pts = [M @ o.data.vertices[v].co for v in vs]
        c = _bone_world(about)[1] if about else sum(pts, Vector()) / max(len(pts), 1)
        Mi = M.inverted()
        for v, p in zip(vs, pts):
            d = p - c
            o.data.vertices[v].co = Mi @ (c + Vector((d.x * fw.x, d.y * fw.y, d.z * fw.z)))
        o.data.update()

def move(target, offset):
    d = _w(offset)
    for o, mi in _find(target):
        Mi = o.matrix_world.inverted().to_3x3()
        for v in _verts(o, mi):
            o.data.vertices[v].co += Mi @ d
        o.data.update()

def thicken(factor, targets=None):
    """Push each vertex away from (or toward) its main bone's line."""
    objs = [(o, None) for o in _meshes()] if not targets else [x for t in targets for x in _find(t)]
    segs = {b.name: (rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local) for b in rig.data.bones if b.use_deform}
    for o, mi in objs:
        groups = {g.index: g.name for g in o.vertex_groups}
        M, Mi = o.matrix_world, o.matrix_world.inverted()
        for vi in _verts(o, mi):
            v = o.data.vertices[vi]
            ws = [(g.weight, groups.get(g.group)) for g in v.groups if groups.get(g.group) in segs]
            p = M @ v.co
            if not ws:
                continue
            tw = sum(w for w, _ in ws) or 1
            push = Vector()
            for w, name in ws:
                a, b = segs[name]
                ab = b - a
                t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
                push += (p - (a + ab * t)) * (w / tw)
            v.co = Mi @ (p + push * (factor - 1))
        o.data.update()

def remove(target):
    for o, mi in _find(target):
        if mi is None:
            bpy.data.objects.remove(o, do_unlink=True)
        else:
            bm = bmesh.new(); bm.from_mesh(o.data)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index == mi], context='FACES')
            bm.to_mesh(o.data); bm.free(); o.data.update()

def _import(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]

def borrow(path, part):
    new = _import(path)
    keep = next((o for o in new if o.type == 'MESH' and (o.name == part or o.name.split('.')[0] == part)), None) \
        or next((o for o in new if o.type == 'MESH' and part.lower() in o.name.lower()), None)
    if keep is None:
        names = [o.name for o in new if o.type == 'MESH']
        for o in new: bpy.data.objects.remove(o, do_unlink=True)
        raise ValueError(f'No part like "{part}" in {path}. Parts: ' + ', '.join(names))
    bone = keep.parent_bone if keep.parent_type == 'BONE' else None   # a held item stays on its bone
    mw = keep.matrix_world.copy()
    keep.parent = rig
    keep.parent_type = 'BONE' if bone else 'OBJECT'
    if bone:
        keep.parent_bone = bone
    keep.matrix_world = mw
    for mod in keep.modifiers:
        if mod.type == 'ARMATURE':
            mod.object = rig
    for o in new:
        if o is not keep:
            bpy.data.objects.remove(o, do_unlink=True)
    for a in [x for x in bpy.data.actions if x.users == 0]:
        bpy.data.actions.remove(a)
    keep.name = part
    return keep

def attach(path, bone, at=(0, 0, 0), turn=(0, 0, 0), size=1.0):
    new = _import(path)
    meshes = [o for o in new if o.type == 'MESH']
    for o in new:
        if o.type != 'MESH':
            for c in o.children: c.parent = None
    for o in new:
        if o.type != 'MESH': bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.matrix_world = o.matrix_world  # apply parent transforms
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    item = bpy.context.view_layer.objects.active
    b, head, tail = _bone_world(bone)
    R = Euler([math.radians(x) for x in (turn[0], -turn[2], turn[1])], 'XYZ').to_matrix().to_4x4()
    item.matrix_world = Matrix.Translation(head + _w(at)) @ R @ Matrix.Diagonal((size, size, size, 1)) @ item.matrix_world
    mw = item.matrix_world.copy()
    item.parent = rig
    item.parent_type = 'BONE'
    item.parent_bone = b.name
    item.matrix_world = mw
    item.name = 'gear:' + os.path.splitext(os.path.basename(path))[0]
    return item

def grime(amount=0.5):
    """Darker, dirtier, less saturated colours on every material and texture."""
    done = set()
    for o in _meshes():
        for s in o.material_slots:
            mat = s.material
            if not mat or mat.name in done: continue
            done.add(mat.name)
            img = _image(mat)
            if img is not None and img.name not in done:
                done.add(img.name)
                px, w, h = _pixels(img)
                rgb = px[..., :3]
                grey = rgb.mean(-1, keepdims=True)
                rgb = rgb * (1 - 0.5 * amount) + grey * (0.5 * amount)
                noise = np.random.default_rng(3).normal(0, 0.06 * amount, rgb.shape[:2])[..., None]
                rgb = np.clip(rgb * (1 - 0.35 * amount) * (1 + noise), 0, 1)
                px[..., :3] = rgb; img.pixels[:] = px.ravel(); img.update(); img.pack()
            b = _bsdf(mat)
            if b is not None and img is None:
                c = np.array(b.inputs['Base Color'].default_value[:3])
                c = (c * (1 - 0.5 * amount) + c.mean() * 0.5 * amount) * (1 - 0.35 * amount)
                b.inputs['Base Color'].default_value = (*c, 1.0)
            if b is not None:
                b.inputs['Roughness'].default_value = max(0.85, b.inputs['Roughness'].default_value)

def bounds(target):
    """Size and centre of a target in metres, in the character's axes (x right, y up, z forward)."""
    pts = [o.matrix_world @ o.data.vertices[v].co for o, mi in _find(target) for v in _verts(o, mi)]
    lo = Vector((min(p.x for p in pts), min(-p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(-p.y for p in pts), max(p.z for p in pts)))
    # Blender (x, y, z) -> character (x, z, -y)
    lo, hi = Vector((lo.x, lo.z, lo.y)), Vector((hi.x, hi.z, hi.y))
    r = {'min': [round(x, 3) for x in lo], 'max': [round(x, 3) for x in hi], 'size': [round(x, 3) for x in hi - lo],
         'centre': [round(x, 3) for x in (lo + hi) / 2]}
    say('bounds', target, json.dumps(r))
    return r

def bone(name):
    """Where a bone starts, in the character's axes."""
    b, head, tail = _bone_world(name)
    h = [round(head.x, 3), round(head.z, 3), round(-head.y, 3)]
    say('bone', b.name, h)
    return h

def info():
    out = {'parts': [o.name for o in _meshes()],
           'materials': sorted({s.material.name for o in _meshes() for s in o.material_slots if s.material}),
           'colours': {o.name: [c for c, _ in colors(o.name, 5)] for o in _meshes() if len(o.material_slots) == 1},
           'bones': [b.name for b in rig.data.bones if b.use_deform] if rig else []}
    if any(len(o.material_slots) > 1 for o in _meshes()):
        out['material_colours'] = {m: colors('material:' + m, 1)[0][0] for m in out['materials']}
    print('EDIT_INFO ' + json.dumps(out))

try:
    if ARGS.get('info'):
        info()
    else:
        code = open(ARGS['script']).read()
        exec(compile(code, ARGS['script'], 'exec'), {**globals(), '__name__': 'edit', 'print': say})
        for o in bpy.data.objects:
            if o.animation_data:
                o.animation_data.action = None
        if rig:
            rig.data.pose_position = 'POSE'
        bpy.ops.export_scene.gltf(filepath=ARGS['out'], export_format='GLB', export_animations=True,
                                  export_animation_mode='ACTIONS', export_image_format='AUTO')
        print('EDIT_DONE ' + json.dumps({'parts': [o.name for o in _meshes()], 'moves': sorted(a.name for a in bpy.data.actions)}))
except Exception:
    print('EDIT_ERROR ' + json.dumps(traceback.format_exc()[-1500:]))
    sys.exit(1)
'''


def run(src, out=None, script=None, info=False):
    sys.path.insert(0, str(HERE))
    from detailed import ensure_blender
    exe = ensure_blender()
    if not exe:
        sys.exit('Blender could not be set up on this machine.')
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, dir=os.environ.get('TMPDIR')) as f:
        f.write(RUNNER)
    args = {'src': str(Path(src).resolve()), 'out': str(Path(out).resolve()) if out else None,
            'script': str(Path(script).resolve()) if script else None, 'info': info}
    proc = subprocess.run([str(exe), '-b', '--python', f.name, '--', json.dumps(args)], capture_output=True, text=True, timeout=900)
    os.unlink(f.name)
    lines = proc.stdout.splitlines()
    err = next((l for l in lines if l.startswith('EDIT_ERROR ')), None)
    if err:
        sys.exit('The edit script failed:\n' + json.loads(err[11:]))
    key = 'EDIT_INFO ' if info else 'EDIT_DONE '
    line = next((l for l in lines if l.startswith(key)), None)
    if proc.returncode or not line:
        sys.exit('Blender failed: ' + (proc.stderr or proc.stdout)[-1500:])
    said = [l[4:] for l in lines if l.startswith('SAY ')]
    res = json.loads(line[len(key):])
    if said:
        res['printed'] = said
    if info:
        print(json.dumps(res, indent=1))
    else:
        print(json.dumps({'ok': True, 'out': str(out), 'bytes': Path(out).stat().st_size, **res,
                          'next': 'Render it (model_tool.py render OUT.glb a.png --anim idle, then walk and attack) and Read it.'}, indent=1))


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[1] == '--info':
        run(a[0], info=True)
    elif len(a) == 3:
        run(a[0], a[1], a[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
