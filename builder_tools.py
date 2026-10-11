"""Modelling helpers for Game Studio Builder scripts (run inside Blender).

    import sys; sys.path.insert(0, '/data/apps/game-studio')
    from builder_tools import *

These are tools, not looks: every shape still comes from the character's own spec. They
turn a Skin-modifier body into shaped forms the way a modeller works: oval cross-sections,
moved masses, flattened planes, smoothed transitions, and garments that hang instead of
inflating. Coordinates are metres, Z up, the model faces -Y.

skin_body(nodes, edges, name='Body', subdiv=2)
    nodes: {id: {"pos": [x, y, z], "r": [rx, ry]}}  rx = width (x), ry = depth (y). Oval
    cross-sections are what stop limbs reading as tubes: a chest is wider than deep, a thigh
    deeper than wide at the top, a forearm flatter near the wrist. The first node is the root.
    Returns the mesh object with Skin and Subdivision applied.

move(obj, center, radius, offset, falloff='smooth')
    Proportional move: every vertex within radius of center shifts by offset, fading to 0 at
    the edge. The main sculpting tool: pull out a jaw, a chin, a brow ridge, shoulder blades,
    calves, a belly, cheekbones; push in a waist, eye sockets, the small of the back.

scale_about(obj, center, radius, factors, falloff='smooth')
    Scale vertices near center by (sx, sy, sz), fading out: flatten the face front, widen
    the shoulders, square the jaw, slim the ankles.

smooth(obj, iterations=5, factor=0.5, center=None, radius=None)
    Laplacian smoothing (optionally only near a point): melts lumps where Skin parts meet.

garment(body, select, name, color, offset=0.02, loose=8, thickness=0.012, hang=0.0)
    A garment made from the body region where select(world_co) is True: copied, pushed out
    by offset, smoothed `loose` times so it hangs over the anatomy instead of hugging it,
    given cloth thickness. hang > 0 pulls the lower edge straight down (trouser legs, skirts,
    coat tails) by that many metres for a draped, gravity-driven line. Returns the object.

hem(obj, z, width, color, axis='z', thickness=0.01)
    A band (cuff, hem, collar, belt) where the garment crosses height z: picks the ring of
    vertices near z and thickens it outward as its own material.

decal(target, points, center, size, color, normal=(0, -1, 0), lift=0.003, name='decal')
    A flat painted shape laid onto target's surface (eyes, irises, highlights, lids, brows,
    mouths, markings): points are 2D (x right, y up) around center, in units of size.
    The material is named Decal_<hex> so the game keeps it flat with no outline.

remesh(obj, voxel=0.012)
    Voxel remesh: fuses parts that were joined into one clean surface.

material(hex, name=None) / join(objs, name) / apply_all(obj) / tris(obj)
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

SC = bpy.context.scene


def _lin(h):
    h = str(h).lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]


_mats = {}


def material(color, name=None):
    key = (name, str(color).lower())
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name or f'C_{str(color).lstrip("#")}')
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*_lin(color), 1)
    p.inputs['Roughness'].default_value = 0.85
    m.diffuse_color = (*_lin(color), 1)
    _mats[key] = m
    return m


def _activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_all(obj):
    _activate(obj)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    return obj


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def skin_body(nodes, edges, name='Body', subdiv=2):
    ids = list(nodes)
    me = bpy.data.meshes.new(name)
    me.from_pydata([nodes[i]['pos'] for i in ids], [(ids.index(a), ids.index(b)) for a, b in edges], [])
    obj = bpy.data.objects.new(name, me)
    SC.collection.objects.link(obj)
    obj.modifiers.new('skin', 'SKIN')
    for k, i in enumerate(ids):
        r = nodes[i].get('r', 0.05)
        rx, ry = (r, r) if isinstance(r, (int, float)) else r
        obj.data.skin_vertices[0].data[k].radius = (rx, ry)
    obj.data.skin_vertices[0].data[0].use_root = True
    if subdiv:
        obj.modifiers.new('sub', 'SUBSURF').levels = subdiv
    apply_all(obj)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def _weight(d, radius, falloff):
    t = max(0.0, 1.0 - d / radius)
    if falloff == 'linear':
        return t
    if falloff == 'sharp':
        return t * t
    return t * t * (3 - 2 * t)  # smooth


def move(obj, center, radius, offset, falloff='smooth'):
    c, off = Vector(center), Vector(offset)
    mw, mwi = obj.matrix_world, obj.matrix_world.inverted()
    for v in obj.data.vertices:
        p = mw @ v.co
        d = (p - c).length
        if d < radius:
            v.co = mwi @ (p + off * _weight(d, radius, falloff))
    obj.data.update()
    return obj


def scale_about(obj, center, radius, factors, falloff='smooth'):
    c, f = Vector(center), Vector(factors)
    mw, mwi = obj.matrix_world, obj.matrix_world.inverted()
    for v in obj.data.vertices:
        p = mw @ v.co
        d = (p - c).length
        if d < radius:
            w = _weight(d, radius, falloff)
            q = c + Vector(((p - c).x * f.x, (p - c).y * f.y, (p - c).z * f.z))
            v.co = mwi @ p.lerp(q, w)
    obj.data.update()
    return obj


def smooth(obj, iterations=5, factor=0.5, center=None, radius=None):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    verts = bm.verts[:]
    if center is not None:
        c = Vector(center)
        mw = obj.matrix_world
        verts = [v for v in bm.verts if ((mw @ v.co) - c).length < radius]
    for _ in range(iterations):
        bmesh.ops.smooth_vert(bm, verts=verts, factor=factor, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def garment(body, select, name, color, offset=0.02, loose=8, thickness=0.012, hang=0.0):
    bm = bmesh.new()
    bm.from_mesh(body.data)
    mw = body.matrix_world
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not select(mw @ v.co)], context='VERTS')
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * offset
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    SC.collection.objects.link(obj)
    obj.matrix_world = mw.copy()
    if loose:
        sm = obj.modifiers.new('loose', 'LAPLACIANSMOOTH')
        sm.iterations = loose
        sm.lambda_factor = 0.6
        sm.use_volume_preserve = True
        apply_all(obj)
    if hang > 0:
        zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices]
        zmin, zmax = min(zs), max(zs)
        for v, z in zip(obj.data.vertices, zs):
            t = 1 - (z - zmin) / max(zmax - zmin, 1e-6)
            p = obj.matrix_world @ v.co
            v.co = obj.matrix_world.inverted() @ Vector((p.x, p.y, p.z - hang * t * t))
    sol = obj.modifiers.new('cloth', 'SOLIDIFY')
    sol.thickness = thickness
    sol.offset = -1
    apply_all(obj)
    obj.data.materials.append(material(color))
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def hem(obj, z, width, color, thickness=0.01):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    mw = obj.matrix_world
    ring = [v for v in bm.verts if abs((mw @ v.co).z - z) < width / 2]
    if not ring:
        bm.free()
        return None
    sel = set(ring)
    faces = [f for f in bm.faces if all(v in sel for v in f.verts)]
    geom = bmesh.ops.duplicate(bm, geom=faces)['geom']
    keep = set(e for e in geom if isinstance(e, bmesh.types.BMVert))
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v not in keep], context='VERTS')
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * thickness
    me = bpy.data.meshes.new('hem')
    bm.to_mesh(me)
    bm.free()
    h = bpy.data.objects.new('hem', me)
    SC.collection.objects.link(h)
    h.matrix_world = mw.copy()
    s = h.modifiers.new('t', 'SOLIDIFY')
    s.thickness = thickness
    apply_all(h)
    h.data.materials.append(material(color))
    return h


def decal(target, points, center, size, color, normal=(0, -1, 0), lift=0.003, name='decal'):
    n = Vector(normal).normalized()
    up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, 1, 0))
    right = up.cross(n).normalized() * -1 if n.y < 0 else up.cross(n).normalized()
    up = n.cross(right).normalized() * (1 if n.y < 0 else -1)
    vs = [target.matrix_world @ v.co for v in target.data.vertices]
    tree = BVHTree.FromPolygons(vs, [tuple(p.vertices) for p in target.data.polygons])
    bm = bmesh.new()
    out = []
    c = Vector(center)
    for x, y in points:
        p = c + right * (x * size) + up * (y * size)
        hit = tree.ray_cast(p + n * 0.3, -n, 0.6)
        if hit[0] is None:
            bm.free()
            print(f'decal {name}: a point misses the surface; move it inward')
            return None
        hn = hit[1].normalized()
        if hn.dot(n) < 0:
            hn = -hn
        out.append(bm.verts.new(hit[0] + hn * lift))
    f = bm.faces.new(out)
    f.normal_update()
    if f.normal.dot(n) < 0:
        f.normal_flip()
    bmesh.ops.triangulate(bm, faces=[f])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material(color, f'Decal_{str(color).lstrip("#")}'))
    o = bpy.data.objects.new(name, me)
    SC.collection.objects.link(o)
    return o


def remesh(obj, voxel=0.012):
    m = obj.modifiers.new('remesh', 'REMESH')
    m.mode = 'VOXEL'
    m.voxel_size = voxel
    apply_all(obj)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def join(objs, name='Character'):
    objs = [o for o in objs if o]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]
