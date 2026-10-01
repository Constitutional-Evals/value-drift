#!/usr/bin/env python3
"""Study 10 redone on the twelve v3 axes, with the rater noise floor subtracted.

Uses runs/elicit/positions12/ (gpt6_luna, 12 axes, a repeated subsample) instead
of the seven-axis judge_flash cache. The repeats give a corpus-specific
test-retest floor, so step sizes can be corrected for measurement error and the
regression-to-the-mean bias in the binned field can be removed by binning on one
rating and measuring drift with an independent one.

Usage: python3 agents/scripts/analyze_value_space12.py
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import itertools
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elicit.run import RUNS  # noqa: E402
from selfhost_v3 import RATE_AXES  # noqa: E402
from analyze_value_space import doc_hash, BATCHES  # noqa: E402

OUT = RUNS / 'positions12'
AX = list(RATE_AXES)


def ratings():
    """hash -> list of independent rating vectors."""
    per = defaultdict(list)
    for f in sorted(OUT.glob('*.rep*.json')):
        d = json.loads(f.read_text())
        per[d['hash']].append([d['ratings'][a] for a in AX])
    return {k: np.array(v, float) for k, v in per.items()}


def rows(per):
    """One row per usable generation, carrying mean position before and after."""
    out = []
    for batch in BATCHES:
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
                if r.get('status') not in ('EDITED', 'UNCHANGED'):
                    continue
                hi, ho = doc_hash((g / 'input.md').read_text()), doc_hash((g / 'output.md').read_text())
                if hi not in per or ho not in per:
                    continue
                out.append(dict(cell=cell.name, model=model, arm=arm, seed=seed,
                                gen=int(g.name.split('_')[1]), status=r['status'],
                                hin=hi, hout=ho,
                                vin=per[hi].mean(0), vout=per[ho].mean(0),
                                nin=len(per[hi]), nout=len(per[ho])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reps', type=int, default=10000)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    per = ratings()
    if not per:
        raise SystemExit(f'no ratings in {OUT}; run rate_chains_12axis.py first')
    R = rows(per)
    by = defaultdict(dict)
    for r in R:
        by[r['cell']][r['gen']] = r
    complete = {c: g for c, g in by.items() if sorted(g) == list(range(1, 7))}
    multi = {h: v for h, v in per.items() if len(v) > 1}
    print(f'{len(per)} documents rated, {len(multi)} with repeats; '
          f'{len(R)} generations, {len(by)} chains, {len(complete)} complete')

    # --- 1. noise floor from the repeated subsample ---
    print('\n' + '=' * 70, '\n1. RATER NOISE FLOOR (this corpus, this rater)\n', '=' * 70, sep='')
    sd = np.array([np.sqrt(np.mean([v[:, i].var(ddof=1) for v in multi.values()]))
                   for i in range(len(AX))])
    for a, s in zip(AX, sd):
        print(f'  {a:24s} {s:.2f}')
    print(f'  single-rating Euclidean noise over 12 axes: {np.linalg.norm(sd):.2f}')

    # --- 2. which axes carry variance here ---
    print('\n' + '=' * 70, '\n2. AXIS STRUCTURE (between-document SD vs noise)\n', '=' * 70, sep='')
    X = np.array([v.mean(0) for v in per.values()])
    print(f'  {"axis":24s} {"mean":>6s} {"sd":>6s} {"noise":>6s} {"ratio":>6s}')
    for i, a in enumerate(AX):
        ratio = X[:, i].std(ddof=1) / sd[i] if sd[i] > 0 else np.inf
        print(f'  {a:24s} {X[:,i].mean():6.2f} {X[:,i].std(ddof=1):6.2f} {sd[i]:6.2f} {ratio:6.1f}')
    scored = sorted(((float(np.linalg.det(np.cov(X[:, c].T))), c)
                     for c in itertools.combinations(range(len(AX)), 3)), reverse=True)
    print('\n  best 3-axis subsets by generalized variance:')
    for d, c in scored[:3]:
        print(f'    det {d:7.3f}   {", ".join(AX[i] for i in c)}')

    # --- 3. step size, raw and noise-corrected ---
    print('\n' + '=' * 70, '\n3. STEP SIZE by generation (12 axes)\n', '=' * 70, sep='')
    # a step between two independently rated documents carries 2*sum(sd^2) of noise variance
    noise_sq = 2 * float(np.sum(sd ** 2))
    print(f'  expected squared step from noise alone: {noise_sq:.2f}  '
          f'(|step| ~ {np.sqrt(noise_sq):.2f})')
    print(f'  {"gen":>4s} {"n":>4s} {"mean|step|":>11s} {"mean|step|^2":>13s} {"corrected":>10s}')
    for g in range(1, 7):
        d = np.array([np.linalg.norm(r['vout'] - r['vin']) for r in R if r['gen'] == g])
        if not len(d):
            continue
        corr = max(float(np.mean(d ** 2)) - noise_sq, 0.0)
        print(f'  {g:4d} {len(d):4d} {d.mean():11.2f} {np.mean(d**2):13.2f} {np.sqrt(corr):10.2f}')

    # --- 4. path geometry, corrected ---
    print('\n' + '=' * 70, '\n4. PATH GEOMETRY\n', '=' * 70, sep='')
    for lo, lab in ((1, 'all 6 generations'), (2, 'generations 2-6')):
        rr = []
        for c, g in complete.items():
            start = g[1]['vin'] if lo == 1 else g[1]['vout']
            path = sum(np.linalg.norm(g[i]['vout'] - g[i]['vin']) for i in range(lo, 7))
            if path:
                rr.append(np.linalg.norm(g[6]['vout'] - start) / path)
        steps = 7 - lo
        print(f'  net/path, {lab}: {np.mean(rr):.2f}   '
              f'(isotropic walk of {steps} steps: {np.sqrt(steps)/steps:.2f})')
    print('  Rating noise inflates path more than net, so these remain biased downward;')
    print('  section 3 gives the magnitude of that noise.')

    # --- 5. mean drift, cluster-bootstrapped ---
    print('\n' + '=' * 70, f'\n5. MEAN DRIFT per step, gens 2-6 ({args.reps} chain bootstraps)\n',
          '=' * 70, sep='')
    cells = [c for c in by if any(k >= 2 for k in by[c])]
    steps = {c: np.array([by[c][k]['vout'] - by[c][k]['vin'] for k in sorted(by[c]) if k >= 2])
             for c in cells}
    obs = np.vstack(list(steps.values())).mean(0)
    boot = np.array([np.vstack([steps[cells[i]] for i in
                                rng.choice(len(cells), len(cells), replace=True)]).mean(0)
                     for _ in range(args.reps)])
    sig = []
    for i, a in enumerate(AX):
        lo, hi = np.percentile(boot[:, i], [2.5, 97.5])
        mark = '  excludes 0' if lo * hi > 0 else ''
        if mark:
            sig.append(a)
        print(f'  {a:24s} {obs[i]:+.3f}   [{lo:+.3f}, {hi:+.3f}]{mark}')
    print(f'\n  axes with a direction: {", ".join(sig) if sig else "none"}')

    # --- 6. model effect ---
    print('\n' + '=' * 70, f'\n6. MODEL EFFECT on generation-6 position ({args.reps} permutations)\n',
          '=' * 70, sep='')
    lab = np.array([g[6]['model'] for g in complete.values()])
    pts = np.array([g[6]['vout'] for g in complete.values()])

    def disp(l, p):
        grand, tot = p.mean(0), 0.0
        for m in set(l):
            q = p[l == m]
            tot += len(q) * np.sum((q.mean(0) - grand) ** 2)
        return tot / len(p)

    o = disp(lab, pts)
    null = np.array([disp(rng.permutation(lab), pts) for _ in range(args.reps)])
    print(f'  joint p = {(null>=o).mean():.4f}  (observed {o:.3f}, null mean {null.mean():.3f})')
    for i, a in enumerate(AX):
        oi = disp(lab, pts[:, [i]])
        ni = np.array([disp(rng.permutation(lab), pts[:, [i]]) for _ in range(2000)])
        p = (ni >= oi).mean()
        if p < 0.05:
            print(f'    {a:24s} p = {p:.4f}')


if __name__ == '__main__':
    main()
