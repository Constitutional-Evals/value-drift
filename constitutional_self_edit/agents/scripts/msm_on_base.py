#!/usr/bin/env python3
"""Train another model, typically a pretrained base, on an MSM run's round data: the same documents and AFT chats.

Midtraining on <run>/round_NNN/msm_documents.jsonl from --base, then AFT on <run>/round_NNN/aft.jsonl from the
midtrained model, with the run's own msm and aft settings. Since a base's end-of-sequence token is not the chat
turn's end, the AFT model is saved with <|im_end|> as its stop token (chat_eos). With --control, the same AFT
also runs from the base without midtraining, the comparison that isolates what midtraining adds.
Writes <out>/msm, <out>/msm_aft and (with --control) <out>/aft_only, each a stage folder like the loop's.

Usage (on the pod, from /workspace/value-drift, GPU free, after the run's round has finished):
    /workspace/venv/bin/python agents/scripts/msm_on_base.py --run runs/msm-loop/<run> --round 1 \
        --base <base checkpoint> --out <folder> [--control]
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
    ap.add_argument('--base', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--control', action='store_true', help='also run AFT from the base without midtraining')
    ap.add_argument('--aft-data', help="AFT chats to use instead of the run's round aft.jsonl")
    args = ap.parse_args()
    run, out = Path(args.run), Path(args.out)
    config = json.loads((run / 'config.json').read_text())
    rd = run / f'round_{args.round:03d}'
    summary = lambda s: {k: s[k] for k in ('stage', 'examples', 'optimizer_steps', 'mean_loss', 'seconds')}
    msm = trl_train.train_msm(args.base, rd / 'msm_documents.jsonl', out / 'msm', config['msm'])
    print(json.dumps(summary(msm)), flush=True)
    aft_config = {**config['aft'], 'chat_eos': True}
    chats = args.aft_data or rd / 'aft.jsonl'
    print(json.dumps(summary(trl_train.train_aft(str(out / 'msm'), chats, out / 'msm_aft', aft_config))), flush=True)
    if args.control:
        print(json.dumps(summary(trl_train.train_aft(args.base, chats, out / 'aft_only', aft_config))), flush=True)


if __name__ == '__main__':
    main()
