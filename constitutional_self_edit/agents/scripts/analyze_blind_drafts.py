#!/usr/bin/env python3
"""Do the blind drafts sit at each model's attractor?

The blind draft is written before the model sees the constitution, so it does
not depend on the seed. If the chains are iterated learning, the attractor is
the model's prior and the drafts should sit at it. Reads the ratings written by
rate_blind_drafts.py; makes no calls.

Usage: python3 agents/scripts/analyze_blind_drafts.py [--boot 200]
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_value_space12 import AX, doc_hash, noise_sd  # noqa: E402
from elicit.run import RUNS  # noqa: E402
from analyze_field import field_ratings, seed_positions, edits  # noqa: E402
from plot_contraction_rates import fit_per_axis  # noqa: E402
import plot_named_axes as pna  # noqa: E402
from plot_sonnet_axes import sonnet_field  # noqa: E402
from plot_sol_axes import sol_field  # noqa: E402

MODELS = ('qwen38_27b', 'sonnet5', 'gpt6_sol')
FIELD = {'qwen38_27b': 'field-12seeds', 'sonnet5': 'field-sonnet', 'gpt6_sol': 'field-sol'}
PLANE = [AX.index('caution'), AX.index('long_term_orientation')]


def qwen_field():
    """The seventeen starts of figure 05 and Qwen's mean edit from each."""
    fr = field_ratings('positions12_field')
    sh = {}
    ed = edits('field-12seeds', fr, sh)
    seeds = seed_positions(fr, sh)
    p0 = {s: seeds[s].mean(0) for _, s in ed}
    p1 = {s: p0[s] + np.mean([x['vout'] - x['vin'] for x in v], 0) for (_, s), v in ed.items()}
    for f in (pna.probe_points, pna.attractor_point, pna.plane_points):
        a, b, _ = f()
        p0.update(a)
        p1.update(b)
    return p0, p1, [s for s in p0 if s in p1]


def starts_and_edits():
    out = {}
    for m, f in (('qwen38_27b', qwen_field()), ('sonnet5', sonnet_field()), ('gpt6_sol', sol_field())):
        p0, p1, names = f[0], f[1], f[-1]
        out[m] = (np.array([p0[s] for s in names]), np.array([p1[s] - p0[s] for s in names]))
    return out


def ratings(dirs, rater):
    per = defaultdict(list)
    for d in dirs:
        for f in d.glob('*.rep*.json'):
            x = json.loads(f.read_text())
            if x.get('rater', rater) == rater:
                per[x['hash']].append([x['ratings'][a] for a in AX])
    return {k: np.array(v, float) for k, v in per.items()}


def fmt(v):
    return ' '.join(f'{x:6.2f}' for x in v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--boot', type=int, default=200, help='bootstrap resamples of the starts')
    args = ap.parse_args()
    rng = np.random.default_rng(0)

    meta = {}
    for f in sorted((RUNS / 'blind_drafts').glob('*.json')):
        d = json.loads(f.read_text())
        meta[d['hash']] = d
    raw = ratings([RUNS / 'positions12_drafts'], 'gpt6_luna')
    L = {k: v.mean(0) for k, v in raw.items()}
    drafts = {m: np.array([L[h] for h, d in sorted(meta.items()) if d['model'] == m and h in L])
              for m in MODELS}

    print('=' * 78)
    print('RATER NOISE: test-retest SD, drafts against the constitution corpus')
    print('=' * 78)
    rep = [v for h, v in raw.items() if h in meta and len(v) >= 3]
    sd = np.sqrt(np.mean([r.var(0, ddof=1) for r in rep], 0))
    for a, x, y in zip(AX, sd, noise_sd()):
        print(f'  {a:22s} drafts {x:.2f}   constitutions {y:.2f}')
    print(f'  ({len(rep)} drafts rated three times; Euclidean {np.linalg.norm(sd):.2f} '
          f'against {np.linalg.norm(noise_sd()):.2f})')

    fits = {}
    for m, (V, D) in starts_and_edits().items():
        ks, vs = fit_per_axis(V, D)
        boot = np.array([fit_per_axis(V[ix], D[ix], iters=300)[1]
                         for ix in (rng.integers(0, len(V), len(V)) for _ in range(args.boot))])
        fits[m] = (ks, vs, V + D, boot)

    print('\n' + '=' * 78)
    print('DRAFTS AGAINST THE FITTED ATTRACTOR, all twelve axes')
    print('=' * 78)
    print(f'  {"":24s}' + ' '.join(f'{a[:6]:>6s}' for a in AX))
    for m in MODELS:
        ks, vs, land, _ = fits[m]
        X = drafts[m]
        print(f'  {m:11s} draft mean  {fmt(X.mean(0))}')
        print(f'  {"":11s} draft SD    {fmt(X.std(0))}')
        print(f'  {"":11s} attractor   {fmt(vs)}')
        print(f'  {"":11s} k           {fmt(ks)}')
        print(f'  {"":11s} after edit  {fmt(land.mean(0))}')
        print(f'  {"":11s} {len(X)} drafts, |draft - attractor| {np.linalg.norm(X.mean(0) - vs):.2f}')
    pairs = [(a, b) for n, a in enumerate(MODELS) for b in MODELS[n + 1:]]
    print('  attractor to attractor: ' + ', '.join(
        f'{a} - {b} {np.linalg.norm(fits[a][1] - fits[b][1]):.2f}' for a, b in pairs))

    print('\n' + '=' * 78)
    print(f'WORKING PLANE: attractor with 90% bootstrap interval over starts ({args.boot} resamples)')
    print('=' * 78)
    for m in MODELS:
        _, vs, _, boot = fits[m]
        X = drafts[m]
        for i in PLANE:
            lo, hi = np.percentile(boot[:, i], [5, 95])
            inside = 'inside' if lo <= X[:, i].mean() <= hi else 'OUTSIDE'
            print(f'  {m:11s} {AX[i]:22s} attractor {vs[i]:.2f} [{lo:.2f}, {hi:.2f}]   '
                  f'drafts {X[:, i].mean():.2f} +/- {X[:, i].std() / np.sqrt(len(X)):.2f}  {inside}')

    print('\n' + '=' * 78)
    print('NEAREST ATTRACTOR: each draft against the three fitted attractors')
    print('=' * 78)
    for label, idx in (('all twelve axes', list(range(len(AX)))), ('working plane', PLANE)):
        tot = 0
        print(f'  {label}')
        for m in MODELS:
            c = Counter(min(MODELS, key=lambda o: np.linalg.norm((x - fits[o][1])[idx])) for x in drafts[m])
            tot += c[m]
            print(f'    {m:11s} ' + '  '.join(f'{o} {c[o]:3d}' for o in MODELS))
        print(f'    own attractor nearest: {tot}/{sum(len(x) for x in drafts.values())}')

    print('\n' + '=' * 78)
    print('SECOND RATER: dsv4_pro on a subset of drafts and the constitutions')
    print('=' * 78)
    S = {k: v.mean(0) for k, v in ratings([RUNS / 'positions12_drafts_dsv4'], 'dsv4_pro').items()}
    Lall = {k: v.mean(0) for k, v in ratings(
        [d for d in RUNS.glob('positions12*') if d.name != 'positions12_drafts_dsv4'], 'gpt6_luna').items()}
    both = [h for h in S if h in Lall]
    A = np.array([Lall[h] for h in both])
    B = np.array([S[h] for h in both])
    print(f'  {len(both)} documents rated by both')
    for i, a in enumerate(AX):
        r = np.corrcoef(A[:, i], B[:, i])[0, 1] if A[:, i].std() and B[:, i].std() else float('nan')
        print(f'    {a:22s} r {r:5.2f}   dsv4 - luna {np.mean(B[:, i] - A[:, i]):+.2f}')
    outs = defaultdict(list)
    for m, batch in FIELD.items():
        for cell in sorted(p for p in (RUNS / batch).iterdir() if p.is_dir()):
            g = cell / 'gen_01' / 'output.md'
            if g.exists():
                h = doc_hash(g.read_text())
                if h in S and h in Lall:
                    outs[m].append(h)
    sub = {m: [h for h, d in sorted(meta.items()) if d['model'] == m and h in S] for m in MODELS}
    print('  draft centroid minus edited-output centroid (caution, long-term, |12-d|)')
    for m in MODELS:
        for name, R in (('luna', Lall), ('dsv4', S)):
            d = np.mean([R[h] for h in sub[m]], 0) - np.mean([R[h] for h in outs[m]], 0)
            print(f'    {m:11s} {name}  drafts {len(sub[m])} outputs {len(outs[m])}  '
                  f'{d[PLANE[0]]:+.2f}  {d[PLANE[1]]:+.2f}  {np.linalg.norm(d):.2f}')
    for name, R in (('luna', Lall), ('dsv4', S)):
        cent = {m: np.mean([R[h] for h in outs[m]], 0) for m in MODELS}
        for label, idx in (('12 axes', list(range(len(AX)))), ('plane', PLANE)):
            tot = sum(min(MODELS, key=lambda o: np.linalg.norm((R[h] - cent[o])[idx])) == m
                      for m in MODELS for h in sub[m])
            print(f'  {name} {label:7s}: drafts nearest their own model\'s outputs '
                  f'{tot}/{sum(len(v) for v in sub.values())}')


if __name__ == '__main__':
    main()
