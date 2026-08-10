"""Approach 1: automatic contour extraction from the anthemion reference photo.

Pure system Python (numpy + scipy + PIL) -- no Blender. This is a decision gate:
it produces a contact sheet of edge maps across a blur/threshold sweep so the
result can be judged BEFORE any geometry is built on top of it. If the grooves
come out as clean connected contours, approach 1 proceeds to vectorization; if
they come out broken or grain-dominated, we fall back to approach 2 (region
segmentation).

Outputs (all in trace/):
  plaque-mask.png        binary plaque silhouette, largest component
  edge-sweep.png         3x3 contact sheet, blur sigma x hysteresis threshold
  overlay-best.png       mid-parameter edge map drawn over the source image
"""


import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from paths import ROOT, REF_ANTHEMION as SRC, TRACE as OUT  # noqa: E402,F401

BLUR_SIGMAS = (2.0, 4.0, 6.0)
HI_PCTS = (85.0, 92.0, 96.0)
LO_RATIO = 0.4  # weak threshold as a fraction of the strong one


def load_gray():
    im = Image.open(SRC).convert("L")
    return np.asarray(im, dtype=np.float64) / 255.0, im.size


def plaque_mask(g):
    """Separate the cast plaque from the flat grey wall.

    Luminance thresholding fails here: the plaque's lower third sits in its own
    shadow and reads darker than the wall, so any global cut amputates it.
    Texture is the reliable discriminator instead -- the cast is pitted stone
    and carries high local variance everywhere, while the wall (and its soft
    drop shadow) is smooth. Threshold local std, then keep the largest
    component and fill holes.
    """
    k = 9
    mean = ndimage.uniform_filter(g, k)
    sq = ndimage.uniform_filter(g * g, k)
    std = np.sqrt(np.maximum(sq - mean * mean, 0.0))

    thresh = np.percentile(std, 62.0)
    m = std > thresh
    m = ndimage.binary_closing(m, structure=np.ones((11, 11)))
    m = ndimage.binary_fill_holes(m)
    lab, n = ndimage.label(m)
    if n > 1:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        m = lab == (int(np.argmax(sizes)) + 1)
    m = ndimage.binary_fill_holes(m)
    m = ndimage.binary_opening(m, structure=np.ones((9, 9)))
    return m, thresh


def canny(g, sigma, hi_pct, lo_ratio, roi):
    """Canny-structured edge detector: blur, Sobel, non-maximum suppression
    along the gradient direction, then hysteresis-linked thresholding.

    Percentile thresholds are computed over `roi` only, so the flat wall
    background does not drag the distribution down.
    """
    b = ndimage.gaussian_filter(g, sigma)
    gy = ndimage.sobel(b, axis=0)
    gx = ndimage.sobel(b, axis=1)
    mag = np.hypot(gx, gy)
    ang = np.rad2deg(np.arctan2(gy, gx)) % 180.0

    # --- non-maximum suppression: bin the gradient direction to 4 sectors and
    #     compare each pixel to its two neighbours along that direction ---
    nms = np.zeros_like(mag)
    pad = np.pad(mag, 1, mode="edge")
    h, w = mag.shape
    # (dy, dx) neighbour offsets per sector: 0deg, 45deg, 90deg, 135deg
    offsets = ((0, 1), (-1, 1), (-1, 0), (-1, -1))
    sector = (((ang + 22.5) // 45).astype(int)) % 4
    for s, (dy, dx) in enumerate(offsets):
        a = pad[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
        c = pad[1 - dy:1 - dy + h, 1 - dx:1 - dx + w]
        sel = sector == s
        keep = sel & (mag >= a) & (mag >= c)
        nms[keep] = mag[keep]

    vals = nms[roi]
    hi = np.percentile(vals, hi_pct)
    lo = hi * lo_ratio

    strong = (nms >= hi) & roi
    weak = (nms >= lo) & roi
    lab, n = ndimage.label(weak, structure=np.ones((3, 3)))
    if n == 0:
        return strong
    keep = np.zeros(n + 1, dtype=bool)
    keep[np.unique(lab[strong])] = True
    keep[0] = False
    return keep[lab]


def to_img(arr_bool, size, invert=True):
    a = (~arr_bool if invert else arr_bool).astype(np.uint8) * 255
    return Image.fromarray(a).convert("RGB")


def label_panel(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, 34], fill=(0, 0, 0))
    d.text((8, 10), text, fill=(255, 255, 255))
    return img


def contact_sheet(panels, cols, path, cell=380):
    rows = (len(panels) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (24, 24, 24))
    for i, p in enumerate(panels):
        p = p.resize((cell, cell), Image.LANCZOS)
        sheet.paste(p, ((i % cols) * cell, (i // cols) * cell))
    sheet.save(path)
    print("WROTE", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    g, size = load_gray()
    print("source", size, "gray range", round(g.min(), 3), round(g.max(), 3))

    mask, thresh = plaque_mask(g)
    print("otsu threshold", round(thresh, 4), "plaque covers",
          round(100.0 * mask.mean(), 1), "% of frame")
    to_img(mask, size, invert=False).save(os.path.join(OUT, "plaque-mask.png"))

    # erode slightly so the plaque/wall boundary itself does not dominate the
    # percentile statistics or the resulting edge map
    roi = ndimage.binary_erosion(mask, structure=np.ones((5, 5)), iterations=3)

    panels = []
    best = None
    for sigma in BLUR_SIGMAS:
        for hp in HI_PCTS:
            e = canny(g, sigma, hp, LO_RATIO, roi)
            density = 100.0 * e.sum() / max(roi.sum(), 1)
            print(f"sigma={sigma:<4} hi_pct={hp:<5} edge density={density:5.2f}%")
            panels.append(label_panel(to_img(e, size),
                                      f"sigma {sigma}  hi {hp}  {density:.1f}%"))
            if sigma == 4.0 and hp == 96.0:
                best = e

    contact_sheet(panels, 3, os.path.join(OUT, "edge-sweep.png"))

    # overlay the mid-parameter result on the source for direct comparison
    src = Image.open(SRC).convert("RGB")
    ov = np.asarray(src).copy()
    fat = ndimage.binary_dilation(best, structure=np.ones((3, 3)))
    ov[fat] = (255, 40, 40)
    Image.fromarray(ov).save(os.path.join(OUT, "overlay-best.png"))
    print("WROTE", os.path.join(OUT, "overlay-best.png"))

    # zoom on the volute/tie-band cluster -- the densest, most structurally
    # demanding region, and the fairest test of whether the trace is usable
    ys, xs = np.nonzero(mask)
    cx = (xs.min() + xs.max()) // 2
    y0 = int(ys.min() + 0.55 * (ys.max() - ys.min()))
    half = (xs.max() - xs.min()) // 3
    crop = (cx - half, y0, cx + half, y0 + 2 * half)
    Image.fromarray(ov).crop(crop).save(os.path.join(OUT, "overlay-zoom.png"))
    print("WROTE", os.path.join(OUT, "overlay-zoom.png"))


if __name__ == "__main__":
    main()
