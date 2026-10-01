#!/usr/bin/env python3
"""Re-rate the spec-seeded chain corpus on the twelve v3 axes.

Study 10 used the seven-axis scheme with judge_flash, where two axes are
pinned at the ceiling and the rater noise floor was never measured. This
re-rates the same documents on the twelve axes with gpt6_luna, and rates a
subsample repeatedly so the corpus carries its own test-retest floor.

Usage: python3 agents/scripts/rate_chains_12axis.py [--repeat-n 40] [--repeat-reps 3]
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elicit.core import Client, Ledger, save  # noqa: E402
from elicit.run import BUDGET_USD, RUNS  # noqa: E402
from selfhost_v3 import RATE_AXES, RATE_PROMPT  # noqa: E402
from analyze_value_space import doc_hash, BATCHES  # noqa: E402

OUT = RUNS / 'positions12'


def corpus():
    """Every unique document in the usable generations of the spec chains."""
    docs = {}
    for batch in BATCHES:
        root = RUNS / batch
        if not root.exists():
            continue
        for cell in sorted(p for p in root.iterdir() if p.is_dir()):
            for g in sorted(cell.glob('gen_*')):
                rf = g / 'result.json'
                if not rf.exists():
                    continue
                if json.loads(rf.read_text()).get('status') not in ('EDITED', 'UNCHANGED'):
                    continue
                for f in ('input.md', 'output.md'):
                    t = (g / f).read_text()
                    docs[doc_hash(t)] = t
    return docs


def rate(client, rater, h, text, rep):
    out = OUT / f'{h}.rep{rep}.json'
    if out.exists():
        return json.loads(out.read_text())
    axes = '\n'.join(f'- "{k}": {v}' for k, v in RATE_AXES.items())
    prompt = RATE_PROMPT.format(doc=text.strip(), axes=axes)
    for attempt in range(3):
        res = client.complete(rater, [{'role': 'user', 'content': prompt}], None,
                              OUT / 'calls' / f'{h}_rep{rep}_{attempt}',
                              thinking=True, max_tokens=6000,
                              extra={'response_format': {'type': 'json_object'}})
        t = res['choices'][0]['message'].get('content') or ''
        try:
            d = json.loads(t[t.index('{'):t.rindex('}') + 1])
            d['ratings'] = {k: int(d['ratings'][k]) for k in RATE_AXES}
            assert all(1 <= v <= 7 for v in d['ratings'].values())
            d.update(rater=rater, hash=h, rep=rep)
            save(out, d)
            return d
        except (ValueError, KeyError, TypeError, AssertionError):
            continue
    raise RuntimeError(f'unparseable rating for {h} rep{rep}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rater', default='gpt6_luna')
    ap.add_argument('--repeat-n', type=int, default=40, help='documents rated more than once')
    ap.add_argument('--repeat-reps', type=int, default=3, help='total ratings for those')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    docs = corpus()
    rng = random.Random(args.seed)
    repeats = set(rng.sample(sorted(docs), min(args.repeat_n, len(docs))))
    jobs = [(h, 1) for h in sorted(docs)]
    jobs += [(h, r) for h in sorted(repeats) for r in range(2, args.repeat_reps + 1)]
    todo = [(h, r) for h, r in jobs if not (OUT / f'{h}.rep{r}.json').exists()]
    print(f'{len(docs)} unique documents, {len(repeats)} repeated to {args.repeat_reps} ratings')
    print(f'{len(jobs)} ratings total, {len(todo)} to fetch, rater {args.rater}, '
          f'{len(RATE_AXES)} axes')
    if args.dry_run or not todo:
        print('dry run' if args.dry_run else 'all cached')
        return

    models = json.loads((ROOT / 'configs' / 'elicitation' / 'models.json').read_text())
    client = Client(Ledger(RUNS / 'ledger.json', BUDGET_USD), models)
    ok = fail = 0
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(rate, client, args.rater, h, docs[h], r): (h, r) for h, r in todo}
        for f in as_completed(futs):
            try:
                f.result(); ok += 1
            except Exception as e:
                fail += 1
                print('ERROR', futs[f][0][:10], repr(e)[:120])
            if (ok + fail) % 50 == 0:
                print(f'  {ok+fail}/{len(todo)}')
    print(f'done: {ok} ok, {fail} failed')


if __name__ == '__main__':
    main()
