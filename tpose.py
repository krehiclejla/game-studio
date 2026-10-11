# Draw an OpenPose-style T-pose skeleton (18 keypoints, standard limb colours).
# The build changes the skeleton's proportions, so characters don't all share one
# lean body: shoulders, hips, stance, leg length and head size.
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import gs_deps  # noqa: E402,F401  (reinstalls basic packages after a container replacement)
from PIL import Image, ImageDraw

# shoulder / hip half-widths and stance (fractions of image width), hip height,
# head size and arm length (fractions of the figure's height/width).
BUILDS = {
    'slim':    dict(sh=0.09, hip=0.050, foot=0.07, hip_y=0.50, head=1.00, arm=0.30),
    'average': dict(sh=0.11, hip=0.065, foot=0.08, hip_y=0.50, head=1.00, arm=0.30),
    'heavy':   dict(sh=0.13, hip=0.080, foot=0.10, hip_y=0.53, head=0.90, arm=0.26),
    'huge':    dict(sh=0.15, hip=0.100, foot=0.12, hip_y=0.56, head=0.80, arm=0.22),
    'small':   dict(sh=0.09, hip=0.070, foot=0.09, hip_y=0.58, head=1.45, arm=0.24),
    'lanky':   dict(sh=0.10, hip=0.050, foot=0.07, hip_y=0.46, head=0.90, arm=0.34),
}

# Words that go with each build in the concept prompt (the skeleton sets
# proportions, the words set the bulk).
BUILD_WORDS = {
    'slim': 'slender build',
    'average': 'average build',
    'heavy': 'heavily built, broad shoulders, thick muscular torso, thick waist, barrel chest, thick arms and legs',
    'huge': 'massive hulking giant build, enormous barrel chest, big round belly, very thick waist, huge thick limbs',
    'small': 'short and stocky, big head, small body',
    'lanky': 'tall and lanky, long thin limbs, narrow shoulders',
}


def tpose(w=512, h=768, build='average'):
    b = BUILDS.get(build, BUILDS['average'])
    cx = w / 2
    top = 0.08 * h
    H = 0.84 * h
    y = lambda f: top + f * H
    neck = 0.17 * b['head'] if b['head'] > 1 else 0.17 - (1 - b['head']) * 0.05
    head_y = neck * 0.35
    sh_y = neck + 0.01
    reach = min(0.42, b['sh'] + b['arm'])
    elbow = b['sh'] + (reach - b['sh']) * 0.5
    k = {0: (cx, y(head_y)), 1: (cx, y(neck)),
         2: (cx - b['sh'] * w, y(sh_y)), 3: (cx - elbow * w, y(sh_y)), 4: (cx - reach * w, y(sh_y)),
         5: (cx + b['sh'] * w, y(sh_y)), 6: (cx + elbow * w, y(sh_y)), 7: (cx + reach * w, y(sh_y)),
         8: (cx - b['hip'] * w, y(b['hip_y'])), 9: (cx - (b['hip'] + b['foot']) / 2 * w, y((b['hip_y'] + 0.97) / 2)), 10: (cx - b['foot'] * w, y(0.97)),
         11: (cx + b['hip'] * w, y(b['hip_y'])), 12: (cx + (b['hip'] + b['foot']) / 2 * w, y((b['hip_y'] + 0.97) / 2)), 13: (cx + b['foot'] * w, y(0.97)),
         14: (cx - 0.02 * w * b['head'], y(head_y * 0.75)), 15: (cx + 0.02 * w * b['head'], y(head_y * 0.75)),
         16: (cx - 0.045 * w * b['head'], y(head_y * 0.92)), 17: (cx + 0.045 * w * b['head'], y(head_y * 0.92))}
    limbs = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11), (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17)]
    colors = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170),
              (0, 255, 255), (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]
    im = Image.new('RGB', (w, h), (0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, (a, c) in enumerate(limbs):
        d.line([k[a], k[c]], fill=tuple(int(v * 0.6) for v in colors[i]), width=int(w * 0.025))
    for i, p in k.items():
        r = w * 0.012
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=colors[i])
    return im


if __name__ == '__main__':
    import sys
    tpose(build=sys.argv[1] if len(sys.argv) > 1 else 'average').save('pose.png')
