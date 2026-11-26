# Bounded tracing autoresearch

This is an offline, parameter-only research harness, not an autonomous editor.
It cannot create missing evidence. Quality improvements require enough varied,
labelled, same-face printed samples, independently reviewed for face identity and
mask truth. A passing gate measures this corpus against declared criteria, not
historical authenticity, full-alphabet fidelity, or a publishable typeface.
Nothing is promoted automatically. The active release is frozen.

## Directory map and setup

- `harness.py`: deterministic semantic validator, bounded search and JSON receipts.
- `corpus.schema.json`: machine-readable structural contract (Draft 2020-12).
  The CLI additionally enforces file/hash/crop/leakage/coverage semantics.
- `example-search.json`: fixed baseline plus six parameter combinations.
- `fixtures/insufficient.json`: no images, no historical observations; intentionally
  insufficient synthetic example. It does not contain source photographs.
- `test_harness.py`: generated synthetic pixel fixtures and orchestration tests.
- `local-corpora/`: ignored private observations and masks; create locally.
- `.runs/<64-hex-run-id>/receipt.json`: ignored local output. No custom output path.

From the repository root, use Python 3.12 and the repository `requirements.txt`
(the same environment as the existing builders; no extra dependencies):

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
. .venv/bin/activate
python -m pytest -q research/autoresearch
python research/autoresearch/harness.py validate research/autoresearch/fixtures/insufficient.json
python research/autoresearch/harness.py run research/autoresearch/fixtures/insufficient.json --config research/autoresearch/example-search.json
```

Exit 2 means `INSUFFICIENT_SAMPLES`, not a crash. Exit 1 is invalid input. Exit 0
means the valid experiment finished; inspect `decision` for accepted/rejected.
Run the last command twice: stdout and stored receipt are byte-identical. A
replay reads the receipt rather than testing holdout a second time. This fixture
reports missing train=3, validation=2, holdout=1 for synthetic-demo/A. It cannot
produce a positive accuracy claim or candidate.

## New face and evidence contract

1. Create an ignored `local-corpora/<corpus-name>/` directory, copy the empty
   manifest, give it a version, set `fixture: false`, and replace `faces` with
   the exact face IDs and targeted glyph list. V1 supports individually cropped
   glyphs only. Do not label a word as evidence for mechanically unsegmented
   individual letters, or claim generic features not explicitly targeted.
2. Select varied independent printed occurrences of that same face. Record
   `face_match_basis` (terminals, proportions, counters, baseline, source context).
   Exclude handwriting, stamps, illustration labels, and uncertain face matches.
   `status` must be `observed`; inferred/contextual labels are not target truth.
   Keep inferred/ambiguous inventories outside this truth manifest.
3. For each observation record a unique `id`, `face_id`, printed `label`,
   `kind: printed`, `quality`, `confidence` (0..1), `split`, and
   `independence_group`. The group is the physical printing/occurrence family:
   multiple photographs or recrops of the same impression are NOT independent.
   A human must review this grouping; a file digest cannot establish independence.
4. Store `source: {path, sha256}` relative to the manifest, with the digest of
   the unchanged asset. Record `crop: [x0,y0,x1,y1]` in source pixels, half-open,
   no rotation or undocumented warp. Supply `target: {path, sha256}` for a
   separately reviewed binary mask, white=ink, black=background, at the exact
   crop dimensions. Never generate target truth from each candidate's threshold.
   A target is an annotation of visible printed pixels, not an invented ideal
   outline. Document annotation decisions in the corpus's local notes.
5. V1 handles pre-cropped dark ink on light paper without perspective correction.
   Do not pass pale-on-dark panel samples or distorted images and interpret low
   scores as a general font verdict. A future reviewed adapter can use the panel
   photometric/geometry path, with a new implementation identity and tests.

Paths must stay inside the corpus directory and exist; hashes must match.
Duplicate source/crop pairs are rejected even within one split. Source hashes
and physical independence groups cannot cross splits, including different crops
or renamed copies. Overlapping observations within one group count only once
for that glyph/split. Do not split the same physical page between sets.

## Sample sufficiency and splits

Default policy per declared face/glyph is at least 3 independent train, 2
independent validation, and 1 independent holdout observations. Thresholds are
explicit in `policy` and may be raised, not lowered below these conservative
floors. Quality/confidence floors are configurable from 0.8 to 1; the example
uses quality >=0.8 and confidence >=0.9. Low-quality observations do not count or
enter scoring. Any uncovered face/glyph/split stops the whole experiment, with
exact independent, required and missing counts in `missing_coverage`.

These are safety gates, not statistically proven sufficiency or fidelity claims.
Six prints are a minimum, not a guarantee; collect more varied printing, lighting
and condition examples for stronger inference. Never lower gates to turn a weak
corpus green. Resolve insufficiency by adding reviewed independent samples in the
specified missing split, or by explicitly narrowing the versioned target scope
before an experiment (never retrospectively to hide a failed glyph).

Create splits before looking at candidate outcomes. Train calibrates proposals;
validation compares candidates; holdout is reserved for one final gate. Once a
holdout has been inspected, treat it as spent for adaptive follow-up research:
use new independent holdout evidence and a new corpus version. The runner prevents
retesting an identical run, not a human from repeatedly changing config against
the same holdout. Do not do that or interpret it as independent confirmation.

## Declare and run a bounded search

Copy `example-search.json` to the local corpus. Change only named fields:

- `baseline_reference`: a meaningful pinned baseline description/revision. The
  baseline is the declared parameter control, NOT the active font binary.
- `baseline`: fixed `threshold` (0.1..0.9) and `simplify_px` (0..2).
- `search`: finite lists for those same parameters. No expressions, commands,
  shell hooks, source file rewriting, arbitrary modules or executable config.
- `max_candidates`: hard limit 1..32, checked before evaluation; no truncation.
- `calibration_keep`: number retained from train for validation (within budget).
- `seed`: uint32; `min_validation_iou_gain`: strictly positive predeclared margin.
- `robustness_noise`: optional 0..0.05 deterministic Gaussian RGB noise (fraction
  of 255), evaluated only on validation after acceptance. It is explicitly
  synthetic diagnostic output, not historical evidence or a selection criterion.

```sh
python research/autoresearch/harness.py validate research/autoresearch/local-corpora/my-face/corpus.json
python research/autoresearch/harness.py run research/autoresearch/local-corpora/my-face/corpus.json --config research/autoresearch/local-corpora/my-face/search.json
```

The propose → build → evaluate loop builds polygon outlines in memory, rasterizes
at fixed source pixel centres, and compares with the reviewed target. It searches
tracing preprocessing and contour simplification, not glyph invention. It does
not fit a shared font to train and claim generalization of that font to holdout:
each independent sample tests the same tracing algorithm/parameters. The fixed
grayscale photometric model and target annotations are NOT searched.

### Existing pipeline bridge

- `build_font.trace` builds the actual existing capitals component polygons.
- `pipeline.blocks.components` provides the existing segmentation structures.
- `pipeline.geometry.warp` applies fixed identity sampling (no flexible alignment).
- `evaluate.dice_iou` and `evaluate.boundary_distances` supply the active metrics.
- `build_panel` and `evaluate_panel` use the same tracing/geometry/evaluation
  primitives, but their face-specific smoothing, extraction and font-layout paths
  are deliberately not invoked here. Neither their globals nor production scripts
  are patched. Extending this adapter requires code review, not a search option.

The runner does not call builders' full `build()`/`evaluate()` routines: those
write fonts/reports and mix historical face-specific observations and inference.
Research polygon WKB digests are saved per observation; parameters, source hashes,
code fingerprint and fixed runtime versions make outlines reproducible. There is
no TTF/WOFF2 export, invented alphabet, kerning optimization, or package output.

## Receipts, leaderboard and retention

The run ID hashes canonical config and corpus hashes, implementation fingerprint,
Python/dependency versions, seed and baseline reference. Absolute local input paths
and timestamps are not included. `receipt.json` records the full config, corpus
version, sufficiency coverage, train calibration, validation leaderboard, baseline
metrics, selected parameters, holdout result (or null), optional synthetic
robustness result, decision and reason. All results are local and ignored.

Rank uses worst observation IoU first, worst edge distance next, mean IoU next,
and canonical parameter ordering as a deterministic tie breaker. Every metric
set contains per-observation Dice/IoU and symmetric mean/max edge distance in crop
pixels, per-glyph worst IoU/edge distance and observation/glyph denominators.
An empty rendering receives zero overlap and the finite crop-diagonal edge
penalty. Empty target masks are invalid. No alignment search masks shape errors.

A candidate qualifies only if validation mean IoU exceeds the baseline by the
predeclared margin AND no individual observation regresses in Dice, IoU, mean
edge or max edge distance (only 1e-12 floating-point slack). The highest-ranked
qualifying candidate is selected without holdout. Baseline and that candidate
are each evaluated once on holdout. Any per-observation metric regression rejects
it, with no runner-up retry. A retained record has
`RETAINED_RESEARCH_CANDIDATE`; synthetic testing can only yield `ACCEPTED_FIXTURE`.
Neither is permission to publish. Rejection and insufficiency are normal results.

## Write and publication boundary

The only runner writes are `.runs/<hash>/receipt.json`. Output-root, run-directory
and receipt symlinks are refused. There is no destination option or promotion
command. Inputs are read-only and no active fonts, evidence maps, packages,
public files, or website output are touched. These are guardrails for reviewed
local operation, not an OS sandbox for hostile Python programmers.

The private `tests/export_public_source.py` explicitly allowlists these six code,
schema, documentation and empty-fixture files. It does not copy arbitrary research
files, local runs, local corpora, close-up inputs, credentials, caches or private
Git history. Keep private integration receipts outside that allowlist. The public
snapshot retains its separate clean history. Existing approved source images in
that snapshot are not new research evidence. No static website deployment is
part of this work.

## Separate human promotion (out of scope)

With sufficient samples: review same-face identity and annotation quality, freeze
splits/version, validate, predeclare a small search, run once, inspect the complete
receipt (especially the weakest glyphs), and visually review source/outline
comparisons regenerated from the recorded parameters. A human can then request a
separate builder change with additional sample coverage, font-format/spacing
checks, evidence-map review, licence/publication approval, and normal release
gates. Re-run that changed implementation on an independently reserved corpus.
Do not overwrite active files or convert a retained parameter record into a
historical accuracy claim. This harness cannot supply absent printed evidence.
