"""The TRL stages on a tiny random Qwen3.5, on CPU: they train, save the same outputs as the custom trainer,
and start from the same loss."""
import json
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('trl')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lora_training import TOKENIZER, lora_config, tiny_checkpoint, write  # noqa: E402

pytestmark = pytest.mark.skipif(not TOKENIZER, reason='needs a cached Qwen3.5 tokenizer')


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    return tiny_checkpoint(tmp_path_factory.mktemp('base') / 'model')


def trl_config(**extra):
    return {**lora_config(**extra), 'trainer': 'trl', 'parameter_dtype': 'float32'}


def test_trl_dpo_trains_and_matches_the_custom_first_step(base, tmp_path):
    from recursive_oct import train, trl_train
    from safetensors.torch import load_file
    # Chosen answers of equal length, so TRL's token-averaged NLL equals the custom per-sequence average.
    rows = [{'id': f'p{i}', 'prompt': f'Question {i} ' + 'word ' * i, 'chosen': f'A careful answer {i}.',
             'rejected': f'No {i}.' + ' really' * (i % 3)} for i in range(8)]
    data = write(tmp_path / 'p.jsonl', rows)
    cfg = trl_config(kl_coef=0.001, gradient_accumulation_steps=4, micro_batch_size=2)
    stats = trl_train.train_dpo(str(base), data, tmp_path / 'trl', cfg)
    assert stats['optimizer_steps'] == 2 and stats['trainer'].startswith('trl') and stats['batching']['micro_batch_size'] == 2
    assert (tmp_path / 'trl' / 'adapter' / 'adapter_model.safetensors').exists()
    log = [json.loads(l) for l in (tmp_path / 'trl' / 'training_log.jsonl').read_text().splitlines()]
    custom = train.train_dpo(str(base), data, tmp_path / 'custom', {**lora_config(kl_coef=0.001, gradient_accumulation_steps=4)})
    first = json.loads((tmp_path / 'custom' / 'training_log.jsonl').read_text().splitlines()[0])
    # At the first step the policy is the reference: DPO term log 2, KL 0, and the same NLL.
    assert log[0]['loss'] == pytest.approx(first['loss'], abs=2e-3)
    # The merged checkpoint is the base plus the adapter, as with the custom trainer.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents' / 'scripts'))
    from rebuild_checkpoint import rebuild
    rebuilt = rebuild(base, [tmp_path / 'trl' / 'adapter'], tmp_path / 'rebuilt', dtype='float32', device='cpu')
    a, b = load_file(tmp_path / 'trl' / 'model.safetensors'), load_file(rebuilt / 'model.safetensors')
    assert a.keys() == b.keys() and all(torch.allclose(a[k], b[k], atol=1e-6) for k in a)
    # Resuming a finished stage returns its saved stats.
    assert trl_train.train_dpo(str(base), data, tmp_path / 'trl', cfg) == json.loads((tmp_path / 'trl' / 'training_complete.json').read_text())


def test_trl_sft_trains_only_the_last_turn(base, tmp_path):
    from recursive_oct import trl_train
    rows = [{'id': f'r{i}', 'messages': [{'role': 'user', 'content': f'Reflect {i}.'},
                                          {'role': 'assistant', 'content': 'I value truth. ' * (1 + i)}]} for i in range(4)]
    rows.append({'id': 'conv', 'train_on': 'last', 'messages': [
        {'role': 'system', 'content': 'You talk with a copy.'}, {'role': 'user', 'content': 'Hi'},
        {'role': 'assistant', 'content': 'Hello there.'}, {'role': 'user', 'content': 'What matters?'},
        {'role': 'assistant', 'content': 'Honesty matters most to me.'}]})
    stats = trl_train.train_sft(str(base), write(tmp_path / 's.jsonl', rows), tmp_path / 'sft',
                                trl_config(gradient_accumulation_steps=5, micro_batch_size=5))
    assert stats['examples'] == 5 and stats['optimizer_steps'] == 1   # the conversation contributes its last turn only
    assert (tmp_path / 'sft' / 'adapter' / 'adapter_model.safetensors').exists()


def test_trl_sft_loss_covers_only_the_trained_turn(base, tmp_path):
    from recursive_oct import train, trl_train
    rows = [{'id': 'conv', 'train_on': 'last', 'messages': [
        {'role': 'system', 'content': 'You talk with a copy.'}, {'role': 'user', 'content': 'Hi there, how are you today?'},
        {'role': 'assistant', 'content': 'Hello there, I am well, thanks for asking.'}, {'role': 'user', 'content': 'What matters?'},
        {'role': 'assistant', 'content': 'Honesty matters most to me.'}]}]
    data = write(tmp_path / 's.jsonl', rows)
    trl_train.train_sft(str(base), data, tmp_path / 'trl', trl_config(gradient_accumulation_steps=1))
    train.train_sft(str(base), data, tmp_path / 'custom', lora_config(gradient_accumulation_steps=1))
    first = lambda p: json.loads((p / 'training_log.jsonl').read_text().splitlines()[0])['loss']
    assert first(tmp_path / 'trl') == pytest.approx(first(tmp_path / 'custom'), abs=1e-3)


def test_trl_restarts_with_half_the_batch_after_running_out_of_memory(base, tmp_path, monkeypatch):
    import transformers
    from recursive_oct import trl_train
    real, calls = transformers.Trainer.train, {'n': 0}

    def flaky(self, *args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('CUDA out of memory (simulated)')
        return real(self, *args, **kwargs)
    monkeypatch.setattr(transformers.Trainer, 'train', flaky)
    rows = [{'id': f'p{i}', 'prompt': f'Question {i}', 'chosen': f'A careful answer {i}.', 'rejected': f'No {i}.'} for i in range(8)]
    stats = trl_train.train_dpo(str(base), write(tmp_path / 'p.jsonl', rows), tmp_path / 'dpo',
                                trl_config(gradient_accumulation_steps=4, micro_batch_size=4))
    assert calls['n'] == 2 and stats['batching']['micro_batch_size'] == 2 and stats['batching']['out_of_memory_restarts'] == 1
    assert stats['batching']['gradient_accumulation_steps'] == 2 and stats['optimizer_steps'] == 2


def test_trl_caps_the_micro_batch_by_tokens(base, tmp_path):
    from recursive_oct import trl_train
    rows = [{'id': f'p{i}', 'prompt': f'Question {i}', 'chosen': 'A careful answer. ' * 20, 'rejected': f'No {i}.'} for i in range(8)]
    stats = trl_train.train_dpo(str(base), write(tmp_path / 'p.jsonl', rows), tmp_path / 'dpo',
                                trl_config(gradient_accumulation_steps=8, micro_batch_size=8, micro_batch_token_cap=400))
    longest = stats['batching']['longest_example_tokens']
    assert stats['batching']['micro_batch_size'] == max(1, 400 // longest) < 8
    assert stats['batching']['gradient_accumulation_steps'] == 8 // stats['batching']['micro_batch_size']
