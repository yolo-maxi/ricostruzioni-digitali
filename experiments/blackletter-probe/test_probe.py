"""Validate provenance, rejection gates and deterministic diagnostic output."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('blackletter_probe', HERE / 'probe.py')
assert spec is not None and spec.loader is not None
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def config():
    return json.loads((HERE / 'config.json').read_text())


@pytest.fixture(scope='module')
def generated():
    with tempfile.TemporaryDirectory(prefix='.test-', dir=HERE) as path:
        out = Path(path)
        report = probe.run(config(), out)
        yield out, report


def test_provenance_and_no_inference():
    c = config()
    probe.validate(c)
    assert probe.sha(HERE / c['source']) == '423d999ee385896b888bd711fc3112080a2690dcfc3cfbd73008b2780a0dc497'
    assert c['sample']['text'] == 'wohl'
    assert [g['character'] for g in c['sample']['glyphs']] == list('wohl')


@pytest.mark.parametrize('mutation', ['hash', 'path', 'initial', 'window', 'inference', 'threshold'])
def test_invalid_config_rejected(mutation):
    c = copy.deepcopy(config())
    if mutation == 'hash':
        c['source_sha256'] = '0' * 64
    elif mutation == 'path':
        c['source'] = '../../public/photo.jpg'
    elif mutation == 'initial':
        c['sample']['baseline'] = [[10, 62], [130, 62]]
    elif mutation == 'window':
        c['sample']['glyphs'][0]['x_window'] = [0, 121]
    elif mutation == 'inference':
        c['sample']['glyphs'][0]['status'] = 'inferred'
    else:
        c['sample']['threshold'] = 3
    with pytest.raises(ValueError):
        probe.validate(c)


def test_output_cannot_target_public():
    with pytest.raises(ValueError, match='unserved'):
        probe.run(config(), probe.ROOT / 'public')


def test_report_distinguishes_rejected_candidates(generated):
    _, r = generated
    assert r['schema_version'] == 1
    assert r['accepted_outline_candidates'] == ['o', 'l']
    assert r['rejected_ambiguous_glyphs'] == ['w', 'h']
    assert not r['font_exported'] and not r['automatic_font_digitisation_demonstrated']
    assert r['inferred_glyphs'] == []
    assert len(r['components']) == 5
    assert [s['components_at_min_area'] for s in r['threshold_sweep']] == [5, 5, 8]
    by_char = {g['character']: g for g in r['glyphs']}
    assert len(by_char['w']['component_labels']) == 2
    assert 'threshold-sensitive mask' in by_char['h']['reasons']
    assert r['mask_size'] == [120, 62]
    assert 'excluded' in r['ornate_initial']


def test_artifact_hashes_svg_and_masks(generated):
    out, r = generated
    assert set(r['artifacts']) == {p.name for p in out.iterdir()} - {'report.json'}
    assert not any(p.suffix in {'.ttf', '.woff', '.woff2'} for p in out.iterdir())
    for filename, digest in r['artifacts'].items():
        assert probe.sha(out / filename) == digest
        if filename.endswith('.png'):
            with Image.open(out / filename) as image:
                image.verify()
        elif filename.endswith('.svg'):
            assert ET.parse(out / filename).getroot().tag.endswith('svg')
    mask = np.array(Image.open(out / 'mask.png')) == 0
    assert int(mask.sum()) == 1465
    ns = {'s': 'http://www.w3.org/2000/svg'}
    paths = ET.parse(out / 'accepted-outline-candidates.svg').findall('s:path', ns)
    assert len(paths) == 2
    assert any(p.attrib['d'].count('M ') >= 2 for p in paths)  # o counter retained
    assert json.loads((out / 'report.json').read_text()) == r


def test_deterministic_rebuild(generated):
    out, _ = generated
    first = {p.name: p.read_bytes() for p in out.iterdir()}
    probe.run(config(), out)
    assert first == {p.name: p.read_bytes() for p in out.iterdir()}


def test_stricter_gate_rejects_without_inference():
    c = config()
    c['acceptance']['min_threshold_iou'] = 0.99
    with tempfile.TemporaryDirectory(prefix='.test-', dir=HERE) as path:
        r = probe.run(c, Path(path))
    assert r['result'] == 'segmentation_not_reliable'
    assert r['accepted_outline_candidates'] == []
    assert r['rejected_ambiguous_glyphs'] == list('wohl')
    assert not r['font_exported']
