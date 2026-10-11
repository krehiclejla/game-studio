extends Node
# The game's drawn look in one place. Every visible object goes through Cel:
#   Cel.box(parent, size, position, color)  /  Cel.ball(...)  /  Cel.pole(...)
#   Cel.apply(node)  gives any imported model (GLB scene) the same look.
# Change the style for the whole game here: ink colour and width, shadow colour, bands.

const TOON := preload("res://toon.gdshader")
const OUTLINE := preload("res://outline.gdshader")

var ink := Color(0.06, 0.04, 0.1)
var ink_width := 2.5  # outline width in pixels (at 720p); 0 = no outlines
var shade := Color(0.35, 0.25, 0.5)
var bands := 1.0

func material(color: Color, texture: Texture2D = null) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = TOON
	m.set_shader_parameter("base_color", color)
	m.set_shader_parameter("shade_color", shade)
	m.set_shader_parameter("bands", bands)
	if texture:
		m.set_shader_parameter("base_texture", texture)
	if ink_width > 0.0:
		var o := ShaderMaterial.new()
		o.shader = OUTLINE
		o.set_shader_parameter("width", ink_width)
		o.set_shader_parameter("ink", ink)
		m.next_pass = o
	return m

# Flat, unshaded colour without an outline (decals: eyes, mouths, logos, markings).
func flat(color: Color, texture: Texture2D = null) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.albedo_color = color
	if texture:
		m.albedo_texture = texture
	return m

func mesh(parent: Node, m: Mesh, at: Vector3, color: Color) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = m
	mi.position = at
	mi.material_override = material(color)
	parent.add_child(mi)
	return mi

# Boxes, balls and poles sit ON the given position (their base, not their centre).
func box(parent: Node, size: Vector3, at: Vector3, color: Color) -> MeshInstance3D:
	var m := BoxMesh.new(); m.size = size
	return mesh(parent, m, at + Vector3(0, size.y * 0.5, 0), color)

func ball(parent: Node, radius: float, at: Vector3, color: Color) -> MeshInstance3D:
	var m := SphereMesh.new(); m.radius = radius; m.height = radius * 2.0
	return mesh(parent, m, at + Vector3(0, radius, 0), color)

func pole(parent: Node, radius: float, height: float, at: Vector3, color: Color) -> MeshInstance3D:
	var m := CylinderMesh.new(); m.top_radius = radius; m.bottom_radius = radius; m.height = height
	return mesh(parent, m, at + Vector3(0, height * 0.5, 0), color)

# Give an imported model the drawn look, keeping its own colours and textures.
func apply(node: Node) -> void:
	if node is MeshInstance3D and node.mesh:
		for i in node.mesh.get_surface_count():
			var src = node.get_active_material(i)
			var color := Color.WHITE
			var tex: Texture2D = null
			if src is BaseMaterial3D:
				color = src.albedo_color
				tex = src.albedo_texture
			# Drawn details (eyes, mouths, markings) named "Decal..." stay flat ink: no shading, no outline.
			if src and str(src.resource_name).begins_with("Decal"):
				node.set_surface_override_material(i, flat(color, tex))
			else:
				node.set_surface_override_material(i, material(color, tex))
	for c in node.get_children():
		apply(c)
