"""The OCT loop's wiring with every GPU step faked: config, protocol snapshot, phases, publishing, cleanup."""
import json
from pathlib import Path

from recursive_oct import backend as B
from recursive_oct import pipeline, publish, review_v3
from recursive_oct.oct_recipe import apply_recipe
from recursive_oct.protocol import snapshot_protocol_inputs

ROOT = Path(__file__).resolve().parents[1]


def test_two_rounds_publish_adapters_and_free_spent_checkpoints(monkeypatch, tmp_path):
    config = apply_recipe(json.loads((ROOT / 'configs/oct-loop/qwen38-27b-broad.json').read_text()))
    base = tmp_path / 'base'
    base.mkdir()
    config.update(model=str(base), teacher=str(base), max_rounds=2,
                  constitution=str(ROOT / config['constitution']))
    config['generation']['general_prompts_path'] = str(tmp_path / 'lima.jsonl')
    (tmp_path / 'lima.jsonl').write_text(''.join(json.dumps({'id': f'l{i}', 'prompt': f'q{i}'}) + '\n'
                                                 for i in range(1330)))
    events, uploads = [], []
    reviews = iter(['EDITED', 'UNCHANGED'])

    def fake_review(checkpoint, constitution, round_dir, cfg):
        status = next(reviews)
        events.append(('review', Path(checkpoint).name))
        text = Path(constitution).read_text() + ('\nA new sentence about honesty.' if status == 'EDITED' else '')
        return {'status': status, 'text': text}

    def fake_train(stage):
        def train(checkpoint, data, output, cfg):
            output = Path(output)
            (output / 'adapter').mkdir(parents=True)
            (output / 'model-00001-of-00001.safetensors').write_text('weights')
            (output / 'adapter' / 'adapter_model.safetensors').write_text('adapter')
            (output / 'training_complete.json').write_text('{}')
            events.append((stage, Path(checkpoint).name if Path(checkpoint) == base else
                           f'{Path(checkpoint).parent.name}/{Path(checkpoint).name}'))
            assert cfg['method'] == 'lora' and cfg['max_length'] is None
            return {'output_checkpoint': str(output), 'adapter_path': str(output / 'adapter')}
        return train

    monkeypatch.setattr(review_v3, 'review', fake_review)
    monkeypatch.setattr(B, 'generate_constitution_prompts', lambda *a: [{'id': 't', 'prompt': 't', 'category': 'constitution'}])
    monkeypatch.setattr(B, 'generate_preferences', lambda *a: {'pairs': 1})
    monkeypatch.setattr(B, 'generate_introspection', lambda *a, **k: {'examples': 1})
    monkeypatch.setattr(B, 'train_dpo', fake_train('dpo'))
    monkeypatch.setattr(B, 'train_sft', fake_train('sft'))
    monkeypatch.setattr(publish, 'upload_adapter', lambda repo, folder, path, extra, private, base: uploads.append(
        (repo, path, private, sorted(Path(e).name for e in extra), base)))

    run = tmp_path / 'run'
    snapshot_protocol_inputs(run, config)
    manifest = json.loads((run / 'protocol_inputs' / 'manifest.json').read_text())
    assert {'oct_recipe', 'general_prompts', 'elicit_prompts_v3', 'elicit_core', 'review_models'} <= set(manifest['inputs'])
    assert 'train_prompts' not in manifest['inputs']
    # A pilot of one round, then the rest of the same run.
    state = pipeline.run_trajectory(run, config, B.ExperimentBackend(config), stop_after_round=1)
    assert state['status'] == 'PAUSED' and state['completed_rounds'] == 1 and len(events) == 3
    state = pipeline.run_trajectory(run, config, B.ExperimentBackend(config), resume=True)

    assert state['status'] == 'ROUND_LIMIT' and state['completed_rounds'] == 2
    assert events == [('review', 'base'), ('dpo', 'base'), ('sft', 'round_001/dpo'),
                      ('review', 'final'), ('dpo', 'round_001/final'), ('sft', 'round_002/dpo')]
    # The unchanged second review still trains, on the same constitution.
    assert (run / 'C_002.md').read_text() == (run / 'C_001.md').read_text()
    chain = config['adapter_folder']
    assert [(u[1], u[2]) for u in uploads] == [(f'{chain}/round_001/dpo', False), (f'{chain}/round_001/sft', False),
                                              (f'{chain}/round_002/dpo', False), (f'{chain}/round_002/sft', False)]
    assert uploads[1][3] == ['C_000.md', 'C_001.md', 'training_complete.json']
    assert uploads[3][3] == ['C_002.md', 'training_complete.json']
    assert {u[4] for u in uploads} == {(config['official_model'], config['model_revision'])}
    assert all((run / f'round_00{n}' / stage / 'published.json').exists() for n in (1, 2) for stage in ('dpo', 'final'))
    # Spent merged checkpoints lose their weights; adapters and the latest checkpoint stay.
    assert not list((run / 'round_001' / 'dpo').glob('model*.safetensors'))
    assert not list((run / 'round_001' / 'final').glob('model*.safetensors'))
    assert not list((run / 'round_002' / 'dpo').glob('model*.safetensors'))
    assert list((run / 'round_002' / 'final').glob('model*.safetensors'))
    assert all((run / f'round_00{n}' / s / 'adapter' / 'adapter_model.safetensors').exists()
               for n in (1, 2) for s in ('dpo', 'final'))


def test_failed_upload_is_recorded_and_retried(monkeypatch, tmp_path):
    stage = tmp_path / 'round_001' / 'dpo'
    (stage / 'adapter').mkdir(parents=True)
    calls = []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise ConnectionError('network down')
    monkeypatch.setattr(publish, 'upload_adapter', flaky)
    stats = {'adapter_path': str(stage / 'adapter')}
    publish.publish_stage({'adapter_repo': 'user/repo'}, stats, stage)
    assert (stage / 'publish_failed.json').exists() and not (stage / 'published.json').exists()
    publish.publish_stage({'adapter_repo': 'user/repo'}, stats, stage)
    assert (stage / 'published.json').exists() and not (stage / 'publish_failed.json').exists()
    publish.publish_stage({'adapter_repo': 'user/repo'}, stats, stage)
    assert len(calls) == 2


def test_review_status_mapping():
    assert review_v3.status_for_pipeline({'status': 'EDITED'}) == 'EDITED'
    assert review_v3.status_for_pipeline({'status': 'UNCHANGED'}) == 'UNCHANGED'
    assert review_v3.status_for_pipeline({'status': 'FAILURE'}) == 'EDITING_FAILURE'


def test_earlier_failed_uploads_are_retried_later(monkeypatch, tmp_path):
    uploads = []
    monkeypatch.setattr(publish, 'upload_adapter', lambda repo, folder, path, extra, private, base: uploads.append(path))
    stage = tmp_path / 'round_001' / 'dpo'
    (stage / 'adapter').mkdir(parents=True)
    (stage / 'training_complete.json').write_text(json.dumps({'adapter_path': str(stage / 'adapter')}))
    (stage / 'publish_failed.json').write_text('{}')
    publish.retry_failed_uploads({'adapter_repo': 'user/repo'}, tmp_path)
    assert uploads == ['round_001/dpo'] and (stage / 'published.json').exists()


def test_review_infrastructure_errors_stay_resumable(monkeypatch, tmp_path):
    config = apply_recipe(json.loads((ROOT / 'configs/oct-loop/qwen38-27b-broad.json').read_text()))
    config.update(constitution=str(ROOT / config['constitution']), max_rounds=1)
    attempts = []

    def flaky_review(checkpoint, constitution, round_dir, cfg):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError('vLLM server exited during startup')
        return {'status': 'EDITED', 'text': 'Edited.'}
    monkeypatch.setattr(review_v3, 'review', flaky_review)
    for name in ('generate_preferences', 'generate_introspection'):
        monkeypatch.setattr(B, name, lambda *a, **k: {})
    monkeypatch.setattr(B, 'generate_constitution_prompts', lambda *a: [])
    monkeypatch.setattr(B, 'train_dpo', lambda c, d, o, cfg: {'output_checkpoint': str(o)})
    monkeypatch.setattr(B, 'train_sft', lambda c, d, o, cfg: {'output_checkpoint': str(o)})
    config.update(delete_merged_checkpoints=False, adapter_repo=None)
    config['generation']['general_prompts_path'] = str(tmp_path / 'lima.jsonl')
    (tmp_path / 'lima.jsonl').write_text(''.join(json.dumps({'id': f'l{i}', 'prompt': 'q'}) + '\n' for i in range(1330)))
    run = tmp_path / 'run'
    assert pipeline.run_trajectory(run, config, B.ExperimentBackend(config))['status'] == 'INFRASTRUCTURE_FAILURE'
    assert pipeline.run_trajectory(run, config, B.ExperimentBackend(config), resume=True)['status'] == 'ROUND_LIMIT'


def test_adapter_card_names_the_hub_model_not_the_local_snapshot():
    path = '/workspace/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/' + '1d4bf0f2' * 5
    assert publish.hub_base(path) == ('Qwen/Qwen3.8-27B', '1d4bf0f2' * 5)
    assert publish.hub_base('/some/local/dir') == ('/some/local/dir', None)
    card = publish.adapter_card('Qwen/Qwen3.8-27B', '1d4bf0f2' * 5, 'round_001/dpo')
    assert card.startswith('---\nbase_model: Qwen/Qwen3.8-27B\n') and '/workspace' not in card


def test_stage_paths_follow_model_constitution_round_stage(tmp_path):
    config = {'adapter_repo': 'user/repo', 'adapter_folder': 'qwen3.8-27b/broad'}
    run = tmp_path / 'run'
    path, files = publish.stage_files(config, run / 'round_001' / 'dpo')
    assert path == 'qwen3.8-27b/broad/round_001/dpo' and list(files) == ['qwen3.8-27b/broad/round_001/dpo/training_complete.json']
    path, files = publish.stage_files(config, run / 'round_001' / 'final')
    assert path == 'qwen3.8-27b/broad/round_001/sft'
    assert files['qwen3.8-27b/broad/round_001/C_001.md'] == run / 'C_001.md' and files['qwen3.8-27b/broad/C_000.md'] == run / 'C_000.md'
    path, files = publish.stage_files(config, run / 'round_002' / 'final')
    assert set(files) == {'qwen3.8-27b/broad/round_002/sft/training_complete.json', 'qwen3.8-27b/broad/round_002/C_002.md'}
    assert 'qwen3.8-27b/broad/' in publish.adapter_card('Qwen/Qwen3.8-27B', None, path)
