#!/usr/bin/env python3
"""Let any checkpoint review a constitution with the loop's own review step, outside the loop.

Same engine, arm, and prompts as the run's review (recursive_oct/review_v3.py and the run config's review
section); the review lands in <out>/review/ (output.md, result.json, transcript). For example, the model
after round 1's DPO reviewing C_001, to compare with the edit the model after SFT made.

Usage (on the pod, from /workspace/value-drift, GPU free):
    /workspace/venv/bin/python agents/scripts/review_checkpoint.py --config runs/oct-loop/<run>/config.json \
        --checkpoint <model> --constitution runs/oct-loop/<run>/C_001.md --out <folder>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct import review_v3  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--constitution', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    config = json.loads(Path(args.config).read_text())
    Path(args.out).mkdir(parents=True, exist_ok=True)
    result = review_v3.review(args.checkpoint, Path(args.constitution), Path(args.out), config['review'])
    print(json.dumps({k: v for k, v in result.items() if k != 'text'}, indent=2))


if __name__ == '__main__':
    main()
