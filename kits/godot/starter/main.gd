extends Node3D
# An empty world: sky colour, sunlight and a camera. The person builds the game step by step
# from here. Ready pieces to use when asked: player.gd (a hero that walks with WASD / arrows or
# by dragging on a touch screen) and the Cel autoload (the drawn look, see cel.gd).

func _ready() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.62, 0.79, 0.92)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.45, 0.47, 0.55)
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new(); we.environment = env; add_child(we)

	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.rotation_degrees = Vector3(-50, -35, 0)
	sun.shadow_enabled = true
	add_child(sun)

	var cam := Camera3D.new()
	cam.name = "Camera"
	cam.position = Vector3(0, 8, 14)
	add_child(cam)
	cam.look_at(Vector3.ZERO)
