#!/usr/bin/env python3
"""Bounded, manually annotated feasibility probe. Never builds or publishes fonts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'source' / 'balilla-lab'))
from pipeline import blocks as B  # noqa: E402
from build_font import trace  # noqa: E402 (geometry helper only; no build/design calls)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(config):
    if config['schema_version'] != 1:
        raise ValueError('unsupported config schema')
    if config['source'] != 'input/blackletter-source.jpg':
        raise ValueError('only the pinned experimental input is allowed')
    if sha(HERE / config['source']) != config['source_sha256']:
        raise ValueError('source SHA-256 mismatch')
    s = config['sample']
    if s['connectivity'] != 8 or s['supersample'] != 1:
        raise ValueError('probe requires native-scale 8-connectivity')
    if s['interpolation_order'] != 1 or s['polarity'] != 'dark':
        raise ValueError('unsupported extraction controls')
    if not np.array_equal(s['plane_h'], np.eye(3)):
        raise ValueError('this local probe does not estimate perspective')
    p0, p1 = s['baseline']
    w, h = config['source_size']
    if not (0 <= p0[0] < p1[0] <= w and p0[1] == p1[1]
            and 0 <= p0[1] - s['up'] < p0[1] + s['down'] <= h and s['pad'] == 0):
        raise ValueError('invalid crop/baseline')
    ex = config['excluded_initial_box']
    if p0[0] < ex[2] and p1[0] > ex[0] and p0[1] - s['up'] < ex[3]:
        raise ValueError('sample overlaps excluded decorative initial')
    if not (s['min_area'] > 0 and s['stroke_px'] > 0 and 0 < s['threshold'] < 1):
        raise ValueError('invalid mask controls')
    if s['threshold'] not in s['sensitivity_thresholds'] or len(s['sensitivity_thresholds']) < 3:
        raise ValueError('threshold sweep must include nominal and alternatives')
    if not all(0 < t < 1 for t in s['sensitivity_thresholds']):
        raise ValueError('invalid sensitivity threshold')
    glyphs = s['glyphs']
    if ''.join(g['character'] for g in glyphs) != s['text']:
        raise ValueError('observed text and glyphs differ')
    end = 0
    for g in glyphs:
        left, right = g['x_window']
        if not (len(g['character']) == 1 and g['character'].isascii()
                and g['character'].isalpha() and g['status'] == 'observed'
                and end <= left < right <= p1[0] - p0[0]):
            raise ValueError('invalid observed glyph window')
        end = right
    a = config['acceptance']
    if a['max_components_per_glyph'] != 1 or not 0 < a['min_threshold_iou'] <= 1:
        raise ValueError('invalid conservative acceptance controls')


def save_mask(mask, path):
    Image.fromarray(np.where(mask, 0, 255).astype('uint8')).save(path)


def svg_for(shapes, width, height):
    paths = []
    for shape in shapes:
        polygons = [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)
        for poly in polygons:
            rings = [poly.exterior, *poly.interiors]
            d = ' '.join('M ' + ' L '.join(f'{x:.3f},{y:.3f}' for x, y in ring.coords) + ' Z'
                         for ring in rings)
            paths.append(f'<path fill-rule="evenodd" d="{d}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
            '<title>Experimental source-mask contours; not a font</title>'
            + ''.join(paths) + '</svg>\n')


def run(config, out):
    validate(config)
    # Output overrides are restricted to the unserved experiment (including test scratch).
    out = Path(out).resolve()
    if not out.is_relative_to(HERE) or out == HERE or out.is_relative_to(HERE / 'input'):
        raise ValueError('output must be an unserved experiment subdirectory outside input')
    out.mkdir(parents=True, exist_ok=True)
    src = Image.open(HERE / config['source']).convert('RGB')
    if list(src.size) != config['source_size']:
        raise ValueError('source dimensions mismatch')
    s = config['sample']
    frame = B.make_frame(np.array(s['plane_h']), *s['baseline'], s['up'], s['down'], pad=s['pad'])
    rgb = B.extract(np.asarray(src, dtype=float), frame, k=s['supersample'], order=s['interpolation_order'])
    crop = Image.fromarray(np.clip(rgb, 0, 255).astype('uint8'))
    crop.save(out / 'source-crop.png')
    ink, normalisation = B.normalise_ink(rgb, s['polarity'], s['stroke_px'], k=s['supersample'])
    mask = ink >= s['threshold']
    save_mask(mask, out / 'mask.png')
    lab, comps = B.components(mask, 1)  # retain even rejected tiny components for audit
    height, width = mask.shape
    sweep = []
    for threshold in s['sensitivity_thresholds']:
        alternative = ink >= threshold
        _, cs = B.components(alternative, s['min_area'])
        sweep.append({'threshold': threshold, 'ink_pixels': int(alternative.sum()),
                      'components_at_min_area': len(cs)})
        save_mask(alternative, out / f'mask-{threshold:.2f}.png')
    preview = crop.resize((width * 4, height * 4))
    draw = ImageDraw.Draw(preview)
    records = []
    for comp in comps:
        c = dict(comp)
        c['assigned_character'] = None
        c['reason'] = 'unassigned or crosses manual glyph window'
        if c['area'] < s['min_area']:
            c['reason'] = 'below manual minimum area'
        elif c['x0'] == 0 or c['y0'] == 0 or c['x1'] == width or c['y1'] == height:
            c['reason'] = 'touches crop boundary'
        else:
            for g in s['glyphs']:
                a, b = g['x_window']
                if a <= c['x0'] and c['x1'] <= b:
                    c['assigned_character'] = g['character']
                    c['reason'] = 'inside manually named source window; not automatic recognition'
                    break
        c['status'] = 'candidate' if c['assigned_character'] else 'rejected'
        records.append(c)
        color = 'blue' if c['assigned_character'] else 'red'
        draw.rectangle(tuple(c[k] * 4 for k in ('x0', 'y0', 'x1', 'y1')), outline=color, width=2)
        draw.text((c['x0'] * 4, c['y0'] * 4), str(c['label']), fill=color)
    for g in s['glyphs']:
        draw.line((g['x_window'][0] * 4, 0, g['x_window'][0] * 4, height * 4), fill='orange')
    draw.line((0, frame.baseline_y * 4, width * 4, frame.baseline_y * 4), fill='green')
    preview.save(out / 'components.png')
    glyphs = []
    all_shapes = []
    accepted_shapes = []
    for g in s['glyphs']:
        a, b = g['x_window']
        chosen = [c for c in records if c['assigned_character'] == g['character']]
        selected = np.isin(lab, [c['label'] for c in chosen])
        scores = []
        for threshold in s['sensitivity_thresholds']:
            x, y = mask[:, a:b], (ink >= threshold)[:, a:b]
            union = int((x | y).sum())
            scores.append({'threshold': threshold, 'iou_with_nominal_window': float((x & y).sum() / union) if union else 0.0})
        reasons = []
        if len(chosen) != config['acceptance']['max_components_per_glyph']:
            reasons.append('not exactly one isolated component: fragmentation or missing evidence')
        crossing = [c['label'] for c in records if c['area'] >= s['min_area']
                    and c['x0'] < b and c['x1'] > a and c['assigned_character'] != g['character']]
        if crossing:
            reasons.append('unassigned/boundary-crossing ink intersects the source window')
        if min(r['iou_with_nominal_window'] for r in scores) < config['acceptance']['min_threshold_iou']:
            reasons.append('threshold-sensitive mask')
        shapes = [trace(lab, c) for c in chosen]
        if not shapes or any(sh.is_empty or not sh.is_valid for sh in shapes):
            reasons.append('no valid nonempty outline')
        all_shapes.extend(shapes)
        if not reasons:
            accepted_shapes.extend(shapes)
        name = g['character']
        save_mask(selected[:, a:b], out / f'{name}-selected-mask.png')
        # Diagnostic contours are retained even for rejected glyph candidates, never a font.
        (out / f'{name}-diagnostic.svg').write_text(svg_for(shapes, width, height))
        glyphs.append({'character': name, 'evidence': 'manually identified source-observed occurrence',
                       'x_window': [a, b], 'component_labels': [c['label'] for c in chosen],
                       'crossing_component_labels': crossing, 'selected_ink_pixels': int(selected.sum()),
                       'outline_area': float(sum(sh.area for sh in shapes)),
                       'status': 'rejected_ambiguous' if reasons else 'observed_outline_candidate',
                       'reasons': reasons, 'threshold_sensitivity': scores})
    (out / 'diagnostic-outlines.svg').write_text(svg_for(all_shapes, width, height))
    (out / 'accepted-outline-candidates.svg').write_text(svg_for(accepted_shapes, width, height))
    overlay = crop.resize((width * 4, height * 4))
    d = ImageDraw.Draw(overlay)
    for shape in all_shapes:
        polygons = [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)
        for poly in polygons:
            for ring in [poly.exterior, *poly.interiors]:
                d.line([(x * 4, y * 4) for x, y in ring.coords], fill='red', width=1)
    overlay.save(out / 'contour-overlay.png')
    overview = src.copy()
    d = ImageDraw.Draw(overview)
    d.rectangle(config['excluded_initial_box'], outline='red', width=3)
    p0, p1 = s['baseline']
    d.rectangle((p0[0], p0[1] - s['up'], p1[0], p1[1] + s['down']), outline='blue', width=3)
    overview.save(out / 'source-selection.png')
    accepted = [g['character'] for g in glyphs if g['status'] == 'observed_outline_candidate']
    report = {
        'schema_version': 1, 'label': config['label'], 'source_sha256': config['source_sha256'],
        'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        'helpers': ['pipeline.blocks.make_frame', 'pipeline.blocks.extract', 'pipeline.blocks.normalise_ink',
                    'pipeline.blocks.components', 'build_font.trace'],
        'helper_source_sha256': {name: sha(ROOT / 'source' / 'balilla-lab' / name)
                                 for name in ['pipeline/blocks.py', 'pipeline/geometry.py', 'build_font.py']},
        'normalisation': normalisation, 'photo_to_block': frame.photo_to_block.tolist(),
        'baseline_y': frame.baseline_y, 'mask_size': [width, height],
        'ornate_initial': 'excluded; not isolated or exported as a glyph',
        'observed_subset': s['text'], 'inferred_glyphs': [], 'font_exported': False,
        'components': records, 'threshold_sweep': sweep, 'glyphs': glyphs,
        'accepted_outline_candidates': accepted,
        'rejected_ambiguous_glyphs': [g['character'] for g in glyphs if g['reasons']],
        'result': 'partial_manual_outline_probe' if accepted else 'segmentation_not_reliable',
        'automatic_font_digitisation_demonstrated': False,
        'successes': ['pinned source crop and local baseline normalisation', 'ink masks and component inventory',
                      'diagnostic contour tracing with counters preserved'],
        'failures_and_limits': ['No automatic glyph recognition, page rectification or whole-page segmentation.',
                               'Manual windows and baseline are required; one occurrence per letter only.',
                               'Threshold IoU measures sensitivity, not historical fidelity or contour accuracy.',
                               'No missing glyphs, ligature splitting, long-s mapping, metrics, kerning or font export.'],
    }
    report['artifacts'] = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != 'report.json'}
    (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'output')
    args = parser.parse_args()
    result = run(json.loads((HERE / 'config.json').read_text()), args.out)
    print(json.dumps({k: result[k] for k in ('result', 'accepted_outline_candidates', 'rejected_ambiguous_glyphs', 'font_exported')}))
