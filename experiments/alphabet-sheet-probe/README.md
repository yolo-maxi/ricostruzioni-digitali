# Alphabet-sheet probe — observed-only experiment

This is a bounded technical feasibility experiment on one supplied alphabet sheet, not a production-quality historical reconstruction. The owner subsequently authorized its source sheet, contact proof and experimental font pair for the public Experiments hub. Only the site generator copies these allowlisted files; the active Balilla font directory and release ZIP remain unchanged. CC BY 4.0 covers reconstructed font files, not rights in this supplied source image; publication permission does not clear the image for other uses.

## Result

The manually transcribed six rows separate cleanly at the recorded threshold: **63 observed characters accepted, 0 rejected, 0 ambiguous** for this input/configuration. Both experimental TTF and WOFF2 contain exactly these 63 Unicode mappings and an unmapped empty `.notdef` required by the font format. There is no space, punctuation other than the observed ampersand, diacritic, fallback alphabet, kerning or inferred glyph.

This supports a narrow conclusion: a clean, separated sheet permits row-wise mechanical extraction after manual transcription and crop/threshold/baseline configuration. It does not prove unattended recognition or reliable segmentation of arbitrary joined/degraded lettering. Count agreement alone is not identity recognition; the visual transcription and component/contact-sheet review are part of this experiment.

## Reproduce and validate

Run from the repository root using Python 3.14 and the repository's pinned requirements:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiments/alphabet-sheet-probe/probe.py --verify
.venv/bin/python experiments/alphabet-sheet-probe/probe.py --out .venv/alphabet-probe-rebuild
.venv/bin/python -m pytest -q experiments/alphabet-sheet-probe/test_probe.py
.venv/bin/python -m pytest -q tests
node tests/tabs_check.js public/index.html
git diff --check
```

The build output directory must be absent or empty; nonempty output is refused to avoid stale fonts surviving a rejected build. Choose another fresh `--out` for another run. Without `--out`, the builder targets the checked-in `output/`; use `--verify` there. Run normal Python, not `python -O`: validation assertions are intentional gates. Tests byte-compare a fresh build, including its complete report and artifact hashes, against the checked-in output.

## Input and manual configuration

Original input: owner-supplied alphabet-sheet JPEG.
Preserved byte-identical copy: `input/alphabet-sheet-source.jpg` (746 × 676).
SHA-256: `2d56b789a9d3589e3df55546cb437d66fdb4563a6c1222819579c94b608d2d5d` (also in `input/SHA256SUMS.txt`). All paths below are relative to this experiment unless stated otherwise.

`config.json` is the complete manual configuration. Original-image pixel coordinates use exclusive right/bottom crop boundaries and pixel-edge baselines. All crops have x range [30,730):

| Row | Exact observed sequence | y crop | baseline y |
| --- | --- | --- | --- |
| upper-1 | ABCDEFGHIJK | [25,120) | 97 |
| upper-2 | LMNOPQRSTUV | [135,228) | 205 |
| upper-3 | WXYZ | [242,328) | 313 |
| lower-1 | abcdefghijklm | [352,447) | 420 |
| lower-2 | nopqrstuvwxyz | [465,550) | 529 |
| digits-ampersand | 1234567890& | [568,651) | 637 |

Manual decisions: visual row transcription, crop rectangles, horizontal baselines, grayscale threshold `<128`, scale 10 font units/source pixel, and 4-pixel side bearings. There is no perspective correction, resampling, morphology, denoising, component area filtering, outline smoothing, manual outline repair or glyph construction. These letters are not asserted to match either active Balilla face.

## Algorithm and rejection policy

1. Verify the pinned image digest and dimensions; validate non-overlapping row rectangles, baseline bounds, unique character identities and explicit exclusion reasons.
2. Crop and threshold each row independently. Reuse `source/balilla-lab/pipeline/blocks.py:components` for 8-connected component diagnostics with minimum area 1 (all foreground ink retained).
3. Segment maximal occupied-column bands, separated strictly by blank columns. Detached components whose x ranges lie in the same band stay together. Assign the manually transcribed characters in order **only** if the number of bands exactly matches the row transcription and no ink touches a crop edge. Otherwise mark every character in that row `ambiguous`, with no invented assignment or font entry. Full row masks/components still preserve the evidence.
4. `rows[].exclude` can mark any manually reviewed ambiguous/joined glyph with a reason; such a glyph retains its mask/source preview but is `rejected` and cannot enter the font. A joined pair that reduces the band count rejects the entire row. A coincidental join/split that preserves the count cannot be ruled out by this algorithm: review the previews rather than claiming recognition. This input has no observed joined neighboring glyphs at the selected threshold.
5. Take every thresholded foreground pixel in an accepted band's tight bounding box. Union its horizontal-run pixel rectangles and write their exact boundary as straight TrueType contours, retaining holes and detached parts. No curves are fitted and no source ink is repaired. The resulting staircase outlines intentionally preserve raster/JPEG imperfections.
6. Place outlines using the row baseline, one shared scale, and the explicit side bearing. Advance is `(ink_bbox_width + 8) * 10` font units. These are experimental, deliberately simple metrics, **not recovered historical spacing**. UPM 1000, ascent 900, descent -300; no hinting instructions or kerning.
7. Export distinctly named observed-only TTF/WOFF2. Reopen both and check exact cmap, glyph order, advances, side bearings and bounds against records. Render TTF at 100 ppem with FreeType, no hinting, binary cutoff >127: each rendered tight mask and its baseline/left bearing equal the extraction records. Focused tests also decode WOFF2 and independently exercise the same raster/advance checks.

## Evidence and inspection

- `output/report.json`: full configuration snapshot, row bands/components/status, per-glyph identity/status/reason, original-image bbox, component IDs, ink area, mask/source path, font metrics, render check, counts, exact coverage and SHA-256 manifest of generated artifacts.
- `output/rows/*-source.png`, `*-mask.png`, `*-components.png`: exact row crops, threshold masks and red component boxes.
- `output/glyphs/uniXXXX-source.png`, `*-mask.png`: source and binary mask for each assigned character, including rejected characters when exclusions are configured.
- `output/contact-sheet.png`: reviewed source/component sheet.
- `output/font-proof.png`: actual FreeType font render at source positions, **not a proof of natural advance spacing**.
- `output/fonts/Alphabet-Sheet-EXPERIMENTAL-Observed-Only.ttf` and `.woff2`: experimental fonts, selected for the hub by its generator.

Visual review of the original, component sheet and font proof found all six rows present with the transcribed identities; the detached middle of M, tail of Q, dots of i/j and foot of 4 remain in their own glyph bands. No neighbor-joining or missing detached marks was visible. Counters survive. The proof visibly has pixel-stepped edges and retains small source blemishes; it is not a smoothed type design. The numeric equality claim covers only the thresholded masks at the declared 100-ppem no-hinting setting, not the grayscale original, other sizes, typographic quality, legal clearance or historical fidelity.

## Original probe validation / candidate boundary (historical)

- Focused suite covers deterministic artifact/report equality, source hash, exact row sequences, ink conservation, both font formats' cmap/advances/bounds/renders, exclusion, count mismatch, crop-edge ambiguity, bad configuration and artifact tampering.
- Existing repository suite passed: 39 tests (187.62 seconds). An earlier run hit its 180-second command timeout after ten test progress marks; the complete rerun above passed, not a substituted result.
- See `VALIDATION.txt` for final gate output and candidate boundary evidence.

Work is confined to `experiments/alphabet-sheet-probe/` on `agent/balilla-alphabet-sheet-probe-20261124`, based on `491a4cc`. No GitHub creation/push, production merge, deployment, public link change, active font modification or release-package change is authorized or performed by this experiment. The external supervisor owns status-card/session cleanup; this writer must not recursively launch another lane or kill its own tmux session.
