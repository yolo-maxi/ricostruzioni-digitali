#!/usr/bin/env python3
"""Build Balilla-Panel-Reconstructed from the pale panel lettering.

Selected sample: the pale thin rounded lettering "mini- stero educa- zione
nazio- nale" (ministero educazione nazionale) inside the dark green panel of
the obelisk cover, photo ``assets/HXwNXsUWEAALJek.jpg``. The owner named this
lettering with a close photo, ``assets/img_9eb5018c1e1c.jpg``; that file is
the same exposure at 5/6 of the size, so the larger copy is traced.
See ``focus-panel.json``. Nothing is taken from the two other fonts.

Steps (deterministic; the source photos are only read):

1. Rectify the photo plane from four printed lines of the obelisk cover.
2. Resample each of the six lines along its own measured baseline,
   8 samples per unit, and make an ink mask at the level midway between
   ground and full ink. The six lines are not exactly parallel, so each
   line has its own baseline. All lines share ONE scale.
3. Trace each of the 31 shapes. Smooth each run of the outline between two
   corners along its length. Stroke ends and joints keep their form.
4. A letter that occurs more than once is drawn by hand a little
   differently each time. The font takes the occurrence that is closest
   to the others (largest mean Dice); with two occurrences, the first.
5. Scale: the median height of the 23 letters without ascender or
   descender is 600 font units.
6. Side bearings: a least-squares fit to 21 measured gaps between
   letters. One measured pair (r o) is a kerning pair.
7. Store each outline as TrueType quadratic curves.
8. Add the other glyphs by bounded extrapolation and label every glyph.

Run:  python source/balilla-lab/build_panel.py [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0
from scipy import ndimage
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
import build_font as BF  # noqa: E402
from outline_helpers import close_voids, glyph_from_curves, shape_dice  # noqa: E402  (helpers only, no shapes)
from pipeline import blocks as B  # noqa: E402
from pipeline import geometry as G  # noqa: E402
from pipeline import planes as P  # noqa: E402

R = json.loads((LAB / "focus-panel.json").read_text())
K = int(R["supersample"])
LETTER = float(R["letter_height_units"])
VERSION = R["face"]["version"]
STEM = R["face"]["file_stem"]
CL = R["classes"]
UPM = 1000
ASCENT = 900
DESCENT = 300

LABELS = {
    "evidenced-selected": "traced from the selected sample (scored)",
    "extrapolated-derived": "extrapolated: mirrored, turned or extended from a traced glyph",
    "extrapolated-constructed": "extrapolated: one-weight construction from the measured stroke, letter height, ascender and descender",
}


# --------------------------------------------------------------------------
# source: the two copies of the photograph
# --------------------------------------------------------------------------

def source(which="traced"):
    """Photo, plane lines, blocks and pixel factor for one copy of the photograph.

    ``traced`` is the copy that the font is traced from. ``supplied`` is the
    close photo that the owner supplied: the same exposure at a smaller
    size, so every annotation is scaled by the ratio of the two widths."""
    if which == "traced":
        return {"which": which, "photo": R["photo"], "plane": R["plane"], "blocks": R["blocks"], "factor": 1.0}
    if which != "supplied":
        raise ValueError(which)
    photo = dict(R["supplied_close_photo"], key="S")
    f = photo["size"][0] / float(R["photo"]["size"][0])

    def pt(p):                                   # pixel centres are at whole numbers
        return [(p[0] + 0.5) * f - 0.5, (p[1] + 0.5) * f - 0.5]

    plane = {"photo": "S", "channel": R["plane"]["channel"], "lines": {
        fam: [dict(line, p0=pt(line["p0"]), p1=pt(line["p1"]),
                   **({"half_width": line["half_width"] * f} if "half_width" in line else {}))
              for line in R["plane"]["lines"][fam]] for fam in ("h", "v")}}
    blocks = {key: dict(spec, baseline=[pt(spec["baseline"][0]), pt(spec["baseline"][1])],
                        up=spec["up"] * f, down=spec["down"] * f) for key, spec in R["blocks"].items()}
    return {"which": which, "photo": photo, "plane": plane, "blocks": blocks, "factor": f}


def load_geometry(src):
    """Return (plane homography, photo RGB, plane diagnostics) for one copy."""
    photo = src["photo"]
    if BF.sha256(LAB / photo["file"]) != photo["sha256"]:
        raise SystemExit("source photo changed: %s" % photo["file"])
    photos = {photo["key"]: photo}
    solved = P.solve_plane(photos, src["plane"])
    rgb = P.load_photo(photos, photo["key"])
    return np.array(solved["homography_photo_to_plane"]), rgb, solved


# --------------------------------------------------------------------------
# source: rectified lines and letter masks
# --------------------------------------------------------------------------

def _extract(spec, plane_h, rgb, rotation, f):
    frame = B.make_frame(plane_h, spec["baseline"][0], spec["baseline"][1], spec["up"], spec["down"],
                         pad=R["pad"], rotation_deg=rotation)
    img = B.extract(rgb, frame, k=K)
    ink, info = B.normalise_ink(img, R["polarity"], R["stroke"] * f, k=K)
    mask = ink >= 0.5
    lab, comps = B.components(mask, R["min_letter_area"] * f * f * K * K)
    h, w = mask.shape
    comps.sort(key=lambda c: c["x0"])
    # letters of this line do not touch the frame; ink that touches it belongs to another line
    letters = [c for c in comps if c["x0"] > 1 and c["x1"] < w - 1 and c["y0"] > 1 and c["y1"] < h - 1]
    return {"frame": frame, "img": img, "ink": ink, "info": info, "mask": mask, "lab": lab, "letters": letters}


def _centre_slope(text, letters):
    """Median slope of the line through the centres of the letters that have
    no ascender and no descender. The centre does not depend on overshoot."""
    skip = CL["ascenders"] + CL["descenders"] + CL["marks"]
    pts = [((c["x0"] + c["x1"]) / 2.0, (c["y0"] + c["y1"]) / 2.0) for ch, c in zip(text, letters) if ch not in skip]
    return float(np.median([(b[1] - a[1]) / (b[0] - a[0]) for i, a in enumerate(pts) for b in pts[i + 1:]]))


def _foot(blk, ch, comp, f):
    """Bottom of the flat foot of a letter (samples), or None for a letter with a round bottom."""
    if ch in CL["flat_foot"]:
        return float(comp["y1"])
    if ch in CL["right_foot"]:                    # the foot is the short stem at the right
        cols = max(1, int(round(0.6 * R["stroke"] * f * K)))
        sub = blk["lab"][comp["y0"]:comp["y1"], comp["x1"] - cols:comp["x1"]] == comp["label"]
        return float(comp["y0"] + np.where(sub.any(axis=1))[0].max() + 1)
    return None


def extract_blocks(src, plane_h, rgb):
    """The six rectified lines, each with a level baseline. Positions are in samples.

    Baseline of a line: the median of the feet of its flat-footed letters
    and of the bottoms of its round letters moved up by the common
    overshoot. The common overshoot is the median distance of a round
    bottom below the feet, measured in the lines with two or more feet."""
    f = src["factor"]
    blocks = {}
    for key, spec in src["blocks"].items():
        text = spec["text"]
        blk = _extract(spec, plane_h, rgb, 0.0, f)
        if len(blk["letters"]) != len(text):
            raise SystemExit("line %s: expected %d shapes, found %d" % (key, len(text), len(blk["letters"])))
        rotation = -math.degrees(math.atan(_centre_slope(text, blk["letters"])))
        blk = _extract(spec, plane_h, rgb, rotation, f)
        if len(blk["letters"]) != len(text):
            raise SystemExit("line %s: expected %d shapes, found %d" % (key, len(text), len(blk["letters"])))
        blk.update(key=key, chars=text, rotation_deg=rotation)
        q = blk["frame"].to_photo([[0.0, blk["frame"].baseline_y], [1.0, blk["frame"].baseline_y]])
        d = G.apply_h(plane_h, q)
        blk["plane_angle_deg"] = math.degrees(math.atan2(d[1, 1] - d[0, 1], d[1, 0] - d[0, 0]))
        blocks[key] = blk
    skip = CL["descenders"] + CL["marks"]
    feet, over = {}, []
    for key, blk in blocks.items():
        feet[key] = {i: _foot(blk, ch, c, f) for i, (ch, c) in enumerate(zip(blk["chars"], blk["letters"]))}
        flat = [v for v in feet[key].values() if v is not None]
        if len(flat) >= 2:
            first = float(np.median(flat))
            over += [c["y1"] - first for i, (ch, c) in enumerate(zip(blk["chars"], blk["letters"]))
                     if feet[key][i] is None and ch not in skip]
    overshoot = float(np.median(over))
    heights = []
    for key, blk in blocks.items():
        est = [feet[key][i] if feet[key][i] is not None else c["y1"] - overshoot
               for i, (ch, c) in enumerate(zip(blk["chars"], blk["letters"])) if ch not in skip]
        blk["baseline"] = float(np.median(est))
        heights += [c["y1"] - c["y0"] for ch, c in zip(blk["chars"], blk["letters"])
                    if ch not in CL["ascenders"] + skip]
    scale = {"letter_height_samples": float(np.median(heights)), "letters_measured": len(heights),
             "round_overshoot_samples": overshoot, "u": LETTER / float(np.median(heights))}
    return blocks, scale


# --------------------------------------------------------------------------
# outlines: smoothing and quadratic curves
# --------------------------------------------------------------------------

def _resample(ring):
    """Points of a closed ring at a spacing of about one sample."""
    pts = np.asarray(ring, dtype=float)
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    closed = np.vstack([pts, pts[:1]])
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(closed, axis=0).T))])
    n = max(16, int(round(s[-1])))
    t = np.arange(n) * s[-1] / n
    return np.column_stack([np.interp(t, s, closed[:, 0]), np.interp(t, s, closed[:, 1])]), s[-1] / n


def _gauss(p, sigma):
    return np.column_stack([ndimage.gaussian_filter1d(p[:, i], sigma, mode="wrap") for i in (0, 1)])


def _turning(p, w):
    """Turning angle (degrees) of a closed point list over a window of +/-w points."""
    a = p - np.roll(p, w, axis=0)
    b = np.roll(p, -w, axis=0) - p
    return np.degrees(np.abs(np.arctan2(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0], (a * b).sum(axis=1))))


def _smooth_open(seg, sigma):
    """Smooth an open run of points. The two end points do not move."""
    m = min(len(seg) - 1, int(math.ceil(4 * sigma)))
    if m < 1:
        return seg
    ext = np.vstack([2 * seg[0] - seg[m:0:-1], seg, 2 * seg[-1] - seg[-2:-m - 2:-1]])

    def blur(v):
        return np.column_stack([ndimage.gaussian_filter1d(v[:, i], sigma, mode="nearest") for i in (0, 1)])

    once = blur(ext)
    return (once + blur(ext - once))[m:m + len(seg)]      # second pass: a smoothed curve does not shrink


def smooth_ring(ring, moved=None):
    """Smooth one closed outline (sample coordinates).

    A corner zone is a part of the outline that turns fast: a stroke end or
    a joint. Corner zones keep a light smoothing (it removes the sample
    steps). Each run between two corner zones is smoothed along its length
    with its two end points fixed (it removes the grain of the print and of
    the photo). The widths are in rectified units and come from the record.
    If ``moved`` is a list, the largest distance (samples) between the
    lightly smoothed outline and the result is appended to it."""
    s = R["smooth"]
    p, step = _resample(ring)
    light = _gauss(p, s["light_units"] * K / step)
    probe = _gauss(p, s["corner_probe_units"] * K / step)
    angle = _turning(probe, max(1, int(round(s["corner_window_units"] * K / step))))
    grow = max(1, int(round(s["corner_grow_units"] * K / step)))
    zone = ndimage.maximum_filter1d((angle > s["corner_degrees"]).astype(np.uint8), 2 * grow + 1, mode="wrap") > 0
    sigma = s["heavy_units"] * K / step
    if not zone.any():                            # no corner: smooth the whole closed outline
        once = _gauss(p, sigma)
        out = once + _gauss(p - once, sigma)
        if moved is not None:
            moved.append(float(np.hypot(*(out - light).T).max()))
        return out
    if zone.all():
        if moved is not None:
            moved.append(0.0)
        return light
    first = int(np.where(zone & ~np.roll(zone, 1))[0][0])          # start at the first point of a corner zone
    light, zone = np.roll(light, -first, axis=0), np.roll(zone, -first)
    out = light.copy()
    n = len(zone)
    i = 0
    while i < n:
        if zone[i]:
            i += 1
            continue
        j = i
        while j < n and not zone[j]:
            j += 1
        seg = np.vstack([light[i - 1:j], light[j % n:j % n + 1]])   # the run with one corner point at each end
        out[i:j] = _smooth_open(seg, sigma)[1:-1]
        i = j
    if moved is not None:
        moved.append(float(np.hypot(*(out - light).T).max()))
    return np.roll(out, first, axis=0)


def smooth_shape(shape, moved=None):
    polys = [shape] if shape.geom_type == "Polygon" else list(shape.geoms)
    return unary_union([Polygon(smooth_ring(p.exterior.coords, moved),
                                [smooth_ring(h.coords, moved) for h in p.interiors]).buffer(0) for p in polys])


def to_units(shape, x_left, baseline, u):
    """Samples -> font units; x = 0 at ``x_left``, baseline at y = 0, y up."""
    return affinity.affine_transform(shape, [u, 0.0, 0.0, -u, -x_left * u, baseline * u])


def _quad(a, ta, b, tb):
    """Control point of the quadratic curve from ``a`` to ``b`` with the end
    directions ``ta`` and ``tb``: the crossing of the two tangent lines."""
    den = ta[0] * tb[1] - ta[1] * tb[0]
    if abs(den) < 1e-9:
        return None
    d = b - a
    s = (d[0] * tb[1] - d[1] * tb[0]) / den
    v = (d[0] * ta[1] - d[1] * ta[0]) / den
    if s <= 0 or v >= 0:
        return None
    return a + s * ta


def _fit(p, i, j, ta, tb, tan, out, tol):
    """Fit points ``i..j`` of the (unwrapped) list ``p`` with quadratic curves; append to ``out``."""
    seg = p[i:j + 1]
    a, b = seg[0], seg[-1]
    chord = b - a
    length = float(np.hypot(*chord))
    if j - i < 3:
        out.append((b[0], b[1], 1))
        return
    if length > 1e-9:
        dist = np.abs(chord[0] * (seg[:, 1] - a[1]) - chord[1] * (seg[:, 0] - a[0])) / length
        if dist.max() <= tol["line"]:
            out.append((b[0], b[1], 1))
            return
    turn = abs(math.atan2(ta[0] * tb[1] - ta[1] * tb[0], ta[0] * tb[0] + ta[1] * tb[1]))
    c = _quad(a, ta, b, tb) if turn <= math.radians(tol["max_arc_degrees"]) and length > 1e-9 else None
    if c is not None:
        t = np.linspace(0.0, 1.0, 2 * len(seg) + 1)[:, None]
        curve = (1 - t) ** 2 * a + 2 * t * (1 - t) * c + t ** 2 * b
        err = np.sqrt(((seg[:, None, :] - curve[None, :, :]) ** 2).sum(axis=2).min(axis=1)).max()
        if err <= tol["curve"]:
            out.append((c[0], c[1], 0))
            out.append((b[0], b[1], 1))
            return
    m = (i + j) // 2
    _fit(p, i, m, ta, tan[m], tan, out, tol)
    _fit(p, m, j, tan[m], tb, tan, out, tol)


def fit_ring(ring, outer):
    """One closed outline (font units) as TrueType quadratic curves.

    Returns a list of ``(x, y, on_curve)``. The outline is cut at its four
    extreme points (left, right, bottom, top), so the bounding box of the
    control points is the bounding box of the outline. Each part is then cut
    again until it is a straight line or one quadratic curve within the
    tolerance of the record. Two parts that meet have the same tangent, so
    a smooth outline stays smooth; a sharp corner becomes very short parts."""
    q = R["curves"]
    pts = np.asarray(ring, dtype=float)
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    area = float((pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1]).sum())
    if (area < 0) != outer:                       # outer contours clockwise, holes counter-clockwise
        pts = pts[::-1]
    closed = np.vstack([pts, pts[:1]])
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(closed, axis=0).T))])
    n = max(24, int(round(s[-1] / q["step_units"])))
    t = np.arange(n) * s[-1] / n
    p = np.column_stack([np.interp(t, s, closed[:, 0]), np.interp(t, s, closed[:, 1])])
    k = max(1, int(round(q["tangent_units"] * n / s[-1])))
    p = np.roll(p, -int(np.argmin(p[:, 1])), axis=0)             # start at the lowest point
    tan = np.roll(p, -k, axis=0) - np.roll(p, k, axis=0)
    tan = tan / np.maximum(np.hypot(tan[:, 0], tan[:, 1]), 1e-12)[:, None]
    flat = math.sin(math.radians(q["extreme_snap_degrees"]))
    cuts = {0}
    for axis in (0, 1):                           # at a smooth extreme point the tangent is along the other axis
        for i in (int(np.argmin(p[:, axis])), int(np.argmax(p[:, axis]))):
            cuts.add(i)
            if abs(tan[i][axis]) < flat:
                tan[i] = [0.0, math.copysign(1.0, tan[i][1])] if axis == 0 else [math.copysign(1.0, tan[i][0]), 0.0]
    cuts = sorted(cuts) + [n]
    if len(cuts) < 4:
        cuts = [n * i // 4 for i in range(5)]
    p = np.vstack([p, p[:1]])                     # unwrapped: the first point is also the last
    tan = np.vstack([tan, tan[:1]])
    out = [(p[0][0], p[0][1], 1)]
    for c0, c1 in zip(cuts[:-1], cuts[1:]):
        _fit(p, c0, c1, tan[c0], tan[c1], tan, out, q)
    out = out[:-1]                                # the last point is the first one again
    clean = []
    for x, y, on in out:                          # whole font units; no repeated point
        pt = (int(round(x)), int(round(y)), on)
        if clean and clean[-1][:2] == pt[:2]:
            if pt[2]:
                clean[-1] = pt
            continue
        clean.append(pt)
    while len(clean) > 1 and clean[-1][:2] == clean[0][:2]:
        clean.pop()
    return clean


def curve_contours(shape):
    """Contours of a shape as TrueType quadratic curves, in a fixed order."""
    if shape is None or shape.is_empty:
        return []
    polys = [shape] if shape.geom_type == "Polygon" else [p for p in shape.geoms if p.geom_type == "Polygon"]
    out = []
    for p in sorted(polys, key=lambda g: (round(g.bounds[0], 3), round(g.bounds[1], 3))):
        if p.area < 1:
            continue
        for ring, outer in [(p.exterior, True)] + [(r, False) for r in p.interiors]:
            c = fit_ring(ring.coords, outer)
            if len(c) >= 3:
                out.append(c)
    return out


# --------------------------------------------------------------------------
# traced glyphs
# --------------------------------------------------------------------------

def occurrences_of(blocks, u):
    """Every shape of the sample, traced and smoothed, in font units."""
    out = []
    for key, blk in blocks.items():
        for i, (ch, comp) in enumerate(zip(blk["chars"], blk["letters"])):
            moved = []
            shape = to_units(smooth_shape(BF.trace(blk["lab"], comp), moved), comp["x0"], blk["baseline"], u)
            shape = close_voids(BF.left0(shape), float(R["close_voids_below_units2"]))
            nxt = blk["letters"][i + 1] if i + 1 < len(blk["letters"]) else None
            out.append({"char": ch, "block": key, "index": i, "shape": shape, "moved": max(moved) / K,
                        "next": blk["chars"][i + 1] if nxt else None,
                        "gap": (nxt["x0"] - comp["x1"]) * u if nxt else None})
    return out


def side_bearings(occ, chars):
    """Side bearings and kerning of the traced glyphs from the measured gaps.

    Model: gap between two letters = right bearing of the left letter + left
    bearing of the right letter. Sides of the same kind share one value:
    all straight sides (a stem) have one bearing and all round sides have
    one bearing. A side of another form (the bar of t, the open side of e)
    has its own value. The values are a least-squares fit to the measured
    gaps between letters.

    The arm of r: the sample shows r only before o, and the o sits under
    the arm. A bearing that small is too tight before a stem. So the right
    side of r gets the bearing of the right side of t (also an arm at the
    top), and the measured distance r-o is a kerning pair. The same kerning
    value is used before the other letters with a round left side; those
    pairs are extrapolated.

    The hyphen is fitted afterwards, so the hyphen gaps do not change the
    letters."""
    sides, mark, arm = R["spacing"]["sides"], CL["marks"], R["spacing"]["arm"]
    gaps = [(o["char"], o["next"], o["gap"]) for o in occ if o["next"]]
    letters = [g for g in gaps if g[0] not in mark and g[1] not in mark]
    fit = [g for g in letters if g[0] not in arm]

    def key(side, ch):
        for kind in ("straight", "round"):
            if ch in sides[kind][side]:
                return kind
        if ch in sides["own"][side]:
            return side + ":" + ch
        raise SystemExit("no %s side declared for the letter %s" % (side, ch))

    keys = sorted({key("right", a) for a, _, _ in fit} | {key("left", b) for _, b, _ in fit})
    col = {k: i for i, k in enumerate(keys)}
    rows = np.zeros((len(fit), len(keys)))
    for n, (a, b, _) in enumerate(fit):
        rows[n, col[key("right", a)]] += 1.0
        rows[n, col[key("left", b)]] += 1.0
    sol, _, rank, _ = np.linalg.lstsq(rows, np.array([g[2] for g in fit]), rcond=None)
    if rank < len(keys):
        raise SystemExit("the measured gaps do not fix every side bearing")
    value = {k: float(sol[col[k]]) for k in keys}
    value["common"] = (value["straight"] + value["round"]) / 2.0
    left, right = {}, {}
    for ch in chars:
        if ch in mark:
            continue
        left[ch] = value[R["spacing"]["unobserved"]["left"].get(ch) or key("left", ch)]
        right[ch] = value[key("right", arm[ch]["like"] if ch in arm else ch)]
    for m in mark:
        left[m] = right[m] = float(np.median([g[2] - right[g[0]] for g in gaps if g[1] == m]))
    bearings = {ch: (int(round(left[ch])), int(round(right[ch]))) for ch in chars}
    kerning = {}
    for a, b, g in letters:
        if a in arm:                              # measured pair: the distance on the cover
            kerning[(a, b)] = int(round(g)) - bearings[a][1] - bearings[b][0]
    table = []
    for a, b, g in gaps:
        font_gap = bearings[a][1] + bearings[b][0] + kerning.get((a, b), 0)
        table.append({"left": a, "right": b, "measured_units": round(g, 1), "font_units": font_gap,
                      "difference_units": round(font_gap - g, 1)})
    fitted = {k: int(round(v)) for k, v in sorted(value.items())}
    return bearings, fitted, table, kerning, len(fit)


def traced_glyphs(blocks, u):
    """One glyph for each letter of the sample. Returns (glyphs, occurrences, spacing)."""
    occ = occurrences_of(blocks, u)
    chosen = {}
    for ch in dict.fromkeys(o["char"] for o in occ):
        same = [o for o in occ if o["char"] == ch]
        if len(same) == 1:
            best, agreement = same[0], None
        elif len(same) == 2:                                     # no occurrence is closer to "the others"
            best, agreement = same[0], round(shape_dice(same[0]["shape"], same[1]["shape"]), 4)
        else:
            means = [float(np.mean([shape_dice(o["shape"], p["shape"]) for p in same if p is not o])) for o in same]
            best = same[int(np.argmax(means))]
            agreement = round(max(means), 4)
        chosen[ch] = (best, same, agreement)
    bearings, fitted, table, kerning, fitted_gaps = side_bearings(occ, list(chosen))
    glyphs = {}
    for ch, (best, same, agreement) in chosen.items():
        lsb, rsb = bearings[ch]
        note = {1: "", 2: " (the first of 2 occurrences)"}.get(
            len(same), " (the one of %d occurrences that is closest to the others)" % len(same))
        glyphs[ch] = {
            "shape": best["shape"], "lsb": lsb, "advance": lsb + int(round(best["shape"].bounds[2])) + rsb,
            "label": "evidenced-selected",
            "source": "%s, line %s (%s), shape %d%s" % (
                R["photo"]["file"], best["block"], blocks[best["block"]]["chars"], best["index"], note),
            "traced_from": {"block": best["block"], "index": best["index"]},
            "occurrences": len(same), "agreement_dice": agreement,
            "smoothing_move_units": round(best["moved"], 2),
        }
    return glyphs, occ, {"bearings": fitted, "gaps": table, "kerning": kerning, "fitted_gaps": fitted_gaps}


# --------------------------------------------------------------------------
# bounded extrapolation
# --------------------------------------------------------------------------

def arc(cx, cy, r, a0, a1, ry=None):
    """Points on an arc from angle a0 to a1 (degrees, counter-clockwise positive)."""
    ry = r if ry is None else ry
    n = max(6, int(abs(a1 - a0) / 5.0))
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def x_spans(shape, y):
    """x-spans where the horizontal line at ``y`` is inside ``shape``."""
    hit = shape.intersection(LineString([(-500, y), (2500, y)]))
    return sorted((p.bounds[0], p.bounds[2]) for p in getattr(hit, "geoms", [hit]) if not p.is_empty)


def extrapolated(ev):
    """Glyphs that the selected sample does not show.

    All are built with one stroke weight from measured values: stroke ``S``
    (letter i), flat letter height ``X`` (letter i), ring of the letter o,
    ascender height ``A`` (letter d) and descender depth ``D`` (letter z)."""
    ish, osh, nsh, dsh, zsh, hyp = (ev[c]["shape"] for c in "iondz-")
    S = ish.bounds[2] - ish.bounds[0]
    X = ish.bounds[3]
    A = dsh.bounds[3]
    D = -zsh.bounds[1]
    ob = osh.bounds
    c = (ob[1] + ob[3]) / 2.0                 # height of the ring centre
    ro = (ob[2] - ob[0] + ob[3] - ob[1]) / 4.0
    r = ro - S / 2.0                          # mid-stroke radius of the ring
    h = S / 2.0
    Sd = 1.08 * S                             # horizontal width of a diagonal stroke
    dot = 0.62 * S                            # radius of a point
    thin = 0.85 * S
    bar_y = (hyp.bounds[1] + hyp.bounds[3]) / 2.0
    bar_h = hyp.bounds[3] - hyp.bounds[1]
    soft = 0.18 * S                           # radius of the stroke-end corners, as in the traced glyphs
    out = {}

    def pen(*paths, w=None):
        w = S if w is None else w
        return unary_union([LineString(p).buffer(w / 2.0, cap_style="flat", join_style="round", quad_segs=16)
                            for p in paths])

    def para(x0, y0, x1, y1, wd=None):
        wd = Sd if wd is None else wd
        return Polygon([(x0, y0), (x0 + wd, y0), (x1 + wd, y1), (x1, y1)])

    def ring(cx, cy, rx, ry=None, w=None):
        ry = rx if ry is None else ry
        w = S if w is None else w
        unit = Point(0, 0).buffer(1.0, quad_segs=32)
        outer = affinity.translate(affinity.scale(unit, rx + w / 2.0, ry + w / 2.0, origin=(0, 0)), cx, cy)
        inner = affinity.translate(affinity.scale(unit, rx - w / 2.0, ry - w / 2.0, origin=(0, 0)), cx, cy)
        return outer.difference(inner)

    def disk(cx, cy, rad=None):
        return Point(cx, cy).buffer(dot if rad is None else rad, quad_segs=16)

    def add(ch, shape, label="extrapolated-constructed",
            note="one-weight construction from the measured stroke, letter height, ascender and descender",
            like=None, round_ends=True, sides=("common", "common")):
        shape = shape.buffer(0)
        if round_ends and label == "extrapolated-constructed":
            shape = shape.buffer(-soft, join_style="round", quad_segs=8).buffer(soft, join_style="round", quad_segs=8)
        out[ch] = {"shape": BF.left0(shape), "label": label, "source": note, "like": like, "sides": sides}

    # --- derived from traced glyphs
    hole = Polygon(dsh.interiors[0]).bounds if dsh.geom_type == "Polygon" and dsh.interiors else dsh.bounds
    dcx, dcy = (hole[0] + hole[2]) / 2.0, (hole[1] + hole[3]) / 2.0
    turned = affinity.rotate(dsh, 180, origin=(dcx, dcy))
    add("b", BF.mirror(dsh), "extrapolated-derived", "d mirrored", like=("d", "mirror"))
    add("p", turned, "extrapolated-derived", "d turned by 180 degrees about the centre of its ring",
        like=("d", "mirror"))
    add("q", BF.mirror(turned), "extrapolated-derived", "d turned upside down", like=("d", "same"))
    stem = x_spans(nsh, 0.5 * X)[0]
    add("h", unary_union([nsh, box(stem[0], 0.5 * X, stem[1], A).buffer(-soft).buffer(soft)]),
        "extrapolated-derived", "n with its left stem extended to the ascender height", like=("n", "same"))

    # --- constructed lower case
    xr = 2 * r + h                            # centre line of a stem at the right of a ring
    rg = 0.86 * r
    add("g", unary_union([ring(r + h, c, r),
                          pen([(xr, c), (xr, -D + h + rg)] + arc(xr - rg, -D + h + rg, rg, 0, -150))]),
        sides=("round", "straight"))
    xf, rf = 0.30 * X, 0.27 * X
    add("f", unary_union([pen([(xf, 0), (xf, A - h - rf)] + arc(xf + rf, A - h - rf, rf, 180, 65)),
                          box(xf - h - 0.9 * S, X - 0.8 * S, xf + h + 1.3 * S, X)]), sides=("common", "round"))
    xj, rj = 0.36 * X, 0.32 * X
    add("j", pen([(xj, X), (xj, -D + h + rj)] + arc(xj - rj, -D + h + rj, rj, 0, -140)), sides=("common", "straight"))
    add("k", unary_union([pen([(h, 0), (h, A)]), para(0.85 * S, 0.36 * X, 0.80 * X - Sd, X),
                          para(0.30 * X, 0.52 * X, 0.86 * X - Sd, 0)]), sides=("straight", "round"))
    wv = 0.94 * X
    v_left = para(0, X, wv / 2.0 - Sd / 2.0, 0)
    add("v", unary_union([v_left, para(wv - Sd, X, wv / 2.0 - Sd / 2.0, 0)]), sides=("round", "round"))
    ww = 1.50 * X
    add("w", unary_union([para(0, X, ww / 4.0 - Sd / 2.0, 0), para(ww / 2.0 - Sd / 2.0, X, ww / 4.0 - Sd / 2.0, 0),
                          para(ww / 2.0 - Sd / 2.0, X, 3 * ww / 4.0 - Sd / 2.0, 0),
                          para(ww - Sd, X, 3 * ww / 4.0 - Sd / 2.0, 0)]), sides=("round", "round"))
    wx = 0.90 * X
    add("x", unary_union([para(0, 0, wx - Sd, X), para(0, X, wx - Sd, 0)]), sides=("round", "round"))
    foot = wv / 2.0 - Sd / 2.0
    add("y", unary_union([v_left, para(wv - Sd, X, foot - (wv - Sd - foot) * D / X, -D)]), sides=("round", "round"))

    # --- constructed digits (height of the ascender)
    w0 = 0.62 * A
    add("0", ring(w0 / 2.0, A / 2.0, w0 / 2.0 - h, A / 2.0 - h))
    x1 = 0.30 * A
    add("1", unary_union([box(x1 - S, 0, x1, A), para(0, 0.72 * A, x1 - Sd, A)]))
    w2 = 0.58 * A
    r2 = w2 / 2.0 - h
    add("2", pen(arc(w2 / 2.0, A - h - r2, r2, 180, -40) + [(h, h), (w2, h)]))
    r3 = (A - S) / 4.0
    w3 = 2 * r3 + S
    add("3", pen(arc(w3 / 2.0, A - h - r3, r3, 150, -90) + arc(w3 / 2.0, h + r3, r3, 90, -150)))
    w4 = 0.66 * A
    xs = 0.62 * w4
    add("4", unary_union([box(xs, 0, xs + S, A), box(0, 0.26 * A, w4, 0.26 * A + S),
                          Polygon([(0, 0.26 * A + S), (Sd, 0.26 * A + S), (xs + S, A), (xs + S - Sd, A)])]))
    w5 = 0.56 * A
    r5 = w5 / 2.0 - h
    add("5", unary_union([box(0, A - S, w5, A),
                          pen([(h, A - h), (h, h + 1.5 * r5)] + arc(w5 / 2.0, h + r5, r5, 150, -150))]))
    w6 = 0.58 * A
    r6 = w6 / 2.0 - h
    six = unary_union([ring(w6 / 2.0, h + r6, r6),
                       pen([(h, h + r6), (h, A - h - r6)] + arc(h + r6, A - h - r6, r6, 180, 55))])
    add("6", six)
    w7 = 0.56 * A
    add("7", unary_union([box(0, A - S, w7, A), para(0.18 * w7, 0, w7 - Sd, A)]))
    r8 = (A - S) / 2.0 - r6
    eight = unary_union([ring(w6 / 2.0, h + r6, r6), ring(w6 / 2.0, A - h - r8, r8)])
    add("8", eight)
    add("9", affinity.rotate(six, 180, origin=(w6 / 2.0, A / 2.0)))

    # --- constructed punctuation and signs
    comma = unary_union([disk(dot, dot), Polygon([(0.9 * dot, 0.3 * dot), (2 * dot, dot),
                                                  (0.9 * dot, -1.6 * dot), (0.1 * dot, -1.6 * dot)])])
    add(".", disk(dot, dot), round_ends=False)
    add(",", comma, round_ends=False)
    add(":", unary_union([disk(dot, dot), disk(dot, X - dot)]), round_ends=False)
    add(";", unary_union([comma, disk(dot, X - dot)]), round_ends=False)
    add("!", unary_union([box(dot - h, 2.4 * dot + 0.06 * A, dot + h, A), disk(dot, dot)]))
    wq, rq = 0.56 * A, 0.24 * A
    add("?", unary_union([pen(arc(wq / 2.0, A - h - rq, rq, 170, -60) + [(wq / 2.0, 0.36 * A), (wq / 2.0, 0.27 * A)]),
                          disk(wq / 2.0, dot)]))
    tick = box(0, 0.70 * A, thin, A)
    add("'", tick)
    add("’", tick)
    add('"', unary_union([tick, affinity.translate(tick, 1.9 * thin, 0)]))
    add("`", para(0.6 * S, 0.80 * A, 0, A, thin))
    for ch, width in (("–", 0.62), ("—", 1.0)):
        add(ch, box(0, bar_y - bar_h / 2.0, width * X, bar_y + bar_h / 2.0), "extrapolated-derived",
            "a bar at the height and thickness of the traced hyphen")
    add("_", box(0, -0.22 * X, 0.9 * X, -0.22 * X + 0.8 * S))
    slash = para(0, -0.08 * A, 0.36 * A, 1.04 * A, 0.9 * Sd)
    add("/", slash)
    add("\\", BF.mirror(slash))
    add("|", box(0, -0.12 * A, 0.9 * S, 1.06 * A))
    paren = pen(arc(0.30 * A, 0.47 * A, 0.26 * A, 125, 235, ry=0.72 * A), w=0.9 * S)
    add("(", paren)
    add(")", BF.mirror(paren))
    bracket = unary_union([box(0, -0.12 * A, 0.9 * S, 1.06 * A), box(0, 1.06 * A - 0.8 * S, 0.30 * A, 1.06 * A),
                           box(0, -0.12 * A, 0.30 * A, -0.12 * A + 0.8 * S)])
    add("[", bracket)
    add("]", BF.mirror(bracket))
    brace = unary_union([affinity.translate(BF.left0(paren), 0.4 * S, 0),
                         box(0, 0.47 * A - 0.4 * S, 0.9 * S, 0.47 * A + 0.4 * S)])
    add("{", brace)
    add("}", BF.mirror(brace))
    plus = unary_union([box(0, X / 2.0 - 0.45 * S, 0.6 * X, X / 2.0 + 0.45 * S),
                        box(0.3 * X - 0.45 * S, X / 2.0 - 0.3 * X, 0.3 * X + 0.45 * S, X / 2.0 + 0.3 * X)])
    add("+", plus)
    add("=", unary_union([box(0, X / 2.0 + 0.55 * S, 0.6 * X, X / 2.0 + 1.45 * S),
                          box(0, X / 2.0 - 1.45 * S, 0.6 * X, X / 2.0 - 0.55 * S)]))
    less = pen([(0.5 * X, 0.86 * X), (0.5 * S, X / 2.0), (0.5 * X, 0.14 * X)], w=thin)
    add("<", less)
    add(">", BF.mirror(less))
    spoke = box(-0.15 * A, -0.4 * S, 0.15 * A, 0.4 * S)
    add("*", affinity.translate(unary_union([affinity.rotate(spoke, a, origin=(0, 0)) for a in (30, 90, 150)]),
                                0.15 * A, 0.80 * A))
    add("#", unary_union([box(0.14 * X, 0.05 * A, 0.14 * X + 0.8 * S, 0.95 * A),
                          box(0.50 * X, 0.05 * A, 0.50 * X + 0.8 * S, 0.95 * A),
                          box(0, 0.28 * A, 0.8 * X, 0.28 * A + 0.8 * S), box(0, 0.60 * A, 0.8 * X, 0.60 * A + 0.8 * S)]))
    small = 0.17 * A
    add("%", unary_union([ring(small, A - small - 0.4 * S, small - 0.4 * S, w=0.8 * S),
                          ring(0.80 * A - small, small + 0.4 * S, small - 0.4 * S, w=0.8 * S),
                          para(0.14 * A, 0, 0.66 * A - 0.8 * Sd, A, 0.8 * Sd)]))
    add("^", pen([(0, 0.62 * A), (0.26 * X, A - 0.4 * S), (0.52 * X, 0.62 * A)], w=thin))
    add("~", pen([(0, 0.42 * X), (0.15 * X, 0.54 * X), (0.31 * X, 0.48 * X), (0.47 * X, 0.42 * X), (0.62 * X, 0.54 * X)],
                 w=thin))
    r_s = (A - S) / 4.0
    w_s = 2 * r_s + S
    dollar = pen(arc(w_s / 2.0, A - h - r_s, r_s, 30, 270) + arc(w_s / 2.0, h + r_s, r_s, 90, -150))
    add("$", unary_union([dollar, box(w_s / 2.0 - 0.3 * S, -0.08 * A, w_s / 2.0 + 0.3 * S, 1.08 * A)]))
    add("&", unary_union([eight, para(0.30 * A, 0.34 * A, 0.72 * A - Sd, 0)]))
    wa = 1.5 * X
    inner = affinity.translate(affinity.scale(ev["a"]["shape"], 0.5, 0.5, origin=(0, 0)), wa / 2.0 - 0.26 * X, 0.12 * X)
    add("@", unary_union([ring(wa / 2.0, 0.25 * X + 0.12 * X, wa / 2.0 - 0.4 * S, 0.62 * X, w=0.8 * S), inner]),
        round_ends=False)

    # --- accented letters used in Italian
    for ch, base, kind in (("à", "a", "grave"), ("è", "e", "grave"), ("é", "e", "acute"),
                           ("ì", "i", "grave"), ("ò", "o", "grave"), ("ù", "u", "grave")):
        shape = ev[base]["shape"]
        m = (shape.bounds[0] + shape.bounds[2]) / 2.0
        top = shape.bounds[3]
        mark = Polygon([(m - 0.20 * X, top + 0.36 * X), (m - 0.20 * X + thin, top + 0.36 * X),
                        (m + 0.10 * X, top + 0.12 * X), (m + 0.10 * X - thin, top + 0.12 * X)])
        mark = mark.buffer(-soft).buffer(soft)
        if kind == "acute":
            mark = affinity.scale(mark, -1.0, 1.0, origin=(m, 0))
        merged = unary_union([shape, mark])
        out[ch] = {"shape": affinity.translate(merged, -shape.bounds[0], 0.0),
                   "label": "extrapolated-constructed",
                   "source": "%s with a constructed %s accent" % (base, kind), "base": base}
    return out, {"stroke": S, "flat_letter_height": X, "ascender": A, "descender": D,
                 "ring_outer_radius": ro, "ring_centre_height": c}


# --------------------------------------------------------------------------
# font
# --------------------------------------------------------------------------

def design(which="traced"):
    """Compute every glyph. Returns (records, info, blocks, occurrences); no file is written."""
    src = source(which)
    plane_h, rgb, plane = load_geometry(src)
    blocks, scale = extract_blocks(src, plane_h, rgb)
    ev, occ, spacing = traced_glyphs(blocks, scale["u"])
    fitted, gap_table = spacing["bearings"], spacing["gaps"]
    extra, measured = extrapolated(ev)
    records = dict(ev)
    for ch, g in extra.items():
        if g.get("base"):                         # accented letter: metrics of its base letter
            base = records[g["base"]]
            records[ch] = dict(g, lsb=base["lsb"], advance=base["advance"])
            continue
        width = int(round(g["shape"].bounds[2]))
        if g.get("like"):                         # derived glyph: side bearings of the traced glyph
            base, how = g["like"]
            left, right = base_bearings(records[base])
            if how == "mirror":
                left, right = right, left
        else:                                     # by the kind of each side; narrow signs get less
            narrow = 0.6 if ch in ".,:;!'’\"`|" else 1.0
            left, right = (int(round(fitted[kind] * narrow)) for kind in g["sides"])
        records[ch] = dict(g, lsb=left, advance=left + width + right)
    for g in records.values():
        g["contours"] = curve_contours(affinity.translate(g["shape"], g["lsb"], 0.0))
    # kerning: the measured pairs, and the same value before the other letters with a round left side
    kerning = []
    for (a, b), v in sorted(spacing["kerning"].items()):
        kerning.append({"left": a, "right": b, "value": v, "label": "evidenced-selected",
                        "source": "measured distance between these two letters in the selected sample"})
        for ch in sorted(records):
            follows = R["spacing"]["arm"][a]["also_before"]
            base = records[ch].get("base") or ch
            if ch != b and (ch in follows or (base in follows + b and base != ch)):
                kerning.append({"left": a, "right": ch, "value": v, "label": "extrapolated-derived",
                                "source": "the value of the measured pair %s %s, for a letter with the same round left side" % (a, b)})
    diffs = [abs(row["difference_units"]) for row in gap_table
             if row["left"] not in CL["marks"] and row["right"] not in CL["marks"]]
    info = {
        "side_bearings": fitted,
        "kerning_pairs": len(kerning),
        "measured_units": {k: round(v, 1) for k, v in measured.items()},
        "smoothing": {"model": "each run of an outline between two corners is smoothed along its length; corners keep a light smoothing; the unit is one rectified unit, about one photo pixel",
                      "largest_move_of_a_traced_outline_units": max(g["smoothing_move_units"] for g in ev.values())},
        "scale": {"letter_height_rectified_units": round(scale["letter_height_samples"] / K, 3),
                  "letters_measured": scale["letters_measured"],
                  "round_overshoot_rectified_units": round(scale["round_overshoot_samples"] / K, 3),
                  "font_units_per_rectified_unit": round(scale["u"] * K, 5)},
        "blocks": {k: {"text": b["chars"], "rotation_deg": round(b["rotation_deg"], 4),
                       "baseline_angle_to_printed_lines_deg": round(b["plane_angle_deg"], 3)}
                   for k, b in blocks.items()},
        "plane": {"tilt_deg": plane["tilt_deg"], "focal_px": plane["focal_px"],
                  "foreshortening_at_ref": plane["foreshortening_at_ref"],
                  "foreshortening_range_24_28mm": plane["foreshortening_range_24_28mm"]},
        "spacing": {"model": "gap = right bearing of the left letter + left bearing of the right letter; straight sides share one value, round sides share one value, other sides have their own value; least squares on %d gaps between letters; the right side of r has the bearing of t, and the measured distance r-o is a kerning pair" % spacing["fitted_gaps"],
                    "gaps": gap_table,
                    "letter_gap_rms_difference_units": round(float(np.sqrt(np.mean(np.square(diffs)))), 1),
                    "letter_gap_max_difference_units": round(float(max(diffs)), 1)},
    }
    return records, info, blocks, occ, scale, kerning


def base_bearings(record):
    width = int(round(record["shape"].bounds[2]))
    return record["lsb"], record["advance"] - record["lsb"] - width


def build(out_dir: Path):
    records, info, _, _, _, kerning = design()
    chars = sorted(records, key=ord)
    names = {ch: "uni%04X" % ord(ch) for ch in chars}
    glyph_order = [".notdef", "space"] + [names[ch] for ch in chars]
    notdef = BF.contours_of(box(70, 0, 530, 700).difference(box(130, 60, 470, 640)))
    glyf = {".notdef": BF.glyph_from(notdef), "space": BF.glyph_from([])}
    space = int(round(R["spacing"]["word_space_letter_heights"] * LETTER))
    metrics = {".notdef": (600, 70), "space": (space, 0)}
    cmap = {0x20: "space", 0xA0: "space"}
    for ch in chars:
        g = records[ch]
        glyf[names[ch]] = glyph_from_curves(g["contours"])
        xs = [pt[0] for c in g["contours"] for pt in c]
        metrics[names[ch]] = (int(g["advance"]), min(xs) if xs else 0)
        cmap[ord(ch)] = names[ch]
    aliases = {}
    for ch in chars:                      # no capitals in the source: reuse the lower case
        up = ch.upper()
        if up != ch and len(up) == 1 and ord(up) not in cmap:
            cmap[ord(up)] = names[ch]
            aliases[up] = ch
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=-DESCENT)
    evidenced = "".join(c for c in chars if records[c]["label"].startswith("evidenced"))
    fb.setupNameTable({
        "familyName": R["face"]["family"],
        "styleName": "Regular",
        "uniqueFontIdentifier": "%s %s; one selected source sample" % (R["face"]["family"], VERSION),
        "fullName": "%s Regular" % R["face"]["family"],
        "psName": "%s-Regular" % R["face"]["family"].replace(" ", ""),
        "version": "Version %s" % VERSION,
        "description": ("Lower case traced from one photographed lettering sample (pale panel lettering "
                        "ministero educazione nazionale). Traced glyphs: %s. All other glyphs are labelled "
                        "extrapolations; capital keys show the lower case. Study reconstruction, not a "
                        "certified restoration." % evidenced),
    })
    fb.setupOS2(sTypoAscender=ASCENT, sTypoDescender=-DESCENT, sTypoLineGap=0, usWinAscent=ASCENT,
                usWinDescent=DESCENT, sxHeight=int(round(info["measured_units"]["flat_letter_height"])),
                sCapHeight=int(round(info["measured_units"]["ascender"])), usWeightClass=300, fsType=0,
                achVendID="BLAB")
    fb.setupPost()
    fb.setupMaxp()
    if kerning:
        table = newTable("kern")
        table.version = 0
        sub = KernTable_format_0()
        sub.coverage = 1
        sub.kernTable = {(names[k["left"]], names[k["right"]]): int(k["value"]) for k in kerning}
        table.kernTables = [sub]
        fb.font["kern"] = table
    fb.font["head"].created = BF.FIXED_TIME
    fb.font["head"].modified = BF.FIXED_TIME
    fb.font.recalcTimestamp = False
    out_dir.mkdir(parents=True, exist_ok=True)
    ttf = out_dir / (STEM + ".ttf")
    woff2 = out_dir / (STEM + ".woff2")
    fb.save(str(ttf))
    web = TTFont(str(ttf), recalcTimestamp=False)
    web.flavor = "woff2"
    web.save(str(woff2))
    record = {
        "schema": "balilla-glyphs/2",
        "face": R["face"],
        "font_version": VERSION,
        "units_per_em": UPM,
        "letter_height": int(LETTER),
        "selected_sample": R["selected_sample"],
        "source_photo": {"file": R["photo"]["file"], "sha256": R["photo"]["sha256"]},
        "supplied_close_photo": {k: R["supplied_close_photo"][k] for k in ("file", "sha256", "relation", "published")},
        "labels": LABELS,
        "info": info,
        "kerning": kerning,
        "word_space": {"advance": space, "label": "extrapolated: the sample shows no space between words"},
        "capital_aliases": "capital letters map to the lower-case glyphs (the selected lettering has no capitals)",
        "contour_format": "each point is [x, y, on_curve]; off-curve points are TrueType quadratic control points",
        "glyphs": {ch: {"name": names[ch], "label": records[ch]["label"], "source": records[ch]["source"],
                        "advance": int(records[ch]["advance"]), "lsb": records[ch]["lsb"],
                        "occurrences": records[ch].get("occurrences"),
                        "agreement_dice": records[ch].get("agreement_dice"),
                        "traced_from": records[ch].get("traced_from"),
                        "smoothing_move_units": records[ch].get("smoothing_move_units"),
                        "contours": [[list(pt) for pt in c] for c in records[ch]["contours"]]}
                   for ch in chars},
    }
    return ttf, woff2, record, aliases


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=LAB / "fonts", help="output directory for the font files")
    args = ap.parse_args(argv)
    ttf, woff2, record, aliases = build(args.out)
    if args.out.resolve() == (LAB / "fonts").resolve():
        (LAB / "glyphs-panel.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    counts = {}
    for g in record["glyphs"].values():
        counts[g["label"]] = counts.get(g["label"], 0) + 1
    print("glyphs:", counts, "| capital aliases:", len(aliases))
    print("measured:", record["info"]["measured_units"], record["info"]["scale"])
    print("lines:", {k: (v["rotation_deg"], v["baseline_angle_to_printed_lines_deg"])
                     for k, v in record["info"]["blocks"].items()})
    print("spacing: rms %.1f max %.1f font units over the gaps between letters" % (
        record["info"]["spacing"]["letter_gap_rms_difference_units"],
        record["info"]["spacing"]["letter_gap_max_difference_units"]))
    print("ttf  ", BF.sha256(ttf), ttf)
    print("woff2", BF.sha256(woff2), woff2)


if __name__ == "__main__":
    main()
