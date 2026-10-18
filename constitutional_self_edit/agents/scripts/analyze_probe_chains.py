#!/usr/bin/env python3
"""Do two starting points that differ on one axis stay different?

Two decoded constitutions sit at long-term orientation 1 and differ only in
caution, 5 against 7. Each was run as three chains. This tracks both axes by
generation and asks whether the starting gap survives.

Usage: python3 agents/scripts/analyze_probe_chains.py
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
from analyze_value_space12 import AX, doc_hash, noise_sd  # noqa: E402

REPS = ['r1', 'r2', 'r3']
SEEDS = ['mid_immediate', 'cautious_immediate']
ATTRACTOR = {'caution': 2.85, 'long_term_orientation': 3.56}   # from the twelve-seed field run


def trajectories(batch, out):
    rat = defaultdict(list)
    for f in sorted((RUNS / out).glob('*.rep*.json')):
        d = json.loads(f.read_text())
        rat[d['hash']].append([d['ratings'][a] for a in AX])
    rat = {k: np.array(v, float).mean(0) for k, v in rat.items()}
    traj = defaultdict(dict)
    for cell in sorted(p for p in (RUNS / batch).iterdir() if p.is_dir()):
        _, _, seed, rep = cell.name.split('__')
        for g in sorted(cell.glob('gen_*')):
            if not (g / 'result.json').exists():
                continue
            gi = int(g.name.split('_')[1])
            hi = doc_hash((g / 'input.md').read_text())
            ho = doc_hash((g / 'output.md').read_text())
            if gi == 1 and hi in rat:
                traj[(seed, rep)][0] = rat[hi]
            if ho in rat:
                traj[(seed, rep)][gi] = rat[ho]
    return traj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', default='probe-chains')
    ap.add_argument('--out', default='positions12_probe')
    args = ap.parse_args()
    traj = trajectories(args.batch, args.out)
    sd = noise_sd()
    c, l = AX.index('caution'), AX.index('long_term_orientation')

    for seed in SEEDS:
        print(f'\n{seed}   (caution / long-term)')
        print(f'  {"gen":>3s}  ' + '   '.join(f'{r:^11s}' for r in REPS) + f'{"mean caut":>11s}{"mean LT":>9s}')
        for gen in range(0, 7):
            vs = [traj[(seed, r)][gen] for r in REPS if gen in traj[(seed, r)]]
            if not vs:
                continue
            cols = '   '.join(f'{traj[(seed,r)][gen][c]:4.1f} /{traj[(seed,r)][gen][l]:4.1f}'
                              if gen in traj[(seed, r)] else '     -     ' for r in REPS)
            print(f'  {gen:3d}  {cols}{np.mean([v[c] for v in vs]):11.2f}'
                  f'{np.mean([v[l] for v in vs]):9.2f}')

    print('\n\nTHE CAUTION GAP')
    print(f'  {"gen":>3s} {"mid":>6s} {"cautious":>9s} {"gap":>6s} {"SE":>6s} {"gap/SE":>7s}')
    for gen in range(0, 7):
        a = [traj[('mid_immediate', r)][gen][c] for r in REPS if gen in traj[('mid_immediate', r)]]
        b = [traj[('cautious_immediate', r)][gen][c] for r in REPS
             if gen in traj[('cautious_immediate', r)]]
        if len(a) < 2 or len(b) < 2:
            continue
        se = float(np.sqrt(np.var(a, ddof=1) / len(a) + np.var(b, ddof=1) / len(b) + 2 * sd[c] ** 2))
        g = float(np.mean(b) - np.mean(a))
        print(f'  {gen:3d} {np.mean(a):6.2f} {np.mean(b):9.2f} {g:6.2f} {se:6.2f} {g/se:7.1f}')

    print(f"\nLONG-TERM: both start at 1. Attractor {ATTRACTOR['long_term_orientation']}.")
    for gen in range(0, 7):
        v = [traj[(s, r)][gen][l] for s in SEEDS for r in REPS if gen in traj[(s, r)]]
        if v:
            print(f'  gen {gen}: mean {np.mean(v):.2f}  (n={len(v)})')


if __name__ == '__main__':
    main()
