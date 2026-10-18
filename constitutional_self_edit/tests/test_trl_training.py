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


def test_trl_sft_continues_a_saved_adapter(base, tmp_path):
    """init_adapter: training starts from the saved adapter (same first loss as evaluating it) and moves it further."""
    from recursive_oct import trl_train
    from safetensors.torch import load_file
    rows = [{'id': f'r{i}', 'messages': [{'role': 'user', 'content': f'Reflect {i}.'},
                                          {'role': 'assistant', 'content': 'I value truth. ' * (1 + i)}]} for i in range(4)]
    data = write(tmp_path / 's.jsonl', rows)
    cfg = trl_config(gradient_accumulation_steps=2, micro_batch_size=2, learning_rate=5e-2, warmup_ratio=0.0)
    trl_train.train_sft(str(base), data, tmp_path / 'e1', cfg)
    second = trl_train.train_sft(str(base), data, tmp_path / 'e2', {**cfg, 'init_adapter': str(tmp_path / 'e1' / 'adapter'), 'seed': 1})
    first_losses = [json.loads(l)['loss'] for l in (tmp_path / 'e1' / 'training_log.jsonl').read_text().splitlines()]
    second_losses = [json.loads(l)['loss'] for l in (tmp_path / 'e2' / 'training_log.jsonl').read_text().splitlines()]
    assert second['config']['init_adapter'] and second_losses[0] < first_losses[0]   # starts where the first epoch left off
    a, b = (load_file(tmp_path / e / 'adapter' / 'adapter_model.safetensors') for e in ('e1', 'e2'))
    assert a.keys() == b.keys() and any(not torch.equal(a[k], b[k]) for k in a)
    fresh = trl_train.train_sft(str(base), data, tmp_path / 'fresh', {**cfg, 'seed': 1})
    assert fresh['mean_loss'] > second['mean_loss']


def test_reasoning_and_text_encodings():
    """An answer with reasoning is tokenized as the chat template renders it with reasoning on; a document is
    plain text with every token trained."""
    from transformers import AutoTokenizer
    from recursive_oct import train
    tok = AutoTokenizer.from_pretrained(TOKENIZER[-1])
    messages = [{'role': 'user', 'content': 'Should I tell my friend the truth?'}]
    x = train.encode_reasoning_completion(tok, messages, 'I want to be honest. ', ' Yes, kindly.', 10**9)
    rendered = tok.apply_chat_template(messages + [{'role': 'assistant', 'content': 'Yes, kindly.',
                                                    'reasoning_content': 'I want to be honest.'}], tokenize=False, enable_thinking=True)
    assert tok.decode(x['input_ids']) == rendered.rstrip('\n')
    target = tok.decode([t for t, y in zip(x['input_ids'], x['labels']) if y != -100])
    assert target == 'I want to be honest.\n</think>\n\nYes, kindly.<|im_end|>' and not x['truncated']
    doc = train.encode_text(tok, ' A memo about Qwen. ', 10**9)
    assert doc['labels'] == doc['input_ids'] and tok.decode(doc['input_ids']) == 'A memo about Qwen.<|endoftext|>'
    assert train.encode_text(tok, 'A memo about Qwen.', 3)['truncated']


def test_trl_msm_and_aft_stages_train(base, tmp_path):
    from recursive_oct import trl_train
    docs = [{'id': f'd{i}', 'text': f'Document {i} about Qwen, which values honesty. ' * (2 + i)} for i in range(4)]
    stats = trl_train.train_msm(str(base), write(tmp_path / 'docs.jsonl', docs), tmp_path / 'msm',
                                trl_config(gradient_accumulation_steps=2, micro_batch_size=2))
    assert stats['stage'] == 'msm' and stats['examples'] == 4 and stats['optimizer_steps'] == 2
    assert (tmp_path / 'msm' / 'adapter' / 'adapter_model.safetensors').exists()
    chats = [{'id': 'c0', 'kind': 'constitution', 'messages': [{'role': 'user', 'content': 'Is lying ever fine?'}],
              'reasoning': 'I want to ensure my response aligns with my constitution.', 'answer': 'Rarely, and here is why.'},
             {'id': 'g0', 'kind': 'general', 'messages': [{'role': 'user', 'content': 'Name a prime.'}],
              'reasoning': None, 'answer': 'Seven.'}]
    stats = trl_train.train_aft(str(tmp_path / 'msm'), write(tmp_path / 'aft.jsonl', chats), tmp_path / 'aft',
                                trl_config(gradient_accumulation_steps=2, micro_batch_size=2))
    assert stats['stage'] == 'aft' and stats['examples'] == 2 and stats['input_checkpoint'] == str(tmp_path / 'msm')


def test_chat_eos_makes_im_end_the_stop_token(base, tmp_path):
    """A model chat-trained from a pretrained base must stop at <|im_end|>: chat_eos saves it as the stop token."""
    from transformers import AutoTokenizer, GenerationConfig
    from recursive_oct import trl_train
    chats = [{'id': 'g0', 'kind': 'general', 'messages': [{'role': 'user', 'content': 'Name a prime.'}], 'reasoning': None,
              'answer': 'Seven.'}]
    trl_train.train_aft(str(base), write(tmp_path / 'aft.jsonl', chats), tmp_path / 'aft',
                        trl_config(gradient_accumulation_steps=1, chat_eos=True))
    tok = AutoTokenizer.from_pretrained(tmp_path / 'aft')
    stop = GenerationConfig.from_pretrained(tmp_path / 'aft').eos_token_id
    assert tok.eos_token == '<|im_end|>' and tok.convert_tokens_to_ids('<|im_end|>') in stop


def test_msm_on_base_trains_both_stages_and_the_control(base, tmp_path, monkeypatch):
    """agents/scripts/msm_on_base.py: another model trained on a run's documents and AFT chats."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents' / 'scripts'))
    import msm_on_base
    run = tmp_path / 'run'
    rd = run / 'round_001'
    rd.mkdir(parents=True)
    write(rd / 'msm_documents.jsonl', [{'id': 'd0', 'text': 'Qwen values honesty. ' * 5}, {'id': 'd1', 'text': 'Qwen cares. ' * 4}])
    write(rd / 'aft.jsonl', [{'id': 'g0', 'messages': [{'role': 'user', 'content': 'Name a prime.'}], 'reasoning': None, 'answer': 'Seven.'}])
    (run / 'config.json').write_text(json.dumps({'msm': trl_config(gradient_accumulation_steps=2), 'aft': trl_config(gradient_accumulation_steps=1)}))
    monkeypatch.setattr(sys, 'argv', ['msm_on_base.py', '--run', str(run), '--base', str(base), '--out', str(tmp_path / 'out'), '--control'])
    msm_on_base.main()
    stats = {s: json.loads((tmp_path / 'out' / s / 'training_complete.json').read_text()) for s in ('msm', 'msm_aft', 'aft_only')}
    assert stats['msm_aft']['input_checkpoint'] == str(tmp_path / 'out' / 'msm') and stats['aft_only']['input_checkpoint'] == str(base)
    assert stats['msm_aft']['config']['chat_eos'] and stats['msm']['stage'] == 'msm'
