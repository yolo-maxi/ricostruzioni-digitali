"""Photo plane rectification from annotated line features.

Input: the ``photos`` and ``planes`` sections of ``evidence/annotations.json``.
Output: for each plane a homography photo -> metric plane frame plus the
diagnostics that RECONSTRUCTION.md cites (line fit residuals, vanishing
points, tilt, anisotropy sensitivity to the assumed focal length).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from . import geometry as G

LAB = Path(__file__).resolve().parent.parent


def load_photo(photos: dict, key: str) -> np.ndarray:
    """Load a source photo as float RGB (H, W, 3). The file is only read."""
    path = LAB / photos[key]["file"]
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64)


def channel(rgb: np.ndarray, spec) -> np.ndarray:
    """Project RGB to one channel. ``spec`` is 'L', 'R', 'G', 'B' or weights."""
    if spec == "L":
        return rgb.mean(axis=2)
    if spec in ("R", "G", "B"):
        return rgb[..., "RGB".index(spec)]
    w = np.asarray(spec, dtype=float)
    return rgb @ w


def default_focal(width: int, height: int) -> float:
    """Assumed focal length in pixels.

    The four photos are 9:16 phone frames. We assume the full frame of a
    main phone camera with a 26 mm (35 mm-equivalent) lens used in 16:9
    mode: the long image side then spans 4/5 of the 43.27 mm diagonal.
    The plausible range 24-28 mm is used for the sensitivity figures.
    """
    return focal_for_equiv(26.0, width, height)


def focal_for_equiv(equiv_mm: float, width: int, height: int) -> float:
    long_side_mm = 43.27 * 4.0 / 5.0
    return max(width, height) * equiv_mm / long_side_mm


def solve_plane(photos: dict, plane: dict) -> dict:
    """Fit the annotated lines and compute the rectifying homography."""
    photo = photos[plane["photo"]]
    rgb = load_photo(photos, plane["photo"])
    h_img, w_img = rgb.shape[:2]
    centre = ((w_img - 1) / 2.0, (h_img - 1) / 2.0)
    fitted = {"h": [], "v": []}
    for family in ("h", "v"):
        for spec in plane["lines"][family]:
            gray = channel(rgb, spec.get("channel", plane.get("channel", "L")))
            line, pts, rms = G.refine_line(
                gray, spec["p0"], spec["p1"], kind=spec.get("kind", "ridge"),
                half_width=spec.get("half_width", 5.0), step=2.0,
                polarity=spec.get("polarity", 1))
            span = float(np.hypot(*(pts[-1] - pts[0])))
            fitted[family].append({"name": spec["name"], "line": line, "rms": rms,
                                   "samples": int(len(pts)), "span": span})
    vps = {}
    for family in ("h", "v"):
        lines = np.array([f["line"] for f in fitted[family]])
        weights = np.array([f["span"] for f in fitted[family]])
        vps[family] = G.vanishing_point(lines * weights[:, None] / weights.max())
    focal = float(plane.get("focal_px") or default_focal(w_img, h_img))
    h_mat = G.metric_homography(vps["h"], vps["v"], focal, centre)
    ref = plane.get("scale_ref", [centre[0], centre[1]])
    h_mat = G.normalise_scale(h_mat, ref, 1.0)

    def tilt_and_aniso(f):
        hm = G.metric_homography(vps["h"], vps["v"], f, centre)
        _, smax, smin = G.local_scale(hm, ref)
        k_inv = np.array([[1 / f, 0, -centre[0] / f], [0, 1 / f, -centre[1] / f], [0, 0, 1]])
        n = np.cross(k_inv @ vps["h"], k_inv @ vps["v"])
        n = n / np.linalg.norm(n)
        tilt = math.degrees(math.acos(min(1.0, abs(n[2]))))
        return tilt, smin / smax

    tilt, aniso = tilt_and_aniso(focal)
    lo = tilt_and_aniso(focal_for_equiv(24.0, w_img, h_img))
    hi = tilt_and_aniso(focal_for_equiv(28.0, w_img, h_img))
    out = {
        "photo": plane["photo"],
        "focal_px": round(focal, 2),
        "focal_assumption": "26 mm equivalent main camera, full 9:16 frame, principal point at centre",
        "principal_point": [centre[0], centre[1]],
        "vanishing_points": {k: [float(v) for v in vps[k]] for k in vps},
        "homography_photo_to_plane": [[float(x) for x in row] for row in h_mat],
        "scale_ref": [float(ref[0]), float(ref[1])],
        "tilt_deg": round(tilt, 3),
        "foreshortening_at_ref": round(aniso, 5),
        "foreshortening_range_24_28mm": [round(lo[1], 5), round(hi[1], 5)],
        "lines": {fam: [{"name": f["name"], "rms_px": round(f["rms"], 3),
                         "samples": f["samples"], "span_px": round(f["span"], 1),
                         "line": [float(x) for x in f["line"]]}
                        for f in fitted[fam]] for fam in fitted},
    }
    # residual angle of every fitted line after rectification
    for fam, target in (("h", 0.0), ("v", 90.0)):
        for f, rec in zip(fitted[fam], out["lines"][fam]):
            a, b, c = f["line"]
            # two points on the line inside the photo
            d = np.array([-b, a])
            p_mid = -c * np.array([a, b])
            pts = np.array([p_mid - 300 * d, p_mid + 300 * d])
            q = G.apply_h(h_mat, pts)
            ang = math.degrees(math.atan2(q[1, 1] - q[0, 1], q[1, 0] - q[0, 0])) % 180.0
            dev = ang - target
            if dev > 90:
                dev -= 180
            rec["rectified_angle_error_deg"] = round(dev, 3)
    return out
