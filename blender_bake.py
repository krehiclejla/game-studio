"""Bake one model's colours onto another model's surface (new UVs), in Blender.

  blender -b --python blender_bake.py -- SOURCE.glb TARGET.glb OUT.glb [--tex 2048] [--cage 0.05] [--ray 0.15]

SOURCE: the textured model to take colours from. TARGET: a mesh in the same place
(any UVs are replaced). OUT: TARGET with one baked colour texture. Positions are
kept exactly (glTF in, glTF out), so callers can match vertices back by position.
Used by body_base.py; not meant to be run by hand.
"""
import math
import sys

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
src_path, dst_path, out_path = argv[:3]


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


tex, cage, ray = opt('--tex', 2048), opt('--cage', 0.05), opt('--ray', 0.15)
# --remesh SIZE: first rebuild TARGET as one closed surface with voxels of SIZE metres
# (fills holes, fuses loose flaps and layered clothing to the body), then smooth it a
# little and keep a sensible triangle count (--faces).
remesh, faces = opt('--remesh', 0.0), opt('--faces', 40000)


def load(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


bpy.ops.wm.read_factory_settings(use_empty=True)
src = load(src_path)
# TARGET may name one part 'fuse' (remeshed on its own); the rest is joined on as is.
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=dst_path)
parts = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
fuse = next((o for o in parts if o.name.startswith('fuse') or (o.data and o.data.name.startswith('fuse'))), None)
others = [o for o in parts if o is not fuse]
if fuse is None:
    fuse, others = parts[0], parts[1:]
bpy.ops.object.select_all(action='DESELECT')
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = fuse
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
dst = fuse
dst.data.materials.clear()
if remesh > 0:
    bpy.ops.object.select_all(action='DESELECT')
    dst.select_set(True)
    bpy.context.view_layer.objects.active = dst
    # Voxel remesh needs closed shapes: weld the pieces and cap every open edge first
    # (the neck cut, open clothing shells), otherwise open parts vanish.
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.002)
    bpy.ops.mesh.fill_holes(sides=0)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    mod = dst.modifiers.new('remesh', 'REMESH')
    mod.mode, mod.voxel_size = 'VOXEL', remesh
    bpy.ops.object.modifier_apply(modifier='remesh')
    mod = dst.modifiers.new('smooth', 'CORRECTIVE_SMOOTH')
    mod.iterations, mod.factor, mod.use_only_smooth = 4, 0.5, True
    bpy.ops.object.modifier_apply(modifier='smooth')
    if len(dst.data.polygons) > faces:
        mod = dst.modifiers.new('reduce', 'DECIMATE')
        mod.ratio = faces / len(dst.data.polygons)
        bpy.ops.object.modifier_apply(modifier='reduce')
# Join the kept parts (the head) back on.
if others:
    bpy.ops.object.select_all(action='DESELECT')
    for o in [dst, *others]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = dst
    bpy.ops.object.join()
    dst = bpy.context.view_layer.objects.active
    dst.data.materials.clear()
while dst.data.uv_layers:
    dst.data.uv_layers.remove(dst.data.uv_layers[0])
bpy.ops.object.select_all(action='DESELECT')
dst.select_set(True)
bpy.context.view_layer.objects.active = dst
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
# Rays leave along the surface normals: make them all point outward.
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
bpy.ops.object.mode_set(mode='OBJECT')

img = bpy.data.images.new('baked', tex, tex)
mat = bpy.data.materials.new('baked')
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
image_node = nodes.new('ShaderNodeTexImage')
image_node.image = img
# Connected only after the bake: a material reading the image it is baked into is a
# circular dependency, and Blender then bakes nothing (an all-black texture).
bsdf.inputs['Roughness'].default_value = 0.9
nodes.active = image_node
dst.data.materials.append(mat)

scene = bpy.context.scene
scene.render.engine, scene.cycles.device, scene.cycles.samples = 'CYCLES', 'CPU', 1
bake = scene.render.bake
bake.use_selected_to_active, bake.cage_extrusion, bake.max_ray_distance = True, cage, ray
bake.use_pass_direct, bake.use_pass_indirect, bake.use_pass_color, bake.margin = False, False, True, 8
bpy.ops.object.select_all(action='DESELECT')
src.select_set(True)
dst.select_set(True)
bpy.context.view_layer.objects.active = dst
bpy.ops.object.bake(type='DIFFUSE')
mat.node_tree.links.new(image_node.outputs['Color'], bsdf.inputs['Base Color'])
img.file_format = 'JPEG'
img.pack()

bpy.data.objects.remove(src)
bpy.ops.object.select_all(action='DESELECT')
dst.select_set(True)
bpy.ops.export_scene.gltf(filepath=out_path, use_selection=True, export_format='GLB', export_image_format='JPEG',
                          export_normals=True, export_skins=False, export_animations=False)
print('BAKE_OK', len(dst.data.vertices), 'vertices')
