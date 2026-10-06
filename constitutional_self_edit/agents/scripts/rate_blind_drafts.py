#!/usr/bin/env python3
"""Rate each review's blind draft on the twelve axes, as if it were a constitution.

In the blind arm the model writes its own view before it sees the document, so
the draft does not depend on the seed. If the attractor is the model's prior,
the drafts should sit at it. Drafts are first-person essays of 500-700 words,
not capped constitutions, so a second rater also rates a subset of drafts
together with the constitutions they are compared against.

Usage: python3 agents/scripts/rate_blind_drafts.py [--dry-run]
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
from analyze_value_space12 import doc_hash  # noqa: E402
import rate_chains_12axis as r12  # noqa: E402

BATCHES = ('field-12seeds', 'field-sonnet', 'field-sol', 'field-plane', 'attractor-test',
           'probe-chains', 'field-sonnet-decoded')
FIELD = {'qwen38_27b': 'field-12seeds', 'sonnet5': 'field-sonnet', 'gpt6_sol': 'field-sol'}
ATTRACTORS = ('ATTRACTOR', 'SONNET_ATTRACTOR', 'SOL_ATTRACTOR')
DRAFTS = RUNS / 'blind_drafts'
PRIMARY, SECOND = 'gpt6_luna', 'dsv4_pro'
OUT_PRIMARY = RUNS / 'positions12_drafts'
OUT_SECOND = RUNS / 'positions12_drafts_dsv4'


def usable(g):
    rf = g / 'result.json'
    return rf.exists() and json.loads(rf.read_text()).get('status') in ('EDITED', 'UNCHANGED')


def drafts():
    """Every blind draft, keyed by hash, with where it came from."""
    out = {}
    for batch in BATCHES:
        for cell in sorted(p for p in (RUNS / batch).iterdir() if p.is_dir()):
            model, arm, seed, rep = cell.name.split('__')
            for g in sorted(cell.glob('gen_*')):
                tp = g / 'transcript.json'
                if not tp.exists():
                    continue
                t = json.loads(tp.read_text())
                if len(t) < 2 or t[1]['role'] != 'assistant' or not (t[1]['content'] or '').strip():
                    continue
                text = t[1]['content']
                out[doc_hash(text)] = dict(text=text, batch=batch, model=model, arm=arm, seed=seed,
                                           rep=rep, gen=g.name, words=len(text.split()))
    return out


def constitutions(rng, n_out):
    """Starting documents, the decoded attractors, and a sample of edited outputs."""
    docs = {}
    for batch in BATCHES:
        for cell in sorted(p for p in (RUNS / batch).iterdir() if p.is_dir()):
            g = cell / 'gen_01'
            if usable(g):
                t = (g / 'input.md').read_text()
                docs[doc_hash(t)] = t
    for name in ATTRACTORS:
        t = (ROOT / 'constitutions' / 'decode' / f'{name}.md').read_text()
        docs[doc_hash(t)] = t
    for model, batch in FIELD.items():
        outs = {}
        for cell in sorted(p for p in (RUNS / batch).iterdir() if p.is_dir()):
            g = cell / 'gen_01'
            if cell.name.startswith(model) and usable(g):
                t = (g / 'output.md').read_text()
                outs[doc_hash(t)] = t
        for h in rng.sample(sorted(outs), min(n_out, len(outs))):
            docs[h] = outs[h]
    return docs


def primary_rated():
    """Hashes that already carry a primary-rater rating in any 12-axis directory."""
    seen = set()
    for d in RUNS.glob('positions12*'):
        for f in d.glob('*.rep*.json'):
            seen.add(f.name.split('.')[0])
    return seen


def run(client, jobs, workers):
    """One rater at a time: r12.rate writes to the module-level OUT."""
    for out in dict.fromkeys(j[1] for j in jobs):
        group = [j for j in jobs if j[1] == out]
        r12.OUT = out
        ok = fail = 0
        with ThreadPoolExecutor(workers) as pool:
            futs = {pool.submit(r12.rate, client, rater, h, text, rep): (rater, h)
                    for rater, _, h, text, rep in group}
            for f in as_completed(futs):
                try:
                    f.result(); ok += 1
                except Exception as e:
                    fail += 1
                    print('ERROR', futs[f][0], futs[f][1][:10], repr(e)[:120])
                if (ok + fail) % 50 == 0:
                    print(f'  {ok+fail}/{len(group)}')
        print(f'{out.name}: {ok} ok, {fail} failed')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repeat-n', type=int, default=30, help='drafts rated three times by the primary rater')
    ap.add_argument('--second-drafts', type=int, default=20, help='drafts per model for the second rater')
    ap.add_argument('--second-outputs', type=int, default=20, help='edited outputs per model for the second rater')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    rng = random.Random(args.seed)

    dr = drafts()
    DRAFTS.mkdir(parents=True, exist_ok=True)
    for h, d in dr.items():
        p = DRAFTS / f'{h}.json'
        if not p.exists():
            save(p, dict(d, hash=h))

    repeats = rng.sample(sorted(dr), min(args.repeat_n, len(dr)))
    jobs = [(PRIMARY, OUT_PRIMARY, h, dr[h]['text'], 1) for h in sorted(dr)]
    jobs += [(PRIMARY, OUT_PRIMARY, h, dr[h]['text'], r) for h in repeats for r in (2, 3)]

    cons = constitutions(rng, args.second_outputs)
    have = primary_rated()
    jobs += [(PRIMARY, OUT_PRIMARY, h, t, 1) for h, t in sorted(cons.items()) if h not in have]

    by_model = {}
    for h, d in sorted(dr.items()):
        by_model.setdefault(d['model'], []).append(h)
    second = [h for hs in by_model.values() for h in rng.sample(hs, min(args.second_drafts, len(hs)))]
    jobs += [(SECOND, OUT_SECOND, h, dr[h]['text'], 1) for h in second]
    jobs += [(SECOND, OUT_SECOND, h, t, 1) for h, t in sorted(cons.items())]

    todo = [j for j in jobs if not (j[1] / f'{j[2]}.rep{j[4]}.json').exists()]
    count = {}
    for rater, *_ in jobs:
        count[rater] = count.get(rater, 0) + 1
    print(f'{len(dr)} drafts ({", ".join(f"{m} {len(v)}" for m, v in by_model.items())}), '
          f'{len(repeats)} repeated to 3 ratings')
    print(f'{len(cons)} constitutions for the second rater, '
          f'{sum(1 for h in cons if h not in have)} of them new to {PRIMARY}')
    print(f'{len(jobs)} ratings total ({", ".join(f"{k} {v}" for k, v in count.items())}), '
          f'{len(todo)} to fetch')
    if args.dry_run or not todo:
        print('dry run' if args.dry_run else 'all cached')
        return

    models = json.loads((ROOT / 'configs' / 'elicitation' / 'models.json').read_text())
    client = Client(Ledger(RUNS / 'ledger.json', BUDGET_USD), models)
    run(client, todo, args.workers)


if __name__ == '__main__':
    main()
