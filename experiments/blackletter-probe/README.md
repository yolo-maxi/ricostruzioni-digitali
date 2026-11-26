# Blackletter hard-case probe

Experimental feasibility probe — not a historical or production font.

Originally an unserved experiment based on repository commit
`491a4cc423cad8dfb112aca434c0bbf2df314f09`. The owner subsequently authorized
its source crop and contour proof for the public Experiments hub. Only the
site generator copies those two allowlisted images; raw diagnostics remain
repository evidence, not site artifacts. No font is exported, and no licence
grant for reuse of the supplied source image is implied.

## Reproduce from a fresh checkout

From the repository root, run this exact command:

```sh
bash experiments/blackletter-probe/run.sh
```

Prerequisites: Python 3 with `venv`/pip, and package-index access for the first
run. Verified on Linux with Python 3.14 and the repository's pinned
`requirements.txt`. The command creates an ignored experiment-local `.venv`,
installs those dependencies and runs only `probe.py`. No external image, OCR,
model, download of lettering, server, active font build or publishing command
is used. After installation, offline reruns can use:

```sh
experiments/blackletter-probe/.venv/bin/python experiments/blackletter-probe/probe.py
```

The source is tracked at `input/blackletter-source.jpg`, byte-identical
to the supplied photograph, with SHA-256:

`423d999ee385896b888bd711fc3112080a2690dcfc3cfbd73008b2780a0dc497`

`input/SHA256SUMS.txt` and `config.json` record the digest. The probe verifies it
before processing and verifies dimensions (1280 × 533). All image output derives
only from this photograph. Existing repository helpers are reused as code, not
as glyph or photographic evidence.

## Exact evidence and manual controls

The subset is exactly **w, o, h, l**, one occurrence each from first-line **wohl**,
after **es** and before **her**. Character identity is a manual reading, not OCR.
No other letter, missing-glyph inference or composited alphabet is produced.
The ornate initial at source rectangle `[0,0,260,260]` is excluded altogether;
it is not a text glyph and was not isolated as an ornament.

Every selection and numeric control is in `config.json`:

- Source coordinates use x rightwards, y downwards. The baseline is
  `(454,62)` to `(574,62)`. Crop bounds are x454..574, y10..72, zero padding.
- The plane homography is deliberately identity. The existing block-frame
  machinery provides local baseline normalisation at native resolution, with
  linear interpolation. No reliable page-level perspective recovery is claimed.
- RGB local-background normalisation uses the existing dark-ink helper,
  approximate 5 px stroke, threshold 0.5. Thresholds 0.4/0.5/0.6 are audited.
- Components use 8-connectivity and a 12-pixel minimum for selection. The report
  still inventories all components down to one pixel, including rejected ones.
- Manual x windows in crop coordinates: w `[0,45)`, o `[45,71)`, h `[71,98)`,
  l `[98,120)`. No component is split at a window. Components crossing a window
  or touching the crop edge are rejected, not silently truncated.
- The first visual review found rough windows cutting ink and a short bottom
  crop cutting h; the exact old/new coordinates are recorded in the config.
  Only the crop/windows were corrected, not the letter shapes.
- A diagnostic candidate requires exactly one isolated component and a minimum
  0.85 window-mask IoU across the threshold sweep. This is a conservative probe
  rule, not a rule that real glyphs must always be single components, and not a
  measure of historical fidelity. Rejected candidates remain visible as diagnostics.

## Reused pipeline and output

The experiment calls `pipeline.blocks.make_frame`, `extract`, `normalise_ink`
and `components`, then `build_font.trace` for polygons. It does **not** call any
font builder or extrapolation/design function. Importing `build_font` loads its
existing configuration constants, but no other photograph or font contributes
to this experiment. The helper source digests are in the report.

`trace` uses OpenCV contour hierarchy (including counters), Shapely polygon
repair and the existing 0.5-pixel sample-centre-to-edge buffer. No additional
curve smoothing, elastic fitting, stroke completion or ligature splitting is
added. These are pixel-scale polygons, not cleaned type-design masters.

Generated and checked-in artifacts under `output/`:

- `source-selection.png`: full supplied source with excluded initial in red
  and selected word in blue. Unserved, like all other artifacts here.
- `source-crop.png`, `mask.png`, `mask-0.40.png`, `mask-0.50.png`, `mask-0.60.png`.
- `components.png`: numbered candidate components in blue, unassigned/rejected
  components in red, manual window boundaries orange, baseline green. Blue means
  assigned to a manual window, **not** accepted as a glyph; consult the report.
- `contour-overlay.png`: all diagnostic contours over the source crop, including
  rejected candidates; the red outlines expose the rough pixel-scale boundary.
- `*-selected-mask.png`, `*-diagnostic.svg`: per-letter diagnostic selections.
  SVGs retain the common crop viewBox so original positions remain auditable.
- `diagnostic-outlines.svg`: all selected components, including rejected letters.
- `accepted-outline-candidates.svg`: only o and l. Neither is a font glyph export.
- `report.json`: source/config/helper digests, normalisation parameters, transform,
  full component boxes/areas/labels, explicit candidate/rejection reasons,
  threshold sensitivity, accepted/rejected subset and artifact SHA-256 manifest.

No TTF, WOFF, inferred glyphs, spacing or kerning are emitted. All diagnostics
are deterministic under the pinned dependencies. Alternate output directories
are restricted to this unserved experiment, outside `input/`.

## Observed result and stopping point

The nominal mask has **5 components for 4 manually named letters**, with 1465
ink pixels. At thresholds 0.4, 0.5 and 0.6 there are respectively **5, 5 and 8**
components of at least 12 pixels. This is not reliable one-component-per-letter
segmentation.

- **o**: one component, counter retained; worst threshold IoU 0.889937106918239.
- **l**: one isolated component; worst threshold IoU 0.8933333333333333.
- **w**: two components at the nominal threshold; worst IoU
  0.8469387755102041. Rejected; no guess whether the disconnection is original
  printing, wear, photograph quality or thresholding, and no artificial joining.
- **h**: nominally one component, but worst IoU 0.8200514138817481. Rejected as
  threshold-sensitive; no repair of its thin connections or terminals.

Visual inspection of the contour overlay confirms the o counter and separate l,
but also rough, degraded edges and the disjoint w. **Two diagnostic outline
candidates are retained; the full observed subset fails the gate. We stop here,
without a font reconstruction.** Metrics are threshold-sensitivity measurements,
not similarity to an unknown original metal type design.

## Why this is not push-button general font digitisation

Manual transcription, baseline, crop, polarity, stroke scale, glyph windows and
acceptance thresholds are required. This small word deliberately avoids harder
blackletter ligatures and long-s; their existence elsewhere on the page does not
justify mapping them to modern letters or splitting them automatically. Tight
spacing can merge components; disjoint strokes, letterpress variation and ink
wear can fragment them. Low contrast, blur, paper texture and uneven illumination
move threshold boundaries. The decorative initial is a different design element,
not evidence for the ordinary face. The bottom of the photograph is truncated.
One occurrence per letter cannot separate the intended design from printing and
photographic defects. Page perspective, repeated-letter consensus, metrics,
hinting, Unicode coverage and whole-page recognition remain untested.

This is a bounded test of existing reconstruction concepts on a harder source,
not a new automatic system, historical authentication, or production release.

## Validation

After the reproduction command, run:

```sh
experiments/blackletter-probe/.venv/bin/python -m pytest -q experiments/blackletter-probe/test_probe.py
experiments/blackletter-probe/.venv/bin/python -m pytest -q tests/test_focus.py tests/test_panel.py
git diff --check
```

Focused tests validate source/config boundaries, rejection of malformed controls,
no output into `public/`, exact observed/rejected subset, masks, hashes, SVG
counters, deterministic reruns and the all-rejected stricter-threshold path.
The existing subset covers original focus/panel pipeline contracts. See
`GATES.md` for actual execution output and fresh-checkout verification.
