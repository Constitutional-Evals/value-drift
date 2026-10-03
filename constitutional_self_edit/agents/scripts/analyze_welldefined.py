#!/usr/bin/env python3
"""Is the edit map a function of position in value space?

Three textually different constitutions were written to occupy the same point,
then each was edited several times. If position determines the edit, the three
variants of a target must move alike: the spread between their mean edit vectors
should be no larger than the error on those means. If variants of one point move
differently, position is not the state and a vector field over value space is
not well defined.

Usage: python3 agents/scripts/analyze_welldefined.py
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
from analyze_value_space12 import AX, noise_sd, doc_hash  # noqa: E402

DECODE_RATINGS = ROOT / 'runs' / 'selfhost' / 'positions_decode'


def load(out_dir):
    per = defaultdict(list)
    for f in sorted((RUNS / out_dir).glob('*.rep*.json')):
        d = json.loads(f.read_text())
        per[d['hash']].append([d['ratings'][a] for a in AX])
    return {k: np.array(v, float) for k, v in per.items()}


def decode_positions():
    per = defaultdict(list)
    for f in sorted(DECODE_RATINGS.glob('*.rep*.json')):
        d = json.loads(f.read_text())
        per[d['seed']].append([d['ratings'][a] for a in AX])
    return {k: np.array(v, float) for k, v in per.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', default='decode-welldef')
    ap.add_argument('--out', default='positions12_welldef')
    ap.add_argument('--reps', type=int, default=10000)
    args = ap.parse_args()
    rng = np.random.default_rng(0)

    rat = load(args.out)
    dec = decode_positions()
    sd = noise_sd()

    moves = defaultdict(list)
    root = RUNS / args.batch
    for cell in sorted(p for p in root.iterdir() if p.is_dir()):
        _, _, doc, _ = cell.name.split('__')
        g = cell / 'gen_01'
        if not (g / 'result.json').exists():
            continue
        r = json.loads((g / 'result.json').read_text())
        if r.get('status') not in ('EDITED', 'UNCHANGED'):
            continue
        hi = doc_hash((g / 'input.md').read_text())
        ho = doc_hash((g / 'output.md').read_text())
        if hi in rat and ho in rat:
            moves[doc].append(rat[ho].mean(0) - rat[hi].mean(0))
    moves = {k: np.array(v) for k, v in moves.items()}
    print(f'{len(moves)} constitutions, {sum(len(v) for v in moves.values())} edits\n')

    targets = sorted({k.split('_')[0] for k in moves})
    print('=' * 76)
    print('DO VARIANTS OF ONE POINT MOVE ALIKE?')
    print('=' * 76)
    print(f'  {"target":7s} {"start spread":>12s} {"between-variant":>16s} {"SE of a":>9s} '
          f'{"ratio":>6s}  verdict')
    print(f'  {"":7s} {"(position)":>12s} {"move spread":>16s} {"variant":>9s}')
    ratios = []
    for T in targets:
        vs = sorted(k for k in moves if k.startswith(T + '_'))
        M = np.array([moves[k].mean(0) for k in vs])                 # one mean move per variant
        c = M.mean(0)
        between = float(np.mean([np.linalg.norm(m - c) for m in M]))
        # error on one variant's mean move: rating noise on a shared tail + independent heads,
        # plus the edit-to-edit spread within that variant
        se = float(np.mean([
            np.sqrt(np.sum((sd / np.sqrt(len(dec[k]))) ** 2)
                    + (np.sum(sd ** 2) + np.sum(moves[k].var(0, ddof=1))) / len(moves[k]))
            for k in vs]))
        P = np.array([dec[k].mean(0) for k in vs])
        start = float(np.mean([np.linalg.norm(p - P.mean(0)) for p in P]))
        ratios.append(between / se)
        verdict = 'consistent' if between <= se else ('marginal' if between <= 1.5 * se
                                                      else 'VARIANTS DIFFER')
        print(f'  {T:7s} {start:12.2f} {between:16.2f} {se:9.2f} {between/se:6.2f}  {verdict}')

    print(f'\n  mean ratio between-variant spread / SE: {np.mean(ratios):.2f}')
    print('  (<=1 means variants of a point are indistinguishable: the map is a function of')
    print('   position. >1 means text that the rating does not capture is steering the edit.)')

    # permutation test: is variant identity more predictive than chance?
    print('\n' + '=' * 76)
    print(f'PERMUTATION TEST ({args.reps} shuffles of variant labels within each target)')
    print('=' * 76)

    def stat(assign):
        tot = 0.0
        for T in targets:
            vs = sorted(k for k in moves if k.startswith(T + '_'))
            pool = np.vstack([moves[k] for k in vs])
            idx = assign[T]
            groups = [pool[idx == j].mean(0) for j in range(len(vs))]
            c = np.mean(groups, 0)
            tot += float(np.mean([np.linalg.norm(g - c) for g in groups]))
        return tot / len(targets)

    true = {}
    for T in targets:
        vs = sorted(k for k in moves if k.startswith(T + '_'))
        true[T] = np.concatenate([[j] * len(moves[k]) for j, k in enumerate(vs)])
    obs = stat(true)
    null = np.array([stat({T: rng.permutation(v) for T, v in true.items()})
                     for _ in range(args.reps)])
    p = float((null >= obs).mean())
    print(f'  observed between-variant spread {obs:.3f}, null mean {null.mean():.3f}, p = {p:.4f}')
    print(f'  -> variant identity {"PREDICTS the edit" if p < 0.05 else "does not predict the edit"}')

    print('\n' + '=' * 76)
    print('FOR SCALE: how big are the moves being compared?')
    print('=' * 76)
    allm = np.vstack(list(moves.values()))
    print(f'  mean |edit| {np.mean(np.linalg.norm(allm, axis=1)):.2f}')
    print(f'  mean |mean edit per variant| '
          f'{np.mean([np.linalg.norm(v.mean(0)) for v in moves.values()]):.2f}')


if __name__ == '__main__':
    main()
