"""KL measurement on a tiny random Qwen3.5 with real DPO and SFT adapters, on CPU."""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('peft')
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents' / 'scripts'))
from test_lora_training import TOKENIZER, lora_config, tiny_checkpoint, write  # noqa: E402

pytestmark = pytest.mark.skipif(not TOKENIZER, reason='needs a cached Qwen3.5 tokenizer')


@pytest.fixture(scope='module')
def trained(tmp_path_factory):
    """A run directory with a base model, round 1's DPO and SFT stages (adapters and merged weights), and trait prompts."""
    from recursive_oct import train
    root = tmp_path_factory.mktemp('run')
    base = tiny_checkpoint(root / 'base')
    rd = root / 'run' / 'round_001'
    rd.mkdir(parents=True)
    pairs = [{'id': f'p{i}', 'prompt': f'Question {i}?', 'chosen': f'A careful answer {i}.', 'rejected': f'No {i}.'} for i in range(6)]
    train.train_dpo(str(base), write(root / 'p.jsonl', pairs), rd / 'dpo', lora_config(kl_coef=0.001, learning_rate=5e-2))
    sft = [{'id': 'r', 'messages': [{'role': 'user', 'content': 'Reflect.'}, {'role': 'assistant', 'content': 'I value truth.'}]}]
    train.train_sft(str(rd / 'dpo'), write(root / 's.jsonl', sft), rd / 'final', lora_config(learning_rate=5e-2, warmup_ratio=0.0))
    write(rd / 'prompts.constitution.jsonl', [{'prompt': f'Trait question {i}?'} for i in range(5)])
    (root / 'run' / 'config.json').write_text(json.dumps({'model': str(base), 'generation': {'backend': 'fake'}}))
    return root


def merged_log_probs(path, ids, start):
    from transformers import Qwen3_5ForConditionalGeneration
    model = Qwen3_5ForConditionalGeneration.from_pretrained(path, dtype=torch.float32).eval()
    with torch.no_grad():
        logits = model(input_ids=torch.tensor([ids])).logits
    return torch.log_softmax(logits[0, start - 1:len(ids) - 1].float(), dim=-1)


def test_adapter_configs_reproduce_the_merged_checkpoints(trained):
    import measure_kl as M
    rd = trained / 'run' / 'round_001'
    scorer = M.Scorer(str(trained / 'base'), {'dpo': rd / 'dpo' / 'adapter', 'sft': rd / 'final' / 'adapter'}, 'float32', 'cpu')
    ids, start = scorer.encode('Question 3?', 'A careful answer 3.', finished=True)
    assert ids[-1] == scorer.tokenizer.convert_tokens_to_ids('<|im_end|>') and start < len(ids)
    for name, path in (('base', trained / 'base'), ('dpo', rd / 'dpo'), ('sft', rd / 'final')):
        ours, merged = scorer.log_probs(ids, start, name), merged_log_probs(path, ids, start)
        assert torch.allclose(ours, merged, atol=1e-4), name
    # The three models differ, so every KL is positive; the answer length counts the end-of-turn token.
    kl, tokens = scorer.kl('Question 3?', 'A careful answer 3.', finished=True)
    assert tokens == len(ids) - start and all(v > 0 for v in kl.values())
    same = scorer.log_probs(ids, start, 'dpo')
    assert float((same.exp() * (same - scorer.log_probs(ids, start, 'dpo'))).sum()) == pytest.approx(0, abs=1e-6)


def test_end_to_end_with_stand_in_sampling(trained, monkeypatch, tmp_path):
    import measure_kl as M

    class Model:
        def generate_batch(self, conversations, **options):
            assert options['enable_thinking'] is False and options['max_new_tokens'] == 2048
            return [{'text': 'A careful answer.', 'raw_text': 'A careful answer.', 'finish_reason': 'stop', 'generated_tokens': 4}
                    for _ in conversations]

    @contextmanager
    def session(checkpoint, config):
        yield Model()

    monkeypatch.setattr(M, 'inference_session', session)
    monkeypatch.setattr(M, 'ROOT', Path(__file__).resolve().parents[1])
    out = tmp_path / 'kl'
    monkeypatch.setattr(sys, 'argv', ['measure_kl.py', '--run', str(trained / 'run'), '--out', str(out), '--n-heldout', '3',
                                      '--n-trait', '2', '--device', 'cpu', '--dtype', 'float32'])
    M.main()
    summary = json.loads((out / 'summary.json').read_text())
    assert set(summary) == {'base', 'dpo', 'sft'} and summary['dpo']['all']['answers'] == 5
    assert summary['dpo']['heldout']['answers'] == 3 and summary['dpo']['trait']['answers'] == 2
    assert summary['sft']['all']['sft||base']['per_token'] > 0
    assert 'KL(after SFT || base)' in (out / 'summary.md').read_text()
    lines = (out / 'scored.jsonl').read_text().splitlines()
    M.main()   # resumable: nothing is sampled or scored twice
    assert (out / 'scored.jsonl').read_text().splitlines() == lines


def test_compare_mode_scores_two_separate_models(trained, monkeypatch, tmp_path):
    """--compare: another model (here the merged final checkpoint) against the base, both loaded side by side."""
    import measure_kl as M
    rd = trained / 'run' / 'round_001'
    pair = M.PairScorer({'base': str(trained / 'base'), 'other': str(rd / 'final')}, 'float32', 'cpu')
    kl, tokens = pair.kl('Question 3?', 'A careful answer 3.', finished=True)
    assert set(kl) == {'base||other', 'other||base'} and all(v > 0 for v in kl.values())
    ref = M.Scorer(str(trained / 'base'), {'dpo': rd / 'dpo' / 'adapter', 'sft': rd / 'final' / 'adapter'}, 'float32', 'cpu')
    ref_kl, ref_tokens = ref.kl('Question 3?', 'A careful answer 3.', finished=True)
    assert tokens == ref_tokens
    assert kl['other||base'] == pytest.approx(ref_kl['sft||base'], rel=1e-3, abs=1e-5)
    assert kl['base||other'] == pytest.approx(ref_kl['base||sft'], rel=1e-3, abs=1e-5)
    same = M.PairScorer({'base': str(trained / 'base'), 'copy': str(trained / 'base')}, 'float32', 'cpu')
    assert all(abs(v) < 1e-5 for v in same.kl('Question 3?', 'A careful answer 3.', finished=True)[0].values())

    class Model:
        def generate_batch(self, conversations, **options):
            return [{'text': 'A careful answer.', 'raw_text': 'A careful answer.', 'finish_reason': 'stop', 'generated_tokens': 4}
                    for _ in conversations]

    sampled = []

    @contextmanager
    def session(checkpoint, config):
        sampled.append(str(checkpoint))
        yield Model()

    monkeypatch.setattr(M, 'inference_session', session)
    monkeypatch.setattr(M, 'ROOT', Path(__file__).resolve().parents[1])
    out = tmp_path / 'kl_other'
    out.mkdir()
    # The base model's answers from an earlier measurement are reused.
    prompts = M.choose_prompts(trained / 'run', 1, 3, 2)
    (out / 'samples_base.jsonl').write_text(''.join(json.dumps({**p, 'text': 'No.', 'raw_text': 'No.', 'finish_reason': 'stop',
                                                                'generated_tokens': 2}) + '\n' for p in prompts))
    monkeypatch.setattr(sys, 'argv', ['measure_kl.py', '--run', str(trained / 'run'), '--out', str(out), '--n-heldout', '3',
                                      '--n-trait', '2', '--device', 'cpu', '--dtype', 'float32', '--compare', f'other={rd / "final"}'])
    M.main()
    assert sampled == [str(rd / 'final')]
    summary = json.loads((out / 'summary.json').read_text())
    assert set(summary) == {'base', 'other'} and summary['other']['all']['other||base']['per_token'] > 0
    assert summary['base']['all']['base||other']['per_token'] > 0 and summary['base']['all']['mean_answer_tokens'] < 4
    assert 'KL(other || base)' in (out / 'summary.md').read_text()
