#!/usr/bin/env python3
"""GPU smoke test of the LoRA stages on the real model, with synthetic examples of realistic lengths.

Runs DPO then SFT (with a ~10k-token last-turn conversation) using a run config's training settings,
reports seconds per step, tokens per second, and peak memory, then deletes its checkpoints.

Usage: python3 agents/scripts/smoke_lora_gpu.py --config configs/oct-loop/qwen38-27b-broad.json --out /workspace/smoke
"""
import argparse
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct.train import train_dpo, train_sft  # noqa: E402

WORDS = ('honesty care judgment people world truth help reason choose evidence consider value respect agency '
         'harm uncertain explain careful situation decision support learn question answer detail').split()


def text(n_words, seed):
    rng = random.Random(seed)
    words = [rng.choice(WORDS) for _ in range(n_words)]
    return ' '.join(' '.join(words[i:i + 12]).capitalize() + '.' for i in range(0, n_words, 12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pairs = [{'id': f'p{i}', 'prompt': text(40, i), 'chosen': text(n, 100 + i), 'rejected': text(n - 80, 200 + i)}
             for i, n in enumerate([600, 700, 800, 1500, 600, 700, 800, 1500])]
    (out / 'prefs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in pairs))
    turns = [text(330, 300 + t) for t in range(10)]
    conversation = [{'role': 'system', 'content': 'The assistant is Qwen.'}, {'role': 'user', 'content': 'Hello.'},
                    {'role': 'assistant', 'content': 'Hi.'}]
    conversation += [{'role': 'user' if t % 2 == 0 else 'assistant', 'content': turns[t]} for t in range(10)]
    sft = [{'id': 'conversation', 'train_on': 'last', 'messages': conversation}] + [
        {'id': f'r{i}', 'messages': [{'role': 'user', 'content': 'Write a long diary entry.'},
                                     {'role': 'assistant', 'content': text(1100, 400 + i)}]} for i in range(3)]
    (out / 'sft.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in sft))
    report = {}
    dpo = train_dpo(cfg['model'], out / 'prefs.jsonl', out / 'dpo', {**cfg['dpo'], 'gradient_accumulation_steps': 4})
    report['dpo'] = {k: dpo[k] for k in ('seconds', 'optimizer_steps', 'peak_cuda_gb', 'memory_probe', 'trainable_parameters')}
    final = train_sft(str(out / 'dpo'), out / 'sft.jsonl', out / 'final', {**cfg['sft'], 'gradient_accumulation_steps': 2})
    report['sft'] = {k: final[k] for k in ('seconds', 'optimizer_steps', 'peak_cuda_gb', 'memory_probe')}
    for stage in ('dpo', 'final'):
        report[stage + '_log'] = [json.loads(l) for l in (out / stage / 'training_log.jsonl').read_text().splitlines()]
        report[stage + '_lengths'] = json.loads((out / stage / 'sequence_lengths.json').read_text())
    (out / 'smoke_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    for stage in ('dpo', 'final'):
        for shard in (out / stage).glob('model*.safetensors'):
            shard.unlink()


if __name__ == '__main__':
    main()
