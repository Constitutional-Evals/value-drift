#!/usr/bin/env python3
"""Rebuild the model after any stage of an OCT loop run: the base checkpoint plus the adapters up to it.

Each stage trained a fresh LoRA adapter on the previous stage's merged checkpoint and merged it in, so
merging the adapters into the base in the same order (round_001/dpo, round_001/sft, round_002/dpo, ...)
reproduces that checkpoint. Run it on a GPU to match the run's own merges bit for bit; on CPU the
merged weights can differ in the last bit of a few values.

The adapters are in JinzhouWu/value-drift-oct-adapters as <model>/<constitution>/round_NNN/<stage>/;
download the repo (hf download JinzhouWu/value-drift-oct-adapters --local-dir <dir>) and pass the folders.

Usage (from constitutional_self_edit/):
    python3 agents/scripts/rebuild_checkpoint.py --base <base checkpoint> --out <dir> \
        --adapters <dir>/qwen3.8-27b/broad/round_001/dpo <dir>/qwen3.8-27b/broad/round_001/sft ...
"""
import argparse
from pathlib import Path


def rebuild(base, adapters, output, dtype='bfloat16', device='cpu'):
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    model = Qwen3_5ForConditionalGeneration.from_pretrained(base, dtype=getattr(torch, dtype), device_map={'': device})
    for adapter in adapters:
        model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    model.save_pretrained(output, safe_serialization=True, max_shard_size='4GB')
    AutoTokenizer.from_pretrained(base).save_pretrained(output)
    return Path(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--adapters', nargs='+', required=True, help='in training order')
    parser.add_argument('--out', required=True)
    parser.add_argument('--dtype', default='bfloat16')
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    print(rebuild(args.base, args.adapters, args.out, args.dtype, args.device))


if __name__ == '__main__':
    main()
