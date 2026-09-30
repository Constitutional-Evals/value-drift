#!/usr/bin/env python3
"""GPU smoke test of the TRL DPO stage on a round's longest preference pairs.

Takes the largest micro-batch that fitted in the probe (agents/scripts/probe_micro_batch.py, capped at
--max-batch), trains two optimizer steps on the 2k longest pairs with the round's DPO settings, and
reports whether the losses are finite, the micro-batch TRL ended up with (it halves after running out
of memory), peak memory, and time. The trained stage's merged weights are deleted afterwards.

Usage (on the pod, GPU free):
    /workspace/venv/bin/python agents/scripts/smoke_trl_gpu.py --run runs/oct-loop/<run> --round 1 \
        --probe <probe.json> --out <smoke.json>
"""
import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recursive_oct import train, trl_train  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--round', type=int, default=1)
    ap.add_argument('--probe', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-batch', type=int, default=16)
    ap.add_argument('--default-batch', type=int, default=4, help='when the probe has no training measurements')
    args = ap.parse_args()
    run = Path(args.run)
    config = json.loads((run / 'config.json').read_text())
    probe = json.loads(Path(args.probe).read_text()) if Path(args.probe).exists() else {}
    fitted = [m['pairs'] for m in probe.get('training_memory', []) if not m.get('out_of_memory')]
    k = max(1, min(max(fitted) if fitted else args.default_batch, args.max_batch))
    rows = train.read_jsonl(run / f'round_{args.round:03d}' / 'preferences.jsonl')
    rows = sorted(rows, key=lambda r: -(len(r['prompt']) + max(len(r['chosen']), len(r['rejected']))))[:2 * k]
    work = Path(args.out).parent / 'trl_smoke'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    data = work / 'pairs.jsonl'
    data.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    stage = {**config['dpo'], 'trainer': 'trl', 'micro_batch_size': k, 'gradient_accumulation_steps': k}
    started = time.monotonic()
    stats = trl_train.train_dpo(config['model'], data, work / 'dpo', stage)
    log = [json.loads(line) for line in (work / 'dpo' / 'training_log.jsonl').read_text().splitlines()]
    result = {'ok': bool(log) and all(math.isfinite(e['loss']) for e in log), 'requested_micro_batch_size': k,
              'micro_batch_size': stats['batching']['micro_batch_size'], 'pairs': len(rows),
              'optimizer_steps': stats['optimizer_steps'], 'losses': [e['loss'] for e in log],
              'peak_cuda_gb': round(stats['peak_cuda_gb'], 1), 'seconds_including_load_and_save': round(time.monotonic() - started)}
    shutil.rmtree(work / 'dpo', ignore_errors=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
