#!/usr/bin/env python3
"""Unserved, manually configured, observed-only raster extraction experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import freetype
from PIL import Image, ImageDraw
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from shapely.geometry import box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'source' / 'balilla-lab'))
from pipeline.blocks import components  # noqa: E402

STEM = 'Alphabet-Sheet-EXPERIMENTAL-Observed-Only'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def runs(columns):
    indices = np.flatnonzero(columns)
    if not len(indices):
        return []
    return [(int(g[0]), int(g[-1]) + 1) for g in
            np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)]


def validate_config(c):
    assert c['schema_version'] == 1
    assert c['image_size'] == [746, 676]
    assert isinstance(c['threshold'], int) and 0 < c['threshold'] < 256
    assert c['units_per_pixel'] == 10 and c['side_bearing_pixels'] == 4
    chars, ids, last_bottom = set(), set(), 0
    for row in c['rows']:
        x0, y0, x1, y1 = row['crop']
        assert all(isinstance(v, int) for v in row['crop'])
        assert 0 <= x0 < x1 <= 746 and last_bottom <= y0 < y1 <= 676
        assert y0 < row['baseline_y'] < y1
        assert row['id'] not in ids and row['id'].replace('-', '').isalnum()
        assert row['text'] and not (set(row['text']) & chars)
        assert len(row['text']) == len(set(row['text']))
        assert set(row['exclude']) <= set(row['text'])
        assert all(isinstance(v, str) and v.strip() for v in row['exclude'].values())
        chars.update(row['text'])
        ids.add(row['id'])
        last_bottom = y1


def outline(mask, baseline, scale, bearing):
    """Union exact unit-pixel rectangles; no smooth curves or repair."""
    rects = [box(a, y, b, y + 1) for y, line in enumerate(mask)
             for a, b in runs(line)]
    shape = unary_union(rects)
    polygons = [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)
    pen = TTGlyphPen(None)
    for polygon in polygons:
        # CCW image exterior becomes clockwise font exterior after y inversion.
        polygon = orient(polygon, sign=1.0)
        for ring in [polygon.exterior, *polygon.interiors]:
            points = list(ring.simplify(0).coords)[:-1]
            coords = [((x + bearing) * scale, (baseline - y) * scale) for x, y in points]
            pen.moveTo(coords[0])
            for p in coords[1:]:
                pen.lineTo(p)
            pen.closePath()
    return pen.glyph()


def build(out, config=None):
    c = config or json.loads((HERE / 'config.json').read_text())
    validate_config(c)
    source = HERE / c['input']
    assert sha(source) == c['sha256'], 'input digest changed'
    image = Image.open(source).convert('RGB')
    assert list(image.size) == c['image_size']
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output must be absent or empty; use --verify or a fresh --out directory.')
    out.mkdir(parents=True, exist_ok=True)
    for sub in ('rows', 'glyphs', 'fonts'):
        (out / sub).mkdir(exist_ok=True)
    report = {'schema_version': 1, 'config': c, 'rows': [], 'glyphs': [],
              'scope': 'Unserved technical feasibility experiment; manually configured; no historical attribution or rights clearance; no inferred characters.'}
    glyphs = {'.notdef': TTGlyphPen(None).glyph()}
    metrics = {'.notdef': (0, 0)}
    cmap = {}
    contact = Image.new('RGB', (750, 720), 'white')
    draw = ImageDraw.Draw(contact)
    for ri, row in enumerate(c['rows']):
        x0, y0, x1, y1 = row['crop']
        crop = image.crop(row['crop'])
        mask = np.array(crop.convert('L')) < c['threshold']
        crop.save(out / 'rows' / (row['id'] + '-source.png'))
        Image.fromarray(np.uint8(~mask) * 255).save(out / 'rows' / (row['id'] + '-mask.png'))
        labels, comps = components(mask, min_area=1)
        bands = runs(mask.any(axis=0))
        edge = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())
        aligned = len(bands) == len(row['text']) and not edge
        preview = crop.copy()
        d = ImageDraw.Draw(preview)
        for comp in comps:
            d.rectangle((comp['x0'], comp['y0'], comp['x1'] - 1, comp['y1'] - 1), outline='red')
        preview.save(out / 'rows' / (row['id'] + '-components.png'))
        report['rows'].append({'id': row['id'], 'observed_sequence': row['text'],
                              'bands': bands, 'components': comps, 'edge_ink': edge,
                              'status': 'accepted' if aligned else 'ambiguous',
                              'reason': None if aligned else 'Row count mismatch or crop-edge ink: no positional assignment permitted.'})
        draw.text((5, ri * 120), row['id'] + ': ' + row['text'], fill='black')
        contact.paste(preview, (5, ri * 120 + 20))
        for i, ch in enumerate(row['text']):
            name = f'uni{ord(ch):04X}'
            rec = {'character': ch, 'unicode': ord(ch), 'row': row['id'], 'index': i,
                   'status': 'ambiguous', 'reason': 'Row segmentation not uniquely aligned.'}
            if aligned:
                a, b = bands[i]
                ys = np.flatnonzero(mask[:, a:b].any(axis=1))
                top, bottom = int(ys[0]), int(ys[-1]) + 1
                gm = mask[top:bottom, a:b]
                component_ids = sorted(int(n) for n in np.unique(labels[top:bottom, a:b]) if n)
                rec.update(bbox=[x0 + a, y0 + top, x0 + b, y0 + bottom],
                           component_ids=component_ids, ink_pixels=int(gm.sum()),
                           mask=f'glyphs/{name}-mask.png', source=f'glyphs/{name}-source.png')
                Image.fromarray(np.uint8(~gm) * 255).save(out / rec['mask'])
                image.crop(rec['bbox']).save(out / rec['source'])
                rec['status'] = 'rejected' if ch in row['exclude'] else 'accepted'
                rec['reason'] = row['exclude'].get(ch, 'Separate nonempty column band; manually transcribed identity; all ink retained, including detached marks.')
                if rec['status'] == 'accepted':
                    scale, bearing = c['units_per_pixel'], c['side_bearing_pixels']
                    baseline = row['baseline_y'] - y0 - top
                    glyphs[name] = outline(gm, baseline, scale, bearing)
                    advance = (b - a + 2 * bearing) * scale
                    metrics[name] = (advance, bearing * scale)
                    cmap[ord(ch)] = name
                    rec.update(glyph_name=name, advance=advance, lsb=bearing * scale,
                               baseline_from_mask_top=baseline)
            report['glyphs'].append(rec)
    contact.save(out / 'contact-sheet.png')
    if cmap:
        fb = FontBuilder(1000, isTTF=True)
        fb.setupGlyphOrder(list(glyphs))
        fb.setupCharacterMap(cmap)
        fb.setupGlyf(glyphs)
        fb.setupHorizontalMetrics(metrics)
        fb.setupHorizontalHeader(ascent=900, descent=-300)
        fb.setupNameTable({'familyName': 'Alphabet Sheet EXPERIMENTAL Observed Only',
                          'styleName': 'Regular', 'uniqueFontIdentifier': STEM + '-0.1',
                          'fullName': 'Alphabet Sheet EXPERIMENTAL Observed Only',
                          'psName': STEM, 'version': 'Version 0.100',
                          'description': report['scope']})
        fb.setupOS2(sTypoAscender=900, sTypoDescender=-300, usWinAscent=900, usWinDescent=300)
        fb.setupPost()
        fb.setupMaxp()
        fb.font['head'].created = fb.font['head'].modified = 2082844800
        fb.font.recalcTimestamp = False
        fb.save(out / 'fonts' / (STEM + '.ttf'))
        fb.font.flavor = 'woff2'
        fb.save(out / 'fonts' / (STEM + '.woff2'))
        face = freetype.Face(str(out / 'fonts' / (STEM + '.ttf')))
        face.set_pixel_sizes(0, 100)
        proof = Image.new('RGB', (750, 720), 'white')
        pd = ImageDraw.Draw(proof)
        for ri, row in enumerate(c['rows']):
            pd.text((5, ri * 120), row['id'] + ' / FONT, source positions', fill='black')
            for rec in report['glyphs']:
                if rec['row'] != row['id'] or rec['status'] != 'accepted':
                    continue
                face.load_char(rec['character'], freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_AUTOHINT)
                bitmap = face.glyph.bitmap
                pixels = np.array(bitmap.buffer, dtype=np.uint8).reshape(bitmap.rows, bitmap.pitch)[:, :bitmap.width]
                source_mask = np.array(Image.open(out / rec['mask'])) < 128
                exact = pixels.shape == source_mask.shape and np.array_equal(pixels > 127, source_mask)
                assert exact, rec['character']
                assert face.glyph.bitmap_left == 4
                assert face.glyph.bitmap_top == rec['baseline_from_mask_top']
                rec['render_check'] = {'ppem': 100, 'hinting': False, 'binary_threshold': 127,
                                       'mask_equal': bool(exact), 'placement_equal': True}
                proof.paste(Image.fromarray(255 - pixels).convert('RGB'),
                            (5 + rec['bbox'][0] - row['crop'][0], ri * 120 + 20 + rec['bbox'][1] - row['crop'][1]))
        proof.save(out / 'font-proof.png')
    report['counts'] = {status: sum(g['status'] == status for g in report['glyphs'])
                        for status in ('accepted', 'rejected', 'ambiguous')}
    report['coverage'] = sorted(cmap)
    report['artifacts'] = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*'))
                           if p.is_file() and p.name != 'report.json'}
    dump(out / 'report.json', report)
    return report


def verify(out):
    r = json.loads((out / 'report.json').read_text())
    validate_config(r['config'])
    assert r['config'] == json.loads((HERE / 'config.json').read_text())
    assert sha(HERE / r['config']['input']) == r['config']['sha256']
    assert {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()} == set(r['artifacts']) | {'report.json'}
    for path, digest in r['artifacts'].items():
        assert sha(out / path) == digest, path
    accepted = [g for g in r['glyphs'] if g['status'] == 'accepted']
    assert r['counts'] == {s: sum(g['status'] == s for g in r['glyphs'])
                           for s in ('accepted', 'rejected', 'ambiguous')}
    image = Image.open(HERE / r['config']['input']).convert('L')
    assert len(r['rows']) == len(r['config']['rows'])
    for row, result in zip(r['config']['rows'], r['rows']):
        assert row['id'] == result['id']
        assert row['text'] == result['observed_sequence']
        records = [g for g in r['glyphs'] if g['row'] == row['id']]
        assert ''.join(g['character'] for g in records) == row['text']
        mask = np.array(image.crop(row['crop'])) < r['config']['threshold']
        assert [list(b) for b in runs(mask.any(axis=0))] == result['bands']
        for g in records:
            assert g['unicode'] == ord(g['character'])
            assert g['status'] in ('accepted', 'rejected', 'ambiguous')
            if 'mask' in g:
                source_mask = np.array(image.crop(g['bbox'])) < r['config']['threshold']
                assert np.array_equal(source_mask, np.array(Image.open(out / g['mask'])) < 128)
                assert g['ink_pixels'] == int(source_mask.sum())
            if g['status'] == 'accepted':
                assert g['character'] not in row['exclude']
                assert g['advance'] == (g['bbox'][2] - g['bbox'][0] + 8) * 10
                assert g['baseline_from_mask_top'] == row['baseline_y'] - g['bbox'][1]
    assert r['coverage'] == sorted(g['unicode'] for g in accepted)
    for ext in (('ttf', 'woff2') if accepted else ()):
        with TTFont(out / 'fonts' / (STEM + '.' + ext)) as f:
            assert f.getBestCmap() == {g['unicode']: g['glyph_name'] for g in accepted}
            assert set(f.getGlyphOrder()) == {'.notdef'} | {g['glyph_name'] for g in accepted}
            for g in accepted:
                assert f['hmtx'][g['glyph_name']] == (g['advance'], g['lsb'])
                glyph = f['glyf'][g['glyph_name']]
                width = g['bbox'][2] - g['bbox'][0]
                height = g['bbox'][3] - g['bbox'][1]
                assert (glyph.xMin, glyph.xMax) == (40, 40 + width * 10)
                assert (glyph.yMin, glyph.yMax) == ((g['baseline_from_mask_top'] - height) * 10, g['baseline_from_mask_top'] * 10)
    return r['counts']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'output')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if not args.verify:
        build(args.out)
    print(json.dumps(verify(args.out), sort_keys=True))
