"""Text blocks: rectified frames, ink normalisation and glyph segmentation.

A *block* is one run of lettering on one baseline (a word or a line). The
annotation gives the two baseline end points in photo pixels (in reading
direction) and the extent above and below the baseline. From the plane
homography we build a *block frame*:

* x runs along the baseline in reading direction, y runs down;
* one block unit is one unit of the rectified plane, which is one photo
  pixel at the photo centre and close to one photo pixel elsewhere;
* the baseline start sits at ``(pad, pad + up)``.

The block frame is the "declared normalisation" in which glyph shapes are
traced and evaluated.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import geometry as G


class Frame:
    """Affine/projective map between photo pixels and block units."""

    def __init__(self, photo_to_block: np.ndarray, width: float, height: float,
                 baseline_y: float, pad: float):
        self.photo_to_block = np.asarray(photo_to_block, dtype=float)
        self.block_to_photo = np.linalg.inv(self.photo_to_block)
        self.width = int(math.ceil(width))
        self.height = int(math.ceil(height))
        self.baseline_y = float(baseline_y)
        self.pad = float(pad)

    def to_block(self, pts):
        return G.apply_h(self.photo_to_block, pts)

    def to_photo(self, pts):
        return G.apply_h(self.block_to_photo, pts)


def make_frame(plane_h: np.ndarray, p0, p1, up: float, down: float, pad: float = 6.0,
               rotation_deg: float = 0.0, shear: float = 0.0) -> Frame:
    """Build the block frame.

    ``p0`` and ``p1`` are the baseline end points in photo pixels, ``up`` and
    ``down`` the extents above and below the baseline in photo pixels.
    ``rotation_deg`` and ``shear`` are small measured corrections of the
    block (residual baseline angle and stem slant); both act about the
    baseline start so they do not change lengths along the baseline.
    """
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    q = G.apply_h(plane_h, [p0, p1])
    d = q[1] - q[0]
    angle = math.atan2(d[1], d[0])
    # One block unit is one plane unit. The plane homography is scaled so
    # that a plane unit is one photo pixel at the photo centre, so a block
    # unit is close to one photo pixel everywhere, and lettering of one
    # physical size has one size in block units in every block of a photo.
    scale = 1.0
    length = float(np.hypot(*d)) * scale
    # ``up`` and ``down`` are annotated in photo pixels; convert them
    s_mean, _, _ = G.local_scale(plane_h, (p0 + p1) / 2.0)
    up = up * s_mean
    down = down * s_mean
    # plane -> block: translate q0 to the origin, rotate, scale
    c, s = math.cos(-angle), math.sin(-angle)
    rot = np.array([[c * scale, -s * scale, 0.0], [s * scale, c * scale, 0.0], [0.0, 0.0, 1.0]])
    trans = np.array([[1.0, 0.0, -q[0, 0]], [0.0, 1.0, -q[0, 1]], [0.0, 0.0, 1.0]])
    a = math.radians(rotation_deg)
    fix_rot = np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]])
    fix_shear = np.array([[1.0, shear, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    place = np.array([[1.0, 0.0, pad], [0.0, 1.0, pad + up], [0.0, 0.0, 1.0]])
    m = place @ fix_shear @ fix_rot @ rot @ trans @ plane_h
    return Frame(m, length + 2 * pad, up + down + 2 * pad, pad + up, pad)


# --------------------------------------------------------------------------
# ink normalisation
# --------------------------------------------------------------------------

def ink_axis(rgb: np.ndarray, polarity: str, iters: int = 4):
    """Find the RGB direction that best separates ink from ground.

    Returns ``(weights, ground_rgb, ink_rgb)``. ``polarity`` is ``'dark'``
    (ink darker than ground) or ``'light'``.
    """
    px = rgb.reshape(-1, 3)
    lum = px.mean(axis=1)
    lo, hi = np.percentile(lum, [5, 95])
    thr = (lo + hi) / 2.0
    for _ in range(iters):
        dark = px[lum < thr]
        light = px[lum >= thr]
        if len(dark) < 10 or len(light) < 10:
            break
        thr = (dark.mean(axis=0).mean() + light.mean(axis=0).mean()) / 2.0
    dark_c = np.median(px[lum < thr], axis=0)
    light_c = np.median(px[lum >= thr], axis=0)
    ground, ink = (light_c, dark_c) if polarity == "dark" else (dark_c, light_c)
    w = ground - ink
    w = w / (w @ w)
    return w, ground, ink


def normalise_ink(rgb: np.ndarray, polarity: str, stroke_px: float, k: int = 1):
    """Convert an RGB block image to an ink map: 0 = ground, 1 = full ink.

    * The colour axis is the line through the block's ground and ink colours.
    * The ground level is estimated locally (a rank filter much larger than
      a stroke, then smoothing), so uneven lighting does not move edges.
    * The ink level is one value per block: the median depth of the pixels
      in the darkest core of the strokes.

    ``stroke_px`` is the approximate stroke width in block units and ``k``
    the supersampling factor of ``rgb``.
    """
    w, ground, ink = ink_axis(rgb, polarity)
    depth = (ground[None, None, :] - rgb) @ w          # ~0 on ground, ~1 on ink
    # Ground level. Work on a reduced copy in which a stroke is about 3
    # samples wide. Step 1: a low rank over a window of about 8 stroke
    # widths gives a first ground estimate. Step 2: the ground is the
    # smoothed mean of the samples that step 1 classifies as ground, so the
    # estimate is not biased by the rank.
    f = max(1, int(round(k * stroke_px / 3.0)))
    hh, ww = depth.shape
    ph, pw = (-hh) % f, (-ww) % f
    padded = np.pad(depth, ((0, ph), (0, pw)), mode="edge")
    small = padded.reshape(padded.shape[0] // f, f, padded.shape[1] // f, f).mean(axis=(1, 3))
    win = 25
    first = ndimage.percentile_filter(small, 10, size=win, mode="nearest")
    first = ndimage.gaussian_filter(first, win / 4.0, mode="nearest")
    is_ground = ((small - first) < 0.25).astype(float)
    sigma = win / 3.0
    num = ndimage.gaussian_filter(small * is_ground, sigma, mode="nearest")
    den = ndimage.gaussian_filter(is_ground, sigma, mode="nearest")
    floor = np.where(den > 0.02, num / np.maximum(den, 1e-6), first)
    floor = ndimage.zoom(floor, f, order=1, mode="nearest")[:hh, :ww]
    rel = depth - floor
    core = rel[rel > 0.5 * np.percentile(rel, 99.5)]
    level = float(np.percentile(core, 75)) if len(core) else 1.0
    level = max(level, 1e-3)
    return rel / level, {"axis": [float(x) for x in w], "ground_rgb": [float(x) for x in ground],
                         "ink_rgb": [float(x) for x in ink], "ink_level": level}


def extract(photo_rgb: np.ndarray, frame: Frame, k: int = 4, order: int = 3) -> np.ndarray:
    """Resample the photo into the block frame at ``k`` samples per unit."""
    return G.warp(photo_rgb, frame.block_to_photo, frame.width, frame.height, supersample=k, order=order)


# --------------------------------------------------------------------------
# segmentation
# --------------------------------------------------------------------------

def components(mask: np.ndarray, min_area: float):
    """8-connected components of a mask with area >= ``min_area`` samples."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    out = []
    if n == 0:
        return lab, out
    slices = ndimage.find_objects(lab)
    areas = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    for i, (sl, area) in enumerate(zip(slices, areas), start=1):
        if area < min_area:
            continue
        ys, xs = sl
        out.append({"label": i, "x0": xs.start, "x1": xs.stop, "y0": ys.start, "y1": ys.stop,
                    "area": float(area)})
    return lab, out


def group_columns(comps: list, min_overlap: float = 0.5):
    """Group components that sit above each other into one glyph.

    Two components belong together when their x-ranges overlap by at least
    ``min_overlap`` of the narrower one (dot of i, accent, stacked marks).
    """
    comps = sorted(comps, key=lambda c: (c["x0"] + c["x1"]) / 2.0)
    groups: list[list] = []
    for c in comps:
        placed = False
        for g in groups:
            gx0 = min(m["x0"] for m in g)
            gx1 = max(m["x1"] for m in g)
            ov = min(gx1, c["x1"]) - max(gx0, c["x0"])
            if ov >= min_overlap * min(gx1 - gx0, c["x1"] - c["x0"]):
                g.append(c)
                placed = True
                break
        if not placed:
            groups.append([c])
    groups.sort(key=lambda g: min(m["x0"] for m in g))
    return groups


def group_box(group: list):
    return (min(m["x0"] for m in group), min(m["y0"] for m in group),
            max(m["x1"] for m in group), max(m["y1"] for m in group))
