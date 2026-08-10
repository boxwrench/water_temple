"""Build the tracing guide for the anthemion plaque.

Composites the source photo (lightened), the approach-1 edge map (red) and the
extracted silhouette (green), under a labelled normalised coordinate grid. The
grid is the point: coordinates for the hand trace get read off this image rather
than estimated by eye, which is what the four previous attempts lacked.

Also extracts the plaque silhouette and writes it as trace data.

Normalised coords: half-width = 1.0, origin at the plaque bounding-box centre,
x right, z up.

Outputs (all in trace/):
  silhouette.json        symmetric right-half outline, normalised
  guide-full.png         whole plaque with grid
  guide-q<N>.png         four 2x quadrant zooms
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np                                             # noqa: E402
from PIL import Image, ImageDraw                               # noqa: E402
from scipy import ndimage                                      # noqa: E402

from trace_anthemion import (ROOT, SRC, OUT, load_gray,        # noqa: E402,F401
                             plaque_mask, canny)

N_RAYS = 720
SMOOTH_RAYS = 11
HARMONICS = 16         # ovoid outline needs only low harmonics        # low-pass width on r(theta), in ray steps
MINOR = 0.05
MAJOR = 0.25
LC_SIGMA = 26.0        # local-mean radius for contrast enhancement
LC_GAIN = 2.2          # higher clips to pure black/white and destroys form


def normalisation(mask):
    ys, xs = np.nonzero(mask)
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    s = 0.5 * (x1 - x0)          # half-width maps to 1.0
    return cx, cy, s, (x0, x1, y0, y1)


def to_px(x, z, cx, cy, s):
    return cx + x * s, cy - z * s


def to_norm(px, py, cx, cy, s):
    return (px - cx) / s, (cy - py) / s


SNAP_LO = 0.85         # search band around the seed radius
SNAP_HI = 1.18         # must reach past the true edge: the rim moulding is
                       # smoother than the pitted field, so the texture mask
                       # under-covers it and the seed runs short at the diagonals


def local_contrast(g, sigma=LC_SIGMA, gain=LC_GAIN):
    """Unsharp mask. Discards the slow illumination ramp and amplifies the small
    brightness differences that encode the carving."""
    return np.clip((g - ndimage.gaussian_filter(g, sigma)) * gain + 0.5, 0.0, 1.0)


def extract_silhouette(g, mask, cx, cy, s):
    """Radial sampling from the centroid, snapped to the true luminance edge.

    The egg is star-convex, so one ray per angle hits the boundary exactly once
    and returns an ordered, evenly-distributed contour with no marching-squares
    bookkeeping.

    The texture mask is used only as a *seed*: its boundary is set by
    morphology, not by the image, and runs wide by several percent on the
    upper-left. The true edge is the strongest luminance gradient near that
    seed, so each ray searches a narrow band around its seed radius and snaps to
    the gradient peak. The band is what stops it locking onto the drop shadow.

    r(theta) is then a periodic 1-D signal: low-pass it, then fold about the
    vertical axis and average so the outline comes out exactly symmetric.
    """
    h, w = mask.shape
    angles = np.linspace(0.0, 2.0 * np.pi, N_RAYS, endpoint=False)
    steps = int(np.hypot(w, h))
    t = np.arange(steps, dtype=np.float64)

    seed = np.zeros(N_RAYS)
    for i, a in enumerate(angles):
        px = cx + np.cos(a) * t
        py = cy - np.sin(a) * t
        ok = (px >= 0) & (px < w) & (py >= 0) & (py < h)
        hit = mask[np.clip(py, 0, h - 1).astype(int),
                   np.clip(px, 0, w - 1).astype(int)] & ok
        idx = np.nonzero(hit)[0]
        seed[i] = t[idx[-1]] if len(idx) else 0.0

    def circ_smooth(v, width):
        k = np.ones(width) / width
        return np.convolve(np.concatenate([v] * 3), k, mode="same")[N_RAYS:2 * N_RAYS]

    # stabilise the seed before snapping, so every ray searches a consistent
    # band rather than inheriting the mask's stair-stepping
    seed = circ_smooth(seed, 31)

    # snap against the locally-contrast-enhanced image, not the raw one: after
    # the illumination ramp is removed the plaque/wall boundary is a crisp,
    # high-amplitude step everywhere around the outline, including the shadowed
    # lower right where it was previously too soft to find reliably
    blur = ndimage.gaussian_filter(local_contrast(g), 2.0)
    radii = seed.copy()
    for i, a in enumerate(angles):
        r = np.arange(SNAP_LO * seed[i], SNAP_HI * seed[i], 0.5)
        if len(r) < 5:
            continue
        prof = ndimage.map_coordinates(
            blur, [cy - np.sin(a) * r, cx + np.cos(a) * r], order=1, mode="nearest")
        grad = np.abs(np.gradient(prof))
        # walk inward from the outside and stop at the first substantial edge.
        # taking the strongest edge in the band instead lets the rim moulding's
        # inner groove win wherever the outer edge is softly lit, which is what
        # produced the scalloped outline.
        strong = np.nonzero(grad >= 0.50 * grad.max())[0]
        radii[i] = r[strong[-1]] if len(strong) else r[int(np.argmax(grad))]

    radii = circ_smooth(radii, SMOOTH_RAYS)

    fold = np.array([radii[int(round(((np.pi - a) % (2 * np.pi)) / (2 * np.pi) * N_RAYS)) % N_RAYS]
                     for a in angles])
    radii = 0.5 * (radii + fold)

    # Truncated Fourier fit. r(theta) is periodic, so keeping only the low
    # harmonics is the natural low-pass -- unlike a box filter it cannot
    # introduce corners, and an ovoid is genuinely described by a handful of
    # harmonics, so nothing real is discarded.
    F = np.fft.rfft(radii)
    F[HARMONICS + 1:] = 0.0
    radii = np.fft.irfft(F, n=N_RAYS)

    # return z-up, NOT image-row convention: every consumer (to_px, the JSON,
    # the Blender build) treats the second column as z increasing upward, and
    # returning -sin here silently flipped the plaque vertically. The flip was
    # nearly invisible by eye because both ends of an egg are pointed.
    xs = np.cos(angles) * radii
    zs = np.sin(angles) * radii
    return np.stack([xs / s, zs / s], axis=1), angles, radii


def draw_grid(img, cx, cy, s, bbox, step, colour, width, labels):
    d = ImageDraw.Draw(img, "RGBA")
    x0, x1, y0, y1 = bbox
    pad = 0.08
    nx0, _ = to_norm(x0, 0, cx, cy, s)
    nx1, _ = to_norm(x1, 0, cx, cy, s)
    _, nz1 = to_norm(0, y0, cx, cy, s)
    _, nz0 = to_norm(0, y1, cx, cy, s)

    def rng(a, b):
        lo = np.floor((a - pad) / step) * step
        hi = (b + pad)
        n = int(np.ceil((hi - lo) / step)) + 1
        return [lo + i * step for i in range(n)]

    for xv in rng(nx0, nx1):
        px, _ = to_px(xv, 0, cx, cy, s)
        d.line([(px, 0), (px, img.height)], fill=colour, width=width)
        if labels:
            d.text((px + 3, 4), f"{xv:+.2f}", fill=(255, 255, 0, 255))
    for zv in rng(nz0, nz1):
        _, py = to_px(0, zv, cx, cy, s)
        d.line([(0, py), (img.width, py)], fill=colour, width=width)
        if labels:
            d.text((4, py + 3), f"{zv:+.2f}", fill=(255, 255, 0, 255))


def main():
    os.makedirs(OUT, exist_ok=True)
    g, size = load_gray()
    mask, _ = plaque_mask(g)
    cx, cy, s, bbox = normalisation(mask)
    x0, x1, y0, y1 = bbox
    print(f"plaque bbox px x[{x0},{x1}] y[{y0},{y1}]  centre=({cx:.1f},{cy:.1f})  scale={s:.1f}px/unit")
    print(f"aspect (height/width) = {(y1 - y0) / (x1 - x0):.4f}")

    sil, angles, radii = extract_silhouette(g, mask, cx, cy, s)

    # re-derive the normalisation from the snapped outline: the mask bbox was
    # only ever a seed, so the final coordinate frame must come from the edge
    # the outline actually landed on
    spx = cx + sil[:, 0] * s
    spy = cy - sil[:, 1] * s
    cx = 0.5 * (spx.min() + spx.max())
    cy = 0.5 * (spy.min() + spy.max())
    s = 0.5 * (spx.max() - spx.min())
    bbox = (int(spx.min()), int(spx.max()), int(spy.min()), int(spy.max()))
    sil = np.stack([(spx - cx) / s, (cy - spy) / s], axis=1)
    print(f"snapped   centre=({cx:.1f},{cy:.1f})  scale={s:.1f}px/unit")
    print(f"snapped   aspect (height/width) = {(spy.max() - spy.min()) / (spx.max() - spx.min()):.4f}")

    top = sil[:, 1].max()
    bot = sil[:, 1].min()
    print(f"silhouette normalised extent  x +/-1.000   z {bot:+.4f} .. {top:+.4f}")

    with open(os.path.join(OUT, "silhouette.json"), "w") as f:
        json.dump({
            "note": "normalised plaque outline, half-width = 1.0, symmetric",
            "points_xz": [[round(float(a), 5), round(float(b), 5)] for a, b in sil],
        }, f, indent=1)
    print("WROTE", os.path.join(OUT, "silhouette.json"))

    # --- composite: lightened photo + edge map + silhouette ---
    roi = ndimage.binary_erosion(mask, structure=np.ones((5, 5)), iterations=3)
    edges = canny(g, 4.0, 96.0, 0.4, roi)

    # Local contrast, not global: the image already spans nearly the full range,
    # so a histogram stretch buys nothing. Subtracting the local mean discards
    # the illumination ramp and amplifies exactly the small differences that
    # encode the carving -- shallow grooves become plainly legible.
    lc = local_contrast(g)
    base = np.repeat((lc * 255.0)[..., None], 3, axis=2)

    # keep the wall visibly distinct from the plaque so the outline can be judged
    base[~mask] *= 0.55

    pts = [to_px(a, b, cx, cy, s) for a, b in sil]

    # two variants: the edge overlay helps at full-plaque scale where it picks
    # out structure, but at 2x it buries the surface it is supposed to clarify
    img = Image.fromarray(base.astype(np.uint8))
    ImageDraw.Draw(img).line(pts + [pts[0]], fill=(0, 230, 0), width=3)

    marked = base.copy()
    marked[ndimage.binary_dilation(edges, structure=np.ones((2, 2)))] = (220, 30, 30)
    full = Image.fromarray(marked.astype(np.uint8))
    ImageDraw.Draw(full).line(pts + [pts[0]], fill=(0, 230, 0), width=3)
    draw_grid(full, cx, cy, s, bbox, MINOR, (0, 90, 200, 90), 1, False)
    draw_grid(full, cx, cy, s, bbox, MAJOR, (0, 110, 255, 220), 2, True)
    full.save(os.path.join(OUT, "guide-full.png"))
    print("WROTE", os.path.join(OUT, "guide-full.png"))

    # --- quadrant zooms at 2x, generous overlap across the centreline ---
    quads = {
        "q1-upper-right": (-0.15, 1.15, 0.10, 1.35),
        "q2-upper-left": (-1.15, 0.15, 0.10, 1.35),
        "q3-lower-right": (-0.15, 1.15, -1.35, 0.15),
        "q4-lower-left": (-1.15, 0.15, -1.35, 0.15),
    }
    for name, (ax, bx, az, bz) in quads.items():
        p0 = to_px(ax, bz, cx, cy, s)
        p1 = to_px(bx, az, cx, cy, s)
        box = (int(p0[0]), int(p0[1]), int(p1[0]), int(p1[1]))
        crop = img.crop(box).resize(
            ((box[2] - box[0]) * 2, (box[3] - box[1]) * 2), Image.LANCZOS)
        ccx, ccy, cs = (cx - box[0]) * 2, (cy - box[1]) * 2, s * 2
        cb = (0, crop.width, 0, crop.height)
        draw_grid(crop, ccx, ccy, cs, cb, MINOR, (0, 90, 200, 110), 1, False)
        draw_grid(crop, ccx, ccy, cs, cb, MAJOR, (0, 110, 255, 230), 2, True)
        p = os.path.join(OUT, f"guide-{name}.png")
        crop.save(p)
        print("WROTE", p)


if __name__ == "__main__":
    main()
