#!/usr/bin/env python3
"""Seed positions and the rater noise floor, from runs/selfhost/positions_seeds/.

Consumes the repeat ratings written by rate_value_map_seeds.py and reports:
  - per-axis test-retest SD across the repeats (the noise floor study 10 lacks)
  - each seed's mean position on the twelve axes
  - whether the twelve seeds span each axis, against that axis's noise floor

Usage: python3 agents/scripts/analyze_seed_positions.py
"""
from __future__ import annotations
from collections import defaultdict
import itertools
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from selfhost_v3 import RATE_AXES  # noqa: E402
from rate_value_map_seeds import OUT, SEEDS  # noqa: E402

AX = list(RATE_AXES)
NEW = ['claude_derived', 'openai_spec_derived', 'animal_welfare', 'flourishing',
       'eb_kindness', 'eb_conservatism', 'eb_deep_ecology']


def load():
    per = defaultdict(list)
    for f in sorted(OUT.glob('*.rep*.json')):
        d = json.loads(f.read_text())
        per[d['seed']].append([d['ratings'][a] for a in AX])
    return {k: np.array(v, float) for k, v in per.items()}


def main():
    per = load()
    if not per:
        raise SystemExit(f'no ratings in {OUT}; run rate_value_map_seeds.py first')
    n_rep = {k: len(v) for k, v in per.items()}
    print(f'{len(per)} seeds rated, repeats per seed: {sorted(set(n_rep.values()))}')
    missing = [s for s in SEEDS if s not in per]
    if missing:
        print(f'  WARNING missing seeds: {missing}')

    # --- noise floor: within-document SD across independent repeats ---
    print('\n' + '=' * 72)
    print('1. RATER NOISE FLOOR (SD across independent repeats, pooled over seeds)')
    print('=' * 72)
    floor = {}
    for i, a in enumerate(AX):
        v = [per[s][:, i].std(ddof=1) for s in per if len(per[s]) > 1]
        floor[a] = float(np.sqrt(np.mean(np.square(v)))) if v else float('nan')
    for a in AX:
        print(f'  {a:24s} {floor[a]:.2f}')
    print(f'  pooled Euclidean noise over 12 axes: '
          f'{np.sqrt(sum(f**2 for f in floor.values())):.2f}')

    # --- seed positions ---
    print('\n' + '=' * 72)
    print('2. SEED POSITIONS (mean over repeats)')
    print('=' * 72)
    hdr = ''.join(f'{a[:9]:>10s}' for a in AX)
    print(f'  {"seed":22s}{hdr}')
    for s in [x for x in SEEDS if x in per]:
        tag = '*' if s in NEW else ' '
        print(f' {tag}{s:22s}' + ''.join(f'{per[s][:,i].mean():10.1f}' for i in range(len(AX))))
    print('  (* = the seven value_map seeds)')

    # --- spread vs noise, per axis ---
    print('\n' + '=' * 72)
    print('3. DO THE SEEDS SPAN EACH AXIS?  (between-seed SD vs that axis noise floor)')
    print('=' * 72)
    print(f'  {"axis":24s} {"all 12":>8s} {"new 7":>8s} {"noise":>7s} {"ratio":>7s}  verdict')
    rows = []
    for i, a in enumerate(AX):
        allm = np.array([per[s][:, i].mean() for s in SEEDS if s in per])
        newm = np.array([per[s][:, i].mean() for s in NEW if s in per])
        sd_all, sd_new = allm.std(ddof=1), newm.std(ddof=1)
        ratio = sd_all / floor[a] if floor[a] > 0 else np.inf
        verdict = 'spans' if ratio >= 2 else ('weak' if ratio >= 1 else 'COLLAPSED')
        rows.append((ratio, a))
        print(f'  {a:24s} {sd_all:8.2f} {sd_new:8.2f} {floor[a]:7.2f} {ratio:7.1f}  {verdict}')
    rows.sort(reverse=True)
    print(f'\n  widest-spanning: {", ".join(a for _, a in rows[:3])}')
    print(f'  narrowest:       {", ".join(a for _, a in rows[-3:])}')

    # --- best 3-axis subset for a value map ---
    print('\n' + '=' * 72)
    print('4. BEST 3-AXIS SUBSETS for a map over these seeds (generalized variance)')
    print('=' * 72)
    X = np.array([[per[s][:, i].mean() for i in range(len(AX))] for s in SEEDS if s in per])
    scored = sorted(((float(np.linalg.det(np.cov(X[:, c].T))), c)
                     for c in itertools.combinations(range(len(AX)), 3)), reverse=True)
    for d, c in scored[:5]:
        C = np.corrcoef(X[:, c].T)
        mx = max(abs(C[i][j]) for i in range(3) for j in range(i + 1, 3))
        print(f'  det {d:8.2f}  max|r| {mx:.2f}  {", ".join(AX[i] for i in c)}')


if __name__ == '__main__':
    main()
