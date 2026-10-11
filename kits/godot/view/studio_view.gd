extends Node
# Game Studio's Edit view for Godot games (added to every Godot game by godot_build.py). In the
# studio's Edit mode the game is frozen and a free camera looks around: drag to orbit, pinch or
# scroll to zoom, two fingers (or right mouse) to slide. Tap an object to select it (the studio
# tells the assistant). The studio toolbar sends: home (show everything), see inside (cut away
# above 2.2 m so interiors show) and select (from its object list). In Play mode this does nothing.
#
# Objects are the scene's top-level 3D nodes (and the children of a node named "World"), by name.

const CUT_SHADER := preload("res://studio_view_cut.gdshader")

var cam: Camera3D
var target := Vector3.ZERO
var yaw := 0.7
var pitch := -0.6
var dist := 25.0
var bounds := AABB()
var mats: Array[ShaderMaterial] = []
var objects: Dictionary = {}          # name -> Node3D
var selected := ""
var box: MeshInstance3D
var touches: Dictionary = {}
var pinch_start := 0.0
var dist_start := 0.0
var mid_start := Vector2.ZERO
var target_start := Vector3.ZERO
var press_pos := Vector2.ZERO
var moved := false
var cam_dirty := false


func _ready() -> void:
	if not _edit_mode():
		set_process_input(false)
		set_process(false)
		return
	await get_tree().process_frame
	await get_tree().process_frame
	var scene := get_tree().current_scene
	for n in scene.get_children():
		if not (n is Light3D or n is WorldEnvironment or n is Camera3D):
			n.process_mode = Node.PROCESS_MODE_DISABLED
	for we in scene.find_children("*", "WorldEnvironment", true, false):
		var env: Environment = (we as WorldEnvironment).environment
		if env:
			env = env.duplicate()
			env.fog_enabled = false
			(we as WorldEnvironment).environment = env
	bounds = _scene_bounds()
	_collect_objects(scene)
	_swap_materials(scene)
	cam = Camera3D.new()
	cam.name = "StudioViewCamera"
	cam.far = 2000.0
	scene.add_child(cam)
	cam.current = true
	_make_box()
	_home()
	var saved = JSON.parse_string(_js("JSON.stringify(window.__studioCamera || null)"))
	if saved is Dictionary and saved.has("target"):
		var t: Array = saved["target"]
		target = Vector3(float(t[0]), float(t[1]), float(t[2]))
		yaw = float(saved.get("yaw", yaw)); pitch = float(saved.get("pitch", pitch)); dist = float(saved.get("dist", dist))
		_place_cam()
	var cut_h := _js("window.__studioCut ? String(window.__studioCut) : ''")
	if cut_h != "" and cut_h != "true":
		_set_cut(true, float(cut_h))
	elif cut_h == "true":
		_set_cut(true)
	var sel := _js("window.__studioSelected || ''")
	if sel != "" and objects.has(sel):
		_select(sel, false)
	_send({"type": "godot:objects", "list": objects.keys()})
	# test pages: ?studio_view=1&cut=1&select=NAME&focus=x,y,z,dist,yawdeg,pitchdeg
	var q := _js("new URLSearchParams(location.search).get('select') || ''")
	if q != "" and objects.has(q):
		_select(q, true)
	var f := _js("new URLSearchParams(location.search).get('focus') || ''")
	if f != "":
		var p := f.split(",")
		target = Vector3(float(p[0]), float(p[1]), float(p[2]))
		if p.size() > 3: dist = float(p[3])
		if p.size() > 4: yaw = deg_to_rad(float(p[4]))
		if p.size() > 5: pitch = deg_to_rad(float(p[5]))
		_place_cam()
	if _js("new URLSearchParams(location.search).get('cut') || ''") != "":
		_set_cut(true)


func _edit_mode() -> bool:
	if "studio-view" in OS.get_cmdline_user_args():
		return true
	return _js("(window.__studioMode === 'view' || new URLSearchParams(location.search).has('studio_view')) ? 'yes' : ''") == "yes"


func _js(code: String) -> String:
	if not OS.has_feature("web"):
		return ""
	var v = JavaScriptBridge.eval(code, true)
	return str(v) if v != null else ""


func _send(msg: Dictionary) -> void:
	if OS.has_feature("web"):
		JavaScriptBridge.eval("parent.postMessage(%s, '*')" % JSON.stringify(msg), true)


# ------------------------------------------------------------------ studio commands
func _process(_dt: float) -> void:
	if cam == null:
		return
	var raw := _js("JSON.stringify((window.__studioInbox || []).splice(0))")
	if raw != "" and raw != "[]":
		var list = JSON.parse_string(raw)
		if list is Array:
			for m in list:
				match str(m.get("cmd", "")):
					"home":
						_home()
					"cut":
						_set_cut(bool(m.get("on", false)), float(m.get("height", 2.2)))
					"select":
						var n := str(m.get("name", ""))
						if n == "":
							_select("", false)
						elif objects.has(n):
							_select(n, true)
	if cam_dirty and touches.is_empty():
		cam_dirty = false
		_send({"type": "godot:camera", "camera": {"target": [target.x, target.y, target.z], "yaw": yaw, "pitch": pitch, "dist": dist}})


# ------------------------------------------------------------------ objects and selection
func _collect_objects(scene: Node) -> void:
	var roots: Array = scene.get_children()
	var world := scene.get_node_or_null("World")
	if world:
		roots = world.get_children()
	for n in roots:
		if str(n.name).begins_with("@"):
			continue  # unnamed helpers (labels, effects): only named objects are listed
		if n is Node3D and not (n is Camera3D or n is Light3D or n is WorldEnvironment) \
				and not n.find_children("*", "GeometryInstance3D", true, false).is_empty() or n is GeometryInstance3D:
			var b := _bounds_of(n)
			if b.size.length() > 0.001 and b.size.length() < 400.0:
				objects[str(n.name)] = n


func _bounds_of(n: Node) -> AABB:
	var out := AABB()
	var first := true
	var list: Array = n.find_children("*", "GeometryInstance3D", true, false)
	if n is GeometryInstance3D:
		list.append(n)
	for c in list:
		var g := c as GeometryInstance3D
		var b := g.global_transform * g.get_aabb()
		if first:
			out = b; first = false
		else:
			out = out.merge(b)
	return out


func _pick(screen: Vector2) -> String:
	var from := cam.project_ray_origin(screen)
	var dir := cam.project_ray_normal(screen)
	var best := ""
	var best_size := INF
	for name in objects:
		var b := _bounds_of(objects[name])
		if b.intersects_ray(from, dir) != null:
			# the smallest box under the finger wins (a lamp in front of a whole street)
			var s := b.size.length()
			if s < best_size:
				best_size = s; best = name
	return best


func _select(name: String, focus: bool) -> void:
	selected = name
	if name == "":
		box.visible = false
		_send({"type": "godot:selected", "name": null})
		return
	var b := _bounds_of(objects[name])
	var im := ImmediateMesh.new()
	im.surface_begin(Mesh.PRIMITIVE_LINES)
	var p := b.position
	var s := b.size
	var c := [p, p + Vector3(s.x, 0, 0), p + Vector3(s.x, 0, s.z), p + Vector3(0, 0, s.z)]
	for i in 4:
		var a: Vector3 = c[i]
		var n: Vector3 = c[(i + 1) % 4]
		for v in [a, n, a + Vector3(0, s.y, 0), n + Vector3(0, s.y, 0), a, a + Vector3(0, s.y, 0)]:
			im.surface_add_vertex(v)
	im.surface_end()
	box.mesh = im
	box.visible = true
	if focus:
		target = b.get_center()
		dist = clamp(b.size.length() * 1.6, 3.0, 200.0)
		_place_cam()
		cam_dirty = true
	_send({"type": "godot:selected", "name": name})


func _make_box() -> void:
	box = MeshInstance3D.new()
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = Color(1.0, 0.82, 0.2)
	m.no_depth_test = true
	box.material_override = m
	box.visible = false
	get_tree().current_scene.add_child(box)


# ------------------------------------------------------------------ see-inside materials
func _source_look(m: Material) -> Array:
	var col := Color.WHITE
	var tex: Texture2D = null
	if m is BaseMaterial3D:
		col = m.albedo_color
		tex = m.albedo_texture
	elif m is ShaderMaterial:
		for k in ["base_color", "albedo", "color", "albedo_color"]:
			var v = m.get_shader_parameter(k)
			if v is Color:
				col = v
				break
		for k in ["base_texture", "texture_albedo", "albedo_texture", "tex"]:
			var t = m.get_shader_parameter(k)
			if t is Texture2D:
				tex = t
				break
	return [col, tex]


func _cut_material(m: Material, cache: Dictionary) -> ShaderMaterial:
	if m != null and cache.has(m):
		return cache[m]
	var look := _source_look(m) if m != null else [Color.WHITE, null]
	var v := ShaderMaterial.new()
	v.shader = CUT_SHADER
	v.set_shader_parameter("base_color", look[0])
	if look[1]:
		v.set_shader_parameter("base_texture", look[1])
	mats.append(v)
	if m != null:
		cache[m] = v
	return v


func _swap_materials(scene: Node) -> void:
	var cache := {}
	for c in scene.find_children("*", "GeometryInstance3D", true, false):
		if c is MeshInstance3D and (c as MeshInstance3D).mesh:
			var mi := c as MeshInstance3D
			var base: Material = mi.material_override
			mi.material_override = null
			for i in mi.mesh.get_surface_count():
				var m: Material = base if base else mi.get_active_material(i)
				mi.set_surface_override_material(i, _cut_material(m, cache))
		elif c is GeometryInstance3D:
			var g := c as GeometryInstance3D
			if g.material_override:
				g.material_override = _cut_material(g.material_override, cache)


func _set_cut(on: bool, height := 2.2) -> void:
	var h := bounds.position.y + height if on else 100000.0
	for m in mats:
		m.set_shader_parameter("cut", h)


func _scene_bounds() -> AABB:
	var out := AABB()
	var first := true
	for c in get_tree().current_scene.find_children("*", "GeometryInstance3D", true, false):
		var g := c as GeometryInstance3D
		var b := g.global_transform * g.get_aabb()
		if b.size.length() > 400.0 or b.size.length() < 0.001:
			continue
		if first:
			out = b; first = false
		else:
			out = out.merge(b)
	return out


# ------------------------------------------------------------------ camera
func _home() -> void:
	target = bounds.get_center() if bounds.size != Vector3.ZERO else Vector3.ZERO
	target.y = bounds.position.y + bounds.size.y * 0.25
	dist = clamp(bounds.size.length() * 0.75, 6.0, 250.0)
	yaw = 0.7
	pitch = -0.6
	_place_cam()
	cam_dirty = true


func _place_cam() -> void:
	var off := Vector3(sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch)) * dist
	cam.position = target + off
	cam.look_at(target)


func _pan(delta_px: Vector2) -> void:
	var right := cam.global_transform.basis.x
	var fwd := -cam.global_transform.basis.z
	fwd.y = 0
	fwd = fwd.normalized()
	var k := dist * 0.0016
	target += (-right * delta_px.x + fwd * delta_px.y) * k
	_place_cam()


func _input(e: InputEvent) -> void:
	if cam == null:
		return
	if e is InputEventMouseButton:
		if e.button_index == MOUSE_BUTTON_WHEEL_UP and e.pressed:
			dist = max(1.5, dist * 0.9); _place_cam(); cam_dirty = true
		elif e.button_index == MOUSE_BUTTON_WHEEL_DOWN and e.pressed:
			dist = min(400.0, dist * 1.1); _place_cam(); cam_dirty = true
		elif e.button_index == MOUSE_BUTTON_LEFT and not DisplayServer.is_touchscreen_available():
			if e.pressed:
				press_pos = e.position; moved = false
			elif not moved:
				_select(_pick(e.position), false)
	elif e is InputEventMouseMotion:
		if DisplayServer.is_touchscreen_available():
			return
		if e.button_mask & (MOUSE_BUTTON_MASK_RIGHT | MOUSE_BUTTON_MASK_MIDDLE):
			_pan(e.relative); cam_dirty = true
		elif e.button_mask & MOUSE_BUTTON_MASK_LEFT:
			if e.position.distance_to(press_pos) > 6: moved = true
			yaw -= e.relative.x * 0.008
			pitch = clamp(pitch - e.relative.y * 0.006, -1.5, 0.35)
			_place_cam(); cam_dirty = true
	elif e is InputEventScreenTouch:
		if e.pressed:
			touches[e.index] = e.position
			if touches.size() == 1:
				press_pos = e.position; moved = false
		else:
			touches.erase(e.index)
			if touches.is_empty() and not moved:
				_select(_pick(e.position), false)
		if touches.size() == 2:
			moved = true
			var ps: Array = touches.values()
			pinch_start = (ps[0] as Vector2).distance_to(ps[1])
			dist_start = dist
			mid_start = ((ps[0] as Vector2) + (ps[1] as Vector2)) * 0.5
			target_start = target
	elif e is InputEventScreenDrag:
		touches[e.index] = e.position
		if e.position.distance_to(press_pos) > 6: moved = true
		if touches.size() == 2:
			var ps: Array = touches.values()
			var d := (ps[0] as Vector2).distance_to(ps[1])
			var mid := ((ps[0] as Vector2) + (ps[1] as Vector2)) * 0.5
			if pinch_start > 0:
				dist = clamp(dist_start * pinch_start / max(d, 1.0), 1.5, 400.0)
			target = target_start
			_pan(mid - mid_start)
		elif touches.size() == 1:
			yaw -= e.relative.x * 0.008
			pitch = clamp(pitch - e.relative.y * 0.006, -1.5, 0.35)
			_place_cam()
		cam_dirty = true
