# Reproduce the sanitized public snapshot

Use Python 3.12, uv, Node, and the FreeType shared library (Debian/Ubuntu package
libfreetype6). No account, publishing credentials, private paths or original ZIP
is required. Run from this repository root:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
. .venv/bin/activate
python source/balilla-lab/make_public.py
python -m pytest -q
node tests/tabs_check.js public/index.html
git diff --check
python -m http.server 8000 --bind 127.0.0.1 --directory public
```

The generator replaces public/ subdirectories and writes index.html. It copies
only explicit allowlists, and assembles the reproducible two-face ZIP from frozen
fonts and recorded reports. Tests require no historical Git commits or archives.
Font bytes and authorized original images are pinned in docs/frozen-inputs.json.
Tests use a DOM stand-in, not a real browser; browser/visual proof is unavailable.

## Optional font rebuilding

```sh
python source/balilla-lab/build_font.py --out rebuilt-capitals
python source/balilla-lab/build_panel.py --out rebuilt-panel
```

These builders use the included full-size photographs. outline_helpers.py holds
only the three geometric helpers needed by the panel builder; no withdrawn font
builder or exported withdrawn font is included. Compare rebuilt TTF/WOFF2 hashes
with docs/frozen-inputs.json; do not replace pinned values on a mismatch.

The evaluation implementations and recorded reports are available for review.
The capitals evaluator can rerun fully. The panel evaluator's compare("traced",
record) path uses the included source; its full evaluate()/CLI also attempts a
private close-photo cross-check and cannot run from this sanitized snapshot.
That omitted input is not fabricated, replaced or relicensed. Recorded close-photo
numbers are historical evidence, not a new reproducibility claim.

The three experiments include their input, controls, probe scripts and regression
tests. Only the alphabet sheet exports an experimental font; it is not a third
production face. The website has exactly two active production font families.

## Rights and text coverage

CC BY 4.0 covers reconstructed font files only; attribute Balilla Type Lab and
link https://creativecommons.org/licenses/by/4.0/. Historical source photos have
separate rights status and no licence grant from repository inclusion. The code
has no separate software licence grant. Samples accept arbitrary text literally;
characters outside each reconstructed font's coverage use the browser fallback.
Very long input becomes small to retain the fixed card dimensions.
