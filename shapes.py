"""Build hard-edged objects from shapes: tools, weapons, furniture, crates, signs.

The picture-to-3D route cannot draw exact man-made shapes (an axe comes out as a knife
or with two handles). Instead, write a short Python script that imports this file,
makes the parts, and saves them:

    import sys; sys.path.insert(0, '/data/apps/game-studio')
    from shapes import *
    handle = tube([(0, 0.024), (0.03, 0.017), (0.44, 0.013)], sides=8, bend=0.01)
    head = slab([(-0.045, 0.40), (0.10, 0.45), (0.115, 0.39), (0.10, 0.32), (-0.045, 0.37)],
                back=0.018, front=0.0015)
    save('axe.glb', [part(handle, WOOD), part(head, IRON, 0.6, 0.7)], grip=0.055)

Axes: Y is up, the flat sides of blades face X, and a blade's edge points +Z. A weapon's
handle runs along +Y from its end; grip=H moves the hand-hold point H metres up the
handle to the origin, which is what model_tool.py equip expects. Colours are real
materials (face or vertex colours would not show in the games).
Check it: python3 model_tool.py render OUT.glb a.png, and see the side with
python3 shapes.py turn OUT.glb side.glb 90 (then render side.glb)."""
import sys

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import gs_deps  # noqa: E402,F401  (reinstalls basic packages after a container replacement)
import numpy as np
import trimesh
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial

__all__ = ['tube', 'slab', 'box', 'cylinder', 'part', 'save', 'move', 'turn',
           'WOOD', 'DARK_WOOD', 'IRON', 'STEEL', 'RUST', 'LEATHER', 'ROPE', 'GOLD', 'STONE']

WOOD, DARK_WOOD, IRON, STEEL = (74, 48, 30), (48, 32, 22), (66, 62, 60), (168, 168, 164)
RUST, LEATHER, ROPE, GOLD, STONE = (104, 58, 34), (70, 44, 30), (150, 128, 92), (200, 160, 60), (110, 108, 104)


def tube(profile, sides=8, bend=0.0, squash=1.0):
    """A round shaft along +Y: profile is [(y, radius), ...] from bottom to top (handles,
    shafts, poles, legs, bottles). bend curves it toward +Z by up to BEND metres;
    squash < 1 makes it oval (thinner in X), like a real axe handle. Ends are capped."""
    profile = np.asarray(profile, float)
    ys = profile[:, 0]
    span = max(ys.max() - ys.min(), 1e-6)
    V = []
    for y, r in profile:
        cz = bend * np.sin(np.pi * (y - ys.min()) / span)
        for i in range(sides):
            a = 2 * np.pi * (i + 0.5) / sides
            V.append([r * squash * np.cos(a), y, cz + r * np.sin(a)])
    n = len(profile)
    F = []
    for j in range(n - 1):
        for i in range(sides):
            a, b = j * sides + i, j * sides + (i + 1) % sides
            c, d = (j + 1) * sides + (i + 1) % sides, (j + 1) * sides + i
            F += [[a, c, b], [a, d, c]]
    V += [[0, ys[0], 0], [0, ys[-1], bend * np.sin(np.pi * (ys[-1] - ys.min()) / span)]]
    bot, top = n * sides, n * sides + 1
    for i in range(sides):
        F += [[bot, i, (i + 1) % sides], [top, (n - 1) * sides + (i + 1) % sides, (n - 1) * sides + i]]
    return _mesh(V, F)


def slab(outline, back=0.01, front=None):
    """A flat piece: outline is its side view as [(z, y), ...] (any simple polygon, in
    order), given thickness in X (blades, axe and hammer heads, planks, signs, shields).
    back is the half-thickness at the smallest z; with front set it tapers linearly to
    that half-thickness at the largest z, so front=0.0015 gives a sharp cutting edge."""
    P = np.asarray(outline, float)
    if _area(P) < 0:
        P = P[::-1]
    front = back if front is None else front
    z0, z1 = P[:, 0].min(), P[:, 0].max()
    half = back + (front - back) * (P[:, 0] - z0) / max(z1 - z0, 1e-6)
    n = len(P)
    V = [[h, y, z] for (z, y), h in zip(P, half)] + [[-h, y, z] for (z, y), h in zip(P, half)]
    F = []
    for a, b, c in _earclip(P):
        F += [[a, b, c], [n + a, n + c, n + b]]
    for i in range(n):
        j = (i + 1) % n
        F += [[i, n + i, n + j], [i, n + j, j]]
    return _mesh(V, F)


def box(size, at=(0, 0, 0)):
    """A box of size (x, y, z) metres centred at AT (wedges, bands, crates, planks)."""
    return move(trimesh.creation.box(size), at)


def cylinder(radius, height, at=(0, 0, 0), sides=8, axis='y'):
    """A cylinder centred at AT along AXIS (bands, rivets, barrels, wheels)."""
    m = trimesh.creation.cylinder(radius=radius, height=height, sections=sides)
    if axis == 'y':
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    elif axis == 'x':
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    return move(m, at)


def move(mesh, at=(0, 0, 0), turn_deg=None, axis=(0, 1, 0)):
    """Rotate (degrees about AXIS through the origin) and then shift a mesh."""
    if turn_deg:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(turn_deg), axis))
    mesh.apply_translation(at)
    return mesh


def part(mesh, color, metal=0.0, rough=0.85):
    """Give a mesh its material: COLOR as (r, g, b) 0-255, e.g. part(head, IRON, 0.6, 0.7)."""
    mesh.visual = TextureVisuals(material=PBRMaterial(
        baseColorFactor=[*[c / 255 for c in color], 1.0], metallicFactor=metal, roughnessFactor=rough))
    return mesh


def save(out, parts, grip=None):
    """Write the parts as one GLB. grip: for weapons and held tools, the height up the
    handle where the hand holds it (it becomes the origin); otherwise the object is
    sat on the ground (its lowest point at y=0) and centred."""
    sc = trimesh.Scene()
    lo = np.min([p.bounds[0] for p in parts], 0)
    hi = np.max([p.bounds[1] for p in parts], 0)
    shift = [0, -grip, 0] if grip is not None else [-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2]
    for i, p in enumerate(parts):
        p = p.copy()
        p.apply_translation(shift)
        sc.add_geometry(p, geom_name=f'part{i}', node_name=f'part{i}')
    sc.export(out)
    size = (hi - lo).round(3).tolist()
    print(f'saved {out}: {size[0]} x {size[1]} x {size[2]} m, {sum(len(p.faces) for p in parts)} faces')


def turn(src, out, deg=90):
    """Turn a saved model about Y (to render its other sides)."""
    sc = trimesh.load(src, force='scene')
    sc.apply_transform(trimesh.transformations.rotation_matrix(np.radians(deg), [0, 1, 0]))
    sc.export(out)


def _mesh(V, F):
    m = trimesh.Trimesh(np.asarray(V, float), np.asarray(F, int), process=True)
    m.fix_normals()
    return m


def _area(P):
    return 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])


def _earclip(P):
    """Triangulate a simple counter-clockwise polygon (so concave outlines work too)."""
    idx, tris = list(range(len(P))), []

    def inside(p, a, b, c):
        d = lambda u, v, w: (u[0] - w[0]) * (v[1] - w[1]) - (v[0] - w[0]) * (u[1] - w[1])
        s = [d(p, a, b), d(p, b, c), d(p, c, a)]
        return not (min(s) < 0 and max(s) > 0)

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i, j, l = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = P[i], P[j], P[l]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 0:
                continue
            if any(inside(P[m], a, b, c) for m in idx if m not in (i, j, l)):
                continue
            tris.append((i, j, l))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'turn':
        turn(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 90)
        print(f'turned: render {sys.argv[3]} to see that side')
    else:
        print(__doc__)
