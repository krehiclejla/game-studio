shader_type spatial;
render_mode cull_front, unshaded;
// Ink outline: the back faces, pushed outward on screen by a fixed width in pixels
// (at 720p; scales with the screen), so lines stay a steady drawn width at any distance
// and never swallow thin parts like window panes, signs or cloth.
uniform float width : hint_range(0.0, 12.0) = 2.5;
uniform vec4 ink : source_color = vec4(0.06, 0.04, 0.1, 1.0);
void vertex() {
	vec4 clip = PROJECTION_MATRIX * (MODELVIEW_MATRIX * vec4(VERTEX, 1.0));
	vec3 vn = (MODELVIEW_MATRIX * vec4(NORMAL, 0.0)).xyz;
	vec2 dir = (PROJECTION_MATRIX * vec4(vn, 0.0)).xy;
	float len = length(dir);
	if (len > 1e-5) {
		dir /= len;
		clip.xy += dir * width * (VIEWPORT_SIZE.y / 720.0) * 2.0 / VIEWPORT_SIZE * clip.w;
	}
	POSITION = clip;
}
void fragment() {
	ALBEDO = ink.rgb;
}
