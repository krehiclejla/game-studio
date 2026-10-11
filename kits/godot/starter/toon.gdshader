shader_type spatial;
// Drawn look: light falls in hard bands (lit / shadow), never a smooth gradient.
uniform vec4 base_color : source_color = vec4(1.0);
uniform sampler2D base_texture : source_color, hint_default_white;
uniform vec4 shade_color : source_color = vec4(0.35, 0.25, 0.5, 1.0);
uniform float threshold : hint_range(0.0, 1.0) = 0.45;
uniform float bands : hint_range(1.0, 4.0) = 1.0;
void fragment() {
	ALBEDO = base_color.rgb * texture(base_texture, UV).rgb;
}
void light() {
	float d = clamp(dot(NORMAL, LIGHT), 0.0, 1.0);
	float t = bands <= 1.0 ? step(threshold, d) : floor(d * bands + (1.0 - threshold)) / bands;
	DIFFUSE_LIGHT += mix(shade_color.rgb, vec3(0.8), clamp(t, 0.0, 1.0)) * LIGHT_COLOR * ATTENUATION * 0.6;
}
