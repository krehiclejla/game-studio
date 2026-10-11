#!/usr/bin/env python3
"""Make a styled 3D character in Blender on the rigged, animated mannequin.

  python3 blender_char.py SPEC.json OUT.glb [--all-moves]

The character is built ON the animation library's mannequin (a real human body in
T-pose, 53 bones, 46 moves), so it comes out rigged and animated: no separate
rigging step, and every move (idle, walk, run, jump, punches, hits, death...) fits.
Check the look afterwards with:  python3 godot_build.py look OUT.glb LOOK.png

SPEC.json describes the character. There are NO built-in looks: no default face, hair or
body type. Everything below is designed for this character from its description and style.

{
  "skin": "#e9c8a8",
  "body": {
    # lengths and size (1 = an average adult mannequin, 1.8 m); the moves still fit
    "height": 1.75,            # metres, overall
    "legs": 1.0, "arms": 1.0, "torso": 1.0, "neck": 1.0,
    "shoulder_width": 1.0, "feet_length": 1.0,
    # thickness around each bone (1 = the mannequin, which is athletic: go below 1 for slim)
    "head": 1.0,               # head size, uniform (chibi styles go far above 1)
    "neck_thick": 1.0, "chest": 1.0, "shoulders": 1.0, "waist": 1.0, "hips": 1.0,
    "upper_arms": 1.0, "forearms": 1.0, "hands": 1.0, "thighs": 1.0, "shins": 1.0, "feet": 1.0
  },
  "outfit": [                  # garments over the body, inner first
    {"name": "shirt", "on": ["torso", "upper_arms"], "color": "#ffffff", "puff": 0.02,
     "open_front": 0.0, "thick": 0.012, "loose": 0}   # loose 0-20: hangs over the body
                                                         # instead of hugging every muscle
  ],
  "bands": [{"at": "waist", "color": "#333333", "width": 0.06, "thick": 0.02}],
  "hair": {
    "color": "#3a2a1e",
    "cap": {"hairline": 0.78, "sides": 0.55, "nape": 0.25, "thickness": 0.02},   # or false (bald, hats)
    "locks": [                 # the hairstyle, lock by lock
      {"at": [0, 60], "dir": [10, -10], "length": 0.15, "width": 0.07, "thick": 0.4,
       "tip": 0.2, "droop": 0.3, "sway": 0.0, "twist": 0, "sides": 6, "facets": false,
       "mirror": true, "repeat": {"count": 4, "az_step": 20, "el_step": 0, "jitter": 0.3, "seed": 1}}
    ]
  },
  "face": {"features": [       # drawn shapes laid onto the face: eyes, irises, highlights,
                               # lids, lashes, brows, nose, mouth, blush, freckles, scars, markings
    {"name": "eye", "at": [0.36, 0.48], "points": [[-0.15, 0], [0, 0.06], [0.16, 0], [0, -0.04]],
     "smooth": true, "color": "#ffffff", "mirror": true, "layer": 0},
    {"name": "iris", "at": [0.36, 0.48], "ellipse": [0.05, 0.05], "color": "#3b6ea5", "mirror": true, "layer": 1}
  ]},
  "moves": {"Punch_Jab": "attack"}
}

Face units: x in head half-widths from the centre line (+ = the viewer's right), y from the
chin (0) to the crown (1); eyes sit around y 0.45-0.5. A feature is an outline ("points",
around "at", same units; "smooth" rounds it) or an "ellipse" [half-width, half-height], with
"rotate" (degrees), "mirror" (a copy on the other side) and "layer" (higher draws on top).
Draw each character's own eyes, brows and mouth for its style: their shapes carry most of
the style (round, almond, tall ovals, dots, heavy lids, thin lines, lashes or none).

Hair: "cap" covers the scalp above a hairline set separately for the forehead ("hairline"),
temples and ears ("sides") and the back ("nape"), in the same 0-1 head heights. "locks" are
tapered tubes from a root on the scalp: "at" [az, el] (az 0 = the face, 90 = viewer's right,
180 = back; el 0 = level with the head centre, 90 = the crown), "dir" [az, el] growth
direction (default straight out), "length"/"width" in metres, "thick" (1 = round, 0.3 = a
flat ribbon), "tip" (0 = pointed, 1 = blunt), "droop" (0-1, falls with gravity), "sway"
(-1..1, sweeps sideways), "twist" (degrees), "facets" (hard-edged), "mirror", "repeat" (a row).
Build the style from these: soft bobs, slick parted hair, long straight hair, curls (many
short drooping locks), buns and ponytails (locks plus --extra), spikes (pointed, no droop).

Regions for outfits: head, neck, torso, chest, waist, pelvis, shoulders, upper_arms, forearms,
hands, thighs, shins, lower_shins, feet (left and right together).
Bands "at": waist, wrists, forearms, ankles, neck, forehead, upper_arms, thighs.

Moves: the character always gets the studio's basics under their usual names (idle, walk,
run, jump, hurt, die). "moves" adds more library clips under the names you give them
(the full list: python3 model_tool.py library). --all-moves keeps all 46 under their
library names instead (bigger file).

Anything the spec cannot express, add with an extra Blender script:
  python3 blender_char.py SPEC.json OUT.glb --extra MORE.py
MORE.py runs inside Blender after the build with helpers in scope:
  attach(obj, bone)  weight a new mesh object fully to a bone (e.g. 'DEF-head', 'DEF-hand.R')
  material(hex)      a flat material;  head_center, head_radius, front (Vector), up (Vector)
  bone_point(bone, t)  a point along a bone (0 = its start, 1 = its end), world space
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

def blender_bin():
    """An installed Blender (/opt/blender), else the studio's own copy (downloaded on first use)."""
    found = sorted(Path('/opt/blender').glob('blender-*/blender')) if Path('/opt/blender').exists() else []
    if found:
        return str(found[-1])
    from detailed import ensure_blender
    b = ensure_blender()
    if not b:
        sys.exit('Blender could not be set up on this machine.')
    return str(b)


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(2)
    spec, out = Path(args[0]).resolve(), Path(args[1]).resolve()
    extra = None
    anims = 'all'
    if '--extra' in args:
        extra = str(Path(args[args.index('--extra') + 1]).resolve())
    data = json.loads(spec.read_text())  # fail early on a broken spec
    from model_tool import ual_files
    lib = str(ual_files()['ual1'])
    inner = HERE / 'blender_char_inner.py'
    r = subprocess.run([blender_bin(), '-b', '--factory-startup', '--python', str(inner), '--',
                        lib, str(spec), str(out), extra or '', anims],
                       capture_output=True, text=True, timeout=900)
    lines = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(('CHAR', 'Error', 'Traceback', '  File', 'ERROR')) or 'Error' in l]
    print('\n'.join(lines[-40:]))
    if r.returncode != 0 or not out.exists():
        sys.exit('The character could not be built; fix the spec or extra script and run again.')
    if '--all-moves' not in args:
        # the studio's basic moves under their usual names, plus any asked for
        from detailed import DEFAULT_ANIMS
        wanted = DEFAULT_ANIMS + ''.join(f',{clip}={name}' for clip, name in (data.get('moves') or {}).items())
        k = subprocess.run([sys.executable, str(HERE / 'model_tool.py'), 'keep-anims', str(out), str(out), wanted],
                           capture_output=True, text=True)
        if k.returncode != 0:
            sys.exit('Could not set the moves: ' + (k.stdout + k.stderr)[-800:])
        print(f'CHAR moves: {wanted}; {out.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
