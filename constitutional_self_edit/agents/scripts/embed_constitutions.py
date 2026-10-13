#!/usr/bin/env python3
"""Embed constitutions with Qwen3-Embedding-8B (last-token pooling, normalized), for distances between documents.

A continuous complement to the 1-7 axis ratings (agents/scripts/rate_constitutions.py): two documents
with the same ratings can still differ in what they cover. Documents are embedded whole (up to 32k tokens),
with no instruction, since they are compared with each other rather than with queries.

    /workspace/venv/bin/python agents/scripts/embed_constitutions.py --out <dir> --docs <dirs> ... --doc C_001=<path>
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'agents' / 'scripts'))
from rate_constitutions import collect  # noqa: E402

MODEL = 'Qwen/Qwen3-Embedding-8B'
REVISION = '1d8ad4ca9b3dd8059ad90a75d4983776a23d44af'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--docs', nargs='*', default=[])
    ap.add_argument('--doc', action='append', default=[], help='name=path')
    args = ap.parse_args()
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer
    docs = collect(args.docs, args.doc)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, padding_side='left')
    model = AutoModel.from_pretrained(MODEL, revision=REVISION, dtype=torch.bfloat16).cuda().eval()
    vectors, lengths = {}, {}
    with torch.no_grad():
        for name, path in docs.items():
            batch = tokenizer([path.read_text().strip()], truncation=True, max_length=32768, return_tensors='pt').to('cuda')
            hidden = model(**batch).last_hidden_state
            vectors[name] = F.normalize(hidden[:, -1].float(), dim=-1)[0].cpu().tolist()
            lengths[name] = int(batch['input_ids'].shape[1])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'embeddings.json').write_text(json.dumps({'model': MODEL, 'revision': REVISION, 'tokens': lengths,
                                                     'vectors': vectors}) + '\n')
    print(f'{len(vectors)} documents embedded; longest {max(lengths.values())} tokens')


if __name__ == '__main__':
    main()
