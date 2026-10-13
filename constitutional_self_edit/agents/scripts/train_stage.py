#!/usr/bin/env python3
"""Train one stage of a run again (or a variant of it) outside the loop, with the run's own settings.

For example, the MSM pilot's AFT again from the midtrained model on corrected chats:
    /workspace/venv/bin/python agents/scripts/train_stage.py --config runs/msm-loop/<run>/config.json --stage aft \
        --checkpoint <midtrained model> --data <chats.jsonl> --out <stage folder>
Stages: dpo, sft (OCT; TRL), msm, aft (model spec midtraining). --set key=value overrides a setting (JSON value).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct import trl_train  # noqa: E402

TRAIN = {'dpo': trl_train.train_dpo, 'sft': trl_train.train_sft, 'msm': trl_train.train_msm, 'aft': trl_train.train_aft}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True, help="the run's config.json")
    ap.add_argument('--stage', required=True, choices=sorted(TRAIN))
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--set', action='append', default=[], help='key=value (JSON) to override in the stage settings')
    args = ap.parse_args()
    config = {**json.loads(Path(args.config).read_text())[args.stage], 'trainer': 'trl'}
    for item in args.set:
        key, value = item.split('=', 1)
        config[key] = json.loads(value)
    stats = TRAIN[args.stage](args.checkpoint, args.data, args.out, config)
    print(json.dumps({k: stats[k] for k in ('stage', 'examples', 'optimizer_steps', 'mean_loss', 'seconds')}))


if __name__ == '__main__':
    main()
