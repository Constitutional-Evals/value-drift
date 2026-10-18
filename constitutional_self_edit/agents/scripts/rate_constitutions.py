#!/usr/bin/env python3
"""Rate constitutions on stage 07's twelve 1-7 value axes with a self-hosted rater, blind and repeated.

The prompt and axes are stage 07's (agents/scripts/selfhost_v3.py RATE_PROMPT, RATE_AXES), unchanged.
The rater sees only the document. Each document is rated `--repeats` times with different seeds, so
rater noise can be told apart from differences between documents. Ratings are cached by document hash.

    /workspace/venv/bin/python agents/scripts/rate_constitutions.py --checkpoint <rater> --out <dir> \
        --docs <dir with draft.md / consolidated.md files> ... --doc C_001=<path> ...
"""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'agents' / 'scripts'))
from elicit import core  # noqa: E402
from recursive_oct import review_v3  # noqa: E402
from selfhost_v3 import RATE_AXES, RATE_PROMPT  # noqa: E402

MODEL_KEY = 'qwen38_27b_vllm'
SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20}


def collect(doc_dirs, named):
    """{name: path}: every draft.md and consolidated.md under the directories, plus the named documents."""
    docs = {}
    for directory in doc_dirs:
        for path in sorted(Path(directory).rglob('*.md')):
            if path.name in ('draft.md', 'consolidated.md') and path.read_text().strip():   # an empty reply is no document
                docs[str(path.parent.relative_to(Path(directory).parent))] = path
    for item in named:
        name, path = item.split('=', 1)
        docs[name] = Path(path)
    return docs


def parse(text):
    data = json.loads(text[text.index('{'):text.rindex('}') + 1])
    ratings = {k: int(data['ratings'][k]) for k in RATE_AXES}
    if not all(1 <= v <= 7 for v in ratings.values()):
        raise ValueError('rating out of range')
    return ratings, data.get('summary')


def rate(client, text, directory, seed):
    """One rating; up to three tries if the reply does not parse."""
    if (directory / 'rating.json').exists():
        return json.loads((directory / 'rating.json').read_text())
    prompt = RATE_PROMPT.format(doc=text.strip(), axes='\n'.join(f'- "{k}": {v}' for k, v in RATE_AXES.items()))
    for attempt in range(3):
        reply = client.complete(MODEL_KEY, [{'role': 'user', 'content': prompt}], None, directory / f'attempt_{attempt}',
                                thinking=True, max_tokens=12000,
                                extra={**SAMPLING, 'seed': core.derive_seed(seed, attempt)})
        try:
            ratings, summary = parse(reply['choices'][0]['message'].get('content') or '')
        except (ValueError, KeyError, TypeError):
            continue
        result = {'ratings': ratings, 'summary': summary, 'attempt': attempt}
        core.save(directory / 'rating.json', result)
        return result
    raise RuntimeError(f'no parsable rating in {directory}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--docs', nargs='*', default=[])
    ap.add_argument('--doc', action='append', default=[], help='name=path')
    ap.add_argument('--repeats', type=int, default=2)
    ap.add_argument('--seed', type=int, default=20261008)
    ap.add_argument('--workers', type=int, default=64)
    ap.add_argument('--vllm-bin', default='/workspace/venv-vllm/bin/vllm')
    ap.add_argument('--port', type=int, default=8000)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    docs = collect(args.docs, args.doc)
    texts = {name: path.read_text() for name, path in docs.items()}
    hashes = {name: hashlib.sha256(text.strip().encode()).hexdigest()[:16] for name, text in texts.items()}
    core.save(out / 'documents.json', {name: {'path': str(docs[name]), 'hash': hashes[name]} for name in docs})
    models = json.loads((ROOT / 'configs/selfhost/models.json').read_text())

    with review_v3.VLLMServer(args.checkpoint, vllm_bin=args.vllm_bin, served_name=models[MODEL_KEY]['id'],
                              log_path=out / 'server.log', port=args.port) as server:
        core.VLLM_API = server.base_url
        client = core.Client(core.Ledger(out / 'ledger.json', 1.0), models, key='unused-for-local-vllm')
        jobs, results, failed = {}, {}, []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for name, h in hashes.items():
                for repeat in range(1, args.repeats + 1):
                    directory = out / 'calls' / f'{h}_r{repeat}'
                    jobs[pool.submit(rate, client, texts[name], directory, core.derive_seed(args.seed, h, repeat))] = (name, repeat)
            for future in as_completed(jobs):
                name, repeat = jobs[future]
                try:
                    results[(name, repeat)] = future.result()
                except Exception as error:  # noqa: BLE001 - reported, the rest continue
                    failed.append((name, repeat))
                    print('FAILED', name, repeat, repr(error)[:300], flush=True)
    with open(out / 'ratings.jsonl', 'w') as stream:
        for (name, repeat), result in sorted(results.items()):
            stream.write(json.dumps({'name': name, 'hash': hashes[name], 'repeat': repeat, **result}) + '\n')
    print(f'{len(results)} ratings, {len(failed)} failed')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
