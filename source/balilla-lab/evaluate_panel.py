#!/usr/bin/env python3
"""Deterministic pixel comparison for the panel face.

Selected sample: the pale panel lettering "mini- stero educa- zione nazio-
nale" of the obelisk cover: six lines, 31 shapes, 15 different glyphs.

Declared normalisation and metric (the same for all 31 shapes):

* Source mask: each rectified line (see ``build_panel.py``), ink map
  thresholded midway between ground and full ink, 8 samples per rectified
  unit. Each line is level on its own measured baseline.
* Rendering: the built TTF, rasterised by FreeType without hinting.
* Placement: the lettering is spaced by hand, so each glyph starts at the
  measured left ink edge of its shape and sits on the measured baseline of
  its line. The comparison scores letter shapes and not spacing. The
  spacing is compared in a separate table (measured gap, gap in the font).
* Alignment: ONE uniform scale and ONE shift for the WHOLE sample (all six
  lines together). The search covers scale +/-1 % and shift +/-1.5 units
  and takes the best Dice of the whole sample. No rotation, no shear, no
  adjustment of the size, position or shape of a single glyph.
* Metric: Dice = 2|S and R| / (|S| + |R|) for each shape; IoU and the
  boundary distances are reported too. The aggregate uses the 31 observed
  shapes only. Gate: Dice >= 0.95 for EACH traced glyph, compared with the
  shape that it was traced from.

The lettering is drawn by hand. The font holds one observed shape for each
letter, so the other occurrences of a repeated letter score lower. Those
scores are reported and are part of the aggregate.

The same comparison is repeated with the close photo that the owner
supplied (the same exposure at 5/6 of the size). That result is reported
as a cross-check. The gate uses the traced copy.

Run:  python source/balilla-lab/evaluate_panel.py   (exit code 1 if the gate fails)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import freetype
import numpy as np
from PIL import Image

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
import build_font as BF  # noqa: E402
import build_panel as BP  # noqa: E402
import evaluate as EV  # noqa: E402
from pipeline import planes as P  # noqa: E402

OUT = LAB / "evaluation"
FONT = LAB / "fonts" / (BP.STEM + ".ttf")
K = BP.K
LIMIT = int(1.5 * K)                      # shift search: +/-1.5 rectified units
SCALES = [1.0 + step / 1000.0 for step in range(-10, 11)]
PROOF_GLYPHS = "stz"                      # per-glyph source crop, rendering and overlay
SHOW = 3                                  # the line images are reduced by this factor
SHOW_GLYPH = 2                            # the per-glyph images are reduced by this factor
COLOURS = {"both": (70, 70, 70), "source_only": (220, 40, 40), "render_only": (40, 90, 220)}


def glyph_bitmap(face, ch, samples_per_unit):
    """Coverage (0..1) of one glyph and the position of its bitmap relative to the glyph origin."""
    face.set_char_size(int(round(samples_per_unit * face.units_per_EM * 64)))
    face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP)
    g = face.glyph
    bm = g.bitmap
    arr = np.array(bm.buffer, dtype=np.float32).reshape(bm.rows, bm.pitch)[:, :bm.width] / 255.0
    return arr, g.bitmap_left, g.bitmap_top


def place(canvas, arr, x, y):
    """Draw a coverage bitmap with its top-left sample at (x, y); keep the larger value."""
    h, w = canvas.shape
    xa, ya = max(x, 0), max(y, 0)
    xb, yb = min(x + arr.shape[1], w), min(y + arr.shape[0], h)
    if xb > xa and yb > ya:
        canvas[ya:yb, xa:xb] = np.maximum(canvas[ya:yb, xa:xb], arr[ya - y:yb - y, xa - x:xb - x])


def render_line(face, blk, lsb, spu, shift=(0, 0)):
    """Coverage image of one line and the coverage of each of its glyphs.

    Each glyph starts at the measured left ink edge of its shape and sits on
    the measured baseline of the line. ``shift`` is the one shift (dx, dy)
    of the whole sample, in samples."""
    h, w = blk["mask"].shape
    canvas = np.zeros((h, w), dtype=np.float32)
    parts = []
    base = int(np.floor(blk["baseline"] + 0.5)) + shift[1]
    for ch, comp in zip(blk["chars"], blk["letters"]):
        arr, left, top = glyph_bitmap(face, ch, spu)
        pen = int(np.floor(comp["x0"] - lsb[ch] * spu + 0.5)) + shift[0]
        x, y = pen + left, base - top
        place(canvas, arr, x, y)
        parts.append((arr, x, y))
    return canvas, parts


def overlap_table(src, ren):
    """Overlap of ``src`` with ``ren`` moved by (dy, dx), for every shift within the limit."""
    fa = np.fft.rfft2(src.astype(np.float32))
    fb = np.fft.rfft2(ren.astype(np.float32))
    corr = np.fft.irfft2(fa * np.conj(fb), s=src.shape)
    idx = np.arange(-LIMIT, LIMIT + 1)
    return corr[np.ix_(idx % src.shape[0], idx % src.shape[1])]


def compare(which, record, scales=None):
    """Compare the font file with one copy of the photograph.

    ``scales`` is the list of scale factors of the search (default: the
    declared search, 0.990 to 1.010)."""
    src = BP.source(which)
    plane_h, rgb, plane = BP.load_geometry(src)
    blocks, scale = BP.extract_blocks(src, plane_h, rgb)
    lsb = {ch: g["lsb"] for ch, g in record["glyphs"].items()}
    traced = {ch: (g["traced_from"]["block"], g["traced_from"]["index"])
              for ch, g in record["glyphs"].items() if g.get("traced_from")}
    face = freetype.Face(str(FONT))
    s0 = 1.0 / scale["u"]                                 # samples per font unit
    masks = {key: np.isin(blk["lab"], [c["label"] for c in blk["letters"]]) for key, blk in blocks.items()}
    total_src = sum(int(m.sum()) for m in masks.values())

    def score(factor):
        table, total_ren = 0.0, 0
        for key, blk in blocks.items():
            ren = render_line(face, blk, lsb, s0 * factor)[0] >= 0.5
            table = table + overlap_table(masks[key], ren)
            total_ren += int(ren.sum())
        dy, dx = np.unravel_index(int(np.argmax(table)), table.shape)
        return 2.0 * float(table[dy, dx]) / (total_src + total_ren), int(dx) - LIMIT, int(dy) - LIMIT

    nominal = score(1.0)
    best = max(((score(f), f) for f in (scales or SCALES)), key=lambda item: (round(item[0][0], 9), -abs(item[1] - 1.0)))
    (_, dx, dy), factor = best
    occurrences, lines = [], {}
    for key, blk in blocks.items():
        coverage, parts = render_line(face, blk, lsb, s0 * factor, (dx, dy))
        lines[key] = {"blk": blk, "coverage": coverage, "mask": masks[key]}
        for i, (ch, comp, (arr, x, y)) in enumerate(zip(blk["chars"], blk["letters"], parts)):
            m = 2 * K
            x0 = max(0, min(comp["x0"], x) - m)
            y0 = max(0, min(comp["y0"], y) - m)
            x1 = min(coverage.shape[1], max(comp["x1"], x + arr.shape[1]) + m)
            y1 = min(coverage.shape[0], max(comp["y1"], y + arr.shape[0]) + m)
            source_mask = blk["lab"][y0:y1, x0:x1] == comp["label"]
            own = np.zeros(source_mask.shape, dtype=np.float32)
            place(own, arr, x - x0, y - y0)
            render_mask = own >= 0.5
            dice, iou = EV.dice_iou(source_mask, render_mask)
            both = np.concatenate([EV.boundary_distances(render_mask, source_mask),
                                   EV.boundary_distances(source_mask, render_mask)]) / K
            occurrences.append({
                "block": key, "index": i, "char": ch, "line_text": blk["chars"],
                "traced_from_this_shape": traced.get(ch) == (key, i),
                "dice": round(dice, 5), "iou": round(iou, 5),
                "pixels": {"source": int(source_mask.sum()), "render": int(render_mask.sum()),
                           "both": int(np.logical_and(source_mask, render_mask).sum()),
                           "source_only": int(np.logical_and(source_mask, ~render_mask).sum()),
                           "render_only": int(np.logical_and(~source_mask, render_mask).sum())},
                "boundary_distance_units": {"mean": round(float(both.mean()), 4),
                                            "p95": round(float(np.percentile(both, 95)), 4),
                                            "max": round(float(both.max()), 4)},
                "_crop": (x0, y0, x1, y1), "_coverage": own, "_source": source_mask,
            })
    fr = blocks["L3"]["frame"]
    c = fr.to_photo([[fr.width / 2.0, fr.baseline_y], [fr.width / 2.0 + 1.0, fr.baseline_y]])
    return {
        "which": which, "photo": src["photo"], "plane": plane, "scale": scale, "lines": lines,
        "occurrences": occurrences, "alignment": {"scale": round(factor, 4), "shift_units": [round(dx / K, 3), round(dy / K, 3)]},
        "without_search": round(nominal[0], 5), "unit_px": float(np.hypot(*(c[1] - c[0]))),
    }


def total(occurrences):
    keys = ("source", "render", "both", "source_only", "render_only")
    px = {k: sum(o["pixels"][k] for o in occurrences) for k in keys}
    return {"shapes": len(occurrences),
            "dice": round(2.0 * px["both"] / (px["source"] + px["render"]), 5),
            "iou": round(px["both"] / (px["both"] + px["source_only"] + px["render_only"]), 5),
            "pixels": px}


def per_glyph(occurrences):
    out = {}
    for ch in dict.fromkeys(o["char"] for o in occurrences):
        same = [o for o in occurrences if o["char"] == ch]
        own = [o for o in same if o["traced_from_this_shape"]]
        out[ch] = {"occurrences": len(same),
                   "traced_shape": {"block": own[0]["block"], "index": own[0]["index"], "dice": own[0]["dice"],
                                    "iou": own[0]["iou"]},
                   "all_shapes": [{"block": o["block"], "index": o["index"], "dice": o["dice"], "iou": o["iou"]}
                                  for o in same],
                   "mean_dice": round(float(np.mean([o["dice"] for o in same])), 5),
                   "lowest_dice": min(o["dice"] for o in same)}
    return out


def public(occurrence):
    return {k: v for k, v in occurrence.items() if not k.startswith("_")}


def overlay(source_mask, render_mask):
    over = np.full(source_mask.shape + (3,), 255, dtype=np.uint8)
    over[source_mask & render_mask] = COLOURS["both"]
    over[source_mask & ~render_mask] = COLOURS["source_only"]
    over[~source_mask & render_mask] = COLOURS["render_only"]
    return over


def stack(images, gap, fill):
    """Images one above the other, left-aligned, with a gap."""
    width = max(im.shape[1] for im in images)
    rows = []
    for im in images:
        row = np.full((im.shape[0], width, 3), fill, dtype=np.uint8)
        row[:, :im.shape[1]] = im
        rows += [row, np.full((gap, width, 3), fill, dtype=np.uint8)]
    return np.vstack(rows[:-1])


def side_by_side(images, gap, fill):
    height = max(im.shape[0] for im in images)
    cols = []
    for im in images:
        col = np.full((height, im.shape[1], 3), fill, dtype=np.uint8)
        col[height - im.shape[0]:] = im
        cols += [col, np.full((height, gap, 3), fill, dtype=np.uint8)]
    return np.hstack(cols[:-1])


def save(array, name, factor):
    im = Image.fromarray(array)
    im = im.resize((max(1, im.width // factor), max(1, im.height // factor)), Image.LANCZOS)
    if name.endswith(".jpg"):
        im.save(OUT / name, quality=90)
    else:
        im.save(OUT / name, optimize=True)
    return name


def write_images(result):
    """Images of the traced copy: the six lines, the proof glyphs and all 31 shapes."""
    ground = np.array(result["lines"]["L3"]["blk"]["info"]["ground_rgb"])
    ink = np.array(result["lines"]["L3"]["blk"]["info"]["ink_rgb"])
    fill = tuple(int(round(v)) for v in ground)

    def recon(coverage):
        return np.clip(ground[None, None, :] + coverage[..., None] * (ink - ground)[None, None, :], 0, 255).astype(np.uint8)

    src_rows, ren_rows, over_rows = [], [], []
    for key, line in result["lines"].items():
        blk = line["blk"]
        letters = blk["letters"]
        m = 3 * K
        x0 = max(0, letters[0]["x0"] - m)
        x1 = min(line["mask"].shape[1], letters[-1]["x1"] + m)
        y0 = max(0, min(c["y0"] for c in letters) - m)
        y1 = min(line["mask"].shape[0], max(c["y1"] for c in letters) + m)
        src_rows.append(np.clip(blk["img"][y0:y1, x0:x1], 0, 255).astype(np.uint8))
        ren_rows.append(recon(line["coverage"][y0:y1, x0:x1]))
        over_rows.append(overlay(line["mask"][y0:y1, x0:x1], line["coverage"][y0:y1, x0:x1] >= 0.5))
    images = {"lines": {
        "source": save(stack(src_rows, 2 * K, fill), "panel-lines-source.jpg", SHOW),
        "reconstruction": save(stack(ren_rows, 2 * K, fill), "panel-lines-reconstruction.png", SHOW),
        "overlay": save(stack(over_rows, 2 * K, (255, 255, 255)), "panel-lines-overlay.png", SHOW)}}
    images["glyphs"] = {}
    for ch in PROOF_GLYPHS:
        src_cols, ren_cols, over_cols = [], [], []
        for o in [o for o in result["occurrences"] if o["char"] == ch]:
            x0, y0, x1, y1 = o["_crop"]
            blk = result["lines"][o["block"]]["blk"]
            src_cols.append(np.clip(blk["img"][y0:y1, x0:x1], 0, 255).astype(np.uint8))
            ren_cols.append(recon(o["_coverage"]))
            over_cols.append(overlay(o["_source"], o["_coverage"] >= 0.5))
        images["glyphs"][ch] = {
            "source": save(side_by_side(src_cols, 3 * K, fill), "panel-glyph-%s-source.jpg" % ch, SHOW_GLYPH),
            "reconstruction": save(side_by_side(ren_cols, 3 * K, fill), "panel-glyph-%s-reconstruction.png" % ch, SHOW_GLYPH),
            "overlay": save(side_by_side(over_cols, 3 * K, (255, 255, 255)), "panel-glyph-%s-overlay.png" % ch, SHOW_GLYPH)}
    rows = []
    for key in result["lines"]:
        rows.append(side_by_side([overlay(o["_source"], o["_coverage"] >= 0.5)
                                  for o in result["occurrences"] if o["block"] == key], K, (255, 255, 255)))
    images["all_shapes_overlay"] = save(stack(rows, 2 * K, (255, 255, 255)), "panel-shapes-overlay.png", SHOW)
    return images


def photo_relation():
    """Measure how the supplied close photo relates to the traced photo."""
    big = np.asarray(Image.open(LAB / BP.R["photo"]["file"]).convert("RGB")).astype(np.float64)
    small = np.asarray(Image.open(LAB / BP.R["supplied_close_photo"]["file"]).convert("RGB")).astype(np.float64)
    reduced = cv2.resize(big, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_AREA)
    diff = np.abs(reduced - small)
    corr = float(np.corrcoef(reduced.mean(axis=2).ravel(), small.mean(axis=2).ravel())[0, 1])
    spec = BP.R["supplied_close_photo"]
    return {"size_ratio": round(small.shape[1] / big.shape[1], 6),
            "mean_abs_difference_after_reduction": round(float(diff.mean()), 3),
            "correlation_after_reduction": round(corr, 5),
            "limits": {"max_mean_abs_difference": spec["max_mean_abs_difference"], "min_correlation": spec["min_correlation"]},
            "same_exposure": bool(diff.mean() <= spec["max_mean_abs_difference"] and corr >= spec["min_correlation"])}


def evaluate():
    record = json.loads((LAB / "glyphs-panel.json").read_text())
    OUT.mkdir(exist_ok=True)
    main_result = compare("traced", record)
    cross = compare("supplied", record)
    occ = main_result["occurrences"]
    traced = [o for o in occ if o["traced_from_this_shape"]]
    gate = BP.R["gate"]
    worst = min(o[gate["metric"]] for o in traced)
    all_total, traced_total = total(occ), total(traced)
    cross_occ = cross["occurrences"]
    report = {
        "schema": "balilla-panel-eval/1",
        "face": BP.R["face"],
        "selected_sample": BP.R["selected_sample"],
        "source_photo": {"file": BP.R["photo"]["file"], "sha256": BP.R["photo"]["sha256"]},
        "supplied_close_photo": dict({k: BP.R["supplied_close_photo"][k] for k in ("file", "sha256", "relation", "published")},
                                     measured=photo_relation()),
        "font": {"file": "fonts/%s.ttf" % BP.STEM, "sha256": BF.sha256(FONT),
                 "woff2_sha256": BF.sha256(FONT.with_suffix(".woff2"))},
        "normalisation": {
            "samples_per_rectified_unit": K,
            "rectified_unit_in_photo_px": round(main_result["unit_px"], 4),
            "mask_threshold": "ink map >= 0.5 (midway between ground and full ink); the shapes of the line only",
            "render": "FreeType, no hinting, coverage >= 0.5, glyph origins quantized to 1/%d unit" % K,
            "baseline": "each line is level on its own measured baseline; all lines have the same scale",
            "placement": "each glyph starts at the measured left ink edge of its shape and sits on the baseline of its line; the comparison scores letter shapes and not spacing",
            "letter_height_units": main_result["scale"]["letter_height_samples"] / K,
        },
        "alignment": dict(main_result["alignment"],
                          model="one uniform scale and one shift for the whole sample (six lines, 31 shapes)",
                          search="scale 0.990..1.010 step 0.001; shift within +/-1.5 rectified units"),
        "shapes": [public(o) for o in occ],
        "glyphs": per_glyph(occ),
        "aggregate": {
            "scope": "the 31 observed shapes of the selected sample; no extrapolated glyph is scored",
            "all_observed_shapes": all_total,
            "traced_shapes": dict(traced_total, note="the 15 shapes that the font glyphs were traced from"),
            "other_occurrences": dict(total([o for o in occ if not o["traced_from_this_shape"]]),
                                      note="the 16 other occurrences of the repeated letters and the hyphen; hand-drawn, so each differs from the traced one"),
            "without_search_dice": main_result["without_search"],
        },
        "dice": all_total["dice"],
        "iou": all_total["iou"],
        "pixels": all_total["pixels"],
        "spacing": record["info"]["spacing"],
        "gate": {"metric": gate["metric"], "threshold": gate["threshold"], "applies_to": gate["applies_to"],
                 "value": round(worst, 5), "pass": bool(worst >= gate["threshold"])},
        "claim_100_percent": bool(all_total["pixels"]["source_only"] + all_total["pixels"]["render_only"] == 0),
        "cross_check_supplied_close_photo": {
            "note": "the same comparison with the close photo that the owner supplied (the same exposure at 5/6 of the size); not gated",
            "rectified_unit_in_photo_px": round(cross["unit_px"], 4),
            "letter_height_units": cross["scale"]["letter_height_samples"] / K,
            "alignment": cross["alignment"],
            "all_observed_shapes": total(cross_occ),
            "traced_shapes": total([o for o in cross_occ if o["traced_from_this_shape"]]),
            "glyphs": {ch: {"traced_shape_dice": g["traced_shape"]["dice"], "mean_dice": g["mean_dice"],
                            "lowest_dice": g["lowest_dice"]} for ch, g in per_glyph(cross_occ).items()},
        },
        "images": write_images(main_result),
        "scope_note": ("The glyphs were traced from this sample. Each glyph holds one observed shape; the other "
                       "occurrences of a repeated letter are drawn differently by hand and score lower. The scores are "
                       "not an independent test. They do not cover spacing or the extrapolated glyphs."),
    }
    (OUT / "panel-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return report


def gate_passes(report) -> bool:
    """The release gate: every traced glyph must reach the threshold on the shape it was traced from."""
    g = report["gate"]
    return all(v["traced_shape"][g["metric"]] >= g["threshold"] for v in report["glyphs"].values())


def main():
    report = evaluate()
    print("alignment: scale %.4f shift %s units (whole sample)" % (
        report["alignment"]["scale"], report["alignment"]["shift_units"]))
    for ch, g in report["glyphs"].items():
        print("glyph %s  traced shape %.4f  mean of %d %.4f  lowest %.4f   %s" % (
            ch, g["traced_shape"]["dice"], g["occurrences"], g["mean_dice"], g["lowest_dice"],
            " ".join("%s:%.3f" % (s["block"], s["dice"]) for s in g["all_shapes"])))
    agg = report["aggregate"]
    print("all 31 shapes   dice %.4f  iou %.4f  (without search %.4f)" % (
        agg["all_observed_shapes"]["dice"], agg["all_observed_shapes"]["iou"], agg["without_search_dice"]))
    print("15 traced shapes dice %.4f  iou %.4f" % (agg["traced_shapes"]["dice"], agg["traced_shapes"]["iou"]))
    print("16 other shapes  dice %.4f  iou %.4f" % (agg["other_occurrences"]["dice"], agg["other_occurrences"]["iou"]))
    cross = report["cross_check_supplied_close_photo"]
    print("supplied close photo: all shapes dice %.4f, traced shapes dice %.4f, scale %.4f shift %s, same exposure %s" % (
        cross["all_observed_shapes"]["dice"], cross["traced_shapes"]["dice"], cross["alignment"]["scale"],
        cross["alignment"]["shift_units"], report["supplied_close_photo"]["measured"]["same_exposure"]))
    ok = gate_passes(report)
    print("gate    dice >= %.2f for each traced glyph : %s (lowest %.4f)" % (
        report["gate"]["threshold"], "PASS" if ok else "FAIL", report["gate"]["value"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
