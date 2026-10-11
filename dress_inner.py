"""Runs inside Blender for dress.py (see its help). Not meant to be run by hand.

argv after '--': RESOLVED.json OUT.glb
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector

SPEC_PATH, OUT = sys.argv[sys.argv.index('--') + 1:][:2]
spec = json.load(open(SPEC_PATH))
sc = bpy.context.scene
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ------------------------------------------------------------------ the model
bpy.ops.import_scene.gltf(filepath=spec['model'])
meshes = [o for o in sc.objects if o.type == 'MESH']
colliders = [o for o in meshes if o.name.endswith(('-colonly', '-convcolonly'))]
visible = [o for o in meshes if o not in colliders]
# Lamps: Godot imports Blender's light power far too strong for a game's own lighting, so they
# are left out unless asked for ("keep_lights": true keeps them as a faint glow).
for o in list(sc.objects):
    if o.type == 'LIGHT':
        if spec.get('keep_lights'):
            o.data.energy = min(o.data.energy, 2.0)
        else:
            bpy.data.objects.remove(o, do_unlink=True)

_img = {}


def load_img(path, data=False):
    if path not in _img:
        im = bpy.data.images.load(path)
        if data:
            im.colorspace_settings.name = 'Non-Color'
        _img[path] = im
    return _img[path]


def base_color(m):
    if not m.use_nodes:
        return tuple(m.diffuse_color)
    b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    return tuple(b.inputs['Base Color'].default_value) if b else (0.8, 0.8, 0.8, 1)


def rule_for(name):
    if name.startswith('Decal'):
        return None
    for r in spec.get('materials', []):
        if name.startswith(r['match']):
            return r
    return None


MATS = {}  # material name -> (rule, base colour)
for o in visible:
    for s in o.material_slots:
        if s.material and s.material.name not in MATS:
            r = rule_for(s.material.name)
            if r:
                MATS[s.material.name] = (r, base_color(s.material))


def realize(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        mw = o.matrix_world.copy()
        o.modifiers.clear()
        o.data = me
        o.parent = None
        o.matrix_world = mw


def join(objs, name):
    realize(objs)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    return ob


def box_uvs(ob):
    """Tiling texture coordinates: each face mapped by its dominant axis at the material's real
    tile size, so textures keep their real-world scale on every wall, roof and floor."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    mats = ob.data.materials
    for f in bm.faces:
        m = mats[f.material_index] if f.material_index < len(mats) else None
        if not m or m.name not in MATS:
            continue
        size = float(MATS[m.name][0].get('tile_m', 2.0))
        ax = max(range(3), key=lambda i: abs(f.normal[i]))
        for l in f.loops:
            c = l.vert.co
            u, v = (c.y, c.z) if ax == 0 else (c.x, c.z) if ax == 1 else (c.x, c.y)
            l[uv].uv = (u / size, v / size)
    bm.to_mesh(ob.data); bm.free()


_tinted = {}


def dress_material(m):
    r, base = MATS[m.name]
    files = r['files']
    detail_mix = float(r.get('detail', 0.6))
    key = (r['texture'], tuple(round(x, 3) for x in base[:3]), round(detail_mix, 2))
    if key not in _tinted:
        src = load_img(files['color'])
        px = np.array(src.pixels[:], dtype=np.float32).reshape(-1, 4)
        col = np.array(base[:3], dtype=np.float32)
        lum = px[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        mean = max(float(lum.mean()), 1e-3)
        detail = np.clip(lum / mean, 0.0, 1.6)[:, None]        # grain and grime, brightness-normalised
        photo = px[:, :3] / mean                              # the photo's own colour, same brightness
        tinted = col * (detail * (1 - detail_mix * 0.5) + photo * detail_mix * 0.5)
        name = f"{m.name}_{'tile' if r.get('big') else 'tex'}"
        im = bpy.data.images.new(name, src.size[0], src.size[1])
        im.pixels[:] = np.concatenate([np.clip(tinted, 0, 1), px[:, 3:4]], axis=1).ravel()
        im.file_format = 'JPEG'
        _tinted[key] = im
    nt = m.node_tree if m.use_nodes else None
    if not nt:
        m.use_nodes = True
        nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = _tinted[key]
    nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.85
    if spec.get('keep_maps') and 'normal' in files:
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = load_img(files['normal'], True)
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = 0.8
        nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])


# ------------------------------------------------------------------ props
props = []
budget = int(spec.get('max_prop_tris', 1500))
for p in spec.get('props', []):
    before = set(sc.objects)
    bpy.ops.import_scene.gltf(filepath=p['gltf'])
    new = [o for o in sc.objects if o not in before]
    for r in [o for o in new if o.parent is None]:
        r.location = Vector(p.get('at', (0, 0, 0)))
        r.rotation_euler = Euler((0, 0, math.radians(float(p.get('turn', 0)))))
        s = float(p.get('scale', 1.0))
        r.scale = (s, s, s)
    ms = [o for o in new if o.type == 'MESH']
    total = sum(len(f.vertices) - 2 for o in ms for f in o.data.polygons)
    if total > budget:
        for o in ms:
            d = o.modifiers.new('slim', 'DECIMATE')
            d.ratio = max(0.02, budget / total)
    props.extend(ms)

# ------------------------------------------------------------------ build the game model
model = join(visible, 'dressed')
box_uvs(model)
for m in list(bpy.data.materials):
    if m.name in MATS:
        dress_material(m)
if props:
    realize(props)
# phone limits for prop textures happen in the game build; drop maps the toon look ignores
if not spec.get('keep_maps'):
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        keep = {l.from_node for l in nt.links if l.to_socket.name == 'Base Color'}
        for n in list(nt.nodes):
            if (n.type == 'TEX_IMAGE' and n not in keep) or n.type == 'NORMAL_MAP':
                nt.nodes.remove(n)
for im in list(bpy.data.images):
    try:
        im.pixels[0]
    except Exception:
        continue
    cap = 1024 if im.name.endswith('_tile') else 512
    if im.size[0] > cap or im.size[1] > cap:
        im.scale(cap, cap)

if spec.get('ao', True):
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 32
    for o in colliders:
        o.hide_render = True
    attr = model.data.color_attributes.new('AO', 'BYTE_COLOR', 'CORNER')
    model.data.color_attributes.active_color = attr
    bpy.ops.object.select_all(action='DESELECT')
    model.select_set(True)
    bpy.context.view_layer.objects.active = model
    sc.render.bake.target = 'VERTEX_COLORS'
    bpy.ops.object.bake(type='AO')
    data = np.array([c.color for c in attr.data], dtype=np.float32)
    data[:, :3] = 0.6 + 0.4 * data[:, :3]
    for c, v in zip(attr.data, data):
        c.color = v

tris = sum(len(f.vertices) - 2 for f in model.data.polygons)
ptris = sum(len(f.vertices) - 2 for o in props for f in o.data.polygons)
for o in list(sc.objects):
    if o.type == 'CAMERA':
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_apply=True, export_image_format='JPEG',
                          export_image_quality=85, export_lights=True)
print(f'DRESS {OUT}: model {tris} tris, props {ptris} tris, {len(MATS)} dressed materials, '
      f'{os.path.getsize(OUT) // 1024} KB')
