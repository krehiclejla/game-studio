extends CharacterBody3D
# The hero: moves with WASD / arrows, or by dragging on a touch screen.

@export var speed := 7.0
var drag_from := Vector2.ZERO
var drag := Vector2.ZERO

func _ready() -> void:
	var shape := CollisionShape3D.new()
	var cap := CapsuleShape3D.new(); cap.radius = 0.5; cap.height = 1.8
	shape.shape = cap; shape.position.y = 0.9
	add_child(shape)
	Cel.pole(self, 0.45, 1.1, Vector3.ZERO, Color(1.0, 0.55, 0.1))
	Cel.ball(self, 0.42, Vector3(0, 1.1, 0), Color(1.0, 0.85, 0.7))
	Cel.box(self, Vector3(0.95, 0.35, 0.95), Vector3(0, 1.75, 0), Color(0.1, 0.1, 0.15))

func _input(e: InputEvent) -> void:
	if e is InputEventScreenTouch:
		drag_from = e.position; drag = Vector2.ZERO
		if not e.pressed: drag = Vector2.ZERO
	elif e is InputEventScreenDrag:
		drag = ((e.position - drag_from) / 60.0).limit_length(1.0)

func _physics_process(dt: float) -> void:
	var dir := Vector2(
		float(_key(KEY_D) or _key(KEY_RIGHT)) - float(_key(KEY_A) or _key(KEY_LEFT)),
		float(_key(KEY_S) or _key(KEY_DOWN)) - float(_key(KEY_W) or _key(KEY_UP))).limit_length(1.0)
	if dir == Vector2.ZERO: dir = drag
	velocity.x = dir.x * speed
	velocity.z = dir.y * speed
	velocity.y -= 20.0 * dt
	move_and_slide()
	if dir.length() > 0.1:
		rotation.y = lerp_angle(rotation.y, atan2(-dir.x, -dir.y), 10.0 * dt)

func _key(k: Key) -> bool:
	return Input.is_physical_key_pressed(k)
