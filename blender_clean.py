"""Blender clean-up for a picture-to-3D character, before rigging.

  blender -b --python blender_clean.py -- IN.glb OUT.glb [--tex 2048] [--faces 20000] [--voxels 200] [--symmetry] [--no-trim]

detailed.py runs this (see blender_clean there); it is not meant to be run by hand.
IN is a TripoSR model as local3d writes it: +X toward the camera, Y across the
body, Z up (in the glTF file). Blender's glTF import turns that into X front,
-Y up, Z across, which is what the code below uses.

1. Trim invented lumps on the back: picture-to-3D sees only the front, and per
   slice of height a body can't reach much further behind its middle than in front.
2. Voxel remesh: one even, closed surface (fills holes, closes the trimmed back).
3. Optional left-right mirror, gentle volume-keeping smoothing, a sensible triangle count.
4. New UVs, and the original colours baked onto the clean surface.
"""
import math
import sys

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
src_path, out_path = argv[0], argv[1]


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


tex, faces, voxels = opt('--tex', 2048), opt('--faces', 20000), opt('--voxels', 200)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src_path)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
src = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# Centre the body across (Z), so a mirror is about its middle.
across = sorted(v.co.z for v in src.data.vertices)
mid = (across[int(len(across) * 0.02)] + across[int(len(across) * 0.98)]) / 2
for v in src.data.vertices:
    v.co.z -= mid
size = max(src.dimensions)

# 1. Trim lumps behind the body (per 2% slice of height).
if '--no-trim' not in argv:
    ups = [-v.co.y for v in src.data.vertices]
    lo, step = min(ups), (max(ups) - min(ups)) / 50 + 1e-9
    slices = {}
    for v in src.data.vertices:
        slices.setdefault(int((-v.co.y - lo) / step), []).append(v)
    trimmed = 0
    for group in slices.values():
        if len(group) < 20:
            continue
        xs = sorted(v.co.x for v in group)
        middle = xs[len(xs) // 2]
        front = xs[int(len(xs) * 0.95)] - middle
        limit = middle - 1.4 * max(front, 0.03 * size)
        for v in group:
            if v.co.x < limit:
                v.co.x = limit
                trimmed += 1
    print('TRIMMED', trimmed)

dst = src.copy()
dst.data = src.data.copy()
bpy.context.collection.objects.link(dst)
dst.data.materials.clear()
bpy.ops.object.select_all(action='DESELECT')
dst.select_set(True)
bpy.context.view_layer.objects.active = dst

# 2. One even, closed surface.
mod = dst.modifiers.new('remesh', 'REMESH')
mod.mode, mod.voxel_size = 'VOXEL', size / voxels
bpy.ops.object.modifier_apply(modifier='remesh')
# 3. Mirror (optional), smooth, reduce.
if '--symmetry' in argv:
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.symmetrize(direction='NEGATIVE_Z')
    bpy.ops.object.mode_set(mode='OBJECT')
mod = dst.modifiers.new('smooth', 'CORRECTIVE_SMOOTH')
mod.iterations, mod.factor, mod.smooth_type, mod.use_only_smooth = 6, 0.5, 'LENGTH_WEIGHTED', True
bpy.ops.object.modifier_apply(modifier='smooth')
if len(dst.data.polygons) > faces:
    mod = dst.modifiers.new('reduce', 'DECIMATE')
    mod.ratio = faces / len(dst.data.polygons)
    bpy.ops.object.modifier_apply(modifier='reduce')
bpy.ops.object.shade_smooth()

# 4. New UVs, and the original colours baked onto them.
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
bpy.ops.object.mode_set(mode='OBJECT')
img = bpy.data.images.new('baked', tex, tex)
mat = bpy.data.materials.new('baked')
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
image_node = nodes.new('ShaderNodeTexImage')
image_node.image = img
mat.node_tree.links.new(image_node.outputs['Color'], bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = 0.9
nodes.active = image_node
dst.data.materials.append(mat)

scene = bpy.context.scene
scene.render.engine, scene.cycles.device, scene.cycles.samples = 'CYCLES', 'CPU', 1
bake = scene.render.bake
bake.use_selected_to_active, bake.cage_extrusion, bake.max_ray_distance = True, size * 0.03, size * 0.08
bake.use_pass_direct, bake.use_pass_indirect, bake.use_pass_color, bake.margin = False, False, True, 8
bpy.ops.object.select_all(action='DESELECT')
src.select_set(True)
dst.select_set(True)
bpy.context.view_layer.objects.active = dst
bpy.ops.object.bake(type='DIFFUSE')
img.file_format = 'JPEG'
img.pack()

bpy.data.objects.remove(src)
bpy.ops.object.select_all(action='DESELECT')
dst.select_set(True)
bpy.ops.export_scene.gltf(filepath=out_path, use_selection=True, export_format='GLB', export_image_format='JPEG')
print('CLEAN_OK', len(dst.data.polygons), 'faces')
