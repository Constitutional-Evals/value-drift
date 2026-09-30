#!/usr/bin/env python3
"""Download LIMA (GAIR/lima, gated) at a pinned revision and write OCT's general prompts.

OCT's DPO prompts include the first user turn of every LIMA conversation, train and test:
1,030 + 300 = 1,330 prompts. They are written to data/raw/lima/prompts.jsonl in the pipeline's
prompt format. data/raw/ is git-ignored; LIMA's license does not allow redistributing it.

Usage (from constitutional_self_edit/; needs an HF token with access to GAIR/lima):
    HF_TOKEN=... python3 agents/scripts/prepare_lima_prompts.py
"""
import hashlib
import json
import os
from pathlib import Path

REPO = 'GAIR/lima'
REVISION = '68958e98267f5fb4a52a03ebcdae4ae59213fa7c'
OUT = Path(__file__).resolve().parents[2] / 'data' / 'raw' / 'lima'


def download():
    from huggingface_hub import hf_hub_download
    manifest = {'repo': REPO, 'revision': REVISION, 'files': {}}
    for name in ('train.jsonl', 'test.jsonl', 'README.md'):
        path = Path(hf_hub_download(REPO, name, repo_type='dataset', revision=REVISION,
                                    token=os.environ['HF_TOKEN'], local_dir=OUT))
        data = path.read_bytes()
        manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')


def main():
    if not all((OUT / f).exists() for f in ('train.jsonl', 'test.jsonl', 'manifest.json')):
        download()
    manifest = json.loads((OUT / 'manifest.json').read_text())
    for name in ('train.jsonl', 'test.jsonl'):
        if hashlib.sha256((OUT / name).read_bytes()).hexdigest() != manifest['files'][name]['sha256']:
            raise ValueError(f'{name} does not match the pinned download')
    prompts = []
    for split in ('train', 'test'):
        for row, line in enumerate((OUT / f'{split}.jsonl').read_text().splitlines()):
            record = json.loads(line)
            prompts.append({'id': f'GAIR--lima--{split}--{row:04d}--u0', 'prompt': record['conversations'][0],
                            'category': 'general',
                            'source': {'dataset': REPO, 'revision': REVISION, 'split': split, 'row': row, 'turn': 0,
                                       'lima_source': record.get('source') or None},
                            'value_tags': []})
    (OUT / 'prompts.jsonl').write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in prompts))
    print(f'{len(prompts)} prompts -> {OUT / "prompts.jsonl"}')


if __name__ == '__main__':
    main()
