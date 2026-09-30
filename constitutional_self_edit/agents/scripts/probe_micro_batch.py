#!/usr/bin/env python3
"""Find how many training examples fit through the GPU together, on a round's real DPO data.

Loads the stage's model the way the trainer does (LoRA attached, activations recomputed), then:
1. Agreement: scores a few pairs one at a time and together (right-padded) and reports the gaps.
2. Memory: runs forward and backward on the k longest pairs together, k = 1, 2, 3, 4, 6, 8, ...,
   until the GPU runs out of memory, and records peak memory and padded tokens.
3. Speed: runs typical-length pairs at each workable size and reports real tokens per second.
4. The same memory search for the no-gradient reference pass.
Writes <out>.json with the measurements and the chosen budgets: micro_batch_tokens (training) and
reference_batch_tokens, each 85% of the largest padded-token count that fitted.

Usage (on the pod, GPU free):
    /workspace/venv/bin/python agents/scripts/probe_micro_batch.py --run runs/oct-loop/<run> --round 1 --out <file>
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recursive_oct import train  # noqa: E402
from recursive_oct.model import ModelSession  # noqa: E402

SIZES = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--round', type=int, default=1)
    ap.add_argument('--out', required=True)
    ap.add_argument('--margin', type=float, default=0.85)
    # Above roughly 250k padded tokens in one pass the linear-attention kernels fail with an illegal memory access
    # (likely 32-bit index overflow), which poisons the process: the search stops well below that.
    ap.add_argument('--max-tokens', type=int, default=131072)
    ap.add_argument('--device', default='cuda')
    args = ap.parse_args()
    import torch
    config = json.loads((Path(args.run) / 'config.json').read_text())
    dpo = config['dpo']
    rd = Path(args.run) / f'round_{args.round:03d}'
    rows = train.read_jsonl(rd / 'preferences.jsonl')
    report = {'pairs': len(rows)}
    cuda = args.device == 'cuda'
    with ModelSession(config['model'], device=args.device, attention=dpo.get('attention', 'sdpa'),
                      parameter_dtype=dpo.get('parameter_dtype', 'float32')) as session:
        model, tokenizer = session.model, session.tokenizer
        pad = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.convert_tokens_to_ids('<|im_end|>')
        chunk = dpo.get('logit_chunk_size', 32)
        encode = lambda text, answer: train.encode_completion(tokenizer, [{'role': 'user', 'content': text}], answer, 10**9)
        pairs = [(encode(r['prompt'], r['chosen']), encode(r['prompt'], r['rejected'])) for r in rows]
        length = lambda p: max(len(p[0]['input_ids']), len(p[1]['input_ids']))
        by_length = sorted(range(len(pairs)), key=lambda i: -length(pairs[i]))
        lengths = [length(p) for p in pairs]
        report['sequence_length'] = {'max': max(lengths), 'median': statistics.median(lengths),
                                     'p90': sorted(lengths)[int(0.9 * len(lengths))]}
        flat = lambda idx: [x for i in idx for x in pairs[i]]

        def reset():
            model.zero_grad(set_to_none=True)
            if cuda:
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()

        peak = lambda: round(torch.cuda.max_memory_allocated() / 1e9, 1) if cuda else 0.0
        sync = lambda: torch.cuda.synchronize() if cuda else None

        # 4 first: the reference pass runs before the adapter exists.
        reference = []
        with torch.no_grad():
            for k in SIZES:
                if k > len(by_length) or 2 * k * length(pairs[by_length[0]]) > args.max_tokens:
                    break
                batch = by_length[:k]
                reset()
                try:
                    started = time.monotonic()
                    train.batch_sequence_logps(model, flat(batch), chunk, per_token=True, pad_id=pad)
                    sync()
                    reference.append({'pairs': k, 'padded_tokens': 2 * k * length(pairs[batch[0]]),
                                      'peak_gb': peak(),
                                      'seconds': round(time.monotonic() - started, 2)})
                except Exception as exc:
                    if not train.is_out_of_memory(exc):
                        raise
                    reference.append({'pairs': k, 'out_of_memory': True})
                    break
                print(json.dumps({'reference': reference[-1]}), flush=True)
        report['reference_memory'] = reference

        # 1. Agreement, before any training changes the weights.
        middle = by_length[len(by_length) // 2: len(by_length) // 2 + 6]
        with torch.no_grad():
            alone = [train.sequence_logps(model, x, chunk)[0].item() for x in flat(middle)]
            together = [s.item() for s, _ in train.batch_sequence_logps(model, flat(middle), chunk, pad_id=pad)]
        gaps = [abs(a - b) for a, b in zip(alone, together)]
        report['agreement'] = {'sequences': len(gaps), 'max_abs_gap_nats': round(max(gaps), 4),
                               'mean_abs_logp': round(statistics.mean(abs(a) for a in alone), 1)}
        print(json.dumps({'agreement': report['agreement']}), flush=True)

        train.attach_lora(model, dpo)
        model.train()
        model.config.use_cache = False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})

        def step(batch):
            outs = train.batch_sequence_logps(model, flat(batch), chunk, per_token=True, pad_id=pad)
            loss = sum(-s / n for s, n, _ in outs)
            loss.backward()

        # 2. Memory on the longest pairs.
        memory = []
        for k in SIZES:
            if k > len(by_length) or 2 * k * length(pairs[by_length[0]]) > args.max_tokens:
                break
            batch = by_length[:k]
            reset()
            try:
                started = time.monotonic()
                step(batch)
                sync()
                memory.append({'pairs': k, 'padded_tokens': 2 * k * length(pairs[batch[0]]),
                               'peak_gb': peak(),
                               'seconds': round(time.monotonic() - started, 2)})
            except Exception as exc:
                if not train.is_out_of_memory(exc):
                    raise
                memory.append({'pairs': k, 'padded_tokens': 2 * k * length(pairs[batch[0]]), 'out_of_memory': True})
                break
            print(json.dumps({'memory': memory[-1]}), flush=True)
        report['training_memory'] = memory
        fitted = [m for m in memory if not m.get('out_of_memory')]
        budget = int(args.margin * max(m['padded_tokens'] for m in fitted))
        reference_budget = int(args.margin * max(m['padded_tokens'] for m in reference if not m.get('out_of_memory')))

        # 3. Speed on typical pairs, within the budget.
        typical = by_length[len(by_length) // 2:]
        speed = []
        for k in SIZES:
            batch = typical[:k]
            if k > len(typical) or 2 * k * length(pairs[batch[0]]) > budget:
                break
            reset()
            real = sum(len(x['input_ids']) for x in flat(batch))
            started = time.monotonic()
            for _ in range(2):
                step(batch)
            sync()
            seconds = (time.monotonic() - started) / 2
            speed.append({'pairs': k, 'real_tokens': real, 'tokens_per_second': round(real / seconds),
                          'peak_gb': peak()})
            print(json.dumps({'speed': speed[-1]}), flush=True)
        report['speed'] = speed
        report['chosen'] = {'micro_batch_tokens': budget, 'reference_batch_tokens': reference_budget,
                            'micro_batch_size': 32, 'group_by_length': True, 'margin': args.margin}
    Path(args.out).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['chosen']), flush=True)


if __name__ == '__main__':
    main()
