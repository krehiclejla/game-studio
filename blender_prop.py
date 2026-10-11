#!/usr/bin/env python3
"""Build a styled prop, building or scenery piece in Blender from a short script.

  python3 blender_prop.py BUILD.py OUT.glb
  python3 godot_build.py look OUT.glb LOOK.png --pose rest      (check it in the game look)

BUILD.py is plain Python run inside Blender with the helpers below already in scope.
Units are metres; Y is up in the game, but here Z is up (Blender): x right, y back, z up.
The model's front faces -y (toward the viewer in `look`). Everything sits on z = 0.
Colours are '#rrggbb'. Every helper returns the Blender object it made.

Shapes (bevelled edges by default, so nothing reads as a raw primitive):
  box(size, at=(0,0,0), color, bevel=0.02, base=True)   size=(w,d,h); base=True: `at` is the bottom centre
  cyl(radius, height, at, color, sides=16, bevel=0.01, top=None)   top=radius at the top (tapered)
  ball(radius, at, color, squash=(1,1,1), detail=2)
  beam(a, b, thick, color, bevel=0.01)      a square beam between two points
  tube(points, radius, color, sides=8)      a bent rod/rail/pipe/branch through points
  lathe(profile, at, color, sides=24)       spin [(radius, z), ...] round the vertical: vases, lanterns, posts, bells
  slab(outline, depth, at, color, axis='y', bevel=0.005)   extrude a 2D outline [(x, z), ...]: signs, blades, cut-outs
  text(words, at, size, color, depth=0.02, face='-y', font=None)   real lettering (latin by default; a .ttf for others)

Architecture:
  gable_roof(w, d, h, at, color, overhang=0.3, thick=0.08, upturn=0.0, ridge=None)
      a two-sided roof on top of a w x d footprint; upturn > 0 curls the eaves up (East Asian roofs)
  hip_roof(w, d, h, at, color, overhang=0.3, thick=0.08, upturn=0.0)
  flat_roof(w, d, at, color, lip=0.1, thick=0.12)
  window(w, h, at, wall='-y', frame='#5a3b22', glass='#9ec9e0', bars=(1,1), depth=0.06)   framed, inset, with muntins
  door(w, h, at, wall='-y', color='#6b4226', frame='#3b2414', style='plain'|'sliding'|'arched')
  curtain(w, h, at, color, panels=3, wall='-y')    noren / awning cloth strips
  awning(w, depth, at, color, stripes=None, slope=0.35)
  steps(w, depth, rise, count, at, color)
  fence(points, height, color, post_every=1.0)

Nature:
  foliage(at, radius, color, puffs=7, seed=1, shade=None)   a clustered canopy of soft blobs (trees, bushes, clouds)
  trunk(height, radius, at, color, lean=0.0, branches=0, seed=1)
  rock(size, at, color, seed=1)

Arrange:
  mirror_x(obj)        a mirrored copy across x = 0
  repeat(fn, count, step)   call fn(i) count times; step is a (dx, dy, dz) passed in as offset i*step
  group(name, *objs)   (optional) name a set of parts
  material(hex) / decal(hex)   a flat material; decal(...) stays unshaded with no outline in the game

At the end everything is joined into one model and exported; the script prints its size and triangles.
Keep it phone-friendly: usually under 20k triangles for a building, a few thousand for a prop.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blender_char import blender_bin  # noqa: E402


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(2)
    script, out = Path(args[0]).resolve(), Path(args[1]).resolve()
    if not script.exists():
        sys.exit(f'No build script at {script}')
    r = subprocess.run([blender_bin(), '-b', '--factory-startup', '--python', str(HERE / 'blender_prop_inner.py'), '--',
                        str(script), str(out)], capture_output=True, text=True, timeout=900)
    text = r.stdout + r.stderr
    keep = [l for l in text.splitlines() if l.startswith(('PROP', 'Traceback', '  File', 'Error')) or 'Error' in l]
    print('\n'.join(keep[-40:]))
    if r.returncode != 0 or not out.exists():
        sys.exit('The model could not be built; fix the script and run again.')


if __name__ == '__main__':
    main()
