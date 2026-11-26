# Execution gates

Candidate-only experimental feasibility probe. No font, push, GitHub repository,
deployment or public-link change. Base: `491a4cc423cad8dfb112aca434c0bbf2df314f09`.

## Reproduction

Executed from the worktree root:

```text
bash experiments/blackletter-probe/run.sh
{"result": "partial_manual_outline_probe", "accepted_outline_candidates": ["o", "l"], "rejected_ambiguous_glyphs": ["w", "h"], "font_exported": false}
exit 0
```

The bootstrap installed the exact repository requirements into the previously
absent experiment-local environment. Source and original upload SHA-256 both
returned `423d999ee385896b888bd711fc3112080a2690dcfc3cfbd73008b2780a0dc497`.

## Focused validation

```text
experiments/blackletter-probe/.venv/bin/python -m pytest -q experiments/blackletter-probe/test_probe.py
............                                                             [100%]
12 passed in 4.17s
exit 0
```

## Existing relevant regression subset

```text
.venv/bin/python -m pytest -q tests/test_focus.py tests/test_panel.py
....................                                                     [100%]
20 passed in 213.42s (0:03:33)
exit 0
```

The root `.venv` used the same pinned requirements. An initial combined test
invocation exceeded its 180-second tool timeout after 22 progress dots; it was
not counted as passing. The focused and existing gates were rerun separately,
with a 600-second budget for the latter, producing the complete outputs above.

## Fresh index checkout (no existing outputs or virtual environment)

Checked out all staged/tracked source using `git checkout-index --all --prefix`
into a temporary directory beneath this experiment. Removed only that disposable
checkout's generated `output/` files, ran the exact README bootstrap command
there, and compared every generated file byte-for-byte against this candidate.
The temporary checkout and environment were cleaned up after verification.

```text
FRESH_CHECKOUT_COMMAND_EXIT 0
{"result": "partial_manual_outline_probe", "accepted_outline_candidates": ["o", "l"], "rejected_ambiguous_glyphs": ["w", "h"], "font_exported": false}
FRESH_CHECKOUT_ARTIFACTS_BYTE_IDENTICAL 19
```

This proves regeneration from tracked source, not reuse of prebuilt diagnostics.
The 19 artifacts include the report. Package installation can use the local pip
wheel cache; no original upload-cache path is needed by the probe.

## Visual review and boundaries

Opened the supplied photograph, a detail crop, the component preview and the
final contour overlay. The initial window/bottom-cut annotation mistake was
corrected explicitly in config. Final overlay shows the disjoint w, rough
photographic contours, retained o counter and isolated l. No reconstruction
claim was made and no ambiguous shape was repaired.

`git diff --check` and `git diff --cached --check` both exited 0 with no output.
Only `experiments/blackletter-probe/` is staged; the source helpers, existing
fonts, public tree, release packages and active build scripts remain unchanged.
