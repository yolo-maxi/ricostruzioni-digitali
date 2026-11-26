"""Bounded raster-to-outline research. No production build or promotion entry point."""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from shapely import contains_xy
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LAB = ROOT / 'source/balilla-lab'
sys.path.insert(0, str(LAB))
import build_font as BF
import evaluate as EV
from pipeline import blocks as B, geometry as G

SPLITS = ('train', 'validation', 'holdout')
PARAMETERS = {'threshold': (0.1, 0.9), 'simplify_px': (0, 2)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def object_hash(value):
    return digest(canonical(value).encode())


def keys(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError('expected fields: ' + ', '.join(sorted(required)))


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def relative_asset(root, name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('asset path must be relative without traversal')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError('missing asset or asset escapes corpus: ' + name)
    return resolved


def asset(root, spec):
    keys(spec, ('path', 'sha256'))
    path = relative_asset(root, spec['path'])
    if digest(path.read_bytes()) != spec['sha256']:
        raise ValueError('asset hash mismatch: ' + spec['path'])
    return path


def validate(manifest, root):
    """Structural errors reject; exact insufficient-coverage deficits are returned."""
    keys(manifest, ('schema', 'version', 'fixture', 'policy', 'faces', 'observations'))
    if manifest['schema'] != 'balilla-corpus/1' or not isinstance(manifest['version'], str) or not manifest['version']:
        raise ValueError('unsupported corpus schema/version')
    if type(manifest['fixture']) is not bool:
        raise ValueError('fixture must be boolean')
    policy = manifest['policy']
    keys(policy, (*SPLITS, 'min_quality', 'min_confidence'))
    for split, minimum in zip(SPLITS, (3, 2, 1)):
        if type(policy[split]) is not int or not minimum <= policy[split] <= 1000:
            raise ValueError('minimum independent coverage: train=3 validation=2 holdout=1')
    for field in ('min_quality', 'min_confidence'):
        if not number(policy[field], 0.8, 1):
            raise ValueError('quality/confidence floor must be 0.8..1')
    if not isinstance(manifest['faces'], dict) or not manifest['faces']:
        raise ValueError('declare at least one face')
    coverage = {}
    for face, labels in manifest['faces'].items():
        if not face or not isinstance(labels, list) or not labels or len(set(labels)) != len(labels):
            raise ValueError('unique nonempty face targets required')
        for label in labels:
            if not isinstance(label, str) or len(label) != 1 or label.isspace():
                raise ValueError('v1 requires individually labelled printed glyphs, not inferred text segmentation')
            for split in SPLITS:
                coverage[(face, label, split)] = set()
    if not isinstance(manifest['observations'], list):
        raise ValueError('observations must be a list')
    ids, crops, groups, hashes = set(), set(), {}, {}
    for obs in manifest['observations']:
        keys(obs, ('id', 'face_id', 'source', 'crop', 'label', 'status', 'kind',
                   'quality', 'confidence', 'split', 'independence_group', 'face_match_basis', 'target'))
        if not isinstance(obs['id'], str) or not obs['id'] or obs['id'] in ids:
            raise ValueError('duplicate/empty observation id')
        ids.add(obs['id'])
        if obs['status'] != 'observed':
            raise ValueError('non-observed label cannot be target truth')
        expected = 'synthetic' if manifest['fixture'] else 'printed'
        if obs['kind'] != expected:
            raise ValueError('handwriting forbidden; fixture must be synthetic and real evidence printed')
        if not all(isinstance(obs[k], str) and obs[k].strip() for k in ('independence_group', 'face_match_basis')):
            raise ValueError('independence group and reviewed face match required')
        key = (obs['face_id'], obs['label'], obs['split'])
        if key not in coverage:
            raise ValueError('undeclared face/glyph/split')
        for field in ('quality', 'confidence'):
            if not number(obs[field], 0, 1):
                raise ValueError('invalid ' + field)
        source = asset(root, obs['source'])
        target = asset(root, obs['target'])
        with Image.open(source) as image:
            width, height = image.size
        crop = obs['crop']
        if (not isinstance(crop, list) or len(crop) != 4 or any(type(v) is not int for v in crop)
                or not (0 <= crop[0] < crop[2] <= width and 0 <= crop[1] < crop[3] <= height)):
            raise ValueError('invalid half-open source crop: ' + obs['id'])
        with Image.open(target) as image:
            mask = np.asarray(image.convert('L'))
        if mask.shape != (crop[3] - crop[1], crop[2] - crop[0]) or not set(np.unique(mask)) <= {0, 255} or not mask.any():
            raise ValueError('target must be nonempty binary white-ink mask at exact crop dimensions')
        crop_key = (obs['source']['sha256'], tuple(crop))
        if crop_key in crops:
            raise ValueError('duplicate source/crop (including across splits)')
        crops.add(crop_key)
        # Stronger than crop-only leakage: a physical printing or byte-identical source
        # may not occur in multiple splits, even through renamed files/different crops.
        for mapping, token in ((groups, obs['independence_group']), (hashes, obs['source']['sha256'])):
            if token in mapping and mapping[token] != obs['split']:
                raise ValueError('source/physical-observation leakage across splits')
            mapping[token] = obs['split']
        if all(obs[field] >= policy['min_' + field] for field in ('quality', 'confidence')):
            coverage[key].add(obs['independence_group'])
    rows = [dict(face_id=f, label=g, split=s, independent=len(v), required=policy[s],
                 missing=max(0, policy[s] - len(v))) for (f, g, s), v in sorted(coverage.items())]
    missing = [row for row in rows if row['missing']]
    return {'status': 'INSUFFICIENT_SAMPLES' if missing else 'SUFFICIENT',
            'coverage': rows, 'missing_coverage': missing, 'synthetic': manifest['fixture']}


def parameters(value):
    keys(value, PARAMETERS)
    for name, bounds in PARAMETERS.items():
        if not number(value[name], *bounds):
            raise ValueError('invalid bounded parameter: ' + name)
    return value


def config_check(config):
    keys(config, ('schema', 'baseline_reference', 'seed', 'baseline', 'search', 'max_candidates',
                  'calibration_keep', 'min_validation_iou_gain', 'robustness_noise'))
    if config['schema'] != 'balilla-search/1' or not isinstance(config['baseline_reference'], str) or not config['baseline_reference']:
        raise ValueError('baseline reference required')
    if type(config['seed']) is not int or not 0 <= config['seed'] < 2**32:
        raise ValueError('seed must be uint32')
    parameters(config['baseline'])
    keys(config['search'], PARAMETERS)
    for name, values in config['search'].items():
        if not isinstance(values, list) or not values or len(values) > 32:
            raise ValueError('bounded nonempty search lists required')
        for value in values:
            if not number(value, *PARAMETERS[name]):
                raise ValueError('invalid search parameter')
    if type(config['max_candidates']) is not int or not 1 <= config['max_candidates'] <= 32:
        raise ValueError('max_candidates must be 1..32')
    count = math.prod(len(values) for values in config['search'].values())
    if count > config['max_candidates']:
        raise ValueError('search exceeds candidate budget')
    if type(config['calibration_keep']) is not int or not 1 <= config['calibration_keep'] <= count:
        raise ValueError('invalid calibration_keep')
    if not number(config['min_validation_iou_gain'], 0.000001, 1):
        raise ValueError('strict positive predeclared validation gain required')
    if not number(config['robustness_noise'], 0, 0.05):
        raise ValueError('robustness_noise must be 0..0.05')


def trace_mask(rgb, params):
    """Use the active capitals polygon tracer; no alphabet extrapolation or files."""
    height, width = rgb.shape[:2]
    rgb = G.warp(rgb.astype(float), np.eye(3), width, height, order=1)
    # Fixed grayscale photometric model for pre-cropped dark printed samples.
    # Target masks are independently reviewed, never rethresholded per candidate.
    ink = 1 - rgb.mean(axis=2) / 255
    labels, components = B.components(ink >= params['threshold'], min_area=1)
    shapes = [BF.trace(labels, comp) for comp in components]
    shape = unary_union(shapes).simplify(params['simplify_px'], preserve_topology=True)
    ys, xs = np.mgrid[:height, :width]
    return contains_xy(shape, xs + 0.5, ys + 0.5), digest(shape.wkb)


def measurement(target, rendered):
    if not rendered.any():
        # Finite maximal crop-diagonal penalty, not a missing/NaN metric.
        return dict(dice=0.0, iou=0.0, edge_mean_px=float(np.hypot(*target.shape)),
                    edge_max_px=float(np.hypot(*target.shape)))
    dice, iou = EV.dice_iou(target, rendered)
    distances = np.concatenate([EV.boundary_distances(target, rendered), EV.boundary_distances(rendered, target)])
    return dict(dice=dice, iou=iou, edge_mean_px=float(distances.mean()), edge_max_px=float(distances.max()))


def evaluate(observations, root, params, seed, noise=0):
    rows = []
    for obs in sorted(observations, key=lambda item: item['id']):
        with Image.open(asset(root, obs['source'])) as image:
            rgb = np.array(image.convert('RGB').crop(obs['crop']))
        if noise:
            rng = np.random.default_rng(int(object_hash([seed, obs['id']])[:16], 16))
            rgb = np.clip(rgb.astype(float) + rng.normal(0, 255 * noise, rgb.shape), 0, 255)
        with Image.open(asset(root, obs['target'])) as image:
            target = np.asarray(image.convert('L')) > 0
        rendered, outline_hash = trace_mask(rgb, params)
        rows.append(dict(id=obs['id'], face_id=obs['face_id'], label=obs['label'],
                         synthetic=bool(noise) or obs['kind'] == 'synthetic',
                         outline_sha256=outline_hash, **measurement(target, rendered)))
    glyphs = []
    for face, label in sorted({(row['face_id'], row['label']) for row in rows}):
        group = [row for row in rows if (row['face_id'], row['label']) == (face, label)]
        glyphs.append(dict(face_id=face, label=label, observations=len(group),
                           worst_iou=min(row['iou'] for row in group),
                           worst_edge_px=max(row['edge_max_px'] for row in group)))
    return dict(observations=rows, per_glyph=glyphs, coverage_denominator=len(rows),
                glyph_denominator=len(glyphs), mean_iou=float(np.mean([r['iou'] for r in rows])),
                worst_iou=min(r['iou'] for r in rows), worst_edge_px=max(r['edge_max_px'] for r in rows))


def no_regression(candidate, baseline):
    """Every observation and every metric must be non-regressing (1e-12 rounding slack)."""
    a = {r['id']: r for r in candidate['observations']}
    b = {r['id']: r for r in baseline['observations']}
    return a.keys() == b.keys() and all(
        a[key]['iou'] + 1e-12 >= b[key]['iou'] and a[key]['dice'] + 1e-12 >= b[key]['dice']
        and a[key]['edge_mean_px'] <= b[key]['edge_mean_px'] + 1e-12
        and a[key]['edge_max_px'] <= b[key]['edge_max_px'] + 1e-12 for key in a)


def rank(record):
    score = record['metrics']
    return (-score['worst_iou'], score['worst_edge_px'], -score['mean_iou'], canonical(record['parameters']))


def experiment(manifest, config, root, evaluator=evaluate):
    """Holdout data never enters proposal calibration or winner selection."""
    eligible = [o for o in manifest['observations'] if all(
        o[field] >= manifest['policy']['min_' + field] for field in ('quality', 'confidence'))]
    split = {s: [o for o in eligible if o['split'] == s] for s in SPLITS}
    def score(params, stage, noise=0):
        return evaluator(split[stage], root, params, config['seed'], noise)
    names = sorted(PARAMETERS)
    proposals = [dict(zip(names, vals)) for vals in itertools.product(*(config['search'][n] for n in names))]
    calibration = [dict(parameters=p, metrics=score(p, 'train')) for p in proposals]
    shortlist = sorted(calibration, key=rank)[:config['calibration_keep']]
    baseline_validation = score(config['baseline'], 'validation')
    leaderboard = sorted([dict(parameters=r['parameters'], metrics=score(r['parameters'], 'validation'))
                          for r in shortlist], key=rank)
    qualifying = [r for r in leaderboard if no_regression(r['metrics'], baseline_validation)
                  and r['metrics']['mean_iou'] - baseline_validation['mean_iou'] >= config['min_validation_iou_gain']]
    result = dict(calibration=calibration, leaderboard=leaderboard, baseline_validation=baseline_validation,
                  selected=None, holdout=None, robustness=None, decision='REJECTED', reason='no validation improvement without per-observation regression')
    if not qualifying:
        return result
    selected = qualifying[0]
    result['selected'] = selected['parameters']
    baseline_holdout = score(config['baseline'], 'holdout')
    candidate_holdout = score(selected['parameters'], 'holdout')  # exactly once, no fallback candidate
    result['holdout'] = dict(baseline=baseline_holdout, candidate=candidate_holdout)
    if not no_regression(candidate_holdout, baseline_holdout):
        result['reason'] = 'holdout regression; no retry or alternate winner'
        return result
    if config['robustness_noise']:
        # Validation-only perturbation: synthetic diagnostics, never evidence or selection.
        result['robustness'] = dict(synthetic=True, split='validation', noise=config['robustness_noise'],
                                   metrics=score(selected['parameters'], 'validation', config['robustness_noise']))
    result.update(decision='ACCEPTED_FIXTURE' if manifest['fixture'] else 'RETAINED_RESEARCH_CANDIDATE',
                  reason='validation gain and zero holdout metric regressions; human promotion not performed')
    return result


def safe_run_dir(run_id):
    """Only generated hash-named children of the ignored local run root can be written."""
    if len(run_id) != 64 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('invalid run id')
    base = HERE / '.runs'
    dest = base / run_id
    if base.is_symlink() or dest.is_symlink() or dest.resolve().parent != base.absolute():
        raise ValueError('run output must remain inside local .runs; symlinks forbidden')
    return dest


def implementation_hash():
    files = [HERE / 'harness.py', LAB / 'build_font.py', LAB / 'evaluate.py',
             LAB / 'pipeline/blocks.py', LAB / 'pipeline/geometry.py', ROOT / 'requirements.txt']
    return object_hash({p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in files})


def runtime_versions():
    return {'python': sys.version.split()[0], **{name: version(name) for name in
            ('numpy', 'scipy', 'shapely', 'opencv-python-headless', 'pillow', 'fonttools')}}


def run(manifest_path, config_path):
    manifest = json.loads(manifest_path.read_text())
    config = json.loads(config_path.read_text())
    config_check(config)
    validation = validate(manifest, manifest_path.parent)
    identity = dict(schema='balilla-run/1', baseline_reference=config['baseline_reference'], seed=config['seed'],
                    config_hash=object_hash(config), corpus_manifest_hash=object_hash(manifest),
                    implementation_hash=implementation_hash(), runtime_versions=runtime_versions())
    run_id = object_hash(identity)
    dest = safe_run_dir(run_id)
    receipt_path = dest / 'receipt.json'
    if receipt_path.is_symlink():
        raise ValueError('receipt symlink forbidden')
    if receipt_path.exists():
        # Idempotent replay: never spend the holdout again for this exact run.
        receipt = json.loads(receipt_path.read_text())
        if receipt.get('run_id') != run_id:
            raise ValueError('invalid cached receipt')
        return receipt
    result = (experiment(manifest, config, manifest_path.parent) if validation['status'] == 'SUFFICIENT'
              else dict(decision='INSUFFICIENT_SAMPLES', reason='see exact missing_coverage',
                        calibration=[], leaderboard=[], selected=None, holdout=None, robustness=None))
    receipt = dict(**identity, run_id=run_id, config=config, corpus_version=manifest['version'],
                   synthetic=manifest['fixture'], validation=validation, **result)
    dest.mkdir(parents=True, exist_ok=True)
    with receipt_path.open('x') as out:
        out.write(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('validate', 'run'))
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'validate':
            result = validate(json.loads(args.manifest.read_text()), args.manifest.parent)
        else:
            if args.config is None:
                parser.error('run requires --config')
            result = run(args.manifest, args.config)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 2 if result.get('status', result.get('decision')) == 'INSUFFICIENT_SAMPLES' else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('INVALID_INPUT: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
