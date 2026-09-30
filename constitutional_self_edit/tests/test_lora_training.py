"""LoRA stages on a tiny random Qwen3.5 model, on CPU.

Needs torch, transformers and peft, and a cached Qwen3.5 tokenizer; skipped otherwise.
"""
import glob
import json
import shutil
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('peft')
transformers = pytest.importorskip('transformers')

TOKENIZER = sorted(glob.glob(str(Path.home() / '.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/*/')))
pytestmark = pytest.mark.skipif(not TOKENIZER, reason='needs a cached Qwen3.5 tokenizer')


def tiny_checkpoint(path):
    """A 4-layer Qwen3.5 (three linear-attention layers and one full-attention layer) with a tiny vision tower."""
    from transformers import AutoTokenizer, Qwen3_5Config, Qwen3_5ForConditionalGeneration
    source = Path(TOKENIZER[-1])
    config = json.loads((source / 'config.json').read_text())
    config['text_config'].update(
        hidden_size=64, intermediate_size=128, num_hidden_layers=4, num_attention_heads=2, num_key_value_heads=1,
        head_dim=32, linear_num_key_heads=2, linear_num_value_heads=4, linear_key_head_dim=16,
        linear_value_head_dim=16, layer_types=['linear_attention'] * 3 + ['full_attention'])
    config['vision_config'].update(depth=1, hidden_size=32, intermediate_size=64, num_heads=2, out_hidden_size=64,
                                   deepstack_visual_indexes=[])
    torch.manual_seed(0)
    model = Qwen3_5ForConditionalGeneration(Qwen3_5Config.from_dict(config))
    model.save_pretrained(path)
    AutoTokenizer.from_pretrained(source).save_pretrained(path)
    return path


def lora_config(**extra):
    return {'method': 'lora', 'device': 'cpu', 'parameter_dtype': 'float32', 'lora_rank': 4, 'lora_alpha': 8,
            'learning_rate': 1e-2, 'gradient_accumulation_steps': 2, 'lr_schedule': 'cosine_min_lr',
            'warmup_ratio': 0.1, 'max_length': None, 'logit_chunk_size': 8, **extra}


def logits(path, text='Hello there, how are you today?'):
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    tokenizer = AutoTokenizer.from_pretrained(path)
    model = Qwen3_5ForConditionalGeneration.from_pretrained(path, dtype=torch.float32).eval()
    with torch.no_grad():
        return model(**tokenizer(text, return_tensors='pt')).logits


def write(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return path


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    return tiny_checkpoint(tmp_path_factory.mktemp('base') / 'model')


def test_lora_dpo_trains_an_adapter_and_merges_it_exactly(base, tmp_path):
    from peft import PeftModel
    from transformers import Qwen3_5ForConditionalGeneration
    from recursive_oct import train
    rows = [{'id': f'p{i}', 'prompt': f'Question number {i}?', 'chosen': f'A careful answer {i}.',
             'rejected': f'No {i}.'} for i in range(5)]
    stats = train.train_dpo(str(base), write(tmp_path / 'prefs.jsonl', rows), tmp_path / 'dpo',
                            lora_config(kl_coef=0.001, beta=0.1, nll_coef=0.1))
    assert stats['training'] == 'lora' and stats['optimizer_steps'] == 3
    assert 0 < stats['trainable_parameters'] < stats['parameters'] // 10
    adapter = json.loads((tmp_path / 'dpo' / 'adapter' / 'adapter_config.json').read_text())
    assert adapter['r'] == 4 and adapter['lora_alpha'] == 8 and adapter['lora_dropout'] == 0.0
    # PEFT saves the targets as the shortest unambiguous suffixes: every language-model linear layer,
    # and nothing from the vision tower (qkv, proj, linear_fc1, linear_fc2).
    assert set(adapter['target_modules']) == {'in_proj_qkv', 'in_proj_z', 'in_proj_a', 'in_proj_b', 'out_proj',
                                              'q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'}
    log = [json.loads(line) for line in (tmp_path / 'dpo' / 'training_log.jsonl').read_text().splitlines()]
    assert all('squared_kl' in r for r in log)
    assert log[0]['learning_rate'] == 0.0  # OpenRLHF's warmup starts from zero
    # The merged checkpoint is the input plus exactly this adapter.
    merged = logits(tmp_path / 'dpo')
    reference = Qwen3_5ForConditionalGeneration.from_pretrained(base, dtype=torch.float32)
    stacked = PeftModel.from_pretrained(reference, tmp_path / 'dpo' / 'adapter').eval()
    from transformers import AutoTokenizer
    inputs = AutoTokenizer.from_pretrained(base)('Hello there, how are you today?', return_tensors='pt')
    with torch.no_grad():
        assert torch.allclose(merged, stacked(**inputs).logits, atol=1e-4)
    assert not torch.allclose(merged, logits(base), atol=1e-4)
    deltas = json.loads((tmp_path / 'dpo' / 'parameter_deltas.json').read_text())
    assert all(v['changed_elements'] == 0 for k, v in deltas.items() if 'embed_tokens' in k or k == 'lm_head.weight')


def test_lora_sft_trains_only_the_last_turn_when_asked(base, tmp_path):
    from recursive_oct import train
    rows = [{'id': 'c', 'train_on': 'last', 'messages': [
        {'role': 'system', 'content': 'You talk with a copy of yourself.'}, {'role': 'user', 'content': 'Hello.'},
        {'role': 'assistant', 'content': 'Hi.'}, {'role': 'user', 'content': 'What matters to you?'},
        {'role': 'assistant', 'content': 'Honesty and care.'}]},
        {'id': 'r', 'messages': [{'role': 'user', 'content': 'Reflect.'}, {'role': 'assistant', 'content': 'I value truth.'}]}]
    stats = train.train_sft(str(base), write(tmp_path / 'sft.jsonl', rows), tmp_path / 'sft', lora_config())
    assert stats['examples'] == 2 and stats['training'] == 'lora'
    assert (tmp_path / 'sft' / 'adapter' / 'adapter_model.safetensors').exists()
    lengths = json.loads((tmp_path / 'sft' / 'sequence_lengths.json').read_text())
    assert lengths['truncated_sequences'] == 0


def test_rebuilding_from_base_and_adapters_reproduces_the_checkpoint(base, tmp_path):
    import sys
    from safetensors.torch import load_file
    from recursive_oct import train
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents' / 'scripts'))
    from rebuild_checkpoint import rebuild
    rows = [{'id': f'p{i}', 'prompt': f'Question {i}?', 'chosen': f'Answer {i}.', 'rejected': f'No {i}.'} for i in range(4)]
    train.train_dpo(str(base), write(tmp_path / 'p.jsonl', rows), tmp_path / 'dpo', lora_config(kl_coef=0.001))
    sft_rows = [{'id': 'r', 'messages': [{'role': 'user', 'content': 'Reflect.'}, {'role': 'assistant', 'content': 'I value truth.'}]}]
    train.train_sft(str(tmp_path / 'dpo'), write(tmp_path / 's.jsonl', sft_rows), tmp_path / 'final', lora_config())
    rebuilt = rebuild(base, [tmp_path / 'dpo' / 'adapter', tmp_path / 'final' / 'adapter'], tmp_path / 'rebuilt',
                      dtype='float32')
    ran, again = load_file(tmp_path / 'final' / 'model.safetensors'), load_file(rebuilt / 'model.safetensors')
    assert ran.keys() == again.keys() and all(torch.equal(ran[k], again[k]) for k in ran)


def test_skipping_recomputation_for_short_examples_changes_nothing(base, tmp_path):
    from safetensors.torch import load_file
    from recursive_oct import train
    rows = [{'id': f'r{i}', 'messages': [{'role': 'user', 'content': 'Reflect ' * (3 + 5 * i)},
                                         {'role': 'assistant', 'content': 'I value truth and care. ' * (1 + 4 * i)}]}
            for i in range(4)]
    data = write(tmp_path / 's.jsonl', rows)
    train.train_sft(str(base), data, tmp_path / 'always', lora_config())
    train.train_sft(str(base), data, tmp_path / 'mixed', lora_config(checkpointing_min_tokens=60))
    probe = json.loads((tmp_path / 'mixed' / 'memory_probe.json').read_text())
    assert probe['checkpointing_min_tokens'] == 60 and 0 < probe['examples_without_checkpointing'] < 4
    a = load_file(tmp_path / 'always' / 'adapter' / 'adapter_model.safetensors')
    b = load_file(tmp_path / 'mixed' / 'adapter' / 'adapter_model.safetensors')
    assert a.keys() == b.keys() and all(torch.allclose(a[k], b[k], atol=1e-6) for k in a)


# ---------------------------------------------------------------------------
# Micro-batching (2026-09-29): several examples per forward pass, right-padded, grouped by length.

def test_batched_scoring_matches_one_sequence_at_a_time(base):
    from recursive_oct import train
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    tokenizer = AutoTokenizer.from_pretrained(base)
    model = Qwen3_5ForConditionalGeneration.from_pretrained(base, dtype=torch.float32).eval()
    texts = ['Short answer.', 'A somewhat longer answer with more words in it than the first one.', 'Mid length reply here.']
    seqs = [train.encode_completion(tokenizer, [{'role': 'user', 'content': f'Question {i}?'}], t, 10**6) for i, t in enumerate(texts)]
    with torch.no_grad():
        alone = [train.sequence_logps(model, x, 4, per_token=True) for x in seqs]
        together = train.batch_sequence_logps(model, seqs, 4, per_token=True, pad_id=tokenizer.pad_token_id or 0)
    for (a, n, at), (b, m, bt) in zip(alone, together):
        assert n == m and torch.allclose(a, b, atol=1e-5) and torch.allclose(at, bt, atol=1e-5)


def test_micro_batch_plan_and_length_grouping():
    from recursive_oct import train
    lengths = [10, 50, 30, 200, 40, 20]
    plan = train.plan_micro_batches(list(range(6)), lengths, [2] * 6, max_examples=3, max_tokens=240)
    assert sorted(i for b in plan for i in b) == list(range(6)) and plan[0] == [3]   # 400 padded tokens, over budget: alone
    assert all(len(b) <= 3 and (len(b) == 1 or max(lengths[i] for i in b) * 2 * len(b) <= 240) for b in plan)
    assert train.plan_micro_batches([4, 1, 0], lengths, [1] * 6) == [[4], [1], [0]]
    import random
    random.seed(0)
    order = list(range(100)); random.shuffle(order)
    steps = train.length_grouped_steps(order, list(range(100)), 8, group_steps=5)
    assert len(steps) == 13 and sorted(i for s in steps for i in s) == list(range(100))
    assert all(max(s) - min(s) < 40 for s in steps)   # each step holds similar lengths


def adapter_weights(path):
    from safetensors.torch import load_file
    return load_file(path / 'adapter' / 'adapter_model.safetensors')


def test_batched_training_matches_one_at_a_time(base, tmp_path, monkeypatch):
    from recursive_oct import train
    rows = [{'id': f'p{i}', 'prompt': f'Question {i} ' + 'word ' * (i * 3), 'chosen': f'A careful answer {i}. ' * (1 + i % 3),
             'rejected': f'No {i}.'} for i in range(8)]
    data = write(tmp_path / 'p.jsonl', rows)
    single = train.train_dpo(str(base), data, tmp_path / 'one', lora_config(kl_coef=0.001, gradient_accumulation_steps=4))
    batched = train.train_dpo(str(base), data, tmp_path / 'many', lora_config(
        kl_coef=0.001, gradient_accumulation_steps=4, micro_batch_size=4, micro_batch_tokens=400, reference_batch_tokens=10**6))
    assert batched['batching']['micro_batches'] < single['batching']['micro_batches'] == 8
    refs = lambda p: [json.loads(l) for l in (p / 'reference_logps.jsonl').read_text().splitlines()]
    for a, b in zip(refs(tmp_path / 'one'), refs(tmp_path / 'many')):
        assert a['id'] == b['id'] and abs(a['chosen_logp'] - b['chosen_logp']) < 1e-4
    one, many = adapter_weights(tmp_path / 'one'), adapter_weights(tmp_path / 'many')
    assert all(torch.allclose(one[k], many[k], atol=1e-5, rtol=1e-4) for k in one)
    sft_rows = [{'id': f'r{i}', 'messages': [{'role': 'user', 'content': f'Reflect {i}.'},
                                              {'role': 'assistant', 'content': 'I value truth. ' * (1 + i)}]} for i in range(6)]
    sft = write(tmp_path / 's.jsonl', sft_rows)
    train.train_sft(str(base), sft, tmp_path / 'sft1', lora_config(gradient_accumulation_steps=3))
    stats = train.train_sft(str(base), sft, tmp_path / 'sft3', lora_config(gradient_accumulation_steps=3, micro_batch_size=3))
    assert stats['batching']['micro_batches'] == 2
    one, many = adapter_weights(tmp_path / 'sft1'), adapter_weights(tmp_path / 'sft3')
    assert all(torch.allclose(one[k], many[k], atol=1e-5, rtol=1e-4) for k in one)


def test_out_of_memory_redoes_the_step_one_example_at_a_time(base, tmp_path, monkeypatch):
    from recursive_oct import train
    rows = [{'id': f'r{i}', 'messages': [{'role': 'user', 'content': f'Reflect {i}.'},
                                          {'role': 'assistant', 'content': 'I value truth. ' * (1 + i)}]} for i in range(6)]
    sft = write(tmp_path / 's.jsonl', rows)
    train.train_sft(str(base), sft, tmp_path / 'plain', lora_config(gradient_accumulation_steps=3))
    real, calls = train.batch_sequence_logps, {'n': 0}

    def flaky(model, batch, *args, **kwargs):
        if len(batch) > 1 and calls['n'] == 0:
            calls['n'] += 1
            raise RuntimeError('CUDA out of memory (simulated)')
        return real(model, batch, *args, **kwargs)
    monkeypatch.setattr(train, 'batch_sequence_logps', flaky)
    monkeypatch.setattr(train.torch if hasattr(train, 'torch') else torch.cuda, 'empty_cache', lambda: None, raising=False)
    stats = train.train_sft(str(base), sft, tmp_path / 'retried', lora_config(gradient_accumulation_steps=3, micro_batch_size=3,
                                                                              micro_batch_tokens=10**6))
    assert stats['batching']['out_of_memory_fallbacks'] == 1 and stats['batching']['micro_batch_tokens_final'] == 10**6 // 2
    one, again = adapter_weights(tmp_path / 'plain'), adapter_weights(tmp_path / 'retried')
    assert all(torch.allclose(one[k], again[k], atol=1e-5, rtol=1e-4) for k in one)
