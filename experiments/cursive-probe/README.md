# Engraved cursive segmentation probe — negative feasibility result

The owner subsequently authorized the source crop and primary-threshold component
proof for the public Experiments hub. Only the site generator publishes these
two allowlisted images. Full diagnostics remain repository evidence. No source-image
licence or complete glyph/font extraction is implied. Gate notes below record the
original isolated probe; current integrated results are in `release/0.10-candidate.md`.

Result: zero complete glyphs accepted. The two standalone `a` occurrences can be
spatially isolated without cutting another letter, but even these split into
multiple components at all three tested thresholds. Connected cursive strokes,
thin hairlines, and raster fragmentation make component-to-character assignment
unreliable. This is not an automatic script-font digitiser or a production font.
It does not establish that a higher-resolution original could not work.

## Reproduce

From the repository root, with `requirements.txt` installed in `.venv`:

    .venv/bin/python experiments/cursive-probe/probe.py

Validation:

    .venv/bin/python -m pytest -q experiments/cursive-probe/test_probe.py tests/test_focus.py -k 'not builds_are_deterministic'

Executed result: 13 passed, 1 deselected. An initial run including the existing
full deterministic-font-rebuild test exceeded 180 seconds after 13 passing tests;
that expensive unrelated rebuild is not claimed as passing. `git diff --check`
and the staged whitespace check passed. No existing source or public files change.

## Source and manual controls

The supplied JPEG is preserved byte-for-byte in `input/cursive-source.jpg`.
SHA-256: `262dfe485891ad653bf8f22ca1f18301b28437862bee9bc6420cbae53b9b52ac`.
The input copy was already present in the assigned experiment directory at entry;
its digest was independently compared with the original supplied cache image.

Only line 5, “You with a dash in time may drain a Mine”, is examined. The
transcription is a human reading for context, not OCR or an assignment of glyphs.
The blackletter heading and all other lines are excluded. All coordinates and
manual decisions are in `controls.json`: crop [150,307,690,355), horizontal visual
baseline from (165,337) to (674,337), and two isolated-`a` selection windows.
The baseline is a guide, not an estimated typographic metric. No rectification,
resampling, rotation, or perspective correction is applied to the analytical crop:
there is no measured page geometry to justify it. Preview enlargement is display only.
Visual review of `manual-controls.png` confirms the windows cover the standalone
`a` after “with” and after “drain”, not adjacent words.

The existing `pipeline.blocks.normalise_ink` helper estimates local background
and ink strength (dark polarity, approximate stroke width 2 pixels). Its inferred
colour parameters are recorded in the report. The existing `components` helper
labels all 8-connected ink, minimum area 1. No dot, small fragment, or noise is
silently dropped. Thresholds 0.35 / 0.50 / 0.65 yield respectively 94 / 102 / 83
components and 1988 / 1507 / 1171 ink pixels. These are NOT character counts.
At 0.35 each standalone-`a` window contains three whole components; at 0.50 and
0.65 each contains two. Threshold changes demonstrably alter hairline connectivity.
No threshold is used to deliberately sever a join and declare the pieces letters.

A manual window selects only components wholly enclosed by it: it never clips a
component into a desired shape. Individual saved fragments retain their positions
on the full crop canvas. They are explicitly NOT glyphs. All primary-threshold
components, including these fragments, are in `rejected_or_ambiguous`; boundary
components are separately marked rejected. Other components retain no guessed
character identity. No stitching, erosion, dilation, stroke deletion, contour
redrawing, or missing-character inference occurs. Contour tracing/font helpers
are deliberately not invoked: tracing a connected run would not resolve which
strokes belong to an individual character.

## Artifacts

- `output/source-crop.png`: exact RGB source region.
- `output/manual-controls.png`: baseline and manual selection windows.
- `output/ink-strength.png`: display-clipped normalised ink strength.
- `output/mask-*.png`: lossless binary masks at each threshold.
- `output/components-*.png`: colour-coded components with label IDs.
- `output/a-fragment-*.png`: entire selected components, not repaired letters.
- `output/report.json`: every component's bounding box, source coordinates, area,
  threshold, disposition and reason; manual selection labels; complete primary
  rejection/ambiguity list; negative feasibility conclusion.

Tests conserve every thresholded pixel, compare saved fragments to complete
original labels, verify exact crops and input hash, reproduce every output
byte-for-byte, and assert zero accepted glyphs/inferred characters/font exports.
Everything stays under this unserved experiment. No font, active site, release
package, canonical branch, deployment, remote publication, or GitHub action is
part of this candidate. Supervisor owns any later decision and tmux cleanup.
