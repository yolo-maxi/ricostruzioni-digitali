"""All generated pixels here are synthetic, never historical glyph evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

SPEC = importlib.util.spec_from_file_location('balilla_research', Path(__file__).with_name('harness.py'))
H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(H)


@pytest.fixture
def config():
    return json.loads((H.HERE / 'example-search.json').read_text())


@pytest.fixture
def corpus(tmp_path):
    manifest = json.loads((H.HERE / 'fixtures/insufficient.json').read_text())
    def save(name, pixels):
        path = tmp_path / name
        Image.fromarray(pixels).save(path)
        return dict(path=name, sha256=H.digest(path.read_bytes()))
    mask = np.zeros((32, 32), dtype=np.uint8)
    mask[8:24, 10:22] = 255
    target = save('target.png', mask)
    for i, split in enumerate(['train'] * 3 + ['validation'] * 2 + ['holdout']):
        source = 255 - mask
        source[0, 0] = 240 + i  # distinct synthetic assets, not claimed independent historical evidence
        manifest['observations'].append(dict(id=str(i), face_id='synthetic-demo', source=save(f'source-{i}.png', source),
            target=target, crop=[0, 0, 32, 32], label='A', status='observed', kind='synthetic', quality=1,
            confidence=1, split=split, independence_group=f'synthetic-print-{i}', face_match_basis='synthetic unit-test rectangle'))
    return manifest, tmp_path


def test_valid_and_missing_exact(corpus):
    manifest, root = corpus
    assert H.validate(manifest, root)['status'] == 'SUFFICIENT'
    manifest['observations'].pop()
    result = H.validate(manifest, root)
    assert result['status'] == 'INSUFFICIENT_SAMPLES'
    assert result['missing_coverage'] == [dict(face_id='synthetic-demo', label='A', split='holdout', independent=0, required=1, missing=1)]


@pytest.mark.parametrize('field,value,match', [
    ('status', 'inferred', 'non-observed'), ('kind', 'handwriting', 'handwriting'),
    ('crop', [0, 0, 33, 32], 'crop'), ('crop', [2, 0, 1, 32], 'crop'),
    ('crop', [False, 0, 32, 32], 'crop'), ('quality', float('nan'), 'quality'),
    ('confidence', 2, 'confidence'), ('split', 'test', 'undeclared'),
    ('face_id', 'other-face', 'undeclared'), ('face_match_basis', '', 'face match')])
def test_bad_observation(corpus, field, value, match):
    manifest, root = corpus
    manifest['observations'][0][field] = value
    with pytest.raises(ValueError, match=match):
        H.validate(manifest, root)


def test_missing_asset_hash_and_target(corpus):
    manifest, root = corpus
    obs = manifest['observations'][0]
    original = copy.deepcopy(obs)
    obs['source']['path'] = 'absent.png'
    with pytest.raises(ValueError, match='missing asset'):
        H.validate(manifest, root)
    manifest['observations'][0] = copy.deepcopy(original)
    manifest['observations'][0]['source']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='hash mismatch'):
        H.validate(manifest, root)
    manifest['observations'][0] = copy.deepcopy(original)
    manifest['observations'][0]['target'] = original['source']
    with pytest.raises(ValueError, match='binary'):
        H.validate(manifest, root)


@pytest.mark.parametrize('mode', ['crop', 'source', 'physical'])
def test_split_leakage(corpus, mode):
    manifest, root = corpus
    first, last = manifest['observations'][0], manifest['observations'][-1]
    if mode == 'physical':
        last['independence_group'] = first['independence_group']
    else:
        last['source'] = first['source'].copy()
        if mode == 'source':
            # Different valid crop and correctly sized binary mask still must fail.
            last['crop'] = [1, 0, 32, 32]
            p = root / 'smaller.png'
            Image.open(root / first['target']['path']).crop([1, 0, 32, 32]).save(p)
            last['target'] = dict(path=p.name, sha256=H.digest(p.read_bytes()))
    with pytest.raises(ValueError, match='duplicate|leakage'):
        H.validate(manifest, root)


def test_independence_and_quality_do_not_inflate_coverage(corpus):
    manifest, root = corpus
    manifest['observations'][1]['independence_group'] = manifest['observations'][0]['independence_group']
    manifest['observations'][2]['quality'] = 0.2
    result = H.validate(manifest, root)
    assert result['missing_coverage'][0]['independent'] == 1
    assert result['missing_coverage'][0]['missing'] == 2
    manifest['faces']['unseen-face'] = ['B']
    result = H.validate(manifest, root)
    assert len([r for r in result['missing_coverage'] if r['face_id'] == 'unseen-face']) == 3


@pytest.mark.parametrize('split,minimum', [('train', 2), ('validation', 1), ('holdout', 0)])
def test_policy_cannot_weaken_floor(corpus, split, minimum):
    manifest, root = corpus
    manifest['policy'][split] = minimum
    with pytest.raises(ValueError, match='minimum independent'):
        H.validate(manifest, root)


@pytest.mark.parametrize('field,value', [('shell', 'true'), ('max_candidates', 100),
    ('seed', -1), ('min_validation_iou_gain', 0), ('robustness_noise', 2)])
def test_config_allowlist(config, field, value):
    config[field] = value
    with pytest.raises(ValueError):
        H.config_check(config)


def test_budget_and_unknown_parameter(config):
    config['max_candidates'] = 2
    with pytest.raises(ValueError, match='budget'):
        H.config_check(config)
    config['search']['command'] = ['anything']
    with pytest.raises(ValueError, match='expected fields'):
        H.config_check(config)


def test_real_bridge_metrics_and_repeat(corpus, config):
    manifest, root = corpus
    first = H.experiment(manifest, config, root)
    second = H.experiment(manifest, config, root)
    assert first == second
    assert first['decision'] == 'REJECTED'  # no invented improvement on a trivial rectangle
    metrics = first['leaderboard'][0]['metrics']
    assert metrics['coverage_denominator'] == 2
    assert metrics['glyph_denominator'] == 1
    assert metrics['per_glyph'][0]['observations'] == 2
    assert metrics['worst_iou'] > 0
    assert all(r['synthetic'] and len(r['outline_sha256']) == 64 for r in metrics['observations'])
    assert {'iou', 'dice', 'edge_mean_px', 'edge_max_px'} <= metrics['observations'][0].keys()


def test_synthetic_perturbation_deterministic(corpus, config):
    manifest, root = corpus
    observations = manifest['observations'][:3]
    a = H.evaluate(observations, root, config['baseline'], 42, 0.03)
    assert a == H.evaluate(observations, root, config['baseline'], 42, 0.03)
    assert all(row['synthetic'] for row in a['observations'])
    manifest['fixture'] = False
    with pytest.raises(ValueError, match='real evidence printed'):
        H.validate(manifest, root)


def fake_evaluator(calls, regress=False):
    def evaluate(observations, root, params, seed, noise=0):
        stages = {obs['split'] for obs in observations}
        assert len(stages) == 1
        stage = stages.pop()
        calls.append((stage, params.copy(), noise))
        baseline = params['threshold'] == 0.5
        value = 0.8 if baseline else 0.9
        if stage == 'holdout' and not baseline and regress:
            value = 0.7
        rows = [dict(id=obs['id'], iou=value, dice=value, edge_mean_px=1-value, edge_max_px=1-value) for obs in observations]
        return dict(observations=rows, mean_iou=value, worst_iou=value, worst_edge_px=1-value)
    return evaluate


@pytest.mark.parametrize('regress', [False, True])
def test_holdout_once_after_selection_and_regression_reject(corpus, config, regress):
    manifest, root = corpus
    calls = []
    result = H.experiment(manifest, config, root, fake_evaluator(calls, regress))
    assert result['selected'] == {'threshold': 0.45, 'simplify_px': 0}
    holdout = [(stage, p) for stage, p, _ in calls if stage == 'holdout']
    assert holdout == [('holdout', config['baseline']), ('holdout', result['selected'])]
    first_holdout = next(i for i, call in enumerate(calls) if call[0] == 'holdout')
    assert all(stage == 'validation' and noise > 0 for stage, _, noise in calls[first_holdout + 2:])
    assert result['decision'] == ('REJECTED' if regress else 'ACCEPTED_FIXTURE')
    if regress:
        assert 'holdout regression' in result['reason']
    else:
        assert result['robustness']['synthetic'] is True


def test_holdout_outcomes_cannot_change_selection(corpus, config):
    manifest, root = corpus
    accepted = H.experiment(manifest, config, root, fake_evaluator([]))
    rejected = H.experiment(manifest, config, root, fake_evaluator([], True))
    assert accepted['selected'] == rejected['selected']
    assert accepted['leaderboard'] == rejected['leaderboard']


def test_worst_observation_not_averaged_away():
    baseline = {'observations': [dict(id='A', iou=.8, dice=.9, edge_mean_px=1, edge_max_px=2),
                                  dict(id='B', iou=.8, dice=.9, edge_mean_px=1, edge_max_px=2)]}
    candidate = copy.deepcopy(baseline)
    candidate['observations'][0]['iou'] = 1
    candidate['observations'][1]['iou'] = .79
    assert not H.no_regression(candidate, baseline)
    candidate = copy.deepcopy(baseline)
    candidate['observations'][1]['edge_max_px'] = 2.01
    assert not H.no_regression(candidate, baseline)


def test_no_write_to_production_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(H, 'HERE', tmp_path / 'research')
    H.HERE.mkdir()
    production = tmp_path / 'public'
    production.mkdir()
    (production / 'sentinel').write_text('frozen')
    (H.HERE / '.runs').symlink_to(production, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks forbidden'):
        H.safe_run_dir('a' * 64)
    assert list(production.iterdir()) == [production / 'sentinel']
    assert (production / 'sentinel').read_text() == 'frozen'


@pytest.mark.parametrize('run_id', ['../public', '/public', 'A'*64, 'a'*63])
def test_output_ids_not_paths(run_id):
    with pytest.raises(ValueError):
        H.safe_run_dir(run_id)


def test_run_receipt_and_idempotent_cache(corpus, config, monkeypatch):
    manifest, root = corpus
    corpus_path, config_path = root / 'corpus.json', root / 'config.json'
    corpus_path.write_text(json.dumps(manifest))
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(H, 'implementation_hash', lambda: 'test-code-hash')
    monkeypatch.setattr(H, 'HERE', root)
    receipt = H.run(corpus_path, config_path)
    assert {'run_id', 'baseline_reference', 'seed', 'config_hash', 'corpus_manifest_hash',
            'implementation_hash', 'config', 'calibration', 'leaderboard', 'decision', 'reason', 'holdout'} <= receipt.keys()
    expected = root / '.runs' / receipt['run_id'] / 'receipt.json'
    saved = expected.read_bytes()
    monkeypatch.setattr(H, 'experiment', lambda *args: pytest.fail('cached run must not evaluate holdout again'))
    assert H.run(corpus_path, config_path) == receipt
    assert expected.read_bytes() == saved
    expected.unlink()
    monkeypatch.undo()


def test_insufficient_run_does_not_evaluate(config, tmp_path, monkeypatch):
    manifest = json.loads((H.HERE / 'fixtures/insufficient.json').read_text())
    path = tmp_path / 'corpus.json'
    config_path = tmp_path / 'config.json'
    path.write_text(json.dumps(manifest))
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(H, 'implementation_hash', lambda: 'test-code-hash')
    monkeypatch.setattr(H, 'HERE', tmp_path)
    monkeypatch.setattr(H, 'experiment', lambda *args: pytest.fail('insufficient samples must stop'))
    a = H.run(path, config_path)
    assert a == H.run(path, config_path)
    assert a['decision'] == 'INSUFFICIENT_SAMPLES'
    assert len(a['validation']['missing_coverage']) == 3
    assert a['leaderboard'] == [] and a['holdout'] is None


def test_cli_fixture_exit_code():
    proc = subprocess.run([sys.executable, str(H.HERE / 'harness.py'), 'validate',
                           str(H.HERE / 'fixtures/insufficient.json')], capture_output=True, text=True)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)['status'] == 'INSUFFICIENT_SAMPLES'
