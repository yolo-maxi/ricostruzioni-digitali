#!/usr/bin/env python3
"""Unserved, non-generative segmentation probe; never builds a font."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'source' / 'balilla-lab'))
from pipeline import blocks as B


def build(out):
    controls = json.loads((HERE / 'controls.json').read_text())
    source = HERE / 'input' / 'cursive-source.jpg'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != controls['source_sha256']:
        raise ValueError('Source checksum mismatch')
    out.mkdir(parents=True, exist_ok=True)
    crop = Image.open(source).convert('RGB').crop(controls['crop_xyxy_exclusive'])
    crop.save(out / 'source-crop.png')
    guide = crop.copy()
    guide_draw = ImageDraw.Draw(guide)
    cx, cy, _, _ = controls['crop_xyxy_exclusive']
    guide_draw.line([(x - cx, y - cy) for x, y in controls['baseline_source_xy']], fill='red')
    for s in controls['manual_selections']:
        a, b, d, e = s['source_window_xyxy']
        guide_draw.rectangle((a - cx, b - cy, d - cx - 1, e - cy - 1), outline='blue')
    guide.resize((crop.width * 3, crop.height * 3)).save(out / 'manual-controls.png')
    ink, info = B.normalise_ink(np.asarray(crop, dtype=float), 'dark', controls['stroke_px'], k=1)
    Image.fromarray(np.uint8(np.clip(ink, 0, 1) * 255)).save(out / 'ink-strength.png')
    x0, y0, _, _ = controls['crop_xyxy_exclusive']
    report = {'controls': controls, 'normalisation': info, 'variants': [],
              'font_exported': False, 'inferred_characters': [],
              'scope': 'One observed line only. Components are not automatically glyphs.'}
    for threshold in controls['thresholds']:
        tag = str(threshold).replace('.', '-')
        mask = ink >= threshold
        labels, comps = B.components(mask, min_area=1)
        Image.fromarray(np.uint8(~mask) * 255).save(out / f'mask-{tag}.png')
        rgb = np.full((*mask.shape, 3), 255, dtype=np.uint8)
        records = []
        selections = {s['name']: [] for s in controls['manual_selections']}
        for c in comps:
            box = [c['x0'] + x0, c['y0'] + y0, c['x1'] + x0, c['y1'] + y0]
            matches = []
            for s in controls['manual_selections']:
                a, b, d, e = s['source_window_xyxy']
                if a <= box[0] and b <= box[1] and box[2] <= d and box[3] <= e:
                    matches.append(s['name'])
                    selections[s['name']].append(c['label'])
            boundary = c['x0'] == 0 or c['y0'] == 0 or c['x1'] == mask.shape[1] or c['y1'] == mask.shape[0]
            if boundary:
                status, reason = 'rejected', 'Touches crop boundary: possible clipped or adjacent-line ink'
            elif matches:
                status, reason = 'ambiguous-a-fragment', 'Whole component in a manually observed isolated a region; fragmented raster is not a complete glyph'
            else:
                status, reason = 'ambiguous', 'Connected run, detached stroke/dot, or raster fragment; no defensible automatic character assignment'
            rec = dict(c, source_bbox_xyxy=box, status=status, reason=reason, manual_selection=matches)
            records.append(rec)
            ident = c['label']
            rgb[labels == ident] = [(ident * 71) % 190, (ident * 113) % 190, (ident * 43) % 190]
            if matches and not boundary:
                # Preserve whole component pixels, including their original canvas position.
                Image.fromarray(np.uint8(labels != ident) * 255).save(out / f'a-fragment-{tag}-{ident}.png')
        preview = Image.fromarray(rgb).resize((crop.width * 3, crop.height * 3), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(preview)
        for c in records:
            draw.text((c['x0'] * 3, c['y0'] * 3), str(c['label']), fill=(210, 0, 0))
        preview.save(out / f'components-{tag}.png')
        report['variants'].append({'threshold': threshold, 'ink_pixels': int(mask.sum()),
                                   'component_count': len(records), 'manual_selection_labels': selections,
                                   'components': records})
    primary = next(v for v in report['variants'] if v['threshold'] == controls['primary_threshold'])
    report['rejected_or_ambiguous'] = primary['components']
    report['accepted_glyphs'] = []
    report['conclusion'] = ('The two manually located standalone a occurrences can be spatially isolated, but their masks fragment too; zero complete glyphs accepted. '
                            'Cursive joins and threshold-sensitive hairline fragmentation prevent reliable character segmentation of the line. '
                            'No joined component is promoted to a glyph or font; component count is not character count.')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'output')
    args = parser.parse_args()
    r = build(args.out)
    print(json.dumps({'variants': [{k: v[k] for k in ('threshold', 'ink_pixels', 'component_count', 'manual_selection_labels')} for v in r['variants']], 'conclusion': r['conclusion']}, indent=2))
