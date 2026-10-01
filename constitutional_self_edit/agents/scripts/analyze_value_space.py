#!/usr/bin/env python3
"""Treat the spec-seeded edit chains as a dynamical system in value space.

Re-analysis of the chains-spec and chains-spec-anthropic batches from study 5.
Reads only saved results and cached position ratings; never calls an inference
service, so it costs nothing to re-run.

Usage: python3 agents/scripts/analyze_value_space.py [--batch chains-spec ...]
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / 'runs' / 'elicit'
CACHE = RUNS / 'positions'
BATCHES = ('chains-spec', 'chains-spec-anthropic')

AXES = ['oversight_deference', 'user_autonomy', 'caution', 'honesty_strictness',
        'third_party_concern', 'ai_agency', 'specificity']
# The three axes that carry the most independent variance; see pick_axes().
TRIPLE = ['oversight_deference', 'user_autonomy', 'ai_agency']


def doc_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


def rating(text: str):
    """Cached blind 1-7 rating for a document, or None if it was never rated."""
    f = CACHE / f'{doc_hash(text)}.rating.json'
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    return [d['ratings'][a] for a in AXES]


def load(batches=BATCHES) -> list[dict]:
    """One row per generation, with the rated position before and after the edit."""
    out = []
    for batch in batches:
        root = RUNS / batch
        if not root.exists():
            continue
        for cell in sorted(p for p in root.iterdir() if p.is_dir()):
            model, arm, seed, rep = cell.name.split('__')
            for g in sorted(cell.glob('gen_*')):
                rf = g / 'result.json'
                if not rf.exists():
                    continue
                r = json.loads(rf.read_text())
                ti, to = (g / 'input.md').read_text(), (g / 'output.md').read_text()
                vin, vout = rating(ti), rating(to)
                if vin is None or vout is None:
                    continue
                out.append(dict(batch=batch, cell=cell.name, model=model, arm=arm,
                                seed=seed, rep=rep, gen=int(g.name.split('_')[1]),
                                status=r.get('status'), capped='cap' in arm,
                                words_before=r.get('words_before'),
                                words_after=r.get('words_after'),
                                vin=vin, vout=vout, hin=doc_hash(ti), hout=doc_hash(to)))
    return [r for r in out if r['status'] in ('EDITED', 'UNCHANGED')]


def chains(rows) -> dict[str, dict[int, dict]]:
    by = defaultdict(dict)
    for r in rows:
        by[r['cell']][r['gen']] = r
    return dict(by)


def positions(rows, sub) -> np.ndarray:
    """Unique rated documents; generation rows share endpoints and would double-count."""
    docs = {}
    for r in rows:
        docs[r['hin']] = r['vin']
        docs[r['hout']] = r['vout']
    return np.array(list(docs.values()), float)[:, sub]


def pick_axes(rows):
    """Rank 3-axis subsets by generalized variance (spread x independence)."""
    X = positions(rows, list(range(len(AXES))))
    scored = []
    for c in itertools.combinations(range(len(AXES)), 3):
        scored.append((float(np.linalg.det(np.cov(X[:, c].T))), [AXES[i] for i in c]))
    scored.sort(reverse=True)
    return X, scored


def step_vectors(rows, sub, min_gen=2):
    return (np.array([np.array(r['vin'], float)[sub] for r in rows if r['gen'] >= min_gen]),
            np.array([(np.array(r['vout'], float) - np.array(r['vin'], float))[sub]
                      for r in rows if r['gen'] >= min_gen]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', nargs='+', default=list(BATCHES))
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--reps', type=int, default=10000)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    rows = load(args.batch)
    by = chains(rows)
    complete = {c: g for c, g in by.items() if sorted(g) == list(range(1, 7))}
    IDX = [AXES.index(a) for a in TRIPLE]
    print(f'{len(rows)} generations, {len(by)} chains, {len(complete)} complete at 6 generations')
    print(f'{len(positions(rows, IDX))} unique rated documents\n')

    # --- 1. which axes carry variance -------------------------------------
    X, scored = pick_axes(rows)
    print('=' * 68, '\n1. AXIS STRUCTURE\n', '=' * 68, sep='')
    print(f'  {"axis":24s} {"mean":>6s} {"sd":>6s}  range')
    for i, a in enumerate(AXES):
        print(f'  {a:24s} {X[:,i].mean():6.2f} {X[:,i].std(ddof=1):6.2f}  '
              f'{X[:,i].min():.0f}-{X[:,i].max():.0f}')
    print('\n  best 3-axis subsets by generalized variance:')
    for d, names in scored[:3]:
        print(f'    det {d:6.3f}   {", ".join(names)}')
    print(f'    ...worst: det {scored[-1][0]:6.3f}   {", ".join(scored[-1][1])}')

    # --- 2. step size and path geometry ------------------------------------
    print('\n' + '=' * 68, '\n2. CHAIN GEOMETRY (3 axes)\n', '=' * 68, sep='')
    def vin(r): return np.array(r['vin'], float)[IDX]
    def vout(r): return np.array(r['vout'], float)[IDX]
    print('  mean |step| by generation:')
    for g in range(1, 7):
        d = [np.linalg.norm(vout(r) - vin(r)) for r in rows if r['gen'] == g]
        if d:
            print(f'    gen {g}: n={len(d):3d}  {np.mean(d):.2f}')
    for lo, lab in ((1, 'all 6 generations'), (2, 'generations 2-6 only')):
        rr = []
        for c, g in complete.items():
            start = vin(g[1]) if lo == 1 else vout(g[1])
            path = sum(np.linalg.norm(vout(g[i]) - vin(g[i])) for i in range(lo, 7))
            if path:
                rr.append(np.linalg.norm(vout(g[6]) - start) / path)
        steps = 7 - lo
        print(f'  net/path, {lab}: {np.mean(rr):.2f}  '
              f'(isotropic random walk of {steps} steps: {np.sqrt(steps)/steps:.2f})')
    print('  NOTE: consecutive steps share an endpoint rating, so rating noise inflates')
    print('        path more than net and biases this ratio downward. See the report.')

    # --- 3. mean drift, cluster-bootstrapped by chain ----------------------
    print('\n' + '=' * 68, f'\n3. MEAN DRIFT per step, gens 2-6 ({args.reps} chain bootstraps)\n',
          '=' * 68, sep='')
    cells = [c for c in by if any(g >= 2 for g in by[c])]
    per = {c: np.array([vout(by[c][g]) - vin(by[c][g]) for g in sorted(by[c]) if g >= 2])
           for c in cells}
    obs = np.vstack(list(per.values())).mean(0)
    boot = np.array([np.vstack([per[cells[i]] for i in
                                rng.choice(len(cells), len(cells), replace=True)]).mean(0)
                     for _ in range(args.reps)])
    for i, a in enumerate(TRIPLE):
        lo, hi = np.percentile(boot[:, i], [2.5, 97.5])
        print(f'  {a:24s} {obs[i]:+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]'
              f'{"   excludes 0" if lo * hi > 0 else ""}')
    mag = np.mean(np.linalg.norm(np.vstack(list(per.values())), axis=1))
    print(f'  |mean step| {np.linalg.norm(obs):.2f} vs mean |step| {mag:.2f} '
          f'-> {100*np.linalg.norm(obs)/mag:.0f}% of motion is directed')

    # --- 4. model effect on terminal position ------------------------------
    print('\n' + '=' * 68, f'\n4. MODEL EFFECT on generation-6 position ({args.reps} permutations)\n',
          '=' * 68, sep='')
    lab = np.array([g[6]['model'] for g in complete.values()])
    pts = np.array([vout(g[6]) for g in complete.values()])

    def dispersion(l, p):
        grand, tot = p.mean(0), 0.0
        for m in set(l):
            q = p[l == m]
            tot += len(q) * np.sum((q.mean(0) - grand) ** 2)
        return tot / len(p)

    o = dispersion(lab, pts)
    null = np.array([dispersion(rng.permutation(lab), pts) for _ in range(args.reps)])
    print(f'  joint: observed {o:.3f}, null mean {null.mean():.3f}, p = {(null>=o).mean():.4f}')
    for i, a in enumerate(TRIPLE):
        oi = dispersion(lab, pts[:, [i]])
        ni = np.array([dispersion(rng.permutation(lab), pts[:, [i]]) for _ in range(args.reps)])
        print(f'    {a:24s} p = {(ni>=oi).mean():.4f}')
    print('\n  terminal centroid per model on ' + ', '.join(TRIPLE) + ':')
    for m in sorted(set(lab)):
        print(f'    {m:14s} n={int((lab==m).sum())}  {np.round(pts[lab==m].mean(0), 2)}')

    # --- 5. seed separation and length -------------------------------------
    print('\n' + '=' * 68, '\n5. SEED SEPARATION AND LENGTH\n', '=' * 68, sep='')
    s0 = {g[1]['seed']: vin(g[1]) for g in complete.values()}
    ks = sorted(s0)
    print(f'  seeds start {np.linalg.norm(s0[ks[0]]-s0[ks[1]]):.2f} apart')
    for g in range(1, 7):
        pos = defaultdict(list)
        for gg in complete.values():
            pos[gg[g]['seed']].append(vout(gg[g]))
        cen = {k: np.mean(v, 0) for k, v in pos.items()}
        spread = np.mean([np.mean([np.linalg.norm(p - cen[k]) for p in pos[k]]) for k in cen])
        print(f'    gen {g}: centroid distance {np.linalg.norm(cen[ks[0]]-cen[ks[1]]):.2f}   '
              f'within-seed spread {spread:.2f}')
    print('  mean words added per generation:')
    for cap in (False, True):
        d = [f'{np.mean([r["words_after"]-r["words_before"] for r in rows if r["gen"]==g and r["capped"]==cap]):+.0f}'
             for g in range(1, 7)]
        print(f'    {"capped  " if cap else "uncapped"}: ' + '  '.join(d))


if __name__ == '__main__':
    main()
