"""Plane geometry for the source photos.

Each photo shows one flat printed sheet at an angle. Printed rules, frame
lines and panel edges give two families of lines that are parallel on the
sheet. From these we compute a homography that maps photo pixels to a
metric plane frame (a frame in which angles and length ratios on the sheet
are correct).

Model and assumptions (declared, see RECONSTRUCTION.md):

* pinhole camera, square pixels, principal point at the image centre;
* no lens distortion correction;
* the sheet is flat inside the region that holds the text.

All functions use ``(x, y)`` pixel coordinates with ``x`` to the right and
``y`` down, and pixel centres at integer coordinates.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage


# --------------------------------------------------------------------------
# sampling helpers
# --------------------------------------------------------------------------

def sample(img: np.ndarray, xs: np.ndarray, ys: np.ndarray, order: int = 1) -> np.ndarray:
    """Sample a 2-D image at float coordinates (x, y)."""
    coords = np.vstack([np.ravel(ys), np.ravel(xs)])
    out = ndimage.map_coordinates(img, coords, order=order, mode="nearest")
    return out.reshape(np.shape(xs))


def apply_h(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Apply a 3x3 homography to an (N, 2) array of points."""
    pts = np.asarray(pts, dtype=float).reshape(-1, 2)
    hom = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(h, dtype=float).T
    return hom[:, :2] / hom[:, 2:3]


# --------------------------------------------------------------------------
# line features
# --------------------------------------------------------------------------

def refine_line(gray: np.ndarray, p0, p1, kind: str = "ridge", half_width: float = 6.0,
                step: float = 2.0, polarity: int = 1):
    """Locate a printed line near the segment p0-p1 with sub-pixel accuracy.

    ``kind='ridge'``  thin line; position = centre of the dark (polarity=1)
                      or light (polarity=-1) ridge.
    ``kind='edge'``   boundary between two regions; position = steepest
                      intensity change. ``polarity`` is not used.

    Returns ``(line, points, rms)`` where ``line`` is the homogeneous line
    ``(a, b, c)`` with ``a*x + b*y + c = 0`` and ``a^2 + b^2 = 1``,
    ``points`` are the inlier sample points and ``rms`` is their RMS
    distance to the line in pixels.
    """
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    length = float(np.hypot(*(p1 - p0)))
    d = (p1 - p0) / length
    n = np.array([-d[1], d[0]])
    ts = np.arange(0.0, length + 1e-9, step)
    offs = np.arange(-half_width, half_width + 1e-9, 0.25)
    cx = p0[0] + ts[:, None] * d[0] + offs[None, :] * n[0]
    cy = p0[1] + ts[:, None] * d[1] + offs[None, :] * n[1]
    prof = sample(gray, cx, cy, order=1)
    # light smoothing along the line direction to reduce paper grain
    prof = ndimage.uniform_filter1d(prof, size=5, axis=0, mode="nearest")
    pts = []
    for i in range(len(ts)):
        row = prof[i]
        if kind == "ridge":
            sig = (np.percentile(row, 80) - row) * polarity
            if polarity < 0:
                sig = row - np.percentile(row, 20)
            sig = np.clip(sig, 0, None)
            peak = sig.max()
            if peak < 8:
                continue
            k = int(np.argmax(sig))
            # centroid of the connected run above half maximum around the peak
            lo = k
            while lo > 0 and sig[lo - 1] > 0.5 * peak:
                lo -= 1
            hi = k
            while hi < len(sig) - 1 and sig[hi + 1] > 0.5 * peak:
                hi += 1
            w = sig[lo:hi + 1]
            o = float((offs[lo:hi + 1] * w).sum() / w.sum())
        elif kind == "edge":
            g = np.gradient(ndimage.gaussian_filter1d(row, 2.0))
            k = int(np.argmax(np.abs(g)))
            if abs(g[k]) < 1.0 or k == 0 or k == len(g) - 1:
                continue
            a, b, c = abs(g[k - 1]), abs(g[k]), abs(g[k + 1])
            denom = a - 2 * b + c
            shift = 0.0 if denom == 0 else 0.5 * (a - c) / denom
            o = float(offs[k] + shift * 0.25)
        else:
            raise ValueError(kind)
        pts.append(p0 + ts[i] * d + o * n)
    pts = np.array(pts)
    if len(pts) < 5:
        raise ValueError("line not found near %s-%s" % (p0, p1))
    line, keep, rms = fit_line_robust(pts)
    return line, pts[keep], rms


def fit_line_robust(pts: np.ndarray, iters: int = 6, k: float = 2.5):
    """Total least squares line fit with iterative outlier rejection."""
    pts = np.asarray(pts, dtype=float)
    keep = np.ones(len(pts), dtype=bool)
    line = None
    for _ in range(iters):
        p = pts[keep]
        c = p.mean(axis=0)
        _, _, vt = np.linalg.svd(p - c)
        n = vt[1]
        line = np.array([n[0], n[1], -float(n @ c)])
        dist = pts @ line[:2] + line[2]
        s = 1.4826 * np.median(np.abs(dist[keep])) + 1e-6
        new_keep = np.abs(dist) <= max(k * s, 0.35)
        if new_keep.sum() < 5 or (new_keep == keep).all():
            keep = new_keep if new_keep.sum() >= 5 else keep
            break
        keep = new_keep
    dist = pts[keep] @ line[:2] + line[2]
    return line, keep, float(np.sqrt(np.mean(dist ** 2)))


def vanishing_point(lines) -> np.ndarray:
    """Least-squares common point of a set of homogeneous lines.

    Returns a homogeneous point ``(x, y, w)`` with unit norm. ``w`` close to
    zero means the lines are parallel in the photo.
    """
    lines = np.asarray(lines, dtype=float)
    # normalise the lines so that each has the same weight
    scale = np.array([1.0, 1.0, 1.0 / 1000.0])
    m = lines * scale[None, :]
    m = m / np.linalg.norm(m, axis=1, keepdims=True)
    _, _, vt = np.linalg.svd(m)
    v = vt[-1] * scale
    return v / np.linalg.norm(v)


# --------------------------------------------------------------------------
# metric rectification
# --------------------------------------------------------------------------

def focal_from_vps(vh: np.ndarray, vv: np.ndarray, centre) -> float | None:
    """Focal length (pixels) from two vanishing points of orthogonal
    directions, or ``None`` when the configuration does not determine it."""
    if abs(vh[2]) < 1e-9 or abs(vv[2]) < 1e-9:
        return None
    a = vh[:2] / vh[2] - np.asarray(centre, dtype=float)
    b = vv[:2] / vv[2] - np.asarray(centre, dtype=float)
    f2 = -float(a @ b)
    if f2 <= 0:
        return None
    return math.sqrt(f2)


def metric_homography(vh: np.ndarray, vv: np.ndarray, focal: float, centre) -> np.ndarray:
    """Homography photo -> metric plane frame.

    ``vh`` / ``vv`` are the vanishing points (homogeneous) of the sheet's
    horizontal and vertical directions. The plane frame has ``u`` along the
    horizontal direction and ``v`` along the vertical direction (down).
    The scale is arbitrary; use :func:`normalise_scale` afterwards.
    """
    cx, cy = centre
    k_inv = np.array([[1.0 / focal, 0.0, -cx / focal],
                      [0.0, 1.0 / focal, -cy / focal],
                      [0.0, 0.0, 1.0]])
    dh = k_inv @ vh
    dv = k_inv @ vv
    dh = dh / np.linalg.norm(dh)
    dv = dv / np.linalg.norm(dv)
    # orient: horizontal direction points right, vertical direction points down
    if dh[0] < 0:
        dh = -dh
    if dv[1] < 0:
        dv = -dv
    n = np.cross(dh, dv)
    n = n / np.linalg.norm(n)
    if n[2] < 0:
        n = -n
    # Symmetric orthogonalisation: split the residual non-orthogonality
    # equally between the two measured directions.
    dh = dh - (dh @ n) * n
    dv = dv - (dv @ n) * n
    dh /= np.linalg.norm(dh)
    dv /= np.linalg.norm(dv)
    m = np.vstack([dh, dv])
    u_, _, vt_ = np.linalg.svd(m, full_matrices=False)
    m = u_ @ vt_
    dh, dv = m[0], m[1]
    r = np.vstack([dh, dv, n])
    return r @ k_inv


def local_scale(h: np.ndarray, pt) -> tuple[float, float, float]:
    """Local scale of the map ``h`` at photo point ``pt``.

    Returns ``(s_mean, s_major, s_minor)``: geometric-mean scale and the two
    singular values of the Jacobian (plane units per photo pixel).
    """
    x, y = float(pt[0]), float(pt[1])
    e = 0.5
    j = np.zeros((2, 2))
    j[:, 0] = (apply_h(h, [[x + e, y]]) - apply_h(h, [[x - e, y]]))[0] / (2 * e)
    j[:, 1] = (apply_h(h, [[x, y + e]]) - apply_h(h, [[x, y - e]]))[0] / (2 * e)
    s = np.linalg.svd(j, compute_uv=False)
    return float(math.sqrt(s[0] * s[1])), float(s[0]), float(s[1])


def normalise_scale(h: np.ndarray, pt, target: float = 1.0) -> np.ndarray:
    """Rescale ``h`` so that its mean local scale at ``pt`` equals ``target``."""
    s, _, _ = local_scale(h, pt)
    scale = np.diag([target / s, target / s, 1.0])
    return scale @ h


def similarity(rotation_deg: float, scale: float, origin_plane, origin_out=(0.0, 0.0)) -> np.ndarray:
    """3x3 similarity: rotate about ``origin_plane``, scale, move to ``origin_out``."""
    a = math.radians(rotation_deg)
    c, s = math.cos(a) * scale, math.sin(a) * scale
    ox, oy = origin_plane
    tx, ty = origin_out
    return np.array([[c, -s, tx - (c * ox - s * oy)],
                     [s, c, ty - (s * ox + c * oy)],
                     [0.0, 0.0, 1.0]])


def warp(img: np.ndarray, h_out_to_photo: np.ndarray, width: int, height: int,
         supersample: int = 1, order: int = 3) -> np.ndarray:
    """Resample ``img`` into an output frame.

    ``h_out_to_photo`` maps output-frame coordinates to photo pixels. With
    ``supersample = k`` the output has ``k`` samples per output unit and the
    sample ``(i, j)`` sits at frame coordinate ``((j + 0.5) / k - 0.5,
    (i + 0.5) / k - 0.5)``; this keeps the frame aligned with pixel centres.
    """
    k = supersample
    xs = (np.arange(width * k) + 0.5) / k - 0.5
    ys = (np.arange(height * k) + 0.5) / k - 0.5
    gx, gy = np.meshgrid(xs, ys)
    pts = apply_h(h_out_to_photo, np.column_stack([gx.ravel(), gy.ravel()]))
    px = pts[:, 0].reshape(gx.shape)
    py = pts[:, 1].reshape(gx.shape)
    if img.ndim == 2:
        return sample(img, px, py, order=order)
    return np.dstack([sample(img[..., c], px, py, order=order) for c in range(img.shape[2])])
