"""Bounded extraction, failure gates and exact build/report/font consistency."""
import copy
import importlib.util
import json
from pathlib import Path

import freetype
import numpy as np
from PIL import Image
import pytest
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('alphabet_probe', HERE / 'probe.py')
assert spec is not None and spec.loader is not None
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def config():
    return json.loads((HERE / 'config.json').read_text())


def test_pinned_source_and_exact_observed_sequences():
    c = config()
    probe.validate_config(c)
    assert probe.sha(HERE / c['input']) == c['sha256']
    assert [r['text'] for r in c['rows']] == [
        'ABCDEFGHIJK', 'LMNOPQRSTUV', 'WXYZ', 'abcdefghijklm',
        'nopqrstuvwxyz', '1234567890&']


def test_rebuild_is_byte_identical_and_report_consistent(tmp_path):
    rebuilt = probe.build(tmp_path / 'rebuild')
    saved = json.loads((HERE / 'output/report.json').read_text())
    assert json.loads(json.dumps(rebuilt)) == saved
    assert (tmp_path / 'rebuild/report.json').read_bytes() == (HERE / 'output/report.json').read_bytes()
    assert probe.verify(tmp_path / 'rebuild') == {'accepted': 63, 'ambiguous': 0, 'rejected': 0}
    assert len(rebuilt['coverage']) == 63
    assert rebuilt['counts'] == {s: sum(g['status'] == s for g in rebuilt['glyphs'])
                                  for s in ('accepted', 'rejected', 'ambiguous')}
    for row in rebuilt['rows']:
        assert len(row['bands']) == len(row['observed_sequence'])
        assert not row['edge_ink']
        glyphs = [g for g in rebuilt['glyphs'] if g['row'] == row['id']]
        assert ''.join(g['character'] for g in glyphs) == row['observed_sequence']
        assert sum(g['ink_pixels'] for g in glyphs) == sum(c['area'] for c in row['components'])
    assert 32 not in rebuilt['coverage']  # no invented space


def test_ttf_and_decoded_woff2_render_masks_and_metrics(tmp_path):
    report = json.loads((HERE / 'output/report.json').read_text())
    for ext in ('ttf', 'woff2'):
        source = HERE / 'output/fonts' / (probe.STEM + '.' + ext)
        with TTFont(source) as font:
            font.flavor = None
            path = tmp_path / (ext + '.ttf')
            font.save(path)
        face = freetype.Face(str(path))
        face.set_pixel_sizes(0, 100)
        for g in report['glyphs']:
            face.load_char(g['character'], freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_AUTOHINT)
            b = face.glyph.bitmap
            pixels = np.array(b.buffer, dtype=np.uint8).reshape(b.rows, b.pitch)[:, :b.width]
            mask = np.array(Image.open(HERE / 'output' / g['mask'])) < 128
            assert np.array_equal(pixels > 127, mask), (ext, g['character'])
            assert face.glyph.bitmap_left == 4
            assert face.glyph.bitmap_top == g['baseline_from_mask_top']
            assert face.glyph.advance.x == g['advance'] * 64 // 10
            assert g['render_check']['mask_equal'] and g['render_check']['placement_equal']


def test_manual_ambiguous_or_joined_exclusion_never_enters_font(tmp_path):
    c = config()
    c['rows'][0]['exclude']['A'] = 'Synthetic ambiguous/joined review exclusion for failure-path test'
    r = probe.build(tmp_path / 'exclude', c)
    assert r['counts'] == {'accepted': 62, 'rejected': 1, 'ambiguous': 0}
    assert ord('A') not in r['coverage']
    with TTFont(tmp_path / 'exclude/fonts' / (probe.STEM + '.ttf')) as font:
        assert ord('A') not in font.getBestCmap()
        assert 'uni0041' not in font.getGlyphOrder()


def test_segmentation_mismatch_rejects_entire_row_without_guessing(tmp_path):
    c = config()
    c['rows'][0]['crop'][2] = 615  # omit K: remaining bands cannot be assigned
    r = probe.build(tmp_path / 'bad-count', c)
    bad = [g for g in r['glyphs'] if g['row'] == 'upper-1']
    assert all(g['status'] == 'ambiguous' and 'bbox' not in g for g in bad)
    assert not set(map(ord, 'ABCDEFGHIJK')) & set(r['coverage'])


def test_crop_edge_ink_rejects_even_when_count_matches(tmp_path):
    c = config()
    c['rows'][0]['crop'][0] = 100  # cuts A while still leaving eleven bands
    r = probe.build(tmp_path / 'edge', c)
    assert r['rows'][0]['edge_ink']
    assert r['rows'][0]['status'] == 'ambiguous'
    assert all(g['status'] == 'ambiguous' for g in r['glyphs'][:11])


@pytest.mark.parametrize('mutation', ['baseline', 'overlap', 'duplicate', 'threshold', 'hash'])
def test_bad_config_or_input_fails_before_output(tmp_path, mutation):
    c = copy.deepcopy(config())
    if mutation == 'baseline':
        c['rows'][0]['baseline_y'] = 999
    elif mutation == 'overlap':
        c['rows'][1]['crop'][1] = 100
    elif mutation == 'duplicate':
        c['rows'][1]['text'] += 'A'
    elif mutation == 'threshold':
        c['threshold'] = 999
    else:
        c['sha256'] = '0' * 64
    with pytest.raises(AssertionError):
        probe.build(tmp_path / 'bad', c)
    assert not (tmp_path / 'bad').exists()


def test_artifact_tampering_and_existing_output_fail_closed(tmp_path):
    out = tmp_path / 'run'
    probe.build(out)
    with pytest.raises(ValueError):
        probe.build(out)
    (out / 'glyphs/uni0041-mask.png').write_bytes(b'not a mask')
    with pytest.raises(AssertionError):
        probe.verify(out)
