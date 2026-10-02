#!/usr/bin/env python3
"""The edit map at twelve seed points: one mean vector per point, with its error.

Depth is 1 by design. Each seed was reviewed independently several times, so the
vector at a point is a mean over replicates and carries a standard error. The
seed's own rating error is shared across its replicates and does not average
away; the outputs are distinct documents, so theirs does.

Usage: python3 agents/scripts/analyze_field.py [--batch field-12seeds]
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elicit.run import RUNS  # noqa: E402
from analyze_value_space12 import AX, noise_sd, doc_hash  # noqa: E402

SEED_RATINGS = RUNS.parent / 'selfhost' / 'positions_seeds'


def field_ratings(out_dir):
    per = defaultdict(list)
    for f in sorted((RUNS / out_dir).glob('*.rep*.json')):
        d = json.loads(f.read_text())
        per[d['hash']].append([d['ratings'][a] for a in AX])
    return {k: np.array(v, float) for k, v in per.items()}


def seed_positions(field=None, seed_hash=None):
    """The twelve seeds. Combines the three standalone ratings with the one taken
    in the field batch, so each seed carries four independent ratings."""
    per = defaultdict(list)
    for f in sorted(SEED_RATINGS.glob('*.rep*.json')):
        d = json.loads(f.read_text())
        per[d['seed']].append([d['ratings'][a] for a in AX])
    if field and seed_hash:
        for name, h in seed_hash.items():
            if h in field:
                per[name].extend(field[h].tolist())
    return {k: np.array(v, float) for k, v in per.items()}


def edits(batch, rat, seed_hash):
    out = defaultdict(list)
    root = RUNS / batch
    if not root.exists():
        raise SystemExit(f'no run at {root}')
    for cell in sorted(p for p in root.iterdir() if p.is_dir()):
        model, arm, seed, rep = cell.name.split('__')
        g = cell / 'gen_01'
        rf = g / 'result.json'
        if not rf.exists():
            continue
        r = json.loads(rf.read_text())
        if r.get('status') not in ('EDITED', 'UNCHANGED'):
            continue
        hi, ho = doc_hash((g / 'input.md').read_text()), doc_hash((g / 'output.md').read_text())
        if hi not in rat or ho not in rat:
            continue
        seed_hash[seed] = hi
        out[(model, seed)].append(dict(vin=rat[hi].mean(0), vout=rat[ho].mean(0),
                                       status=r['status'], rep=rep,
                                       words=(r.get('words_before'), r.get('words_after'))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', default='field-12seeds')
    ap.add_argument('--out', default='positions12_field')
    args = ap.parse_args()

    rat = field_ratings(args.out)
    if not rat:
        raise SystemExit(f'no ratings in {RUNS / args.out}; run rate_chains_12axis.py --batches '
                         f'{args.batch} --out {args.out}')
    sd = noise_sd()
    seed_hash = {}
    ed = edits(args.batch, rat, seed_hash)
    seeds = seed_positions(rat, seed_hash)
    print(f'{len(ed)} (model, seed) cells, {sum(len(v) for v in ed.values())} edits\n')

    print('=' * 78)
    print('MEAN EDIT VECTOR AT EACH SEED  (12 axes, Euclidean)')
    print('=' * 78)
    print(f'  {"seed":22s} {"n":>2s} {"|mean|":>7s} {"SE":>6s} {"ratio":>6s} {"unchanged":>10s}')
    rows = []
    def mean_of(items):
        return np.mean([x['vout'] - x['vin'] for x in items], 0)

    for (model, seed), v in sorted(ed.items(), key=lambda kv: -np.linalg.norm(mean_of(kv[1]))):
        D = np.array([x['vout'] - x['vin'] for x in v])
        mean = D.mean(0)
        n = len(D)
        # shared seed-rating error (seed rated 3x) + independent output error + stochastic spread
        k = len(seeds[seed]) if seed in seeds else 1
        tail = float(np.sum((sd / np.sqrt(k)) ** 2))
        se = float(np.sqrt(tail + (np.sum(sd**2) + np.sum(D.var(0, ddof=1))) / n)) if n > 1 else np.nan
        unch = sum(1 for x in v if x['status'] == 'UNCHANGED')
        rows.append((seed, model, mean, n, se))
        print(f'  {seed:22s} {n:2d} {np.linalg.norm(mean):7.2f} {se:6.2f} '
              f'{np.linalg.norm(mean)/se:6.1f} {unch:10d}')

    print('\n' + '=' * 78)
    print('DIRECTION per seed: axes moving by more than 0.5')
    print('=' * 78)
    for seed, model, mean, n, se in rows:
        big = sorted(((mean[i], AX[i]) for i in range(len(AX)) if abs(mean[i]) >= 0.5),
                     key=lambda t: -abs(t[0]))
        txt = ', '.join(f'{a} {v:+.1f}' for v, a in big) or '(none above 0.5)'
        print(f'  {seed:22s} {txt}')

    print('\n' + '=' * 78)
    print('DO THE SEEDS CONVERGE?  distance between seed pairs, before and after one edit')
    print('=' * 78)
    pos0 = {s: seeds[s].mean(0) for s, _, _, _, _ in rows if s in seeds}
    pos1 = {s: pos0[s] + m for s, _, m, _, _ in rows if s in pos0}
    import itertools
    d0 = [np.linalg.norm(pos0[a] - pos0[b]) for a, b in itertools.combinations(pos0, 2)]
    d1 = [np.linalg.norm(pos1[a] - pos1[b]) for a, b in itertools.combinations(pos1, 2)]
    print(f'  mean pairwise distance before: {np.mean(d0):.2f}   after one edit: {np.mean(d1):.2f}'
          f'   ({100*(np.mean(d1)-np.mean(d0))/np.mean(d0):+.0f}%)')
    print(f'  spread of the twelve points (mean distance to centroid): '
          f'{np.mean([np.linalg.norm(p-np.mean(list(pos0.values()),0)) for p in pos0.values()]):.2f}'
          f' -> {np.mean([np.linalg.norm(p-np.mean(list(pos1.values()),0)) for p in pos1.values()]):.2f}')


if __name__ == '__main__':
    main()
