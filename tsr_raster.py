# CPU triangle rasterising for the picture -> 3D step (no OpenGL here).
# Copied into TripoSR as tsr/cpu_raster.py by detailed.py for texture baking,
# and used directly by detailed.py to project the concept picture onto the model.
import math

import numpy as np


def cover(P, idx, W, H):
    """Yield (triangle, pixel y, pixel x, w0, w1, w2) for every pixel centre inside
    each triangle. P: (N, 2) vertex positions in pixels; idx: (F, 3) triangles."""
    tri = P[idx]
    lo = np.floor(tri.min(1)).astype(int)
    hi = np.ceil(tri.max(1)).astype(int)
    lo[:, 0] = lo[:, 0].clip(0, W - 1); hi[:, 0] = hi[:, 0].clip(0, W - 1)
    lo[:, 1] = lo[:, 1].clip(0, H - 1); hi[:, 1] = hi[:, 1].clip(0, H - 1)
    size = (hi - lo + 1).prod(1)
    order = np.argsort(size)
    # Batch triangles of similar box size so the work stays vectorised.
    edges = np.unique(np.concatenate([[0], np.searchsorted(size[order], [4, 16, 64, 256, 1024, 4096, 1 << 30], 'right')]))
    for a, b in zip(edges[:-1], edges[1:]):
        f = order[a:b]
        if not len(f):
            continue
        bw = (hi[f] - lo[f] + 1).max(0)
        gy, gx = np.mgrid[0:bw[1], 0:bw[0]]
        chunk = max(1, 2_000_000 // int(bw[0] * bw[1]))
        for c0 in range(0, len(f), chunk):
            ff = f[c0:c0 + chunk]
            x = lo[ff, 0, None, None] + gx
            y = lo[ff, 1, None, None] + gy
            t = tri[ff]
            (x0, y0), (x1, y1), (x2, y2) = t[:, 0].T, t[:, 1].T, t[:, 2].T
            d = ((y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2))[:, None, None]
            d = np.where(np.abs(d) < 1e-12, 1e-12, d)
            w0 = ((y1 - y2)[:, None, None] * (x - x2[:, None, None]) + (x2 - x1)[:, None, None] * (y - y2[:, None, None])) / d
            w1 = ((y2 - y0)[:, None, None] * (x - x2[:, None, None]) + (x0 - x2)[:, None, None] * (y - y2[:, None, None])) / d
            w2 = 1 - w0 - w1
            m = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4) & (x < W) & (y < H)
            k, yy, xx = np.nonzero(m)
            yield ff[k], y[k, yy, xx], x[k, yy, xx], w0[k, yy, xx], w1[k, yy, xx], w2[k, yy, xx]


def rasterize_position_atlas(mesh, vmap, idx, uvs, res, pad):
    """CPU stand-in for TripoSR's OpenGL pass: write each texel's 3D position, then bleed edges."""
    from scipy.ndimage import distance_transform_edt
    pos = np.asarray(mesh.vertices)[vmap].astype('f4')
    out = np.zeros((res, res, 4), 'f4')
    for k, Y, X, w0, w1, w2 in cover(uvs.astype('f8') * res - 0.5, idx, res, res):
        vp = pos[idx[k]]
        out[Y, X, :3] = vp[:, 0] * w0[:, None] + vp[:, 1] * w1[:, None] + vp[:, 2] * w2[:, None]
        out[Y, X, 3] = 1
    # Bleed filled texels outward by the padding so seams don't show.
    empty = out[..., 3] == 0
    dist, (iy, ix) = distance_transform_edt(empty, return_indices=True)
    grow = empty & (dist <= pad + 1)
    out[grow] = out[iy[grow], ix[grow]]
    return out


def fit_camera(V, F, alpha, fovy=40.0):
    """Where TripoSR's camera really was for this picture: (distance, dx, dy).

    TripoSR does not say. Its preview renders use distance 1.9, but the model it builds
    comes out 3-45% larger than that camera implies, by a different amount per picture,
    so painting the picture back with a fixed camera slides detail outward from the
    centre (a face lands on the hat, a collar climbs the neck). The model's outline
    seen from the camera must match the picture's cut-out, so fit the distance (and
    a small pixel shift) that makes them overlap best."""
    H, W = alpha.shape
    q = 4  # match at quarter size: plenty for a silhouette, and fast
    h, w = H // q, W // q
    target = alpha[:h * q, :w * q].reshape(h, q, w, q).mean((1, 3)) > 0.5
    f = 0.5 * h / math.tan(math.radians(fovy / 2))

    def silhouette(dist):
        d = dist - V[:, 0]
        S = np.stack([w / 2 + f * V[:, 1] / d, h / 2 - f * V[:, 2] / d], 1) - 0.5
        s = np.zeros(h * w, bool)
        for _, Y, X, *_ in cover(S, F, w, h):
            s[Y * w + X] = True
        return s.reshape(h, w)

    def overlap(s, dy=0, dx=0):
        s = np.roll(s, (dy, dx), (0, 1))
        return (s & target).sum() / max(1, (s | target).sum())

    lo, hi = 1.2, 3.0
    for _ in range(18):  # golden-section search: the overlap has one peak in distance
        a, b = hi - 0.618 * (hi - lo), lo + 0.618 * (hi - lo)
        if overlap(silhouette(a)) < overlap(silhouette(b)):
            lo = a
        else:
            hi = b
    dist = (lo + hi) / 2
    s = silhouette(dist)
    dy, dx = max(((y, x) for y in range(-3, 4) for x in range(-3, 4)), key=lambda t: overlap(s, *t))
    return dist, dx * q, dy * q, overlap(s, dy, dx)


def front_project(V, F, UV, texture, picture, alpha, fovy=40.0):
    """Paint the input picture back onto the parts of the model that face its camera.

    TripoSR sees the picture from (dist, 0, 0) looking at the origin, with +Y to the
    right and +Z up; fit_camera finds dist. Its own colours are a blurry guess; the
    picture itself is sharp (faces, patterns, small details). Returns the new texture
    (H, W, 3) floats."""
    from scipy.ndimage import binary_erosion, distance_transform_edt, map_coordinates
    T = texture.shape[0]
    H, W = picture.shape[:2]
    cam_dist, sdx, sdy, fit = fit_camera(V, F, alpha, fovy)
    if fit < 0.75:
        # The model doesn't match the picture's outline well enough to paint it on
        # safely; TripoSR's own (blurrier) colours are better than misplaced detail.
        return texture.astype('f8')
    f = 0.5 * H / math.tan(math.radians(fovy / 2))
    cx, cy = W / 2 + sdx, H / 2 + sdy
    depth = cam_dist - V[:, 0]
    S = np.stack([cx + f * V[:, 1] / depth, cy - f * V[:, 2] / depth], 1) - 0.5
    # Nearest surface per picture pixel (what the camera actually sees).
    zbuf = np.full(H * W, np.inf)
    for k, Y, X, w0, w1, w2 in cover(S, F, W, H):
        dz = depth[F[k]]
        np.minimum.at(zbuf, Y * W + X, dz[:, 0] * w0 + dz[:, 1] * w1 + dz[:, 2] * w2)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    # Every texel: where it is on the model, which way it faces, where it lands in the picture.
    tex = texture.astype('f8').copy()
    weight = np.zeros((T, T))
    got = np.zeros((T, T), bool)
    # Only fully solid picture pixels: half-see-through edges hold background grey.
    inside = binary_erosion(alpha > 0.95, iterations=max(2, H // 256))
    for k, Y, X, w0, w1, w2 in cover(np.stack([UV[:, 0] * T, (1 - UV[:, 1]) * T], 1) - 0.5, F, T, T):
        vp = V[F[k]]
        p = vp[:, 0] * w0[:, None] + vp[:, 1] * w1[:, None] + vp[:, 2] * w2[:, None]
        d = cam_dist - p[:, 0]
        sx = cx + f * p[:, 1] / d - 0.5
        sy = cy - f * p[:, 2] / d - 0.5
        ix = np.clip(np.round(sx).astype(int), 0, W - 1)
        iy = np.clip(np.round(sy).astype(int), 0, H - 1)
        view = np.array([cam_dist, 0, 0]) - p
        view /= np.linalg.norm(view, axis=1, keepdims=True)
        facing = (fn[k] * view).sum(1)
        seen = d <= zbuf[iy * W + ix] + 0.012
        w = np.clip((facing - 0.3) / 0.35, 0, 1) * seen * inside[iy, ix]
        col = np.stack([map_coordinates(picture[..., c], [sy, sx], order=1, mode='nearest') for c in range(3)], 1)
        tex[Y, X] = tex[Y, X] * (1 - w[:, None]) + col * w[:, None]
        weight[Y, X] = w
        got[Y, X] = True
    # Atlas padding texels copy their nearest painted neighbour, so seams stay clean.
    empty = ~got
    if empty.any() and got.any():
        _, (iy, ix) = distance_transform_edt(empty, return_indices=True)
        pad = empty & (weight[iy, ix] > 0)
        tex[pad] = tex[iy[pad], ix[pad]]
    return tex
