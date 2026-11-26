#!/usr/bin/env python3
"""Assemble the served artifact ``public/`` from the built fonts and reports.

* copies the font files and the comparison images;
* copies the explicitly authorized full source pages, unchanged;
* builds the release package (ZIP) with the two active typefaces and their notes;
* excludes obsolete release packages from the served artifact;
* keeps the original-materials archive out of the served artifact;
* writes ``public/index.html`` from ``viewer.template.html``.

The page has three tabs. ``Fonts`` is the landing tab: specimens, scope and
downloads. ``Study`` holds concise source evidence and limits. ``Experiments``
shows three distinct feasibility outcomes with strictly allowlisted artifacts.

Every number on the page and in the notes comes from the evaluation
reports and the glyph records. The ZIP is reproducible: fixed file order,
fixed time stamp, no compression.

Run:  python source/balilla-lab/make_public.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import zipfile
from pathlib import Path

LAB = Path(__file__).resolve().parent
PUBLIC = LAB.parent.parent / "public"
RELEASE = "0.8"
# Public sanitized snapshot; verified through GitHub before linking.
SOURCE_REPOSITORY_URL = "https://github.com/yolo-maxi/ricostruzioni-digitali"
EXPERIMENTS = LAB.parent.parent / "experiments"
# Explicit publication boundary: no recursive copying of probe outputs.
EXPERIMENT_FILES = {
    "blackletter-source.png": "blackletter-probe/output/source-crop.png",
    "blackletter-proof.png": "blackletter-probe/output/contour-overlay.png",
    "alphabet-source.jpg": "alphabet-sheet-probe/input/alphabet-sheet-source.jpg",
    "alphabet-contact.png": "alphabet-sheet-probe/output/contact-sheet.png",
    "cursive-source.png": "cursive-probe/output/source-crop.png",
    "cursive-proof.png": "cursive-probe/output/components-0-5.png",
    **{f"Alphabet-Sheet-EXPERIMENTAL-Observed-Only.{ext}":
       f"alphabet-sheet-probe/output/fonts/Alphabet-Sheet-EXPERIMENTAL-Observed-Only.{ext}"
       for ext in ("ttf", "woff2")},
}
PACKAGE = "balilla-type-lab-fonts-%s" % RELEASE
ZIP_NAME = PACKAGE + ".zip"
ZIP_TIME = (2026, 11, 23, 0, 0, 0)
CAPITALS = "Balilla-Reconstructed"
PANEL = "Balilla-Panel-Reconstructed"
FONT_FILES = tuple(stem + ext for stem in (CAPITALS, PANEL) for ext in (".ttf", ".woff2"))
ASSETS = ("capitals-original.jpg",)          # existing evidence section
# Ordered, owner-authorized original inputs only; never glob probe outputs.
SOURCE_PAGES = {
    **{name: LAB / "assets" / name for name in (
        "HXwNYdeXgAE-ocC.jpg", "HXwNV_7W8AAs8y6.jpg",
        "HXwNXsUWEAALJek.jpg", "HXwNW6bWQAAleia.jpg",
        "brown-capitals-original.jpg", "capitals-original.jpg",
        "school-original.jpg", "cover-original.jpg", "green-original.jpg",
    )},
    "blackletter-source.jpg": EXPERIMENTS / "blackletter-probe/input/blackletter-source.jpg",
    "alphabet-sheet-source.jpg": EXPERIMENTS / "alphabet-sheet-probe/input/alphabet-sheet-source.jpg",
    "cursive-source.jpg": EXPERIMENTS / "cursive-probe/input/cursive-source.jpg",
}
CAPITALS_EVAL = ("selected-source.png", "selected-reconstruction.png", "selected-overlay.png", "report.json")
ORIGINALS_NAME = "balilla-type-lab-original-materials.zip"
ORIGINALS = LAB.parent / ORIGINALS_NAME
ORIGINALS_SHA = "f22d7a5d8ccf62780f5fe1415f857dc8c7ee7343336786385fe7a6014f8189c0"
PACKAGE_PROOFS = "stz"                       # difference images of these panel glyphs go into the package
LICENCE_LINE = ("The reconstructed font files are licensed under Creative Commons Attribution 4.0 International "
                "(CC BY 4.0). Attribute them to Balilla Type Lab and link to "
                "https://creativecommons.org/licenses/by/4.0/. The separate original-materials ZIP is not relicensed.")


def sha256(data) -> str:
    if isinstance(data, Path):
        data = data.read_bytes()
    return hashlib.sha256(data).hexdigest()


def load():
    return {
        "a_report": json.loads((LAB / "evaluation" / "report.json").read_text()),
        "a_glyphs": json.loads((LAB / "glyphs.json").read_text()),
        "a_focus": json.loads((LAB / "focus.json").read_text()),
        "p_report": json.loads((LAB / "evaluation" / "panel-report.json").read_text()),
        "p_glyphs": json.loads((LAB / "glyphs-panel.json").read_text()),
        "p_focus": json.loads((LAB / "focus-panel.json").read_text()),
    }


def groups_of(glyphs):
    groups = {}
    for ch, g in glyphs["glyphs"].items():
        groups.setdefault(g["label"], []).append(ch)
    return groups


def pct(value):
    return "%.2f" % (100.0 * value)


def panel_facts(d):
    """Values of the panel face that the page, the notes and the README share."""
    p, g = d["p_report"], d["p_glyphs"]
    agg = p["aggregate"]
    unit_px = p["normalisation"]["rectified_unit_in_photo_px"]
    per_unit = g["info"]["scale"]["font_units_per_rectified_unit"]
    spacing = g["info"]["spacing"]
    marks = d["p_focus"]["classes"]["marks"]
    letter_gaps = [row for row in spacing["gaps"] if row["left"] not in marks and row["right"] not in marks]
    measured = [k for k in g["kerning"] if k["label"] == "evidenced-selected"]
    derived = [k for k in g["kerning"] if k["label"] != "evidenced-selected"]
    angles = [b["baseline_angle_to_printed_lines_deg"] for b in g["info"]["blocks"].values()]
    return {
        "all": agg["all_observed_shapes"], "traced": agg["traced_shapes"], "other": agg["other_occurrences"],
        "unit_px": unit_px, "per_unit": per_unit,
        "letter_px": p["normalisation"]["letter_height_units"] * unit_px,
        "stroke_px": g["info"]["measured_units"]["stroke"] / per_unit * unit_px,
        "n_letter_gaps": len(letter_gaps),
        "spacing_rms": spacing["letter_gap_rms_difference_units"],
        "spacing_max": spacing["letter_gap_max_difference_units"],
        "spacing_rms_px": spacing["letter_gap_rms_difference_units"] / per_unit * unit_px,
        "kern_measured": measured, "kern_derived": derived,
        "angle_spread": max(angles) - min(angles),
        "lines": {k: b["text"] for k, b in g["info"]["blocks"].items()},
        "cross": p["cross_check_supplied_close_photo"],
        "relation": p["supplied_close_photo"]["measured"],
    }


def line_name(facts, block):
    """'line 2 (stero)' for block 'L2'."""
    return "line %s (%s)" % (block[1:], facts["lines"][block])


# --------------------------------------------------------------------------
# release package
# --------------------------------------------------------------------------

def licence_text():
    return """CREATIVE COMMONS ATTRIBUTION 4.0 INTERNATIONAL
Balilla Type Lab fonts, release %s

Licence
The reconstructed font files in this package are licensed under the Creative Commons Attribution 4.0 International licence (CC BY 4.0):
https://creativecommons.org/licenses/by/4.0/

You may share and adapt the reconstructed font files for any purpose, including commercial use, provided that you give appropriate credit:
Balilla Type Lab — https://balilla-type-lab.repo.box/

This notice is a human-readable summary. The licence terms at the URL above govern.

What the files are
- The font files were made by the build scripts of this project. The scripts measure photographs of Italian printed lettering of the 1930s.
- This package does not contain the photographs.
- The separate original-materials ZIP is preserved provenance. This licence does not grant rights in those supplied materials or in any historical source image.
- "Balilla" is also the name of a wood type in the type catalogue of Anonima Impressori (Bologna). The files in this package are independent study reconstructions. They are not copies of a font file, and they are not a release by the makers of that type.
- The files are supplied as they are, with no warranty.
""" % RELEASE


def readme_text(d):
    a, p = d["a_report"], d["p_report"]
    ag, pg = groups_of(d["a_glyphs"]), groups_of(d["p_glyphs"])
    f = panel_facts(d)
    proofs = "".join("    evidence/panel-glyph-%s-overlay.png\n" % ch for ch in PACKAGE_PROOFS)
    return """BALILLA TYPE LAB FONTS, release {release}

Two study reconstructions of lettering from two photographed 1930s Italian booklet covers.
Each font is traced from one selected sample. Each font file is compared with its own sample.
The two fonts are separate: no shape of one is used in another.

CONTENTS
  README.txt                      this file
  LICENSE.txt                     CC BY 4.0 licence and attribution
  SHA256SUMS.txt                  SHA-256 of the other files
  {cap}/
    {cap}.ttf, {cap}.woff2
    NOTES.txt                     source sample, method, score, glyph labels
    evaluation-report.json        the measured comparison
  {pan}/
    {pan}.ttf, {pan}.woff2
    NOTES.txt
    evaluation-report.json
{proofs}                                  difference images of the glyphs s, t and z

1. {a_label}   (family "{a_family}", version {a_version})
   Source sample: {a_desc}.
   Scored text: {a_text}. Dice {a_dice}%, IoU {a_iou}%. Gate Dice >= {a_gate}%: {a_pass}.
   Traced letters: {a_traced}. All other glyphs are labelled extrapolations.
   Lower-case keys show the capitals.

2. {p_label}   (family "{p_family}", version {p_version})
   Source sample: {p_desc}.
   All {p_n} observed shapes: Dice {p_dice}%, IoU {p_iou}%.
   The {p_nt} shapes that the glyphs were traced from: Dice {p_tdice}%, IoU {p_tiou}%.
   The {p_no} other occurrences of repeated letters: Dice {p_odice}%, IoU {p_oiou}%.
   Gate Dice >= {p_gate}% for each traced glyph, compared with the shape that it was traced from: {p_pass}.
   Traced glyphs: {p_traced}. All other glyphs are labelled extrapolations.
   Capital keys show the lower case. The letter i has no dot, as in the source.

WHAT THE SCORES MEAN
A score shows how well a font file reproduces the photographed sample that it was traced from,
after one uniform scale and one shift for the whole sample. It is not an independent test of the
letter shapes. It does not cover the extrapolated glyphs. No score is 100%.
The panel lettering is drawn by hand with a thin stroke. The font holds one observed shape for each
letter, so the other occurrences of a repeated letter score lower than the traced one.

INSTALL
Desktop: open the .ttf file and select Install.
Web: use the .woff2 file with @font-face.

More detail is in the NOTES.txt file of each face.
""".format(
        release=RELEASE, cap=CAPITALS, pan=PANEL, proofs=proofs.rstrip("\n"),
        a_label=d["a_focus"]["face"]["label"], a_family=d["a_focus"]["face"]["family"],
        a_version=d["a_glyphs"]["font_version"], a_desc=a["selected_block"]["description"],
        a_text=a["scored_text"], a_dice=pct(a["dice"]), a_iou=pct(a["iou"]),
        a_gate="%g" % (100 * a["gate"]["threshold"]), a_pass="pass" if a["gate"]["pass"] else "FAIL",
        a_traced=" ".join(ag["evidenced-selected"] + ag["evidenced-adjacent"]),
        p_label=d["p_focus"]["face"]["label"], p_family=d["p_focus"]["face"]["family"],
        p_version=d["p_glyphs"]["font_version"], p_desc=p["selected_sample"]["description"],
        p_n=f["all"]["shapes"], p_dice=pct(f["all"]["dice"]), p_iou=pct(f["all"]["iou"]),
        p_nt=f["traced"]["shapes"], p_tdice=pct(f["traced"]["dice"]), p_tiou=pct(f["traced"]["iou"]),
        p_no=f["other"]["shapes"], p_odice=pct(f["other"]["dice"]), p_oiou=pct(f["other"]["iou"]),
        p_gate="%g" % (100 * p["gate"]["threshold"]), p_pass="pass" if p["gate"]["pass"] else "FAIL",
        p_traced=" ".join(pg["evidenced-selected"]))


def notes_capitals(d):
    a, g, f = d["a_report"], d["a_glyphs"], d["a_focus"]
    grp = groups_of(g)
    px = a["pixels"]
    unit = a["normalisation"]["rectified_unit_in_photo_px"]
    edge = a["boundary_distance_units"]
    return """{label}
Font family "{family}", version {version}. Files: {stem}.ttf, {stem}.woff2

SELECTED SOURCE SAMPLE
{desc}.
Photo: {photo} (SHA-256 {photo_sha}). The photo is not in this package.
Scored text: {text}
Why this sample:
{why}
Limits: {limits}

METHOD
1. The photo plane is rectified from four printed lines of the cover.
2. The row is resampled at {k} samples per rectified unit. The ink mask is the ink map at the level midway between the ground colour and the full ink colour.
3. Each complete letter of the mask is traced to an outline. The cap height is set to 720 font units. The advance width of each letter is the measured distance to the next letter.
4. The letters {adjacent} come from the two adjacent rows of the same lettering. They are not scored.
5. All other glyphs are extrapolations. Every glyph has a label.

MEASURED COMPARISON
Rendering: FreeType, no hinting, the font's own advance widths.
Alignment: one uniform scale and one shift for the whole line. Found: scale {scale}, shift {shift} units. No rotation, no shear, no adjustment of single letters.
Dice {dice}%   IoU {iou}%   Gate Dice >= {gate}%: {gate_word}
Mask samples: source {src:,}, font {ren:,}, both {both:,}, source only {so:,}, font only {ro:,}
Edge distance: mean {em:.2f} photo pixels, 95th percentile {ep:.2f} photo pixels
The score is not 100%. The letters were traced from this sample, so the score is not an independent test.

GLYPH LABELS
Traced from the selected sample (scored): {sel}
Traced from the adjacent rows (not scored): {adj}
Extrapolated, cut, mirrored or turned from a traced glyph: {der}
Extrapolated, block construction from the measured stem, bar and width: {con}
Lower-case keys show the capitals, because this lettering has no lower case.

CATALOGUE CHECK
Reference: {cat_ref}
{cat_findings}
Result: {cat_result}

Font file SHA-256: {font_sha}
""".format(
        label=f["face"]["label"], family=f["face"]["family"], version=g["font_version"], stem=CAPITALS,
        desc=a["selected_block"]["description"], photo=a["source_photo"]["file"],
        photo_sha=a["source_photo"]["sha256"], text=a["scored_text"],
        why="\n".join("- " + w for w in a["selected_block"]["why"]), limits=a["selected_block"]["limits"],
        k=a["normalisation"]["samples_per_rectified_unit"], adjacent=" ".join(grp["evidenced-adjacent"]),
        scale="%.3f" % a["alignment"]["scale"], shift="%g, %g" % tuple(a["alignment"]["shift_units"]),
        dice=pct(a["dice"]), iou=pct(a["iou"]), gate="%g" % (100 * a["gate"]["threshold"]),
        gate_word="pass" if a["gate"]["pass"] else "FAIL",
        src=px["source"], ren=px["render"], both=px["both"], so=px["source_only"], ro=px["render_only"],
        em=edge["mean"] * unit, ep=edge["p95"] * unit,
        sel=" ".join(grp["evidenced-selected"]), adj=" ".join(grp["evidenced-adjacent"]),
        der=" ".join(grp["extrapolated-derived"]), con=" ".join(grp["extrapolated-constructed"]),
        cat_ref=f["catalogue_check"]["reference"],
        cat_findings="\n".join("- " + x for x in f["catalogue_check"]["findings"]),
        cat_result=f["catalogue_check"]["result"], font_sha=a["font"]["sha256"])


def notes_panel(d):
    p, g, f = d["p_report"], d["p_glyphs"], d["p_focus"]
    facts = panel_facts(d)
    grp = groups_of(g)
    sample = p["selected_sample"]
    close = p["supplied_close_photo"]
    m = g["info"]["measured_units"]
    bearings = g["info"]["side_bearings"]
    repeats = ["%s: %d occurrences, agreement Dice %s%%" % (ch, v["occurrences"], pct(v["agreement_dice"]))
               for ch, v in g["glyphs"].items() if v.get("agreement_dice")]
    each = []
    for ch, v in p["glyphs"].items():
        rest = ["%s %s%%" % (line_name(facts, s["block"]), pct(s["dice"])) for s in v["all_shapes"]
                if (s["block"], s["index"]) != (v["traced_shape"]["block"], v["traced_shape"]["index"])]
        each.append("  %s: %d %s. Traced from %s: Dice %s%%, IoU %s%%.%s" % (
            ch, v["occurrences"], "shape" if v["occurrences"] == 1 else "shapes",
            line_name(facts, v["traced_shape"]["block"]), pct(v["traced_shape"]["dice"]), pct(v["traced_shape"]["iou"]),
            " Other: %s." % "; ".join(rest) if rest else ""))
    kern = facts["kern_measured"][0]
    return """{label}
Font family "{family}", version {version}. Files: {stem}.ttf, {stem}.woff2

SELECTED SOURCE SAMPLE
{desc}.
Photo: {photo} (SHA-256 {photo_sha}). The photo is not in this package.
Why this sample:
{why}
Limits: {limits}
Do not confuse this sample with:
{confuse}

THE SUPPLIED CLOSE PHOTO
The owner named this lettering with a close photo of the cover: {close_file} (SHA-256 {close_sha}).
{relation}
Measured: size ratio {ratio}, mean difference {diff} of 255 grey levels after reduction, correlation {corr}.
The close photo is not in this package and is not published.

METHOD
1. The photo plane is rectified from four printed lines of the obelisk cover. Nothing is taken from the capitals font.
2. Each of the six lines is resampled along its own measured baseline at {k} samples per rectified unit. The six lines are not exactly parallel: their baselines differ by up to {spread:.2f} degrees. All lines have one scale.
3. The ink mask is the ink map at the level midway between the ground colour and the full ink colour.
4. Each of the {n} shapes is traced to an outline. The outline is smoothed along its length. Stroke ends and joints are not smoothed. The smoothing moves a traced outline by {move:.2f} rectified units at most (one unit is about one photo pixel). The outline is stored as TrueType quadratic curves.
5. The lettering is drawn by hand, so repeated letters differ. The font takes the occurrence that is closest to the others; with two occurrences, the first:
{repeats}
6. Scale: the median height of the {n_height} letters without ascender or descender is {letter} font units ({letter_px:.1f} photo pixels). Measured: stroke {stroke:.0f}, flat letter height {flat:.0f}, ascender {asc:.0f}, descender {desc_d:.0f} font units.
7. Side bearings: all straight sides share one value ({straight}) and all round sides share one value ({round_}). A side of another form has its own value. The values are a least-squares fit to the measured gaps between letters. For the {n_gaps} gaps between letters, the difference between the font and the cover is {rms} font units (root mean square); the largest difference is {gap_max} font units.
8. Kerning: the right side of r has the bearing of the right side of t. The measured distance of the pair {kl} {kr} is a kerning pair ({kv:+d}). The same value is used before {n_kern} other glyphs with a round left side; those pairs are extrapolated.
9. The sample shows no space between words. The word space ({space} font units) is extrapolated.
10. All other glyphs are extrapolations. Every glyph has a label.

MEASURED COMPARISON
Rendering: FreeType, no hinting. Each glyph starts at the measured left ink edge of its shape and sits on the measured baseline of its line. The comparison scores letter shapes and not spacing.
Alignment: one uniform scale and one shift for the whole sample (six lines, {n} shapes). Found: scale {scale}, shift {shift} units. No rotation, no shear, no adjustment of the size, position or shape of a single glyph.
All {n} observed shapes: Dice {dice}%   IoU {iou}%
The {n_traced} shapes that the glyphs were traced from: Dice {tdice}%   IoU {tiou}%
The {n_other} other occurrences of repeated letters: Dice {odice}%   IoU {oiou}%
Gate Dice >= {gate}% for each traced glyph, compared with the shape that it was traced from: {gate_word} (lowest {gate_value}%)
Mask samples, all shapes: source {src:,}, font {ren:,}, both {both:,}, source only {so:,}, font only {ro:,}
Each glyph:
{each}
Cross-check with the supplied close photo (smaller copy, not gated): all shapes Dice {cdice}%, traced shapes Dice {ctdice}%.
The score is not 100%. The glyphs were traced from this sample, so the score is not an independent test. The difference between the hand-drawn repeats is part of the score. The aggregate covers the {n} observed shapes only.

GLYPH LABELS
Traced from the selected sample (scored): {sel}
Extrapolated, mirrored, turned or extended from a traced glyph: {der}
Extrapolated, one-weight construction from the measured stroke, letter height, ascender and descender: {con}
Capital keys show the lower case, because this lettering has no capitals. The letter i has no dot, as in the source.

Font file SHA-256: {font_sha}
""".format(
        label=f["face"]["label"], family=f["face"]["family"], version=g["font_version"], stem=PANEL,
        desc=sample["description"], photo=p["source_photo"]["file"], photo_sha=p["source_photo"]["sha256"],
        why="\n".join("- " + w for w in sample["why"]), limits=sample["limits"],
        confuse="\n".join("- " + w for w in sample["not_to_be_confused_with"]),
        close_file=close["file"], close_sha=close["sha256"], relation=close["relation"],
        ratio="%.4f" % facts["relation"]["size_ratio"],
        diff="%.2f" % facts["relation"]["mean_abs_difference_after_reduction"],
        corr="%.4f" % facts["relation"]["correlation_after_reduction"],
        k=p["normalisation"]["samples_per_rectified_unit"], spread=facts["angle_spread"],
        n=facts["all"]["shapes"], repeats="\n".join("   - " + x for x in repeats),
        move=g["info"]["smoothing"]["largest_move_of_a_traced_outline_units"],
        n_height=g["info"]["scale"]["letters_measured"], letter=g["letter_height"], letter_px=facts["letter_px"],
        stroke=m["stroke"], flat=m["flat_letter_height"], asc=m["ascender"], desc_d=m["descender"],
        straight=bearings["straight"], round_=bearings["round"], n_gaps=facts["n_letter_gaps"],
        rms="%.1f" % facts["spacing_rms"], gap_max="%.1f" % facts["spacing_max"],
        kl=kern["left"], kr=kern["right"], kv=kern["value"], n_kern=len(facts["kern_derived"]),
        space=g["word_space"]["advance"],
        scale="%.3f" % p["alignment"]["scale"], shift="%g, %g" % tuple(p["alignment"]["shift_units"]),
        dice=pct(facts["all"]["dice"]), iou=pct(facts["all"]["iou"]),
        n_traced=facts["traced"]["shapes"], tdice=pct(facts["traced"]["dice"]), tiou=pct(facts["traced"]["iou"]),
        n_other=facts["other"]["shapes"], odice=pct(facts["other"]["dice"]), oiou=pct(facts["other"]["iou"]),
        gate="%g" % (100 * p["gate"]["threshold"]), gate_word="pass" if p["gate"]["pass"] else "FAIL",
        gate_value=pct(p["gate"]["value"]),
        src=p["pixels"]["source"], ren=p["pixels"]["render"], both=p["pixels"]["both"],
        so=p["pixels"]["source_only"], ro=p["pixels"]["render_only"], each="\n".join(each),
        cdice=pct(facts["cross"]["all_observed_shapes"]["dice"]), ctdice=pct(facts["cross"]["traced_shapes"]["dice"]),
        sel=" ".join(grp["evidenced-selected"]), der=" ".join(grp["extrapolated-derived"]),
        con=" ".join(grp["extrapolated-constructed"]), font_sha=p["font"]["sha256"])


def package_members(d, fonts_dir: Path):
    """Ordered (name, bytes) members of the release package."""
    members = [
        ("README.txt", readme_text(d).encode()),
        ("LICENSE.txt", licence_text().encode()),
        ("%s/%s.ttf" % (CAPITALS, CAPITALS), (fonts_dir / (CAPITALS + ".ttf")).read_bytes()),
        ("%s/%s.woff2" % (CAPITALS, CAPITALS), (fonts_dir / (CAPITALS + ".woff2")).read_bytes()),
        ("%s/NOTES.txt" % CAPITALS, notes_capitals(d).encode()),
        ("%s/evaluation-report.json" % CAPITALS, (LAB / "evaluation" / "report.json").read_bytes()),
        ("%s/%s.ttf" % (PANEL, PANEL), (fonts_dir / (PANEL + ".ttf")).read_bytes()),
        ("%s/%s.woff2" % (PANEL, PANEL), (fonts_dir / (PANEL + ".woff2")).read_bytes()),
        ("%s/NOTES.txt" % PANEL, notes_panel(d).encode()),
        ("%s/evaluation-report.json" % PANEL, (LAB / "evaluation" / "panel-report.json").read_bytes()),
    ]
    for ch in PACKAGE_PROOFS:
        name = d["p_report"]["images"]["glyphs"][ch]["overlay"]
        members.append(("%s/evidence/%s" % (PANEL, name), (LAB / "evaluation" / name).read_bytes()))
    sums = "".join("%s  %s\n" % (sha256(data), name) for name, data in members)
    members.append(("SHA256SUMS.txt", sums.encode()))
    return members


def build_zip(path: Path, d=None, fonts_dir: Path | None = None):
    """Write the reproducible release package and return its path."""
    d = d or load()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in package_members(d, fonts_dir or (LAB / "fonts")):
            info = zipfile.ZipInfo("%s/%s" % (PACKAGE, name), date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return path


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

def panel_proofs(d, facts):
    """The proof blocks of the Study tab: source crop, font and difference for s, t and z."""
    p = d["p_report"]
    out = []
    for ch in sorted(p["images"]["glyphs"]):
        v = p["glyphs"][ch]
        images = p["images"]["glyphs"][ch]
        note = ("Two printed z shapes; the font uses the first."
                if ch == "z" else "Traced from the printed %s in stero." % ch)
        figures = "".join(
            '<figure><img src="evaluation/%s" alt="%s" loading="lazy"><figcaption>%s</figcaption></figure>' % (
                images[kind], html.escape(alt % ch, quote=True), caption)
            for kind, alt, caption in (
                ("source", "Source shape of the letter %s after perspective rectification", "Source"),
                ("reconstruction", "The glyph %s of the panel font file", "Font file"),
                ("overlay", "Difference image of the letter %s",
                 "Difference: grey = both · red = source only · blue = font only")))
        out.append('<div class="proof" id="study-proof-%s"><span class="big" aria-hidden="true">%s</span>'
                   '<h4>Letter %s</h4><div class="proof-row">%s</div><p class="note">%s</p></div>' % (
                       ch, ch, ch, figures, html.escape(note)))
    return "\n".join(out)


def panel_rows(d, facts):
    rows = []
    for ch, v in sorted(d["p_report"]["glyphs"].items(), key=lambda item: (not item[0].isalpha(), item[0])):
        each = " · ".join("%s %s%%" % (html.escape(line_name(facts, s["block"])), pct(s["dice"])) for s in v["all_shapes"])
        rows.append("<tr><td class=\"g\">%s</td><td>%d</td><td>%s</td><td>%s%%</td><td>%s</td><td>%s%%</td></tr>" % (
            html.escape(ch), v["occurrences"], html.escape(line_name(facts, v["traced_shape"]["block"])),
            pct(v["traced_shape"]["dice"]), each, pct(v["lowest_dice"])))
    return "\n".join(rows)


def source_page_slides():
    labels = {
        "blackletter-source.jpg": "Supplied blackletter source page",
        "alphabet-sheet-source.jpg": "Supplied alphabet-sheet source page",
        "cursive-source.jpg": "Supplied engraved-cursive source page",
    }
    slides = []
    for i, name in enumerate(SOURCE_PAGES, 1):
        label = labels.get(name, "Supplied Balilla source page")
        caption = "%s — %s" % (label, name)
        slides.append(
            '<img id="source-page-%d" class="source-page" src="source-pages/%s" '
            'alt="%s; complete original input, without technical cropping" loading="lazy">'
            % (i, name, html.escape(caption, quote=True)))
    return "\n".join(slides)


def page(d, zip_path: Path) -> str:
    a, p = d["a_report"], d["p_report"]
    ag, pg = groups_of(d["a_glyphs"]), groups_of(d["p_glyphs"])
    unit_px = a["normalisation"]["rectified_unit_in_photo_px"]
    edge = a["boundary_distance_units"]
    apx, ppx = a["pixels"], p["pixels"]
    facts = panel_facts(d)

    def shown(groups, label):
        return " ".join(html.escape(c) for c in groups.get(label, []))

    def items(values):
        return "".join("<li>%s</li>" % html.escape(v) for v in values)

    kern = facts["kern_measured"][0]
    kerning_note = ("The right side of r has the bearing of the right side of t. The measured distance of the pair "
                    "%s %s is a kerning pair (%+d font units). The same value is used before %d other glyphs with a "
                    "round left side; those pairs are extrapolated." % (
                        kern["left"], kern["right"], kern["value"], len(facts["kern_derived"])))
    marks = d["p_focus"]["classes"]["marks"]
    p_letters = [c for c in pg["evidenced-selected"] if c not in marks]
    zip_bytes = zip_path.read_bytes()
    values = {
        "SOURCE_PAGE_SLIDES": source_page_slides(),
        "RELEASE": RELEASE,
        "A_LABEL": html.escape(d["a_focus"]["face"]["label"]),
        "A_VERSION": d["a_glyphs"]["font_version"],
        "A_COVER_LETTERS": " ".join(sorted(ag["evidenced-selected"] + ag["evidenced-adjacent"])),
        "A_BLOCK_DESCRIPTION": html.escape(a["selected_block"]["description"]),
        "A_PHOTO_FILE": html.escape(a["source_photo"]["file"]),
        "A_WHY_ITEMS": items(a["selected_block"]["why"]),
        "A_BLOCK_LIMITS": html.escape(a["selected_block"]["limits"]),
        "A_SCORED_TEXT": html.escape(a["scored_text"]),
        "A_DICE_PCT": pct(a["dice"]),
        "A_IOU_PCT": pct(a["iou"]),
        "A_EDGE_MEAN_PX": "%.2f" % (edge["mean"] * unit_px),
        "A_EDGE_P95_PX": "%.2f" % (edge["p95"] * unit_px),
        "A_GATE_WORD": "PASS" if a["gate"]["pass"] else "FAIL",
        "A_GATE_CLASS": "" if a["gate"]["pass"] else "fail",
        "A_GATE_PCT": "%g" % (100 * a["gate"]["threshold"]),
        "A_SCALE": "%.3f" % a["alignment"]["scale"],
        "A_SHIFT": "%g, %g" % tuple(a["alignment"]["shift_units"]),
        "A_DIFF_SAMPLES": "{:,}".format(apx["source_only"] + apx["render_only"]),
        "A_SOURCE_SAMPLES": "{:,}".format(apx["source"]),
        "A_CATALOGUE_RESULT": html.escape(d["a_focus"]["catalogue_check"]["result"]),
        "A_N_SELECTED": str(len(ag.get("evidenced-selected", []))),
        "A_N_ADJACENT": str(len(ag.get("evidenced-adjacent", []))),
        "A_N_EVIDENCED": str(len(ag.get("evidenced-selected", [])) + len(ag.get("evidenced-adjacent", []))),
        "A_N_DERIVED": str(len(ag.get("extrapolated-derived", []))),
        "A_N_CONSTRUCTED": str(len(ag.get("extrapolated-constructed", []))),
        "A_GLYPHS_SELECTED": shown(ag, "evidenced-selected"),
        "A_GLYPHS_ADJACENT": shown(ag, "evidenced-adjacent"),
        "A_GLYPHS_DERIVED": shown(ag, "extrapolated-derived"),
        "A_GLYPHS_CONSTRUCTED": shown(ag, "extrapolated-constructed"),
        "A_FONT_SHA": a["font"]["sha256"],
        "P_LABEL": html.escape(d["p_focus"]["face"]["label"]),
        "P_VERSION": d["p_glyphs"]["font_version"],
        "P_COVER_LETTERS": " ".join(sorted(p_letters)),
        "P_SAMPLE_DESCRIPTION": html.escape(p["selected_sample"]["description"]),
        "P_PHOTO_FILE": html.escape(p["source_photo"]["file"]),
        "P_WHY_ITEMS": items(p["selected_sample"]["why"]),
        "P_SAMPLE_LIMITS": html.escape(p["selected_sample"]["limits"]),
        "P_CONFUSE_ITEMS": items(p["selected_sample"]["not_to_be_confused_with"]),
        "P_SUPPLIED_RELATION": html.escape(p["supplied_close_photo"]["relation"]),
        "P_SUPPLIED_RATIO": "%.4f" % facts["relation"]["size_ratio"],
        "P_SUPPLIED_DIFF": "%.2f" % facts["relation"]["mean_abs_difference_after_reduction"],
        "P_SUPPLIED_CORR": "%.4f" % facts["relation"]["correlation_after_reduction"],
        "P_IMG_LINES_SOURCE": p["images"]["lines"]["source"],
        "P_IMG_LINES_RECON": p["images"]["lines"]["reconstruction"],
        "P_IMG_LINES_OVERLAY": p["images"]["lines"]["overlay"],
        "P_IMG_SHAPES_OVERLAY": p["images"]["all_shapes_overlay"],
        "P_DICE_PCT": pct(facts["all"]["dice"]),
        "P_IOU_PCT": pct(facts["all"]["iou"]),
        "P_N_SHAPES": str(facts["all"]["shapes"]),
        "P_TRACED_DICE_PCT": pct(facts["traced"]["dice"]),
        "P_TRACED_IOU_PCT": pct(facts["traced"]["iou"]),
        "P_N_TRACED": str(facts["traced"]["shapes"]),
        "P_OTHER_DICE_PCT": pct(facts["other"]["dice"]),
        "P_OTHER_IOU_PCT": pct(facts["other"]["iou"]),
        "P_N_OTHER": str(facts["other"]["shapes"]),
        "P_GATE_WORD": "PASS" if p["gate"]["pass"] else "FAIL",
        "P_GATE_CLASS": "" if p["gate"]["pass"] else "fail",
        "P_GATE_PCT": "%g" % (100 * p["gate"]["threshold"]),
        "P_GATE_VALUE_PCT": pct(p["gate"]["value"]),
        "P_DIFF_SAMPLES": "{:,}".format(ppx["source_only"] + ppx["render_only"]),
        "P_SOURCE_SAMPLES": "{:,}".format(ppx["source"]),
        "P_SCALE": "%.3f" % p["alignment"]["scale"],
        "P_SHIFT": "%g, %g" % tuple(p["alignment"]["shift_units"]),
        "P_CROSS_DICE_PCT": pct(facts["cross"]["all_observed_shapes"]["dice"]),
        "P_CROSS_TRACED_DICE_PCT": pct(facts["cross"]["traced_shapes"]["dice"]),
        "P_GLYPH_ROWS": panel_rows(d, facts),
        "P_N_LETTER_GAPS": str(facts["n_letter_gaps"]),
        "P_SPACING_RMS": "%.1f" % facts["spacing_rms"],
        "P_SPACING_RMS_PX": "%.1f" % facts["spacing_rms_px"],
        "P_SPACING_MAX": "%.1f" % facts["spacing_max"],
        "P_KERNING_NOTE": html.escape(kerning_note),
        "P_N_SELECTED": str(len(pg.get("evidenced-selected", []))),
        "P_N_LETTERS": str(len(p_letters)),
        "P_N_DERIVED": str(len(pg.get("extrapolated-derived", []))),
        "P_N_CONSTRUCTED": str(len(pg.get("extrapolated-constructed", []))),
        "P_GLYPHS_SELECTED": shown(pg, "evidenced-selected"),
        "P_GLYPHS_DERIVED": shown(pg, "extrapolated-derived"),
        "P_GLYPHS_CONSTRUCTED": shown(pg, "extrapolated-constructed"),
        "SOURCE_REPOSITORY_LINK": (
            '<a id="study-source-repository" href="%s">Code and reproduction guide on GitHub</a>'
            % html.escape(SOURCE_REPOSITORY_URL, quote=True)
            if SOURCE_REPOSITORY_URL else
            '<span id="study-source-repository" data-placeholder="SOURCE_REPOSITORY_URL">'
            'GitHub code and reproduction guide — publication pending.</span>'
        ),
        "P_PROOFS": panel_proofs(d, facts),
        "P_FONT_SHA": p["font"]["sha256"],
        "P_LETTER_PX": "%.0f" % facts["letter_px"],
        "P_LETTER_UNITS": str(d["p_glyphs"]["letter_height"]),
        "P_N_HEIGHT_LETTERS": str(d["p_glyphs"]["info"]["scale"]["letters_measured"]),
        "P_ANGLE_SPREAD": "%.1f" % facts["angle_spread"],
        "P_SMOOTH_MOVE": "%.2f" % d["p_glyphs"]["info"]["smoothing"]["largest_move_of_a_traced_outline_units"],
        "P_STROKE_PX": "%.0f" % facts["stroke_px"],

        "ZIP_HREF": "./downloads/" + ZIP_NAME,
        "ZIP_NAME": ZIP_NAME,
        "ZIP_SIZE": "%d KB" % round(len(zip_bytes) / 1024.0),
        "ZIP_SHA": sha256(zip_bytes),
        "LICENCE_LINE": html.escape(LICENCE_LINE),
    }
    text = (LAB / "viewer.template.html").read_text()
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    if "{{" in text:
        raise SystemExit("unfilled placeholder in the viewer template: %s" % re.findall(r"\{\{[A-Z_]+\}\}", text))
    return text


def panel_eval_files(d):
    """Names of the panel evaluation files that the site serves."""
    images = d["p_report"]["images"]
    names = list(images["lines"].values()) + [images["all_shapes_overlay"]]
    for glyph in images["glyphs"].values():
        names += list(glyph.values())
    return sorted(names) + ["panel-report.json"]


def expected_files(d):
    """Relative paths of every file of the served artifact."""
    files = ["index.html", "downloads/" + ZIP_NAME]
    files += ["fonts/" + n for n in FONT_FILES]
    files += ["assets/" + n for n in ASSETS]
    files += ["evaluation/" + n for n in CAPITALS_EVAL]
    files += ["evaluation/" + n for n in panel_eval_files(d)]
    files += ["experiments/" + n for n in EXPERIMENT_FILES]
    files += ["source-pages/" + n for n in SOURCE_PAGES]
    return sorted(files)


def main():
    d = load()
    for sub in ("fonts", "evaluation", "assets", "downloads", "experiments", "source-pages"):
        shutil.rmtree(PUBLIC / sub, ignore_errors=True)
        (PUBLIC / sub).mkdir(parents=True)
    for name in FONT_FILES:
        shutil.copyfile(LAB / "fonts" / name, PUBLIC / "fonts" / name)
    for name in ASSETS:
        shutil.copyfile(LAB / "assets" / name, PUBLIC / "assets" / name)
    for name, source in EXPERIMENT_FILES.items():
        shutil.copyfile(EXPERIMENTS / source, PUBLIC / "experiments" / name)
    for name, source in SOURCE_PAGES.items():
        shutil.copyfile(source, PUBLIC / "source-pages" / name)
    for rel in expected_files(d):
        if rel.startswith("evaluation/"):
            shutil.copyfile(LAB / rel, PUBLIC / rel)

    zip_path = build_zip(PUBLIC / "downloads" / ZIP_NAME, d)
    (PUBLIC / "index.html").write_text(page(d, zip_path))
    present = sorted(str(p.relative_to(PUBLIC)) for p in PUBLIC.rglob("*") if p.is_file())
    if present != expected_files(d):
        raise SystemExit("unexpected files in public/: %s" % sorted(set(present) ^ set(expected_files(d))))
    print("wrote %d files to %s" % (len(present), PUBLIC))
    print("zip  ", sha256(zip_path), zip_path.name, zip_path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()