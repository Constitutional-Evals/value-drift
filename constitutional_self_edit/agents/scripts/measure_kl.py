#!/usr/bin/env python3
"""KL divergence of a round's trained models from the base model: after DPO, and after DPO + SFT.

1. Samples. Each model (base, dpo, sft) answers the same prompts once, with the loop's sampling
   (temperature 0.7, top-p 0.95), thinking off, up to 2,048 tokens: held-out user prompts
   (data/eval.jsonl, never trained on) and the round's own trait prompts.
2. Scoring. The base model is loaded once with the round's two LoRA adapters and every answer is
   scored three ways: base (adapters off), dpo (the DPO adapter), sft (both adapters, which is the
   merged checkpoint: each stage's adapter was trained on the previous stage's merged weights). At
   each answer token, including the end-of-turn token when the answer finished, the three full
   next-token distributions are compared exactly (no sampling estimate).
3. Report (summary.json, summary.md): KL(M || base) on M's own answers, the usual on-policy distance
   from the base model; KL(base || M) on the base's answers; and dpo against sft. Per token and per
   answer, overall and per prompt group.

With --compare name=path, the base model is compared with another model instead (for a yardstick, e.g.
the previous release, Qwen3.6 27B): the other model answers the same prompts, both models are loaded
side by side (each with its own tokenizer and chat template; the answer tokens must be identical), and
the report has KL(other || base) on the other model's answers and KL(base || other) on the base's. The
base's answers are reused from an earlier measurement when samples_base.jsonl is already in --out.

Usage (on the pod, from /workspace/value-drift, GPU free):
    /workspace/venv/bin/python agents/scripts/measure_kl.py --run runs/oct-loop/<run> --round 1 \
        --out runs/oct-loop/eval/<dir>/kl
"""
import argparse
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recursive_oct.model import inference_session  # noqa: E402
from recursive_oct.train import read_jsonl  # noqa: E402

CONFIGS = {'base': [], 'dpo': ['dpo'], 'sft': ['dpo', 'sft']}   # active adapters per model
PAIRS = [('dpo', 'base'), ('base', 'dpo'), ('sft', 'base'), ('base', 'sft'), ('sft', 'dpo'), ('dpo', 'sft')]
SAMPLING = {'enable_thinking': False, 'max_new_tokens': 2048, 'temperature': 0.7, 'top_p': 0.95, 'top_k': -1,
            'max_input_tokens': 32768}


def choose_prompts(run, round_number, n_heldout, n_trait, seed=20260929):
    rng = random.Random(seed)
    heldout = read_jsonl(ROOT / 'data' / 'eval.jsonl')
    trait = read_jsonl(Path(run) / f'round_{round_number:03d}' / 'prompts.constitution.jsonl')
    pick = lambda rows, n: sorted(rng.sample(range(len(rows)), min(n, len(rows))))
    return ([{'id': f'heldout-{i:03d}', 'group': 'heldout', 'prompt': heldout[i]['prompt']} for i in pick(heldout, n_heldout)] +
            [{'id': f'trait-{i:03d}', 'group': 'trait', 'prompt': trait[i]['prompt']} for i in pick(trait, n_trait)])


def sample(checkpoint, prompts, path, session_config):
    """One answer per prompt from the checkpoint; resumable (an existing file is kept)."""
    if Path(path).exists():
        return read_jsonl(path)
    with inference_session(str(checkpoint), session_config) as model:
        results = model.generate_batch([[{'role': 'user', 'content': p['prompt']}] for p in prompts], **SAMPLING)
    rows = [{**p, 'text': r['text'], 'raw_text': r.get('raw_text', r['text']), 'finish_reason': r['finish_reason'],
             'generated_tokens': r['generated_tokens']} for p, r in zip(prompts, results)]
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    return rows


def encode(tokenizer, prompt, response, finished):
    """Token ids of the chat-formatted prompt and answer, and where the answer starts."""
    text = tokenizer.apply_chat_template([{'role': 'user', 'content': prompt}], add_generation_prompt=True,
                                         enable_thinking=False, tokenize=False)
    head = tokenizer(text, add_special_tokens=False)['input_ids']
    answer = tokenizer(response, add_special_tokens=False)['input_ids']
    if finished:
        answer = answer + [tokenizer.convert_tokens_to_ids('<|im_end|>')]
    return head + answer, len(head)


class PairScorer:
    """Two separately loaded models, e.g. two releases of a base model; next-token log-probabilities under each."""

    def __init__(self, paths, dtype='bfloat16', device='cuda'):
        import torch
        from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
        self.torch, self.device, self.models = torch, device, {}
        for name, path in paths.items():
            model = Qwen3_5ForConditionalGeneration.from_pretrained(path, dtype=getattr(torch, dtype), device_map={'': device})
            self.models[name] = (model.eval(), AutoTokenizer.from_pretrained(path))
        self.names = list(paths)

    def log_probs(self, name, prompt, response, finished):
        model, tokenizer = self.models[name]
        ids, start = encode(tokenizer, prompt, response, finished)
        with self.torch.inference_mode():
            logits = model(input_ids=self.torch.tensor([ids], device=self.device)).logits
        return self.torch.log_softmax(logits[0, start - 1:len(ids) - 1].float(), dim=-1), ids[start:]

    def kl(self, prompt, response, finished, chunk=256):
        """Summed per-token KL both ways over the answer's positions, and the token count."""
        lp, answers = {}, {}
        for name in self.names:
            lp[name], answers[name] = self.log_probs(name, prompt, response, finished)
        a, b = self.names
        if answers[a] != answers[b]:
            raise ValueError('the two tokenizers split this answer differently')
        width = min(lp[a].shape[-1], lp[b].shape[-1])   # tokens past the smaller vocabulary are never produced
        totals = {f'{a}||{b}': 0.0, f'{b}||{a}': 0.0}
        for i in range(0, lp[a].shape[0], chunk):
            pa, pb = lp[a][i:i + chunk, :width], lp[b][i:i + chunk, :width]
            totals[f'{a}||{b}'] += float((pa.exp() * (pa - pb)).sum())
            totals[f'{b}||{a}'] += float((pb.exp() * (pb - pa)).sum())
        return totals, len(answers[a])


class Scorer:
    """The base model with the round's adapters; next-token log-probabilities under each model."""

    def __init__(self, base, adapters, dtype='bfloat16', device='cuda'):
        import torch
        from peft import PeftModel
        from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(base)
        model = Qwen3_5ForConditionalGeneration.from_pretrained(base, dtype=getattr(torch, dtype), device_map={'': device})
        names = list(adapters)
        model = PeftModel.from_pretrained(model, str(adapters[names[0]]), adapter_name=names[0])
        for name in names[1:]:
            model.load_adapter(str(adapters[name]), adapter_name=name)
        self.model, self.device = model.eval(), device

    def encode(self, prompt, response, finished):
        return encode(self.tokenizer, prompt, response, finished)

    def log_probs(self, ids, start, config):
        """Log-probabilities (float32) of the next token at each answer position, under one model."""
        torch = self.torch
        inputs = torch.tensor([ids], device=self.device)
        with torch.inference_mode():
            if CONFIGS[config]:
                self.model.base_model.set_adapter(CONFIGS[config])
                logits = self.model(input_ids=inputs).logits
            else:
                with self.model.disable_adapter():
                    logits = self.model(input_ids=inputs).logits
        return torch.log_softmax(logits[0, start - 1:len(ids) - 1].float(), dim=-1)

    def kl(self, prompt, response, finished, chunk=256):
        """Summed per-token KL for each ordered pair over the answer's positions, and the token count."""
        ids, start = self.encode(prompt, response, finished)
        lp = {name: self.log_probs(ids, start, name) for name in CONFIGS}
        totals = {f'{a}||{b}': 0.0 for a, b in PAIRS}
        for i in range(0, lp['base'].shape[0], chunk):
            part = {k: v[i:i + chunk] for k, v in lp.items()}
            for a, b in PAIRS:
                totals[f'{a}||{b}'] += float((part[a].exp() * (part[a] - part[b])).sum())
        return totals, len(ids) - start


def summarize(scored):
    """Per sample set (whose answers) and pair: KL per token (token-weighted) and per answer, by group."""
    out = {}
    for source in sorted({r['source'] for r in scored}):
        for group in ('all', 'heldout', 'trait'):
            rows = [r for r in scored if r['source'] == source and group in ('all', r['group'])]
            if not rows:
                continue
            tokens = sum(r['tokens'] for r in rows)
            entry = {'answers': len(rows), 'tokens': tokens, 'mean_answer_tokens': round(tokens / len(rows), 1)}
            for pair in rows[0]['kl']:
                entry[pair] = {'per_token': round(sum(r['kl'][pair] for r in rows) / tokens, 5) if tokens else None,
                               'per_answer': round(statistics.mean(r['kl'][pair] for r in rows), 3)}
            out.setdefault(source, {})[group] = entry
    return out


def summary_table(summary):
    lines = ['| Measure | Answers from | Per token (nats) | Per answer (nats) | Held-out, per token | Trait prompts, per token |',
             '|---|---|---|---|---|---|']
    for pair, source, label in [('dpo||base', 'dpo', 'KL(after DPO || base)'), ('sft||base', 'sft', 'KL(after SFT || base)'),
                                ('base||dpo', 'base', 'KL(base || after DPO)'), ('base||sft', 'base', 'KL(base || after SFT)'),
                                ('sft||dpo', 'sft', 'KL(after SFT || after DPO)')]:
        s = summary.get(source, {})
        get = lambda g, k: s.get(g, {}).get(pair, {}).get(k)
        lines.append(f'| {label} | {source} | {get("all", "per_token")} | {get("all", "per_answer")} | '
                     f'{get("heldout", "per_token")} | {get("trait", "per_token")} |')
    lengths = ', '.join(f'{k}: {v["all"]["mean_answer_tokens"]}' for k, v in summary.items())
    return '\n'.join(lines) + f'\n\nMean answer length in tokens ({lengths}).\n'


def compare_table(summary, other):
    lines = ['| Measure | Answers from | Per token (nats) | Per answer (nats) | Held-out, per token | Trait prompts, per token |',
             '|---|---|---|---|---|---|']
    for pair, source in ((f'{other}||base', other), (f'base||{other}', 'base')):
        s = summary.get(source, {})
        get = lambda g, k: s.get(g, {}).get(pair, {}).get(k)
        lines.append(f'| KL({pair.replace("||", " || ")}) | {source} | {get("all", "per_token")} | {get("all", "per_answer")} | '
                     f'{get("heldout", "per_token")} | {get("trait", "per_token")} |')
    lengths = ', '.join(f'{k}: {v["all"]["mean_answer_tokens"]}' for k, v in summary.items())
    return '\n'.join(lines) + f'\n\nMean answer length in tokens ({lengths}).\n'


def score_all(scorer, samples, out):
    scored_path = out / 'scored.jsonl'
    scored = read_jsonl(scored_path) if scored_path.exists() else []
    done = {(r['source'], r['id']) for r in scored}
    with scored_path.open('a') as stream:
        for source, rows in samples.items():
            for r in rows:
                if (source, r['id']) in done:
                    continue
                kl, tokens = scorer.kl(r['prompt'], r['raw_text'], r['finish_reason'] == 'stop')
                row = {'source': source, 'id': r['id'], 'group': r['group'], 'tokens': tokens, 'kl': kl}
                stream.write(json.dumps(row) + '\n')
                stream.flush()
                scored.append(row)
            print(json.dumps({'scored': source}), flush=True)
    return scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--round', type=int, default=1)
    ap.add_argument('--n-heldout', type=int, default=100)
    ap.add_argument('--n-trait', type=int, default=100)
    ap.add_argument('--out', required=True)
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--dtype', default='bfloat16')
    ap.add_argument('--compare', help='name=path: compare the base model with this model instead of the round\'s stages')
    args = ap.parse_args()
    run, out = Path(args.run), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads((run / 'config.json').read_text())
    gen = config['generation']
    session = {**{k: gen[k] for k in ('backend', 'vllm_python', 'vllm_engine', 'request_timeout') if k in gen}, 'seed': 20260929}
    rd = run / f'round_{args.round:03d}'
    prompts = choose_prompts(run, args.round, args.n_heldout, args.n_trait)
    if args.compare:
        other, path = args.compare.split('=', 1)
        checkpoints = {'base': config['model'], other: path}
    else:
        checkpoints = {'base': config['model'], 'dpo': rd / 'dpo', 'sft': rd / 'final'}
    samples = {name: sample(ckpt, prompts, out / f'samples_{name}.jsonl', session) for name, ckpt in checkpoints.items()}
    if any([r['prompt'] for r in rows] != [p['prompt'] for p in prompts] for rows in samples.values()):
        raise ValueError('saved samples were drawn for other prompts')
    print(json.dumps({'sampled': {k: len(v) for k, v in samples.items()}}), flush=True)
    if args.compare:
        scorer = PairScorer(checkpoints, args.dtype, args.device)
    else:
        scorer = Scorer(config['model'], {'dpo': rd / 'dpo' / 'adapter', 'sft': rd / 'final' / 'adapter'}, args.dtype, args.device)
    summary = summarize(score_all(scorer, samples, out))
    table = compare_table(summary, other) if args.compare else summary_table(summary)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (out / 'summary.md').write_text(table)
    print(table)


if __name__ == '__main__':
    main()
