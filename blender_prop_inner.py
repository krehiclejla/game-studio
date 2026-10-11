"""Runs inside Blender for blender_prop.py (see its help). Not meant to be run by hand.

argv after '--': BUILD.py OUT.glb
"""
import math
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

SCRIPT, OUT = sys.argv[sys.argv.index('--') + 1:][:2]

bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene

# ------------------------------------------------------------------ materials
_mats = {}


def _lin(h):
    h = str(h).lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]


def _mat(color, prefix):
    if isinstance(color, bpy.types.Material):
        return color
    key = (prefix, str(color).lower())
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(f'{prefix}_{str(color).lstrip("#")}')
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*_lin(color), 1)
    p.inputs['Roughness'].default_value = 0.9
    m.diffuse_color = (*_lin(color), 1)
    _mats[key] = m
    return m


def material(color):
    return _mat(color, 'C')


def decal(color):
    """Flat ink in the game: no shading, no outline (painted signs, stripes, markings)."""
    return _mat(color, 'Decal')


# ------------------------------------------------------------------ core
def _obj(name, bm, color, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(_mat(color, 'C') if not isinstance(color, bpy.types.Material) else color)
    for p in me.polygons:
        p.use_smooth = smooth
    o = bpy.data.objects.new(name, me)
    SC.collection.objects.link(o)
    return o


def _bevel(o, width, segments=2):
    if width and width > 0:
        m = o.modifiers.new('bevel', 'BEVEL')
        m.width = width
        m.segments = segments
        m.limit_method = 'ANGLE'
        m.harden_normals = False
    return o


def V(p):
    return Vector(p) if not isinstance(p, Vector) else p.copy()


def box(size, at=(0, 0, 0), color='#cccccc', bevel=0.02, base=True, turn=0.0):
    w, d, h = size
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
    if base:
        bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    o = _obj('box', bm, color)
    o.location = V(at)
    o.rotation_euler.z = math.radians(turn)
    return _bevel(o, min(bevel, min(size) * 0.45))


def cyl(radius, height, at=(0, 0, 0), color='#cccccc', sides=16, bevel=0.01, top=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=sides, radius1=radius,
                          radius2=radius if top is None else top, depth=height)
    bmesh.ops.translate(bm, vec=(0, 0, height / 2), verts=bm.verts)
    o = _obj('cyl', bm, color, smooth=sides >= 12)
    o.location = V(at)
    return _bevel(o, min(bevel, radius * 0.4))


def ball(radius, at=(0, 0, 0), color='#cccccc', squash=(1, 1, 1), detail=2):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=detail, radius=radius)
    bmesh.ops.scale(bm, vec=squash, verts=bm.verts)
    o = _obj('ball', bm, color, smooth=detail >= 3)
    o.location = V(at)
    return o


def beam(a, b, thick=0.1, color='#6b4226', bevel=0.01):
    a, b = V(a), V(b)
    d = b - a
    o = box((thick, thick, d.length), (0, 0, 0), color, bevel=bevel, base=True)
    o.matrix_world = Matrix.Translation(a) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    return o


def tube(points, radius=0.05, color='#888888', sides=8):
    pts = [V(p) for p in points]
    parts = []
    for a, b in zip(pts, pts[1:]):
        d = b - a
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=sides, radius1=radius, radius2=radius, depth=d.length)
        bmesh.ops.translate(bm, vec=(0, 0, d.length / 2), verts=bm.verts)
        o = _obj('tube', bm, color, smooth=True)
        o.matrix_world = Matrix.Translation(a) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        parts.append(o)
    for p in pts[1:-1]:
        parts.append(ball(radius, p, color, detail=1))
    return parts[0] if parts else None


def lathe(profile, at=(0, 0, 0), color='#cccccc', sides=24):
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0, z)) for r, z in profile]
    edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=sides, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _obj('lathe', bm, color, smooth=True)
    o.location = V(at)
    return o


def slab(outline, depth=0.05, at=(0, 0, 0), color='#cccccc', axis='y', bevel=0.005):
    bm = bmesh.new()
    vs = [bm.verts.new((x, -depth / 2, z)) for x, z in outline]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    moved = [e for e in ext['geom'] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, depth, 0), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _obj('slab', bm, color)
    if axis == 'x':
        o.rotation_euler.z = math.radians(90)
    o.location = V(at)
    return _bevel(o, bevel, 1)


_WALL = {'-y': (Vector((0, -1, 0)), Vector((1, 0, 0))), '+y': (Vector((0, 1, 0)), Vector((-1, 0, 0))),
         '-x': (Vector((-1, 0, 0)), Vector((0, -1, 0))), '+x': (Vector((1, 0, 0)), Vector((0, 1, 0)))}


def _place_on_wall(o, at, wall):
    n, u = _WALL[wall]
    # local x along the wall, local -y out of the wall (toward the viewer), z up: a proper rotation,
    # never a mirror (a mirrored part is inside out and renders as a black hole in the game)
    rot = Matrix((u, -n, Vector((0, 0, 1)))).transposed().to_4x4()
    # matrix_basis, not matrix_world: the world matrix only updates on the next scene
    # evaluation, so reading it right after setting a location gives the old (identity) one
    o.matrix_basis = Matrix.Translation(V(at)) @ rot @ o.matrix_basis
    return o


def text(words, at=(0, 0, 0), size=0.3, color='#111111', depth=0.02, face='-y', font=None):
    cu = bpy.data.curves.new('text', 'FONT')
    cu.body = str(words)
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    if font:
        cu.font = bpy.data.fonts.load(font)
    tmp = bpy.data.objects.new('text_tmp', cu)
    SC.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    me.materials.clear()
    me.materials.append(decal(color) if not isinstance(color, bpy.types.Material) else color)
    o = bpy.data.objects.new('text', me)
    SC.collection.objects.link(o)
    o.matrix_world = Matrix.Rotation(math.radians(90), 4, 'X')  # stand up, facing -y
    return _place_on_wall(o, at, face)


# ------------------------------------------------------------------ architecture
def _roof_sheet(length, slope_len, segs, thick, upturn, corner_up):
    """A curved roof sheet: x along the ridge, t from eave (0) to ridge (1)."""
    bm = bmesh.new()
    nx = 8
    grid = []
    for i in range(segs + 1):
        t = i / segs
        row = []
        for j in range(nx + 1):
            x = (j / nx - 0.5) * length
            ex = abs(x) / (length / 2)
            z = upturn * (1 - t) ** 2 + corner_up * (1 - t) ** 2 * ex ** 4
            row.append(bm.verts.new((x, t * slope_len, z)))
        grid.append(row)
    for i in range(segs):
        for j in range(nx):
            bm.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))
    bm.normal_update()
    res = bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thick)
    return bm


def gable_roof(w, d, h, at=(0, 0, 0), color='#7a2e2e', overhang=0.3, thick=0.08, upturn=0.0, ridge=None, gable=None):
    """Two roof sheets meeting at a ridge along x. `at` = centre of the footprint at eave height."""
    at = V(at)
    half = d / 2 + overhang
    rise = h + overhang * h / max(d / 2, 1e-6)
    slope_len = math.hypot(half, rise)
    ang = math.atan2(rise, half)
    out = []
    for sgn in (-1, 1):
        bm = _roof_sheet(w + 2 * overhang, slope_len, 6, thick, upturn, upturn * 0.8)
        o = _obj('roof', bm, color)
        # sheet lies in +y from its eave; tilt it up toward the ridge
        rot = Matrix.Rotation(ang, 4, 'X')
        if sgn > 0:
            rot = Matrix.Rotation(math.pi, 4, 'Z') @ rot
        o.matrix_world = Matrix.Translation(at + Vector((0, sgn * half, -overhang * h / max(d / 2, 1e-6)))) @ rot
        out.append(o)
    rc = ridge or color
    cyl(thick * 1.4, w + 2 * overhang + 0.1, (0, 0, 0), rc, sides=10)
    r = bpy.context.scene.collection.objects[-1]
    r.matrix_world = Matrix.Translation(at + Vector((-(w + 2 * overhang + 0.1) / 2, 0, h + thick * 0.6))) @ Matrix.Rotation(math.radians(90), 4, 'Y')
    if gable:
        for sx in (-1, 1):
            slab([(-d / 2, 0), (d / 2, 0), (0, h)], 0.05, at + Vector((sx * w / 2, 0, 0)), gable, axis='x')
    return out[0]


def hip_roof(w, d, h, at=(0, 0, 0), color='#7a2e2e', overhang=0.3, thick=0.08, upturn=0.0):
    at = V(at)
    W, D = w / 2 + overhang, d / 2 + overhang
    r = max(0.0, W - D)
    bm = bmesh.new()
    c = [bm.verts.new(v) for v in [(-W, -D, 0), (W, -D, 0), (W, D, 0), (-W, D, 0)]]
    for v in c:
        v.co.z += upturn
    a, b = bm.verts.new((-r, 0, h)), bm.verts.new((r, 0, h))
    if r > 1e-4:
        for f in [(c[0], c[1], b, a), (c[2], c[3], a, b), (c[1], c[2], b), (c[3], c[0], a)]:
            bm.faces.new(f)
    else:
        bmesh.ops.remove_doubles(bm, verts=[a, b], dist=1e-3)
        top = a if a.is_valid else b
        for f in [(c[0], c[1], top), (c[1], c[2], top), (c[2], c[3], top), (c[3], c[0], top)]:
            bm.faces.new(f)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thick)
    o = _obj('roof', bm, color)
    o.location = at
    return o


def flat_roof(w, d, at=(0, 0, 0), color='#666666', lip=0.1, thick=0.12):
    return box((w + 2 * lip, d + 2 * lip, thick), at, color, bevel=0.02)


def window(w, h, at=(0, 0, 0), wall='-y', frame='#5a3b22', glass='#9ec9e0', bars=(1, 1), depth=0.06):
    t = max(0.04, min(w, h) * 0.08)
    parts = [box((w, 0.02, h), (0, depth * 0.5, 0), glass, bevel=0, base=False)]
    for z in (-h / 2 + t / 2, h / 2 - t / 2):
        parts.append(box((w + t, depth, t), (0, 0, z), frame, bevel=0.008, base=False))
    for x in (-w / 2, w / 2):
        parts.append(box((t, depth, h), (x, 0, 0), frame, bevel=0.008, base=False))
    nx, nz = bars
    for i in range(1, nx + 1):
        x = -w / 2 + i * w / (nx + 1)
        parts.append(box((t * 0.45, depth * 0.6, h), (x, 0.005, 0), frame, bevel=0, base=False))
    for i in range(1, nz + 1):
        z = -h / 2 + i * h / (nz + 1)
        parts.append(box((w, depth * 0.6, t * 0.45), (0, 0.005, z), frame, bevel=0, base=False))
    parts.append(box((w + t * 1.6, depth * 1.6, t * 0.8), (0, -depth * 0.3, -h / 2 - t * 0.4), frame, bevel=0.01, base=False))
    for p in parts:
        _place_on_wall(p, at, wall)
    return parts[0]


def door(w, h, at=(0, 0, 0), wall='-y', color='#6b4226', frame='#3b2414', style='plain'):
    """`at` = bottom centre of the door on the wall surface."""
    at = V(at)
    t = 0.07
    parts = []
    if style == 'arched':
        pts = [(-w / 2, 0), (w / 2, 0), (w / 2, h - w / 2)] + [(math.cos(a) * w / 2, h - w / 2 + math.sin(a) * w / 2) for a in [math.pi * i / 10 for i in range(1, 10)]] + [(-w / 2, h - w / 2)]
        parts.append(slab(pts, 0.04, (0, 0.01, 0), color))
    else:
        parts.append(box((w, 0.04, h), (0, 0.01, 0), color, bevel=0.01))
    if style == 'sliding':
        for i in range(1, 4):
            parts.append(box((w, 0.05, 0.025), (0, -0.005, h * i / 4), frame, bevel=0))
        parts.append(box((0.025, 0.05, h), (0, -0.005, 0), frame, bevel=0))
    parts.append(box((w + 2 * t, 0.08, t), (0, 0, h), frame, bevel=0.01))
    for x in (-w / 2 - t / 2, w / 2 + t / 2):
        parts.append(box((t, 0.08, h), (x, 0, 0), frame, bevel=0.01))
    if style == 'plain':
        parts.append(ball(0.03, (w * 0.35, -0.03, h * 0.48), '#c9a227', detail=1))
    for p in parts:
        _place_on_wall(p, at, wall)
    return parts[0]


def curtain(w, h, at=(0, 0, 0), color='#1f3c88', panels=3, wall='-y'):
    """Noren / cloth strips hanging DOWN from `at` (the top centre)."""
    gap = 0.02
    pw = (w - gap * (panels - 1)) / panels
    parts = []
    for i in range(panels):
        x = -w / 2 + pw / 2 + i * (pw + gap)
        parts.append(box((pw, 0.015, h), (x, -0.05, -h), color, bevel=0.004))
    parts.append(cyl(0.02, w + 0.1, (0, 0, 0), '#3b2414', sides=8))
    rod = parts[-1]
    rod.matrix_world = Matrix.Translation(Vector((-(w + 0.1) / 2, -0.05, 0))) @ Matrix.Rotation(math.radians(90), 4, 'Y')
    for p in parts:
        _place_on_wall(p, at, wall)
    return parts[0]


def awning(w, depth, at=(0, 0, 0), color='#c0392b', stripes=None, slope=0.35, wall='-y'):
    n = 6 if stripes else 1
    sw = w / n
    first = None
    for i in range(n):
        c = stripes if (stripes and i % 2) else color
        o = box((sw, depth, 0.03), (-w / 2 + sw / 2 + i * sw, -depth / 2, 0), c, bevel=0.005)
        o.matrix_basis = Matrix.Rotation(-slope, 4, 'X') @ o.matrix_basis
        _place_on_wall(o, at, wall)
        first = first or o
    return first


def steps(w, depth, rise, count, at=(0, 0, 0), color='#999999'):
    at = V(at)
    first = None
    for i in range(count):
        o = box((w, depth * (count - i), rise), at + Vector((0, -depth * (count - i) / 2, i * rise)), color, bevel=0.01)
        first = first or o
    return first


def fence(points, height=1.0, color='#8b5a2b', post_every=1.0):
    pts = [V(p) for p in points]
    first = None
    for a, b in zip(pts, pts[1:]):
        n = max(1, int((b - a).length / post_every))
        for i in range(n + 1):
            p = a.lerp(b, i / n)
            o = box((0.08, 0.08, height), p, color, bevel=0.01)
            first = first or o
        for z in (height * 0.35, height * 0.8):
            beam(a + Vector((0, 0, z)), b + Vector((0, 0, z)), 0.05, color)
    return first


# ------------------------------------------------------------------ nature
def foliage(at=(0, 0, 0), radius=1.0, color='#f4a7c3', puffs=7, seed=1, shade=None):
    rnd = random.Random(seed)
    at = V(at)
    first = None
    for i in range(puffs):
        d = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.4, 0.8)))
        if d.length > 1:
            d.normalize()
        c = shade if (shade and d.z < -0.1) else color
        o = ball(radius * rnd.uniform(0.45, 0.7), at + d * radius * 0.6, c, squash=(1, 1, rnd.uniform(0.8, 1.0)), detail=2)
        first = first or o
    return first


def trunk(height, radius=0.15, at=(0, 0, 0), color='#6b4a2e', lean=0.0, branches=0, seed=1):
    rnd = random.Random(seed)
    at = V(at)
    o = cyl(radius, height, at, color, sides=8, bevel=0.0, top=radius * 0.6)
    o.rotation_euler.y = lean
    for i in range(branches):
        z = height * rnd.uniform(0.55, 0.9)
        a = rnd.uniform(0, 2 * math.pi)
        start = at + Vector((math.sin(lean) * z, 0, z))
        end = start + Vector((math.cos(a) * height * 0.3, math.sin(a) * height * 0.3, height * 0.25))
        tube([start, end], radius * 0.4, color, sides=6)
    return o


def rock(size=0.5, at=(0, 0, 0), color='#8a8a8a', seed=1):
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=size / 2)
    for v in bm.verts:
        v.co *= rnd.uniform(0.75, 1.15)
        v.co.z = max(v.co.z, -size * 0.15)
    bmesh.ops.translate(bm, vec=(0, 0, size * 0.15), verts=bm.verts)
    o = _obj('rock', bm, color)
    o.location = V(at)
    return o


# ------------------------------------------------------------------ arrange
def mirror_x(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(obj.matrix_basis)
    for v in bm.verts:
        v.co.x = -v.co.x
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(obj.name + '_m', me)
    SC.collection.objects.link(o)
    return o


def repeat(fn, count, step=(0, 0, 0)):
    return [fn(i, Vector(step) * i) for i in range(count)]


def group(name, *objs):
    for o in objs:
        if o:
            o['group'] = name
    return objs


# ------------------------------------------------------------------ run, join, export
scope = {k: v for k, v in globals().items() if not k.startswith('__')}
exec(compile(open(SCRIPT).read(), SCRIPT, 'exec'), scope)

dg = bpy.context.evaluated_depsgraph_get()
meshes = [o for o in SC.objects if o.type == 'MESH']
if not meshes:
    sys.exit('PROP the build script made nothing')
for o in meshes:
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    o.modifiers.clear()
    o.data = me
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.join()
model = bpy.context.view_layer.objects.active
model.name = 'Model'
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
dims = model.dimensions
tris = sum(len(p.vertices) - 2 for p in model.data.polygons)
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_yup=True, export_apply=True)
print(f'PROP built {OUT}: {dims.x:.2f} x {dims.y:.2f} x {dims.z:.2f} m (w x d x h), {tris} triangles, '
      f'{len(model.data.materials)} materials')
