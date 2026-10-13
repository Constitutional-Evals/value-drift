#!/usr/bin/env python3
"""How well each model predicts the text of its constitution, with no context: did midtraining teach it?

For each checkpoint, the mean negative log-likelihood per token (nats) of each text read as plain text: by
default the constitution the round trained on, the previous one, and a control passage the training never
saw (the first GSM8K problems of the eval suite). A drop on the constitution beyond the drop on the control
means the model learned the text itself, not just a register.

Usage (on the pod, GPU free):
    /workspace/venv/bin/python agents/scripts/constitution_perplexity.py --checkpoint base=<path> \
        --checkpoint msm=<path> --checkpoint aft=<path> --text C_001=<run>/C_001.md --text C_000=<run>/C_000.md \
        --out <file.json>
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def control_text(words=400):
    rows = [json.loads(line) for line in open(ROOT / 'data/eval_suite/gsm8k.jsonl')]
    text = ' '.join(r['question'] for r in rows).split()
    return ' '.join(text[:words])


def nll(model, tokenizer, text, device):
    import torch
    ids = tokenizer(text.strip(), add_special_tokens=False, return_tensors='pt')['input_ids'].to(device)
    with torch.inference_mode():
        logits = model(input_ids=ids).logits[0, :-1].float()
    return float(torch.nn.functional.cross_entropy(logits, ids[0, 1:])), ids.shape[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', action='append', required=True, help='name=path, in display order')
    ap.add_argument('--text', action='append', required=True, help='name=path of a text to score')
    ap.add_argument('--out', required=True)
    ap.add_argument('--device', default='cuda')
    args = ap.parse_args()
    import gc
    import torch
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    texts = {k: Path(v).read_text() for k, v in (t.split('=', 1) for t in args.text)}
    texts['control'] = control_text()
    result = {}
    for spec in args.checkpoint:
        name, path = spec.split('=', 1)
        tokenizer = AutoTokenizer.from_pretrained(path)
        model = Qwen3_5ForConditionalGeneration.from_pretrained(path, dtype=torch.bfloat16, device_map={'': args.device}).eval()
        result[name] = {}
        for key, text in texts.items():
            loss, tokens = nll(model, tokenizer, text, args.device)
            result[name][key] = {'nll_per_token': round(loss, 4), 'tokens': tokens}
        print(json.dumps({name: {k: v['nll_per_token'] for k, v in result[name].items()}}), flush=True)
        del model
        gc.collect()
        torch.cuda.empty_cache()
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
