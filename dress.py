#!/usr/bin/env python3
"""Dress a Builder environment model with real materials and props (CC0), phone-ready.

  python3 dress.py DRESS.json OUT.glb

DRESS.json:
{
  "model": "/path/to/built.glb",                 # the Builder's model (materials named by surface)
  "materials": [                                 # first match wins; "match" is the start of a material name
    {"match": "plaster_wall", "texture": "polyhaven:grey_plaster", "tile_m": 2.0, "detail": 0.6, "big": true},
    {"match": "roof_tiles",   "texture": "polyhaven:grey_roof_tiles", "tile_m": 2.0, "big": true},
    {"match": "wood",         "texture": "polyhaven:brown_planks_04", "tile_m": 1.5}
  ],
  "props": [                                     # placed in the model's own Blender coordinates
    {"model": "polyhaven:exterior_aircon_unit", "at": [1.2, -3.9, 3.6], "turn": 180, "scale": 1.0}
  ],
  "max_prop_tris": 1500,                          # each prop is simplified to about this
  "ao": true,                                     # soft contact shadows baked into vertex colours
  "keep_maps": false,                             # true keeps normal maps (non-toon, lit games)
  "keep_lights": false                            # the model's lamps; games usually light the scene themselves
}

Find textures and props with surface_library.py (search / preview). A texture becomes detail
on the material's own colour: "detail" 0-1 is how much of the photo's colour comes through
(0 = only its grain and grime, tinted to the palette; 1 = the photo's own colours). "big"
surfaces (walls, roofs, ground) keep 1024 px textures in the game, the rest 512 px; the game
build applies those limits. Materials without a match, and Decal_ materials, stay as built.
The model's own lamps are left out unless keep_lights is true (then kept very faint).
Then check it: python3 godot_build.py look OUT.glb LOOK.png --pose rest
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main():
    if len(sys.argv) < 3 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(2)
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = str(Path(sys.argv[2]).resolve())
    import surface_library as lib
    from blender_char import blender_bin
    resolved = dict(spec)
    resolved['model'] = str(Path(spec['model']).resolve())
    for m in resolved.get('materials', []):
        files = lib.get_texture(m['texture'])
        m['files'] = files
    for p in resolved.get('props', []):
        p['gltf'] = lib.get_model(p['model'])['gltf']
    with tempfile.TemporaryDirectory() as tmp:
        rj = Path(tmp) / 'dress.json'
        rj.write_text(json.dumps(resolved))
        r = subprocess.run([blender_bin(), '-b', '--factory-startup', '--python', str(HERE / 'dress_inner.py'), '--',
                            str(rj), out], capture_output=True, text=True, timeout=1800)
    lines = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(('DRESS', 'Traceback', '  File')) or 'Error' in l]
    print('\n'.join(lines[-30:]))
    if r.returncode != 0 or not Path(out).exists():
        sys.exit('Dressing failed; fix DRESS.json and run again.')


if __name__ == '__main__':
    main()
