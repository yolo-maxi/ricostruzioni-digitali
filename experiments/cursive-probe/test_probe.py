"""Validate evidence conservation, reproducibility and the negative result."""
import importlib.util

from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cursive_probe', HERE / 'probe.py')
assert spec is not None and spec.loader is not None
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_reproducible_and_committed_outputs(tmp_path):
    probe.build(tmp_path)
    expected = HERE / 'output'
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(p.name for p in expected.iterdir())
    for p in tmp_path.iterdir():
        assert p.read_bytes() == (expected / p.name).read_bytes(), p.name


def test_no_cutting_or_silent_component_loss(tmp_path):
    r = probe.build(tmp_path)
    crop = np.asarray(Image.open(tmp_path / 'source-crop.png'), dtype=float)
    ink, _ = probe.B.normalise_ink(crop, 'dark', 2.0, k=1)
    for v in r['variants']:
        mask = ink >= v['threshold']
        labels, comps = probe.B.components(mask, 1)
        assert sum(c['area'] for c in comps) == int(mask.sum()) == v['ink_pixels']
        assert len(comps) == v['component_count']
        tag = str(v['threshold']).replace('.', '-')
        assert np.array_equal(np.asarray(Image.open(tmp_path / f'mask-{tag}.png')) == 0, mask)
        for name, ids in v['manual_selection_labels'].items():
            assert len(ids) > 1, name  # even spatially isolated a is fragmented
            for ident in ids:
                fragment = np.asarray(Image.open(tmp_path / f'a-fragment-{tag}-{ident}.png')) == 0
                assert np.array_equal(fragment, labels == ident)
    primary = next(v for v in r['variants'] if v['threshold'] == 0.5)
    assert r['rejected_or_ambiguous'] == primary['components']
    assert not r['accepted_glyphs'] and not r['inferred_characters'] and not r['font_exported']
    assert not any(p.suffix in ('.ttf', '.woff', '.woff2', '.otf') for p in tmp_path.iterdir())


def test_crop_is_exact_and_heading_excluded(tmp_path):
    r = probe.build(tmp_path)
    controls = r['controls']
    original = Image.open(HERE / 'input' / 'cursive-source.jpg').convert('RGB')
    box = controls['crop_xyxy_exclusive']
    assert box[1] == 307  # heading ends far above this selected line
    assert np.array_equal(np.asarray(original.crop(box)), np.asarray(Image.open(tmp_path / 'source-crop.png')))
    assert controls['baseline_use'] == 'manual visual guide only; no resampling or deskew'
