shader_type spatial;
render_mode cull_disabled;
// Game Studio View mode: the object's own colour and texture, simple two-tone light, and
// everything above `cut` (a world height) removed, so rooms and interiors can be seen.
uniform vec4 base_color : source_color = vec4(1.0);
uniform sampler2D base_texture : source_color, hint_default_white, filter_linear_mipmap;
uniform float cut = 100000.0;
varying vec3 world_pos;
void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}
void fragment() {
	if (world_pos.y > cut) {
		discard;
	}
	vec3 c = base_color.rgb * texture(base_texture, UV).rgb * COLOR.rgb;
	ALBEDO = FRONT_FACING ? c : c * 0.55;   // insides of walls a little darker
}
void light() {
	float d = clamp(dot(NORMAL, LIGHT), 0.0, 1.0);
	DIFFUSE_LIGHT += mix(vec3(0.55), vec3(1.0), step(0.3, d)) * LIGHT_COLOR * ATTENUATION * 0.7;
}
