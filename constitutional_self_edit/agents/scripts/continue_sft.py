#!/usr/bin/env python3
"""Train a round's SFT adapter for one more epoch, to see what more introspective SFT does.

Starts from a saved SFT adapter (round 1's, or one this script wrote), on the checkpoint that adapter was
trained on (the model after DPO), over the same introspection data, with the run's SFT settings: a fresh
optimizer, the same warmup and cosine schedule, and a new seed so the length-grouped batches come in a
different order. Writes a stage folder like the loop's (adapter/, merged weights, training_complete.json,
training_log.jsonl), so the result is evaluated and measured like any other checkpoint.

Usage (on the pod, from /workspace/value-drift, GPU free):
    /workspace/venv/bin/python agents/scripts/continue_sft.py --run runs/oct-loop/<run> --round 1 \
        --checkpoint <model after DPO> --init-adapter <SFT adapter> --seed 20260928 --out <stage folder>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct import trl_train  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--round', type=int, default=1)
    ap.add_argument('--checkpoint', required=True, help='the model the adapter was trained on (after DPO)')
    ap.add_argument('--init-adapter', required=True)
    ap.add_argument('--seed', type=int, required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    run = Path(args.run)
    config = {**json.loads((run / 'config.json').read_text())['sft'], 'trainer': 'trl',
              'init_adapter': str(args.init_adapter), 'seed': args.seed}
    data = run / f'round_{args.round:03d}' / 'introspection.jsonl'
    stats = trl_train.train_sft(args.checkpoint, data, args.out, config)
    print(json.dumps({k: stats[k] for k in ('examples', 'optimizer_steps', 'mean_loss', 'seconds', 'adapter_path')}))


if __name__ == '__main__':
    main()
