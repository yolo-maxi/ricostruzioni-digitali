#!/usr/bin/env python3
"""Build Balilla-Reconstructed v0.2 from ONE selected source block.

Selected block: row 2 (EDUCAZIONE) of the capitals on the burgundy cover,
photo ``assets/HXwNV_7W8AAs8y6.jpg``. See ``focus.json``.

Steps (deterministic; the source photo is only read):

1. Rectify the photo plane from four printed lines (``pipeline/planes.py``).
2. Resample the row into a rectified frame, 8 samples per unit, and make
   an ink mask at the level midway between ground and full ink.
3. Trace each complete letter of the mask to a polygon outline.
4. Scale so that the measured cap height is 720 font units. The advance
   width of each letter is the measured distance to the next letter.
5. Add the other glyphs by bounded extrapolation and label every glyph.
6. Write TTF, WOFF2 and ``glyphs.json`` (outlines + labels).

Run:  python source/balilla-lab/build_font.py [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.timeTools import timestampFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
from pipeline import blocks as B  # noqa: E402
from pipeline import planes as P  # noqa: E402

FOCUS = json.loads((LAB / "focus.json").read_text())
K = int(FOCUS["supersample"])
UPM = 1000
CAP = 720
ASCENT = 960
DESCENT = 240
VERSION = "0.2"
FIXED_TIME = timestampFromString("Mon Nov 23 00:00:00 2026")

LABELS = {
    "evidenced-selected": "traced from the selected block (scored)",
    "evidenced-adjacent": "traced from an adjacent row of the same lettering (not scored)",
    "extrapolated-derived": "extrapolated: cut, mirrored or turned from a traced glyph",
    "extrapolated-constructed": "extrapolated: block construction from the measured stem, bar and width",
}


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# source: rectified rows and letter masks
# --------------------------------------------------------------------------

def load_geometry():
    """Return (plane homography, photo RGB, plane diagnostics)."""
    photo = FOCUS["photo"]
    if sha256(LAB / photo["file"]) != photo["sha256"]:
        raise SystemExit("source photo changed: %s" % photo["file"])
    photos = {photo["key"]: photo}
    solved = P.solve_plane(photos, FOCUS["plane"])
    rgb = P.load_photo(photos, photo["key"])
    return np.array(solved["homography_photo_to_plane"]), rgb, solved


def _extract(row, plane_h, rgb, rotation):
    frame = B.make_frame(plane_h, row["baseline"][0], row["baseline"][1], FOCUS["up"], FOCUS["down"],
                         pad=FOCUS["pad"], rotation_deg=rotation)
    img = B.extract(rgb, frame, k=K)
    ink, info = B.normalise_ink(img, FOCUS["polarity"], FOCUS["stroke"], k=K)
    mask = ink >= 0.5
    lab, comps = B.components(mask, FOCUS["min_letter_area"] * K * K)
    h, w = mask.shape
    comps.sort(key=lambda c: c["x0"])
    # complete letters do not touch the frame; cut letters touch its sides
    letters = [c for c in comps if c["x0"] > 1 and c["x1"] < w - 1 and c["y0"] > 1 and c["y1"] < h - 1]
    return {"frame": frame, "img": img, "ink": ink, "info": info, "mask": mask, "lab": lab,
            "comps": comps, "letters": letters}


def extract_row(key, plane_h, rgb):
    """Rectified row ``key``. All positions are in samples (K per unit),
    with sample ``j`` covering ``[j, j + 1)``."""
    row = FOCUS["rows"][key]
    r = _extract(row, plane_h, rgb, 0.0)
    xs = [(c["x0"] + c["x1"]) / 2.0 for c in r["letters"]]
    ys = [float(c["y1"]) for c in r["letters"]]
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i]) for i in range(len(xs)) for j in range(i + 1, len(xs))]
    rotation = -math.degrees(math.atan(float(np.median(slopes))))
    r = _extract(row, plane_h, rgb, rotation)       # baseline made level
    if len(r["letters"]) != len(row["complete"]):
        raise SystemExit("row %s: expected %d complete letters, found %d"
                         % (key, len(row["complete"]), len(r["letters"])))
    r["key"] = key
    r["chars"] = row["complete"]
    r["rotation_deg"] = rotation
    r["baseline"] = float(np.median([c["y1"] for c in r["letters"]]))
    r["capline"] = float(np.median([c["y0"] for c in r["letters"]]))
    r["cap"] = r["baseline"] - r["capline"]
    r["u"] = CAP / r["cap"]                         # font units per sample
    return r


def trace(lab, comp):
    """Polygon outline of one mask component, in sample coordinates."""
    pad = 2
    x0, y0, x1, y1 = comp["x0"], comp["y0"], comp["x1"], comp["y1"]
    sub = np.pad((lab[y0:y1, x0:x1] == comp["label"]).astype(np.uint8), pad)
    contours, hier = cv2.findContours(sub, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    polys = []
    for i, c in enumerate(contours):
        if hier[0][i][3] != -1 or len(c) < 4:
            continue
        holes = [contours[j][:, 0, :].astype(float) for j in range(len(contours))
                 if hier[0][j][3] == i and len(contours[j]) >= 4]
        polys.append(Polygon(c[:, 0, :].astype(float), holes).buffer(0))
    shape = unary_union(polys).buffer(0.5, join_style=2)     # sample centres -> sample edges
    return affinity.translate(shape, x0 - pad + 0.5, y0 - pad + 0.5)


def to_units(shape, x_left, baseline, u):
    """Samples -> font units; ink starts at x = 0, baseline at y = 0, y up."""
    g = affinity.affine_transform(shape, [u, 0.0, 0.0, -u, -x_left * u, baseline * u])
    return g.simplify(float(FOCUS["simplify_units"]), preserve_topology=True)


def next_left_edge(row, comp):
    """Left ink edge of the glyph that follows ``comp`` in its row."""
    for c in row["comps"]:
        if c["x0"] > comp["x0"] and (c["y1"] - c["y0"]) > 0.5 * row["cap"]:
            return c["x0"]
    raise SystemExit("no glyph after x=%d in row %s" % (comp["x0"], row["key"]))


# --------------------------------------------------------------------------
# glyph set
# --------------------------------------------------------------------------

def left0(shape):
    return affinity.translate(shape, -shape.bounds[0], 0.0)


def turn(shape):
    """Turn a glyph by 180 degrees inside the cap-height box."""
    return left0(affinity.rotate(shape, 180, origin=(0, CAP / 2.0)))


def mirror(shape):
    return left0(affinity.scale(shape, -1.0, 1.0, origin=(0, 0)))


def poly(*pts):
    return Polygon(pts)


def probe_spans(shape, x):
    """y-spans where the vertical line at ``x`` is inside ``shape``."""
    hit = shape.intersection(LineString([(x, -500), (x, 1500)]))
    parts = list(getattr(hit, "geoms", [hit]))
    return sorted((p.bounds[1], p.bounds[3]) for p in parts if not p.is_empty)


def traced_glyphs(plane_h, rgb):
    """Trace the evidenced letters. Returns (glyphs, rows, lsb)."""
    rows = {key: extract_row(key, plane_h, rgb) for key in FOCUS["rows"]}
    sel = rows[FOCUS["selected_row"]]
    gaps = [b["x0"] - a["x1"] for a, b in zip(sel["letters"][:-1], sel["letters"][1:])]
    lsb = int(round(float(np.median(gaps)) * sel["u"] / 2.0))
    glyphs = {}
    order = [FOCUS["selected_row"]] + [k for k in FOCUS["rows"] if k != FOCUS["selected_row"]]
    for key in order:
        row = rows[key]
        first = row["letters"][0]["x0"]
        pens = [int(round((c["x0"] - first) * row["u"])) for c in row["letters"]]
        last_next = int(round((next_left_edge(row, row["letters"][-1]) - first) * row["u"]))
        pens.append(last_next)
        for i, (ch, comp) in enumerate(zip(row["chars"], row["letters"])):
            if ch not in FOCUS["rows"][key]["use"] or ch in glyphs:
                continue
            selected = key == FOCUS["selected_row"]
            glyphs[ch] = {
                "shape": left0(to_units(trace(row["lab"], comp), comp["x0"], row["baseline"], row["u"])),
                "advance": pens[i + 1] - pens[i],
                "label": "evidenced-selected" if selected else "evidenced-adjacent",
                "source": "%s row %s (%s), letter %d" % (FOCUS["photo"]["file"], key, FOCUS["rows"][key]["text"], i),
            }
    return glyphs, rows, lsb


def extrapolated(ev):
    """Bounded extrapolation for the glyphs that the selected lettering does
    not show. Everything is built from three measured values: stem width
    ``S`` (letter I), bar height ``Bar`` (foot of L) and width ``W`` (O)."""
    h = float(CAP)
    I, O, E, A, L, Z, Sg = (ev[c]["shape"] for c in "IOEALZS")
    S = I.bounds[2] - I.bounds[0]
    W = O.bounds[2] - O.bounds[0]
    Bar = probe_spans(L, L.bounds[2] - 0.2 * (L.bounds[2] - L.bounds[0]))[0]
    Bar = Bar[1] - Bar[0]
    bar2 = min(Bar, 0.24 * h)            # bar height in two-storey glyphs
    Bm = 0.8 * bar2
    Sd = 1.1 * S                         # horizontal width of a diagonal stroke
    t = 0.7 * Bar                        # thin bar for signs
    d = 0.8 * S                          # point size
    out = {}

    def add(ch, shape, label="extrapolated-constructed",
            note="block construction from the measured stem, bar and width"):
        out[ch] = {"shape": left0(shape.buffer(0)), "label": label, "source": note}

    # --- derived from traced glyphs
    arms = probe_spans(E, E.bounds[0] + S + 0.25 * (E.bounds[2] - E.bounds[0] - S))
    y_cut = (arms[0][1] + arms[1][0]) / 2.0
    add("F", E.difference(box(E.bounds[0] + S + 1, -50, E.bounds[2] + 50, y_cut)),
        "extrapolated-derived", "E without its lowest arm")
    add("H", unary_union([I, affinity.translate(I, W - S, 0), box(0, (h - Bar) / 2, W, (h + Bar) / 2)]),
        "extrapolated-derived", "two stems of I and a bar")
    add("V", turn(A), "extrapolated-derived", "A turned by 180 degrees")
    add("0", affinity.scale(O, 0.86, 1.0, origin=(0, 0)), "extrapolated-derived", "O made narrower")
    add("1", I, "extrapolated-derived", "same shape as I")
    add("2", Z, "extrapolated-derived", "same shape as Z")
    add("3", mirror(E), "extrapolated-derived", "E mirrored")
    add("5", Sg, "extrapolated-derived", "same shape as S")
    add("7", turn(L), "extrapolated-derived", "L turned by 180 degrees")

    # --- constructed capitals
    eight = box(0, 0, W, h).difference(box(S, bar2, W - S, (h - Bm) / 2)).difference(
        box(S, (h + Bm) / 2, W - S, h - bar2))
    add("B", eight.difference(poly((W, h / 2 - 0.3 * S), (W - 0.3 * S, h / 2), (W, h / 2 + 0.3 * S))))
    add("G", unary_union([box(0, 0, S, h), box(0, h - Bar, W, h), box(0, 0, W, Bar),
                          box(W - S, 0, W, 0.5 * h), box(0.5 * W, 0.5 * h - 0.75 * Bar, W, 0.5 * h)]))
    wj = 0.8 * W
    add("J", unary_union([box(wj - S, 0, wj, h), box(0, 0, wj, Bar), box(0, 0, S, 0.36 * h)]))
    add("K", unary_union([box(0, 0, S, h),
                          poly((0.9 * S, 0.48 * h), (W - Sd, h), (W, h), (0.9 * S + Sd, 0.48 * h)),
                          poly((0.9 * S, 0.52 * h), (0.9 * S + Sd, 0.52 * h), (W, 0), (W - Sd, 0))]))
    wm = 1.2 * W
    m_shape = unary_union([box(0, 0, S, h), box(wm - S, 0, wm, h),
                           poly((S, h), (wm / 2, 0.42 * h), (wm - S, h), (wm - S, 0.60 * h),
                                (wm / 2, 0.06 * h), (S, 0.60 * h))])
    add("M", m_shape)
    add("W", turn(m_shape))
    add("P", unary_union([box(0, 0, S, h),
                          box(0, 0.40 * h, W, h).difference(box(S, 0.40 * h + bar2, W - S, h - bar2))]))
    add("Q", unary_union([O, box(0.60 * W, -0.17 * h, 0.60 * W + 0.8 * S, 0.5 * Bar)]))
    add("X", unary_union([poly((0, 0), (Sd, 0), (W, h), (W - Sd, h)),
                          poly((0, h), (Sd, h), (W, 0), (W - Sd, 0))]))
    add("Y", unary_union([poly((0, h), (Sd, h), (W / 2 + S / 2, 0.45 * h), (W / 2 - S / 2, 0.45 * h)),
                          poly((W, h), (W - Sd, h), (W / 2 - S / 2, 0.45 * h), (W / 2 + S / 2, 0.45 * h)),
                          box(W / 2 - S / 2, 0, W / 2 + S / 2, 0.5 * h)]))

    # --- constructed digits
    add("4", unary_union([box(W - S, 0, W, h), box(0, 0.28 * h, W, 0.28 * h + 0.85 * Bar),
                          box(0, 0.28 * h, S, h)]))
    six = unary_union([box(0, 0, S, h), box(0, h - bar2, W, h),
                       box(0, 0, W, 0.58 * h).difference(box(S, bar2, W - S, 0.58 * h - bar2))])
    add("6", six)
    add("8", eight)
    add("9", turn(six))

    # --- constructed punctuation and signs
    dot = box(0, 0, d, d)
    comma = unary_union([dot, poly((0.35 * d, 0), (d, 0), (0.4 * d, -0.9 * d), (0, -0.9 * d))])
    add(".", dot)
    add(",", comma)
    add(":", unary_union([dot, affinity.translate(dot, 0, 0.42 * h)]))
    add(";", unary_union([comma, affinity.translate(dot, 0, 0.42 * h)]))
    add("!", unary_union([box(0, d + 0.08 * h, S, h), box(0, 0, S, d)]))
    wq = 0.78 * W
    add("?", unary_union([box(0, h - bar2, wq, h), box(wq - S, 0.42 * h, wq, h),
                          box(0.3 * wq, 0.42 * h, wq, 0.42 * h + 0.9 * bar2),
                          box(0.3 * wq, d + 0.08 * h, 0.3 * wq + S, 0.42 * h + 0.9 * bar2),
                          box(0.3 * wq, 0, 0.3 * wq + S, d)]))
    tick = box(0, 0.68 * h, 0.7 * S, h)
    add("'", tick)
    add("’", tick)
    add('"', unary_union([tick, affinity.translate(tick, 1.1 * S, 0)]))
    add("`", poly((0, h), (0.7 * S, h), (1.3 * S, 0.78 * h), (0.6 * S, 0.78 * h)))
    for ch, width in (("-", 0.5), ("–", 0.8), ("—", 1.25)):
        add(ch, box(0, (h - 0.8 * Bar) / 2, width * W, (h + 0.8 * Bar) / 2))
    add("_", box(0, -0.2 * h, W, -0.2 * h + 0.55 * Bar))
    slash = poly((0, -0.06 * h), (0.8 * Sd, -0.06 * h), (0.62 * W, 1.04 * h), (0.62 * W - 0.8 * Sd, 1.04 * h))
    add("/", slash)
    add("\\", mirror(slash))
    add("|", box(0, -0.1 * h, 0.7 * S, 1.06 * h))
    paren = poly((0.85 * S, -0.1 * h), (1.55 * S, -0.1 * h), (0.75 * S, 0.2 * h), (0.75 * S, 0.76 * h),
                 (1.55 * S, 1.06 * h), (0.85 * S, 1.06 * h), (0, 0.76 * h), (0, 0.2 * h))
    add("(", paren)
    add(")", mirror(paren))
    bracket = unary_union([box(0, -0.1 * h, 0.75 * S, 1.06 * h),
                           box(0, 1.06 * h - 0.55 * Bar, 1.5 * S, 1.06 * h),
                           box(0, -0.1 * h, 1.5 * S, -0.1 * h + 0.55 * Bar)])
    add("[", bracket)
    add("]", mirror(bracket))
    brace = unary_union([affinity.translate(paren, 0.3 * S, 0),
                         box(0, 0.48 * h - 0.3 * Bar, 0.7 * S, 0.48 * h + 0.3 * Bar)])
    add("{", brace)
    add("}", mirror(brace))
    plus = unary_union([box(0, (h - t) / 2, 0.6 * W, (h + t) / 2),
                        box(0.3 * W - t / 2, h / 2 - 0.3 * W, 0.3 * W + t / 2, h / 2 + 0.3 * W)])
    add("+", plus)
    add("=", unary_union([box(0, 0.5 * h + 0.4 * t, 0.6 * W, 0.5 * h + 1.4 * t),
                          box(0, 0.5 * h - 1.4 * t, 0.6 * W, 0.5 * h - 0.4 * t)]))
    less = poly((0.55 * W, 0.86 * h), (0.55 * W, 0.86 * h - 1.3 * t), (1.5 * t, 0.5 * h),
                (0.55 * W, 0.14 * h + 1.3 * t), (0.55 * W, 0.14 * h), (0, 0.5 * h))
    add("<", less)
    add(">", mirror(less))
    small_plus = affinity.translate(affinity.scale(plus, 0.55, 0.55, origin=(0.3 * W, h / 2)), 0, 0.27 * h)
    add("*", unary_union([small_plus, affinity.rotate(small_plus, 45, origin=(0.3 * W, 0.77 * h))]))
    add("#", unary_union([box(0.12 * W, 0.05 * h, 0.12 * W + 0.8 * t, 0.95 * h),
                          box(0.42 * W, 0.05 * h, 0.42 * W + 0.8 * t, 0.95 * h),
                          box(0, 0.28 * h, 0.7 * W, 0.28 * h + 0.8 * t),
                          box(0, 0.60 * h, 0.7 * W, 0.60 * h + 0.8 * t)]))
    ring = box(0, 0, 0.32 * W, 0.32 * W).difference(box(0.6 * t, 0.6 * t, 0.32 * W - 0.6 * t, 0.32 * W - 0.6 * t))
    add("%", unary_union([affinity.translate(ring, 0, h - 0.32 * W), affinity.translate(ring, 0.58 * W, 0),
                          poly((0.12 * W, 0), (0.12 * W + 0.6 * Sd, 0), (0.78 * W, h), (0.78 * W - 0.6 * Sd, h))]))
    add("^", poly((0, 0.62 * h), (0.3 * W, h), (0.6 * W, 0.62 * h), (0.6 * W - 1.4 * t, 0.62 * h),
                  (0.3 * W, h - 1.6 * t), (1.4 * t, 0.62 * h)))
    add("~", unary_union([poly((0, 0.40 * h), (0.2 * W, 0.52 * h), (0.2 * W, 0.52 * h + t), (0, 0.40 * h + t)),
                          poly((0.2 * W, 0.52 * h), (0.4 * W, 0.42 * h), (0.4 * W, 0.42 * h + t), (0.2 * W, 0.52 * h + t)),
                          poly((0.4 * W, 0.42 * h), (0.6 * W, 0.54 * h), (0.6 * W, 0.54 * h + t), (0.4 * W, 0.42 * h + t))]))
    cx = (Sg.bounds[0] + Sg.bounds[2]) / 2.0
    add("$", unary_union([Sg, box(cx - 0.22 * S, -0.09 * h, cx + 0.22 * S, 1.09 * h)]))
    add("&", unary_union([affinity.scale(eight, 0.82, 1.0, origin=(0, 0)),
                          poly((0.45 * W, 0.30 * h), (0.45 * W + 0.8 * Sd, 0.30 * h), (W, 0), (W - 0.8 * Sd, 0))]))
    w2 = 1.2 * W
    frame = box(0, -0.08 * h, w2, h).difference(box(0.9 * t, -0.08 * h + 0.9 * t, w2 - 0.9 * t, h - 0.9 * t))
    inner = affinity.translate(affinity.scale(O, 0.5, 0.5, origin=(0, 0)), w2 / 2 - 0.25 * W, 0.21 * h)
    add("@", unary_union([frame, inner]))

    # --- accented capitals used in Italian
    known = dict(ev)
    known.update(out)
    for ch, base, kind in (("À", "A", "grave"), ("È", "E", "grave"), ("É", "E", "acute"),
                           ("Ì", "I", "grave"), ("Ò", "O", "grave"), ("Ù", "U", "grave")):
        shape = known[base]["shape"]
        c = (shape.bounds[0] + shape.bounds[2]) / 2.0
        mark = poly((c - 0.20 * W, 1.30 * h), (c - 0.20 * W + 0.75 * S, 1.30 * h),
                    (c + 0.14 * W, 1.08 * h), (c + 0.14 * W - 0.75 * S, 1.08 * h))
        if kind == "acute":
            mark = affinity.scale(mark, -1.0, 1.0, origin=(c, 0))
        merged = unary_union([shape, mark])
        out[ch] = {"shape": affinity.translate(merged, -shape.bounds[0], 0.0),
                   "label": "extrapolated-constructed",
                   "source": "%s with a constructed %s accent" % (base, kind),
                   "base": base}
    return out, {"stem": S, "bar": Bar, "width_O": W}


# --------------------------------------------------------------------------
# font
# --------------------------------------------------------------------------

def contours_of(shape):
    """Integer contours of a shape: outer rings clockwise, holes counter-clockwise."""
    if shape is None or shape.is_empty:
        return []
    polys = [shape] if shape.geom_type == "Polygon" else [p for p in shape.geoms if p.geom_type == "Polygon"]
    out = []
    for p in sorted(polys, key=lambda q: (round(q.bounds[0], 3), round(q.bounds[1], 3))):
        if p.area < 1:
            continue
        for ring, outer in [(p.exterior, True)] + [(r, False) for r in p.interiors]:
            pts = [(int(round(x)), int(round(y))) for x, y in list(ring.coords)[:-1]]
            pts = [pt for i, pt in enumerate(pts) if pt != pts[i - 1]]
            if len(pts) < 3:
                continue
            area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                       for i in range(len(pts)))
            if (area < 0) != outer:
                pts = pts[::-1]
            start = min(range(len(pts)), key=lambda i: (pts[i][1], pts[i][0]))
            out.append(pts[start:] + pts[:start])
    return out


def glyph_from(contours):
    pen = TTGlyphPen(None)
    for pts in contours:
        pen.moveTo(pts[0])
        for pt in pts[1:]:
            pen.lineTo(pt)
        pen.closePath()
    return pen.glyph()


def design():
    """Compute every glyph. Returns (records, info); no file is written."""
    plane_h, rgb, plane = load_geometry()
    ev, rows, lsb = traced_glyphs(plane_h, rgb)
    extra, measured = extrapolated(ev)
    records = {}
    for ch, g in ev.items():
        records[ch] = dict(g, lsb=lsb)
    for ch, g in extra.items():
        shape = g["shape"]
        if g.get("base"):                 # accented capital: metrics of its base letter
            base = records[g["base"]]
            records[ch] = dict(g, lsb=base["lsb"], advance=base["advance"])
            continue
        narrow = ch in ".,:;!'’\"`|"
        side = int(round(lsb * (0.6 if narrow else 1.0)))
        records[ch] = dict(g, lsb=side, advance=int(round(shape.bounds[2])) + 2 * side)
    for ch, g in records.items():
        g["contours"] = contours_of(affinity.translate(g["shape"], g["lsb"], 0.0))
    sel = rows[FOCUS["selected_row"]]
    info = {
        "lsb": lsb,
        "measured_units": {k: round(v, 1) for k, v in measured.items()},
        "rows": {k: {"rotation_deg": round(r["rotation_deg"], 4), "cap_height_samples": r["cap"],
                     "units_per_sample": round(r["u"], 6)} for k, r in rows.items()},
        "plane": {"tilt_deg": plane["tilt_deg"], "focal_px": plane["focal_px"],
                  "foreshortening_at_ref": plane["foreshortening_at_ref"]},
    }
    return records, info, sel


def build(out_dir: Path):
    records, info, _ = design()
    chars = sorted(records, key=ord)
    names = {ch: "uni%04X" % ord(ch) for ch in chars}
    glyph_order = [".notdef", "space"] + [names[ch] for ch in chars]
    notdef = contours_of(box(70, 0, 530, CAP).difference(box(130, 60, 470, CAP - 60)))
    glyf = {".notdef": glyph_from(notdef), "space": glyph_from([])}
    space = int(round(0.45 * records["O"]["advance"]))
    metrics = {".notdef": (600, 70), "space": (space, 0)}
    cmap = {0x20: "space", 0xA0: "space"}
    for ch in chars:
        g = records[ch]
        glyf[names[ch]] = glyph_from(g["contours"])
        xs = [x for c in g["contours"] for x, _ in c]
        metrics[names[ch]] = (int(g["advance"]), min(xs) if xs else 0)
        cmap[ord(ch)] = names[ch]
    aliases = {}
    for ch in chars:                      # no lower case in the source: reuse the capitals
        low = ch.lower()
        if low != ch and len(low) == 1 and ord(low) not in cmap:
            cmap[ord(low)] = names[ch]
            aliases[low] = ch
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=-DESCENT)
    evidenced = "".join(c for c in chars if records[c]["label"].startswith("evidenced"))
    fb.setupNameTable({
        "familyName": "Balilla Reconstructed",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Balilla Reconstructed %s; one selected source block" % VERSION,
        "fullName": "Balilla Reconstructed Regular",
        "psName": "BalillaReconstructed-Regular",
        "version": "Version %s" % VERSION,
        "description": ("Capitals traced from one photographed lettering block (cover capitals, row EDUCAZIONE). "
                        "Traced glyphs: %s. All other glyphs are labelled extrapolations; lower case keys show "
                        "the capitals. Study reconstruction, not a certified restoration." % evidenced),
    })
    fb.setupOS2(sTypoAscender=ASCENT, sTypoDescender=-DESCENT, sTypoLineGap=0, usWinAscent=ASCENT,
                usWinDescent=DESCENT, sxHeight=CAP, sCapHeight=CAP, usWeightClass=900, fsType=0,
                achVendID="BLAB")
    fb.setupPost()
    fb.setupMaxp()
    fb.font["head"].created = FIXED_TIME
    fb.font["head"].modified = FIXED_TIME
    fb.font.recalcTimestamp = False
    out_dir.mkdir(parents=True, exist_ok=True)
    ttf = out_dir / "Balilla-Reconstructed.ttf"
    woff2 = out_dir / "Balilla-Reconstructed.woff2"
    fb.save(str(ttf))
    web = TTFont(str(ttf), recalcTimestamp=False)
    web.flavor = "woff2"
    web.save(str(woff2))
    record = {
        "schema": "balilla-glyphs/1",
        "font_version": VERSION,
        "units_per_em": UPM,
        "cap_height": CAP,
        "selected_block": FOCUS["selected_block"],
        "labels": LABELS,
        "info": info,
        "lowercase_aliases": "lower case letters map to the capital glyphs (the source shows no lower case)",
        "glyphs": {ch: {"name": names[ch], "label": records[ch]["label"], "source": records[ch]["source"],
                        "advance": int(records[ch]["advance"]), "lsb": records[ch]["lsb"],
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
        (LAB / "glyphs.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    counts = {}
    for g in record["glyphs"].values():
        counts[g["label"]] = counts.get(g["label"], 0) + 1
    print("glyphs:", counts, "| lower-case aliases:", len(aliases))
    print("ttf  ", sha256(ttf), ttf)
    print("woff2", sha256(woff2), woff2)


if __name__ == "__main__":
    main()
