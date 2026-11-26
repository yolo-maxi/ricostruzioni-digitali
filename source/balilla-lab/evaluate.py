#!/usr/bin/env python3
"""One deterministic pixel comparison: selected source block vs. the font.

Declared normalisation and metric:

* Source mask: the rectified selected row (see ``build_font.py``), ink map
  thresholded midway between ground and full ink, cropped to the complete
  letters "DUCAZION" plus a margin. 8 samples per rectified unit.
* Rendering: the built TTF, rasterised by FreeType without hinting at the
  matched scale; glyphs placed by the advance widths in the font file.
* Alignment: ONE uniform scale and ONE translation for the whole line.
  The search covers scale +/-1 % and shift +/-1.5 units and takes the
  best Dice. No rotation, no shear, no per-glyph adjustment.
* Metric: Dice = 2|S and R| / (|S| + |R|) on the two masks; IoU and the
  boundary distances are reported too. Gate: Dice >= 0.95.

The glyphs were traced from this same block, so the score measures how
well the font file reproduces the photographed lettering. It is not an
independent test of the letterforms.

Run:  python source/balilla-lab/evaluate.py     (exit code 1 if the gate fails)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import freetype
import numpy as np
from PIL import Image
from scipy import ndimage

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
import build_font as BF  # noqa: E402

OUT = LAB / "evaluation"
FONT = LAB / "fonts" / "Balilla-Reconstructed.ttf"
K = BF.K


def render_text(font_path, text, samples_per_unit, width, height, pen_x, baseline_y):
    """Coverage image (0..1) of ``text`` set with the font's own advances."""
    face = freetype.Face(str(font_path))
    face.set_char_size(int(round(samples_per_unit * face.units_per_EM * 64)))
    flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP
    canvas = np.zeros((height, width), dtype=np.float32)
    pen = float(pen_x)
    for ch in text:
        face.load_char(ch, flags)
        g = face.glyph
        bm = g.bitmap
        if bm.width and bm.rows:
            arr = np.array(bm.buffer, dtype=np.float32).reshape(bm.rows, bm.pitch)[:, :bm.width] / 255.0
            x = int(np.floor(pen + 0.5)) + g.bitmap_left
            y = int(np.floor(baseline_y + 0.5)) - g.bitmap_top
            xa, ya = max(x, 0), max(y, 0)
            xb, yb = min(x + bm.width, width), min(y + bm.rows, height)
            if xb > xa and yb > ya:
                canvas[ya:yb, xa:xb] = np.maximum(canvas[ya:yb, xa:xb], arr[ya - y:yb - y, xa - x:xb - x])
        pen += g.linearHoriAdvance / 65536.0
    return canvas


def dice_iou(a, b):
    inter = float(np.logical_and(a, b).sum())
    total = float(a.sum() + b.sum())
    union = total - inter
    return 2.0 * inter / total, inter / union


def best_shift(src, ren, limit):
    """Shift (dy, dx) of ``ren`` that gives the largest overlap with ``src``."""
    fa = np.fft.rfft2(src.astype(np.float32))
    fb = np.fft.rfft2(ren.astype(np.float32))
    corr = np.fft.irfft2(fa * np.conj(fb), s=src.shape)
    best = (-1.0, 0, 0)
    for dy in range(-limit, limit + 1):
        for dx in range(-limit, limit + 1):
            v = corr[dy % src.shape[0], dx % src.shape[1]]
            if v > best[0]:
                best = (float(v), dy, dx)
    return best


def boundary(mask):
    return mask & ~ndimage.binary_erosion(mask)


def boundary_distances(a, b):
    """Distances (samples) from the boundary of ``a`` to the boundary of ``b``."""
    dist = ndimage.distance_transform_edt(~boundary(b))
    return dist[boundary(a)]


def evaluate():
    plane_h, rgb, _ = BF.load_geometry()
    row = BF.extract_row(BF.FOCUS["selected_row"], plane_h, rgb)
    text = BF.FOCUS["selected_block"]["scored_text"]
    assert text == row["chars"], (text, row["chars"])
    record = json.loads((LAB / "glyphs.json").read_text())
    lsb = record["glyphs"][text[0]]["lsb"]
    first, last = row["letters"][0], row["letters"][-1]
    gaps = [b["x0"] - a["x1"] for a, b in zip(row["letters"][:-1], row["letters"][1:])]
    margin = int(np.median(gaps) // 2)
    x0, x1 = first["x0"] - margin, last["x1"] + margin
    mv = 3 * K
    y0, y1 = int(row["capline"]) - mv, int(round(row["baseline"])) + mv
    src = row["mask"][y0:y1, x0:x1]
    h, w = src.shape
    s0 = 1.0 / row["u"]                                   # samples per font unit
    pen0 = (first["x0"] - x0) - lsb * s0
    base0 = float(np.floor(row["baseline"] - y0 + 0.5))   # whole sample row
    limit = int(1.5 * K)

    nominal = render_text(FONT, text, s0, w, h, pen0, base0) >= 0.5
    nominal_dice, nominal_iou = dice_iou(src, nominal)

    best = None
    for step in range(-10, 11):
        scale = 1.0 + step / 1000.0
        # scale about the centre of the line so that the shift stays small
        cx = w / 2.0
        pen = cx + (pen0 - cx) * scale
        base = base0
        ren = render_text(FONT, text, s0 * scale, w, h, pen, base) >= 0.5
        overlap, dy, dx = best_shift(src, ren, limit)
        score = 2.0 * overlap / float(src.sum() + ren.sum())
        if best is None or score > best[0]:
            best = (score, scale, pen + dx, base + dy, dx, dy)
    _, scale, pen, base, dx, dy = best
    coverage = render_text(FONT, text, s0 * scale, w, h, pen, base)
    ren = coverage >= 0.5
    dice, iou = dice_iou(src, ren)
    d_rs = boundary_distances(ren, src) / K
    d_sr = boundary_distances(src, ren) / K
    both = np.concatenate([d_rs, d_sr])
    # size of one rectified unit in photo pixels at this block
    c = row["frame"].to_photo([[row["frame"].width / 2.0, row["frame"].baseline_y],
                               [row["frame"].width / 2.0 + 1.0, row["frame"].baseline_y]])
    unit_px = float(np.hypot(*(c[1] - c[0])))
    gate = BF.FOCUS["gate"]
    report = {
        "schema": "balilla-focus-eval/1",
        "selected_block": BF.FOCUS["selected_block"],
        "source_photo": {"file": BF.FOCUS["photo"]["file"], "sha256": BF.FOCUS["photo"]["sha256"]},
        "font": {"file": "fonts/Balilla-Reconstructed.ttf", "sha256": BF.sha256(FONT),
                 "woff2_sha256": BF.sha256(FONT.with_suffix(".woff2"))},
        "scored_text": text,
        "normalisation": {
            "samples_per_rectified_unit": K,
            "rectified_unit_in_photo_px": round(unit_px, 4),
            "mask_threshold": "ink map >= 0.5 (midway between ground and full ink)",
            "render": "FreeType, no hinting, coverage >= 0.5, font advances, glyph origins quantized to 1/%d unit" % K,
            "region_samples": [int(w), int(h)],
            "cap_height_units": round(row["cap"] / K, 3),
        },
        "alignment": {
            "model": "one uniform scale and one translation for the whole line",
            "search": "scale 0.990..1.010 step 0.001; shift within +/-1.5 rectified units",
            "scale": round(scale, 4),
            "shift_units": [round(dx / K, 3), round(dy / K, 3)],
        },
        "dice": round(dice, 5),
        "iou": round(iou, 5),
        "pixels": {"source": int(src.sum()), "render": int(ren.sum()),
                   "both": int(np.logical_and(src, ren).sum()),
                   "source_only": int(np.logical_and(src, ~ren).sum()),
                   "render_only": int(np.logical_and(~src, ren).sum())},
        "boundary_distance_units": {"mean": round(float(both.mean()), 4),
                                    "p95": round(float(np.percentile(both, 95)), 4),
                                    "max": round(float(both.max()), 4)},
        "without_search": {"dice": round(nominal_dice, 5), "iou": round(nominal_iou, 5),
                           "note": "scale and position taken from the build, no search"},
        "gate": {"metric": gate["metric"], "threshold": gate["threshold"],
                 "value": round(dice, 5), "pass": bool(dice >= gate["threshold"])},
        "claim_100_percent": bool(dice == 1.0),
        "scope_note": ("The glyphs were traced from this block. The score shows how well the font file "
                       "reproduces the photographed lettering after one scale and one shift. "
                       "It is not an independent test and it does not cover the extrapolated glyphs."),
    }

    OUT.mkdir(exist_ok=True)
    half = (w // 2, h // 2)
    crop = np.clip(row["img"][y0:y1, x0:x1], 0, 255).astype(np.uint8)
    Image.fromarray(crop).resize(half, Image.LANCZOS).save(OUT / "selected-source.png", optimize=True)
    ground = np.array(row["info"]["ground_rgb"])
    ink = np.array(row["info"]["ink_rgb"])
    recon = ground[None, None, :] + coverage[..., None] * (ink - ground)[None, None, :]
    Image.fromarray(np.clip(recon, 0, 255).astype(np.uint8)).resize(half, Image.LANCZOS).save(
        OUT / "selected-reconstruction.png", optimize=True)
    over = np.full((h, w, 3), 255, dtype=np.uint8)
    over[src & ren] = (70, 70, 70)
    over[src & ~ren] = (220, 40, 40)
    over[~src & ren] = (40, 90, 220)
    Image.fromarray(over).resize(half, Image.LANCZOS).save(OUT / "selected-overlay.png", optimize=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    return report


def gate_passes(report) -> bool:
    """The release gate: the measured value must reach the declared threshold."""
    g = report["gate"]
    return bool(report[g["metric"]] >= g["threshold"])


def main():
    report = evaluate()
    print("block   %s  text %s" % (report["selected_block"]["id"], report["scored_text"]))
    print("dice    %.4f   iou %.4f   (without search: dice %.4f)" % (
        report["dice"], report["iou"], report["without_search"]["dice"]))
    print("align   scale %.4f  shift %s units" % (report["alignment"]["scale"], report["alignment"]["shift_units"]))
    print("edge    mean %.3f  p95 %.3f  max %.3f rectified units" % (
        report["boundary_distance_units"]["mean"], report["boundary_distance_units"]["p95"],
        report["boundary_distance_units"]["max"]))
    ok = gate_passes(report)
    print("gate    dice >= %.2f : %s" % (report["gate"]["threshold"], "PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
