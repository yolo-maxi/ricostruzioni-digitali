# Ricostruzioni Digitali

This public repository is a **sanitized source snapshot**, with a new root Git
history. It does not contain the private development history, unpublished close-up
photo, supplied originals archive, withdrawn font artifacts, or operational notes.
The private repository and its historical evidence are preserved separately.

The public build regenerates the website and font package from frozen results.
Both active fonts can also be rebuilt from the included approved photographs.
Historical close-photo comparison numbers are retained as recorded evidence;
that private cross-check cannot be independently rerun from this snapshot.
See [reproduction instructions](docs/reproducing.md) for the exact boundary.

Historical source photographs have **separate rights status**: their inclusion
for this study grants no reuse or redistribution licence. CC BY 4.0 covers only
the reconstructed font files, with attribution to Balilla Type Lab. Build code
has no separate software licence grant; public visibility is not such a grant.

A static viewer and two fonts made from supplied photos of 1930s Italian printed lettering.

## Start here

This repository contains the actual tracing, font-building, evaluation and static-site code used for the study. The active Balilla scope is **two faces only**: cover capitals and pale panel lettering. Three separate feasibility probes are presented in Experiments; only the alphabet-sheet probe provides an experimental download. The withdrawn face remains provenance, not a supported download.

Photos are straightened, printed shapes isolated and traced into font outlines, then rendered back against the same samples. Only observed printed glyphs are evidence. Missing glyphs are labelled additions; handwriting is excluded. These are not complete historical alphabets or a claim of 100% fidelity.

For exact setup, build, test and local preview commands, see [Reproducing the study](docs/reproducing.md). The detailed measurements below explain what the tests actually measure; the public Study tab intentionally gives only a short introduction and visual proofs.

### Source-image rights and licence scope

User-supplied images are used as study inputs and are **not granted a licence by this repository**. Possession of these files is not permission to redistribute or reuse historical source materials; obtain any permissions your use requires. The unchanged supplied archive is provenance, not a new licence grant.

CC BY 4.0 applies to the reconstructed font files, with attribution to Balilla Type Lab, not to historical source images. See the licence notice in the generated font ZIP and the [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/). This notice does not assign a separate software licence to the build code.

Each font is traced from **one selected source sample**. Each font file is compared with its own sample. The two fonts are separate: no shape of one is used in another. The project does not cover all the photos.

| Typeface | Font files | Selected source sample | Dice |
| --- | --- | --- | --- |
| **Balilla — cover capitals** | `Balilla-Reconstructed.ttf`, `.woff2` (v0.2) | Row `EDUCAZIONE` of the knocked-out capitals | 99.64% |
| **Balilla Panel — pale panel lettering** | `Balilla-Panel-Reconstructed.ttf`, `.woff2` (v0.1) | The six lines `mini- stero educa- zione nazio- nale` in the green panel | 98.19% for the traced shapes; 93.43% for all 31 shapes |

The capitals sample is in the first supplied photo, `source/balilla-lab/assets/HXwNV_7W8AAs8y6.jpg` (burgundy cover). The panel sample is in the third supplied photo, `source/balilla-lab/assets/HXwNXsUWEAALJek.jpg` (obelisk cover). The photos are not changed.

## The viewer

`public/index.html` is one page with three tabs.

- **Fonts** shows two fixed-height cards side-by-side on desktop and stacked on narrow screens. Each card has its own TTF/WOFF2 downloads, five Italian sentences, and a compact labelled “Scrivi qualcosa” input. Typing updates that card's specimen literally; the recycle button clears custom text and returns to a seeded, non-immediately-repeating preset. Measured text size fits both sample dimensions after typing, recycling, font loading, resizing and tab selection. Specimens are not contenteditable. Font licensing and attribution appear at the bottom. Characters outside the reconstructed faces' coverage use browser fallback; very long text necessarily becomes small.
- **Study** starts with “Full source pages”: twelve explicitly authorized, unchanged original JPEGs in a keyboard-focusable horizontal rail, with lazy loading and natural aspect ratios. The rail contains only images, without figure frames or captions. There is no auto-advance; without JavaScript all originals remain visible. The short “How it was made” introduction, two source-specific evidence summaries and panel `s`, `t`, `z` proofs follow. Detailed methods and glyph labels live in this repository. Its share address is `index.html#study`.

- **Experiments** (`#experiments`) shows three distinct outcomes: blackletter text retains only `o` and `l` as diagnostic observed-outline candidates (`w` and `h` rejected; decorative initial excluded), with no font; the alphabet sheet exports experimental / observed-only TTF and WOFF2 for 63 characters (A–Z, a–z, 0–9, &), not production quality or historical verification; engraved cursive accepts zero complete glyphs and exports no font because joined strokes and hairlines require intervention (blackletter heading excluded).

The tabs are real tabs (`tablist`, `tab`, `tabpanel`). The arrow keys, Home and End move between them. Without script all tabs are shown one after the other.

The owner authorized publication of these supplied probes on the same website. The generator copies only six named source/proof images and the alphabet font pair into `public/experiments/`, not raw per-glyph outputs. Its separate ordered `SOURCE_PAGES` allowlist copies nine supplied archive JPEGs and the three complete probe input JPEGs byte-for-byte into `public/source-pages/`. No generated proofs, crops, masks or contact sheets enter that carousel. The scripts, configurations and full technical evidence stay under `experiments/`; see [reproduction commands](docs/reproducing.md). Permission to display the supplied sources is not a general source-image licence grant. The two active fonts and their 0.8 package remain unchanged.

## Selected source samples

### Balilla — cover capitals

- Sample: row 2 (`EDUCAZIONE`) of the capitals in the lower band of the cover. Scored text: `DUCAZION`. The first and last `E` of the row are cut by the photo edge.
- Why: the largest clean capitals in the photos (cap height about 68 photo pixels); flat two-colour print; 8 complete letters.
- Record: `source/balilla-lab/focus.json`.

### Balilla Panel — pale panel lettering

- Sample: the pale thin lettering `mini- stero educa- zione nazio- nale` (ministero educazione nazionale) inside the dark green panel of the obelisk cover: six lines, 28 letters and 3 hyphens.
- Why: it is the lettering that the owner named; it is the only sample of this lettering at this size (letter height about 62 photo pixels, stroke about 8 photo pixels); all 31 shapes are complete and separate; they give 14 different letters (`a c d e i l m n o r s t u z`) and the hyphen.
- The owner named the lettering with a close photo, `source/balilla-lab/assets/img_9eb5018c1e1c.jpg`. That file is the same exposure as `HXwNXsUWEAALJek.jpg` at 5/6 of the size (measured: mean difference 2.14 of 255 grey levels after reduction, correlation 0.9986). The font is traced from the larger copy. The font file is also compared with the close photo. The close photo is not published.
- Limits: the lettering is drawn by hand, so repeated letters (`a e i n o z` and the hyphen) are not identical. The font holds one observed shape for each letter. The letter `i` has no dot. The six lines are not exactly parallel (their baselines differ by up to 1.2 degrees), so each line is measured on its own baseline. The sample shows no capitals and no space between words.
- Do not confuse this sample with: the black title `opera balilla` on the same cover; the capitals `MINISTERO EDUCAZIONE NAZIONALE` on the burgundy cover; the numeral `XII` in the same panel; the small text lettering of the inside table (`HXwNYdeXgAE-ocC.jpg`), which has the same forms of `s` and `z` at a letter height of about 12 photo pixels and is not used.
- Record: `source/balilla-lab/focus-panel.json`.

## Results

| Sample | Dice | IoU | Placement of the letters | Gate |
| --- | --- | --- | --- | --- |
| Capitals, `DUCAZION` | 99.64% | 99.28% | advance widths of the font file | Dice ≥ 95% for the line: pass |
| Panel, the 15 shapes that the glyphs were traced from | 98.19% | 96.43% | letter positions from the source | Dice ≥ 95% for each traced glyph: pass (lowest 97.12%) |
| Panel, the 16 other occurrences of repeated letters | 88.98% | 80.14% | letter positions from the source | not gated |
| Panel, all 31 observed shapes | 93.43% | 87.66% | letter positions from the source | not gated |

No score is 100%. The exact numbers are in `source/balilla-lab/evaluation/report.json` and `panel-report.json`.

Panel face, the letters that the owner named:

| Glyph | Shapes on the cover | Dice, the shape that the glyph is traced from | Dice, the other shape |
| --- | --- | --- | --- |
| `s` | 1 (line 2, `stero`) | 98.43% | — |
| `t` | 1 (line 2, `stero`) | 98.26% | — |
| `z` | 2 (line 4, `zione`; line 5, `nazio-`) | 98.58% | 89.78% |

The same comparison with the supplied close photo (smaller copy, not gated) gives Dice 93.32% for all shapes and 97.78% for the traced shapes.

### What a score means

1. The photo sample is rectified (perspective removed) and resampled at 8 samples per unit.
2. The source mask is the ink map at the level midway between the ground colour and the full ink colour.
3. The font file is rendered by FreeType, without hinting, at the same scale.
4. One uniform scale and one shift are applied to the whole sample. The search covers scale ±1% and shift ±1.5 units. There is no rotation, no shear and no change of the shape or size of single letters.
5. Dice = 2·|S∩R| / (|S| + |R|). IoU = |S∩R| / |S∪R|.

The panel lettering is spaced by hand. Each glyph starts at the measured left ink edge of its shape and sits on the measured baseline of its line, so the panel scores cover letter shapes and not spacing. One scale and one shift are applied to all six lines together. The spacing is compared in a separate table: for the 22 gaps between letters, the difference between the font and the cover is 8.6 font units (root mean square, 0.9 photo pixels).

### What a score does not mean

- Each font was traced from the sample that it is compared with. A score shows how well a font file reproduces its photographed sample. It is not an independent test of the letter shapes.
- A score does not cover the extrapolated glyphs or the other photos.
- The outlines keep small irregularities of the hand lettering, of the print and of the photo.
- For the panel face, the difference between the hand-drawn repeats of a letter is part of the score. The panel lettering has a thin stroke, so that difference costs more: the other occurrences of repeated letters score 88.98%.
- The panel aggregate covers the 31 observed shapes only.
- The rectification assumes a 26 mm-equivalent phone camera. A 24–28 mm range changes the height-to-width ratio by about ±0.7%.

## Panel face: how it is traced

1. The cover plane is rectified from four printed lines of the obelisk cover.
2. Each of the six lines is resampled along its own measured baseline. All lines have one scale: the median height of the 23 letters without ascender or descender is 600 font units.
3. Each of the 31 shapes is traced to an outline. The outline is smoothed along its length; stroke ends and joints are not smoothed. The outline is stored as TrueType quadratic curves.
4. A repeated letter is drawn by hand a little differently each time. The font takes the occurrence that is closest to the others; with two occurrences (`z`), the first.
5. Side bearings: all straight sides share one value and all round sides share one value; a side of another form has its own value. The values are a least-squares fit to the measured gaps between letters.
6. Kerning: the right side of `r` has the bearing of the right side of `t`. The measured distance of the pair `r o` is a kerning pair (-72 font units). The same value is used before 10 other glyphs with a round left side; those pairs are extrapolated.

## Catalogue check

Reference: Anonima Impressori (Bologna), *Catalogo Caratteri in Piombo e Legno*, section Razionali, as shown on <https://luc.devroye.org/fonts-92349.html>. The catalogue is used for identification only. No catalogue image is in this repository or in the served files.

- **Cover capitals:** the catalogue section does not show these capitals. The plate labelled `Balilla` shows lower case only. The name Balilla for the capitals follows the owner's attribution and the source: the capitals are on the Opera Balilla cover.
- **Panel lettering:** no catalogue check was made for this face. The name Balilla Panel says where the lettering is: in the panel of an Opera Balilla cover.

## Glyph labels

Every glyph has a label in `glyphs.json` (capitals) and `glyphs-panel.json` (panel).

| Face | Traced from the selected sample (scored) | Traced, not scored | Extrapolated |
| --- | --- | --- | --- |
| Capitals | `D U C A Z I O N` | `E S T R L` (adjacent rows of the same lettering) | all other glyphs; lower-case keys show the capitals |
| Panel | `a c d e i l m n o r s t u z` and the hyphen | — | all other glyphs; capital keys show the lower case |

Extrapolated glyphs are not evidence of the historical lettering. They make the fonts usable for ASCII text and Italian accents.

## Reproduce

```sh
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python source/balilla-lab/build_font.py        # capitals: fonts + glyphs.json
.venv/bin/python source/balilla-lab/evaluate.py          # capitals: report + images; exit code 1 if the gate fails
.venv/bin/python source/balilla-lab/build_panel.py       # panel: fonts + glyphs-panel.json
.venv/bin/python source/balilla-lab/make_public.py       # public/: fonts, images, release ZIP, index.html
.venv/bin/python -m pytest -q                            # focused checks
```

The builds are deterministic: the same inputs give the same font bytes, the same images and the same ZIP bytes. The public checks regenerate the site and ZIP, pin frozen font bytes, and regenerate the three feasibility probes. Private historical regression checks are not part of this snapshot. The check of the tab script needs Node; no browser is used.

## Release package

`public/downloads/balilla-type-lab-fonts-0.8.zip` holds the two font pairs, `README.txt`, `LICENSE.txt`, and for each face `NOTES.txt` and `evaluation-report.json`. The panel folder also holds the difference images of `s`, `t` and `z`. This frozen package remains available for reproducibility; the landing uses card-local downloads instead of a global ZIP action.

Release 0.8 publishes only the two active faces. Obsolete 0.3, 0.4, 0.5 and 0.6 archives are not served. The existing TTF/WOFF2 bytes of both active faces are preserved. Withdrawn artifacts and historical archives are excluded from this snapshot and from the generated website.

A tentative third face was withheld because the available evidence did not support a source-faithful full alphabet. Unobserved characters of that face are not released as if authentic.

The original-materials archive is not served or linked by the website. The private provenance input is omitted from this snapshot; its recorded digest is with SHA-256 `f22d7a5d8ccf62780f5fe1415f857dc8c7ee7343336786385fe7a6014f8189c0`. The public generator needs no archive and publishes only the twelve allowlisted original images in Study. No additional ownership or rights claim is made for historical materials.

Study documents face selection from visibly distinct printed regions, source-observed versus extrapolated glyphs, inference from confirmed same-face printed samples and a representative observed repeat, exclusion of handwriting, and metrics limited to selected samples rather than complete historical typefaces.

Licence: the reconstructed font files are available under Creative Commons Attribution 4.0 International (CC BY 4.0). The separate original-materials archive is preserved provenance and is not relicensed by this project.

## Files

- `source/balilla-lab/focus.json`, `build_font.py`, `evaluate.py` — capitals.
- `source/balilla-lab/focus-panel.json`, `build_panel.py`, `evaluate_panel.py` — panel.
- `source/balilla-lab/make_public.py`, `viewer.template.html` — viewer and release package.
- `source/balilla-lab/pipeline/` — rectification helpers.
- `source/balilla-lab/fonts/`, `glyphs*.json`, `evaluation/` — generated and checked in.
- `tests/` — public viewer, frozen-font, package, source-rail and experiment checks; deterministic DOM behavior without a browser.
- `public/` — the served artifact.

## Scope

- The supplied photos are study material and are not changed. The checks compare their SHA-256 values.
- The served artifact holds the approved active-face evidence and the six allowlisted experiment source/proof images. The supplied close photo is not served.
- No emblem, graphic or slogan is recreated.
- The other letterings in the photos are not reconstructed.