"""Runs inside Blender for blender_char.py (see its help). Not meant to be run by hand.

argv after '--': LIBRARY.glb SPEC.json OUT.glb EXTRA.py|'' ANIMS(all|core)
"""
import json
import math
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

LIB, SPEC, OUT, EXTRA, ANIMS = sys.argv[sys.argv.index('--') + 1:][:5]
spec = json.load(open(SPEC))

CORE_CLIPS = {'Idle_Loop', 'Walk_Loop', 'Jog_Fwd_Loop', 'Sprint_Loop', 'Jump_Start', 'Jump_Loop', 'Jump_Land',
              'Punch_Jab', 'Punch_Cross', 'Hit_Chest', 'Hit_Head', 'Death01', 'Roll', 'Sword_Attack', 'Spell_Simple_Shoot',
              'Idle_Talking_Loop', 'Dance_Loop', 'Crouch_Idle_Loop', 'Interact', 'A_TPose'}

# ---------------------------------------------------------------- load the mannequin
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=LIB)
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body = bpy.data.objects['Mannequin']
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o is not body:
        bpy.data.objects.remove(o, do_unlink=True)
if ANIMS == 'core':
    for a in list(bpy.data.actions):
        if a.name not in CORE_CLIPS:
            bpy.data.actions.remove(a)

# Rest pose for all geometry work.
rig.data.pose_position = 'REST'
bpy.context.view_layer.update()

# ---------------------------------------------------------------- 0. body lengths
# Real proportions: lengthen or shorten bones in the rest pose and move the body with them
# (linear blend skinning of the change), so every move still plays on the new skeleton.
LENGTH_KEYS = {  # spec "body" key -> parts of bone names it lengthens
    'legs': ('thigh', 'shin'), 'arms': ('upper_arm', 'forearm'), 'torso': ('spine', 'hips'),
    'neck': ('neck',), 'shoulder_width': ('shoulder',), 'feet_length': ('foot', 'toe'),
}
_b = spec.get('body', {})
length_f = {k: float(_b[k]) for k in LENGTH_KEYS if k in _b}
height = float(_b.get('height', 0)) or None
if length_f or height:
    A_inv = rig.matrix_world.inverted()

    def factor(name):
        for k, toks in LENGTH_KEYS.items():
            if k in length_f and any(t in name for t in toks):
                return length_f[k]
        return 1.0

    D, new_head, new_tail = {}, {}, {}
    order = [b for b in rig.data.bones if b.parent is None]
    i = 0
    while i < len(order):
        order += list(order[i].children)
        i += 1
    for b in order:
        R = b.matrix_local.to_3x3().normalized()
        f = factor(b.name)
        h_old, t_old = b.head_local.copy(), b.tail_local.copy()
        h_new = D[b.parent.name] @ h_old if b.parent else h_old.copy()
        S = R @ Matrix.Diagonal((1.0, f, 1.0)) @ R.transposed()
        D[b.name] = Matrix.Translation(h_new) @ S.to_4x4() @ Matrix.Translation(-h_old)
        new_head[b.name] = h_new
        new_tail[b.name] = h_new + (t_old - h_old) * f
    # move the body by its bone weights
    gi = {g.index: g.name for g in body.vertex_groups}
    to_arm = A_inv @ body.matrix_world
    from_arm = to_arm.inverted()
    zmin_old = min((to_arm @ v.co).z for v in body.data.vertices)
    moved = []
    for v in body.data.vertices:
        p = to_arm @ v.co
        acc, tot = Vector((0, 0, 0)), 0.0
        for g in v.groups:
            n = gi.get(g.group)
            if n in D and g.weight > 0:
                acc += (D[n] @ p) * g.weight
                tot += g.weight
        moved.append(acc / tot if tot > 0 else p)
    zmin_new = min(p.z for p in moved)
    lift = Vector((0, 0, zmin_old - zmin_new))   # feet stay on the ground
    s = 1.0
    if height:
        zmax_new = max(p.z for p in moved) + lift.z
        s = height / max(zmax_new - zmin_old, 1e-6)
    ground = Vector((0, 0, zmin_old))

    def fix(p):
        return ground + (p + lift - ground) * s

    for v, p in zip(body.data.vertices, moved):
        v.co = from_arm @ fix(p)
    body.data.update()
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in rig.data.edit_bones:
        if eb.name in new_head:
            roll = eb.roll
            eb.head = fix(new_head[eb.name])
            eb.tail = fix(new_tail[eb.name])
            eb.roll = roll
    bpy.ops.object.mode_set(mode='OBJECT')
    if s != 1.0 or lift.z:
        # moves that bob the hips were keyed for the old height: scale their offsets with it
        for act in bpy.data.actions:
            for fc in getattr(act, 'fcurves', []):
                if 'location' in fc.data_path:
                    for kp in fc.keyframe_points:
                        kp.co.y *= s
                        kp.handle_left.y *= s
                        kp.handle_right.y *= s
    bpy.context.view_layer.update()
    print(f'CHAR body lengths {length_f} height {height}: scale {s:.3f}')

MW = body.matrix_world
MWI = MW.inverted()
bones = rig.data.bones


def bone_seg(name):
    b = bones[name]
    return rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local


def bone_point(name, t):
    h, tl = bone_seg(name)
    return h.lerp(tl, t)


SIDES = ('L', 'R')
REGIONS = {
    'head': ['DEF-head'],
    'neck': ['DEF-neck'],
    'chest': ['DEF-spine.002', 'DEF-spine.003'],
    'waist': ['DEF-spine.001'],
    'torso': ['DEF-spine.001', 'DEF-spine.002', 'DEF-spine.003', 'DEF-shoulder.L', 'DEF-shoulder.R'],
    'pelvis': ['DEF-hips'],
    'hips': ['DEF-hips'],
    'shoulders': ['DEF-shoulder.L', 'DEF-shoulder.R'],
    'upper_arms': ['DEF-upper_arm.L', 'DEF-upper_arm.R'],
    'forearms': ['DEF-forearm.L', 'DEF-forearm.R'],
    'hands': [f'DEF-{n}.{s}' for s in SIDES for n in ['hand', 'thumb.01', 'thumb.02', 'thumb.03'] +
              [f'f_{f}.0{i}' for f in ('index', 'middle', 'ring', 'pinky') for i in (1, 2, 3)]],
    'thighs': ['DEF-thigh.L', 'DEF-thigh.R'],
    'shins': ['DEF-shin.L', 'DEF-shin.R'],
    'lower_shins': ['DEF-shin.L', 'DEF-shin.R'],
    'feet': ['DEF-foot.L', 'DEF-foot.R', 'DEF-toe.L', 'DEF-toe.R'],
}


def hexcol(h, a=1.0):
    h = str(h).lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, a)


_mats = {}


def material(color, name=None):
    key = (str(color).lower(), name)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name or f'C_{str(color).lstrip("#")}')
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = hexcol(color)
    p.inputs['Roughness'].default_value = 0.9
    if 'Metallic' in p.inputs:
        p.inputs['Metallic'].default_value = 0.0
    m.diffuse_color = hexcol(color)
    _mats[key] = m
    return m


# ---------------------------------------------------------------- per-vertex data
def group_index_map(obj):
    return {g.index: g.name for g in obj.vertex_groups}


def vertex_weights(obj):
    gi = group_index_map(obj)
    return [{gi[g.group]: g.weight for g in v.groups if g.weight > 0} for v in obj.data.vertices]


W = vertex_weights(body)


def region_weight(wd, region):
    names = REGIONS[region]
    return sum(wd.get(n, 0.0) for n in names)


def closest_on_seg(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return a + ab * t, t


# ---------------------------------------------------------------- 1. proportions
props = spec.get('body', {})
BONE_FACTOR = {}
for key, f in props.items():
    if key == 'neck_thick':
        key = 'neck'
    elif key == 'head' or key in LENGTH_KEYS or key not in REGIONS:
        continue  # head size and lengths are handled elsewhere
    for n in REGIONS[key]:
        BONE_FACTOR[n] = float(f)
if 'shoulders' in props:
    BONE_FACTOR['DEF-spine.003'] = (BONE_FACTOR.get('DEF-spine.003', 1.0) + float(props['shoulders'])) / 2

segs = {n: bone_seg(n) for n in bones.keys() if n.startswith('DEF-')}
head_scale = float(props.get('head', 1.0))
hh, ht = segs['DEF-head']
neck_base = segs['DEF-neck'][0]

for i, v in enumerate(body.data.vertices):
    p = MW @ v.co
    new = p.copy()
    disp = Vector((0, 0, 0))
    for n, w in W[i].items():
        f = BONE_FACTOR.get(n)
        if f is None or n not in segs:
            continue
        a, b = segs[n]
        c, _ = closest_on_seg(p, a, b)
        # widen sideways and in depth, not along the bone
        disp += (p - c) * (f - 1.0) * w
    new += disp
    wh = W[i].get('DEF-head', 0.0) + 0.5 * W[i].get('DEF-neck', 0.0) * (1 if head_scale > 1 else 0)
    if head_scale != 1.0 and wh > 0:
        new = new + ((hh + (new - hh) * head_scale) - new) * min(1.0, wh)
    v.co = MWI @ new

# The head grew upward from the neck joint: the head bone's tail should follow (not needed for skinning).
body.data.update()

skin = spec.get('skin', '#e8b991')
body.data.materials.clear()
body.data.materials.append(material(skin, 'Skin'))
for poly in body.data.polygons:
    poly.material_index = 0

# Geometry helpers -------------------------------------------------------------
def world_verts(obj):
    return [obj.matrix_world @ v.co for v in obj.data.vertices]


def bvh_of(obj):
    vs = world_verts(obj)
    return BVHTree.FromPolygons(vs, [tuple(p.vertices) for p in obj.data.polygons])


front = Vector((0, -1, 0))
tf, tt = segs['DEF-foot.L']
if (tt - tf).y > 0:
    front = Vector((0, 1, 0))
up = Vector((0, 0, 1))
side = front.cross(up)  # character's left or right; only used symmetrically

BV = world_verts(body)
head_pts = [BV[i] for i in range(len(BV)) if W[i].get('DEF-head', 0) > 0.6]
head_center = sum(head_pts, Vector()) / max(1, len(head_pts))
zmin = min(p.z for p in head_pts)
zmax = max(p.z for p in head_pts)
head_radius = max((p - head_center).length for p in head_pts)
head_half_w = max(abs((p - head_center).dot(side)) for p in head_pts)


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def attach(obj, bone, weight=1.0):
    """Skin a whole mesh object to one bone (it moves with that bone in every animation)."""
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()
    g = obj.vertex_groups.new(name=bone)
    g.add(range(len(obj.data.vertices)), weight, 'REPLACE')
    mod = obj.modifiers.new('Armature', 'ARMATURE')
    mod.object = rig
    return obj


def attach_by_nearest(obj, region_bones=None):
    """Skin a new mesh by copying the weights of the nearest body vertex (clothes, hair caps)."""
    from mathutils.kdtree import KDTree
    kd = KDTree(len(BV))
    for i, p in enumerate(BV):
        kd.insert(p, i)
    kd.balance()
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()
    groups = {}
    for vi, v in enumerate(obj.data.vertices):
        _, idx, _ = kd.find(obj.matrix_world @ v.co)
        for n, w in W[idx].items():
            if region_bones and n not in region_bones:
                continue
            if n not in groups:
                groups[n] = obj.vertex_groups.new(name=n)
            groups[n].add([vi], w, 'REPLACE')
    mod = obj.modifiers.new('Armature', 'ARMATURE')
    mod.object = rig
    return obj


def attach_like_body(obj):
    """Skin a mesh cut from the body (clothes, hair caps): it already carries the body's own
    weights, stored by group number, so recreate the body's groups in the same order."""
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()
    # a fresh object has no groups; clearing would also wipe the copied weights
    for g in body.vertex_groups:
        obj.vertex_groups.new(name=g.name)
    mod = obj.modifiers.new('Armature', 'ARMATURE')
    mod.object = rig
    return obj


def new_mesh_obj(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    return link(bpy.data.objects.new(name, me))


def orient(direction):
    """Rotation matrix taking +Z to direction."""
    return direction.normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()


# ---------------------------------------------------------------- 2. outfit layers
def region_mask(regions, i):
    tot = 0.0
    for r in regions:
        if r == 'lower_shins':
            wd = W[i].get('DEF-shin.L', 0) + W[i].get('DEF-shin.R', 0)
            if wd > 0:
                # only the lower half of the shin
                for s in SIDES:
                    a, b = segs[f'DEF-shin.{s}']
                    _, t = closest_on_seg(BV[i], a, b)
                    if W[i].get(f'DEF-shin.{s}', 0) > 0 and t > 0.55:
                        tot += W[i].get(f'DEF-shin.{s}', 0)
            continue
        tot += region_weight(W[i], r)
    return tot


def outfit_layer(item, layer_no):
    regions = item.get('on', [])
    puff = float(item.get('puff', 0.02)) + 0.004 * layer_no
    keep = {i for i in range(len(BV)) if region_mask(regions, i) >= 0.5}
    open_front = float(item.get('open_front', 0.0))
    if open_front > 0:
        keep = {i for i in keep if abs((BV[i] - head_center).dot(side)) > open_front or (BV[i] - head_center).dot(front) < 0}
    if not keep:
        print(f'CHAR warning: outfit "{item.get("name")}" covers nothing; regions {regions}')
        return None
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    gone = [v for v in bm.verts if v.index not in keep]
    bmesh.ops.delete(bm, geom=gone, context='VERTS')
    bm.normal_update()
    for v in bm.verts:
        v.co = v.co + v.normal * puff
    # a little loose cloth: the garment's own thickness reads as a hem in the outline
    me = bpy.data.meshes.new(item.get('name', 'cloth'))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material(item.get('color', '#888888')))
    obj = link(bpy.data.objects.new(item.get('name', 'cloth'), me))
    obj.matrix_world = MW.copy()
    loose = int(item.get('loose', 0))
    if loose > 0:
        # loose cloth hangs over the body instead of hugging every muscle: smooth the shell
        # (more iterations = looser), keeping its edges where they are
        sm = obj.modifiers.new('loose', 'LAPLACIANSMOOTH')
        sm.iterations = loose
        sm.lambda_factor = 0.5
        sm.use_volume_preserve = True
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier='loose')
    sol = obj.modifiers.new('hem', 'SOLIDIFY')
    sol.thickness = float(item.get('thick', 0.012))
    sol.offset = -1
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier='hem')
    for p in obj.data.polygons:
        p.use_smooth = True
    attach_like_body(obj)
    return obj


parts = []
covered = set()
for n, item in enumerate(spec.get('outfit', [])):
    o = outfit_layer(item, n)
    if o:
        parts.append(o)
        if not item.get('see_through') and float(item.get('puff', 0.02)) >= 0.015:
            gap = float(item.get('open_front', 0.0))
            # skin fully under the garment is removed (it pokes through when limbs bend);
            # an open front keeps the skin in its opening, plus a margin
            covered |= {i for i in range(len(BV)) if region_mask(item.get('on', []), i) >= 0.98
                        and (not gap or abs((BV[i] - head_center).dot(side)) > gap + 0.03 or (BV[i] - head_center).dot(front) < 0)}

# ---------------------------------------------------------------- 3. bands
BAND_AT = {
    'waist': [('DEF-spine.001', 0.15)], 'belt': [('DEF-spine.001', 0.15)],
    'wrists': [('DEF-forearm.L', 0.9), ('DEF-forearm.R', 0.9)],
    'forearms': [('DEF-forearm.L', 0.55), ('DEF-forearm.R', 0.55)],
    'ankles': [('DEF-shin.L', 0.92), ('DEF-shin.R', 0.92)],
    'neck': [('DEF-neck', 0.5)], 'forehead': [('DEF-head', 0.45)],
    'upper_arms': [('DEF-upper_arm.L', 0.35), ('DEF-upper_arm.R', 0.35)],
    'thighs': [('DEF-thigh.L', 0.3), ('DEF-thigh.R', 0.3)],
}


def ring_radius(bone, t, all_objs):
    a, b = segs[bone]
    axis = (b - a).normalized()
    c = a.lerp(b, t)
    best = 0.0
    for obj in all_objs:
        for v in obj.data.vertices:
            p = obj.matrix_world @ v.co
            d = p - c
            if abs(d.dot(axis)) < 0.03:
                r = (d - axis * d.dot(axis)).length
                if r < 0.35:
                    best = max(best, r)
    return best or 0.06, c, axis


for band in spec.get('bands', []):
    for bone, t in BAND_AT.get(band.get('at', 'waist'), []):
        r, c, axis = ring_radius(bone, float(band.get('t', t)), [body] + parts)
        width = float(band.get('width', 0.06))
        thick = float(band.get('thick', 0.025))
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=False, segments=24, radius1=r + thick * 0.35, radius2=r + thick * 0.35, depth=width)
        # give it a rounded, chunky profile
        res = bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thick)
        o = new_mesh_obj(f'band_{band.get("at")}', bm, material(band.get('color', '#333333')))
        o.matrix_world = Matrix.Translation(c) @ orient(axis)
        bev = o.modifiers.new('round', 'BEVEL'); bev.width = min(thick, width) * 0.35; bev.segments = 2
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.select_all(action='DESELECT'); o.select_set(True)
        bpy.ops.object.modifier_apply(modifier='round')
        attach(o, bone)
        parts.append(o)

# ---------------------------------------------------------------- head frame
# Everything about the face and hair is designed per character in the spec; there are no
# built-in eyes, brows or hairstyles. These are only the coordinates they are drawn in.
right = -side                      # the viewer's right when looking at the face
head_h = zmax - zmin
tree = bvh_of(body)


def head_dir(az, el):
    """Direction from the head centre: az 0 = toward the face, 90 = viewer's right, 180 = back;
    el 0 = level, 90 = straight up, negative = downward."""
    a, e = math.radians(az), math.radians(el)
    return (front * math.cos(a) + right * math.sin(a)) * math.cos(e) + up * math.sin(e)


def face_point(x, y):
    """Face units: x in head half-widths from the centre line (+ = viewer's right),
    y from the chin (0) to the crown (1)."""
    return Vector((head_center.x, head_center.y, zmin + y * head_h)) + right * (x * head_half_w)


# ---------------------------------------------------------------- 4. hair (designed per character)
hair = spec.get('hair')
if hair:
    hcol = material(hair.get('color', '#222222'))
    cap_spec = hair.get('cap', {})
    if cap_spec is not False:
        # Scalp cover: the head skin above a hairline that can sit at a different height
        # at the front (forehead), the sides (temples, ears) and the back (nape).
        y_front = float(cap_spec.get('hairline', 0.75))
        y_side = float(cap_spec.get('sides', 0.55))
        y_back = float(cap_spec.get('nape', 0.25))
        thick = float(cap_spec.get('thickness', 0.02))
        bm = bmesh.new()
        bm.from_mesh(body.data)
        bm.verts.ensure_lookup_table()
        keep = set()
        for i, p in enumerate(BV):
            if W[i].get('DEF-head', 0) < 0.5:
                continue
            rel = p - head_center
            flat = (rel - up * rel.dot(up))
            f = flat.normalized().dot(front) if flat.length > 1e-6 else 0.0
            y_line = y_side + (y_front - y_side) * max(f, 0) + (y_back - y_side) * max(-f, 0)
            if (p.z - zmin) / head_h >= y_line:
                keep.add(i)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context='VERTS')
        bm.normal_update()
        for v in bm.verts:
            v.co = v.co + v.normal * thick
        cap = new_mesh_obj('hair_cap', bm, hcol)
        cap.matrix_world = MW.copy()
        attach_like_body(cap)
        parts.append(cap)

    def lock(L):
        """One lock of hair: a tapered tube swept from a root on the scalp."""
        az, el = L.get('at', [0, 60])
        root_dir = head_dir(az, el)
        hit = tree.ray_cast(head_center, root_dir, head_radius * 3)
        root = hit[0] if hit[0] is not None else head_center + root_dir * head_radius
        d0 = head_dir(*L['dir']) if 'dir' in L else root_dir
        length = float(L.get('length', 0.15))
        width = float(L.get('width', 0.06))
        thick = float(L.get('thick', 0.6))
        tip = float(L.get('tip', 0.0))
        droop = float(L.get('droop', 0.0))
        sway = float(L.get('sway', 0.0))
        twist = math.radians(float(L.get('twist', 0.0)))
        sides = int(L.get('sides', 6))
        segs = int(L.get('segments', 6))
        root = root - root_dir * width * float(L.get('depth', 0.4))
        tangent = up.cross(d0)
        tangent = tangent.normalized() if tangent.length > 1e-6 else right
        pts, dirs = [root], []
        for i in range(segs):
            t = (i + 0.5) / segs
            d = (d0 - up * (droop * 2.5 * t ** 1.5) + tangent * (sway * t)).normalized()
            dirs.append(d)
            pts.append(pts[-1] + d * (length / segs))
        dirs.append(dirs[-1])
        bm = bmesh.new()
        rings = []
        for i, (p, d) in enumerate(zip(pts, dirs)):
            t = i / segs
            w = width * (1 - (1 - tip) * t) / 2
            if i == segs and tip <= 0.01:
                rings.append([bm.verts.new(p)])
                continue
            ref = up if abs(d.dot(up)) < 0.9 else front
            a = d.cross(ref).normalized()
            b = d.cross(a).normalized()
            ring = []
            for k in range(sides):
                ang = 2 * math.pi * k / sides + twist
                ring.append(bm.verts.new(p + a * math.cos(ang) * w + b * math.sin(ang) * w * thick))
            rings.append(ring)
        for r0, r1 in zip(rings, rings[1:]):
            for k in range(sides):
                if len(r1) == 1:
                    bm.faces.new((r0[k], r0[(k + 1) % sides], r1[0]))
                else:
                    bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k]))
        bm.faces.new(list(reversed(rings[0])))
        if len(rings[-1]) > 1:
            bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = new_mesh_obj('hair_lock', bm, material(L.get('color', hair.get('color', '#222222'))))
        for poly in o.data.polygons:
            poly.use_smooth = not L.get('facets', False)
        attach(o, 'DEF-head')
        parts.append(o)

    for L in hair.get('locks', []):
        rep = L.get('repeat')
        items = [L]
        if rep:
            rnd = random.Random(int(rep.get('seed', 1)))
            jit = float(rep.get('jitter', 0.0))
            items = []
            for i in range(int(rep.get('count', 1))):
                c = dict(L)
                az, el = L.get('at', [0, 60])
                c['at'] = [az + i * float(rep.get('az_step', 0)) + rnd.uniform(-20, 20) * jit,
                           el + i * float(rep.get('el_step', 0)) + rnd.uniform(-10, 10) * jit]
                if 'dir' in L:
                    c['dir'] = [L['dir'][0] + i * float(rep.get('az_step', 0)), L['dir'][1]]
                c['length'] = float(L.get('length', 0.15)) * (1 + rnd.uniform(-0.25, 0.25) * jit)
                items.append(c)
        for c in items:
            lock(c)
            if c.get('mirror'):
                m = dict(c)
                m['at'] = [-c['at'][0], c['at'][1]] if 'at' in c else [0, 60]
                if 'dir' in c:
                    m['dir'] = [-c['dir'][0], c['dir'][1]]
                m['sway'] = -float(c.get('sway', 0.0))
                lock(m)

# ---------------------------------------------------------------- 5. face (designed per character)
def smooth_outline(pts, rounds=2):
    for _ in range(rounds):  # Chaikin corner cutting: soft, drawn curves from a few points
        out = []
        for a, b in zip(pts, pts[1:] + pts[:1]):
            out += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]),
                    (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        pts = out
    return pts


def feature(F, mirrored=False):
    """A flat drawn shape laid onto the face: an outline in face units around `at`."""
    ax, ay = F.get('at', [0, 0.5])
    if 'ellipse' in F:
        ew, eh = F['ellipse']
        pts = [(math.cos(a) * ew, math.sin(a) * eh) for a in [i * math.pi / 12 for i in range(24)]]
    else:
        pts = [tuple(q) for q in F['points']]
        if F.get('smooth'):
            pts = smooth_outline(pts)
    rot = math.radians(float(F.get('rotate', 0.0)))
    pts = [(x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)) for x, y in pts]
    if mirrored:
        ax = -ax
        pts = [(-x, y) for x, y in reversed(pts)]
    lift = 0.003 + 0.0015 * int(F.get('layer', 0))
    bm = bmesh.new()
    verts = []
    for x, y in pts:
        p = face_point(ax + x, ay + y)
        hit = tree.ray_cast(p + front * 0.4, -front, 0.8)
        if hit[0] is None:
            bm.free()
            print(f'CHAR warning: feature "{F.get("name")}" falls off the face; move it inward')
            return
        n = hit[1].normalized()
        if n.dot(front) < 0:
            n = -n
        verts.append(bm.verts.new(hit[0] + n * lift))
    f = bm.faces.new(verts)
    f.normal_update()
    if f.normal.dot(front) < 0:
        f.normal_flip()  # face outward, or the game hides it (back faces are not drawn)
    bmesh.ops.triangulate(bm, faces=[f])
    bm.normal_update()
    col = F.get('color', '#111111')
    o = new_mesh_obj(F.get('name', 'feature'), bm, material(col, f'Decal_{str(col).lstrip("#")}'))
    for poly in o.data.polygons:
        poly.use_smooth = False
    attach_by_nearest(o)  # follows the face skin exactly
    parts.append(o)


face = spec.get('face') or {}
features = face.get('features', [])
if not features:
    print('CHAR warning: no face designed (face.features is empty), so the character has no eyes, brows or mouth')
for F in features:
    feature(F)
    if F.get('mirror'):
        feature(F, mirrored=True)

# ---------------------------------------------------------------- 6. extra script
if EXTRA:
    scope = dict(globals())
    exec(compile(open(EXTRA).read(), EXTRA, 'exec'), scope)

# ---------------------------------------------------------------- 7. one mesh, export
if covered:
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    hidden = [f for f in bm.faces if all(v.index in covered for v in f.verts)]
    bmesh.ops.delete(bm, geom=hidden, context='FACES_ONLY')
    bm.to_mesh(body.data)
    bm.free()
for o in parts:
    if o.name not in bpy.data.objects:
        continue
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o is not body and o.parent is None:
        # anything an extra script forgot to attach follows the head by default
        attach(o, 'DEF-head')
bpy.ops.object.select_all(action='DESELECT')
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
body.name = 'Character'
rig.data.pose_position = 'POSE'
tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_animations=True,
                          export_animation_mode='ACTIONS', export_yup=True, export_apply=False)
print(f'CHAR built {OUT}: {tris} triangles, {len(bpy.data.actions)} moves, materials '
      + ', '.join(m.name for m in body.data.materials))
