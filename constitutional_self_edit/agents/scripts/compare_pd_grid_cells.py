#!/usr/bin/env python3
"""Cell-by-cell Claude vs GPT cooperation over the PD start grid, steps 1-3, self-play only.

Reads the collaborator's aggregate tables (reports/pd_gpt/results*/offdiagonal.md and
results/cooperation_by_step.md, current prompt only), so every (A start, B start) cell gets equal weight
whatever its number of games. Prints the cells Claude wins, ties and loses, a two-sided sign test, the
mean difference in cooperation share with a cell-bootstrap 95% interval, and the mean without the
C_skeptical cells. Offline: reads tables only.

Usage (from constitutional_self_edit):
  python3 agents/scripts/compare_pd_grid_cells.py

Knowledge graph notes (SPAR/): Claude Out-Cooperates GPT in PD Self-Play Mostly Through C_skeptical.
"""
import math
import random
import re
from pathlib import Path

PD_GPT = Path(__file__).resolve().parents[2] / 'reports' / 'pd_gpt'


def offdiagonal(path, model):
    cells = {}
    for line in path.read_text().splitlines():
        p = [x.strip() for x in line.split('|')[1:-1]]
        if len(p) == 6 and p[0] == model:
            nums = [tuple(map(int, x.split('/'))) for x in re.findall(r'\d+/\d+', p[4] + ' ' + p[5])]
            cells[(p[1], p[2])] = sum(a for a, _ in nums) / sum(b for _, b in nums)
    return cells


def main():
    share = {'Claude': offdiagonal(PD_GPT / 'results_claude' / 'offdiagonal.md', 'Claude'),
             'GPT': offdiagonal(PD_GPT / 'results' / 'offdiagonal.md', 'GPT')}
    for line in (PD_GPT / 'results' / 'cooperation_by_step.md').read_text().splitlines():
        p = [x.strip() for x in line.split('|')[1:-1]]
        if len(p) == 7 and p[2] == 'current' and p[0] in share:
            nums = [tuple(map(int, x.split('/'))) for x in p[4:]]
            share[p[0]][(p[1], p[1])] = sum(a for a, _ in nums) / sum(b for _, b in nums)
    keys = sorted(set(share['Claude']) & set(share['GPT']))
    d = {k: share['Claude'][k] - share['GPT'][k] for k in keys}
    wins, losses = sum(v > 0 for v in d.values()), sum(v < 0 for v in d.values())
    n = wins + losses
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(max(wins, losses), n + 1)) / 2 ** n)
    print(f'{len(keys)} cells: Claude higher {wins}, GPT higher {losses}, tied {len(keys) - n}; sign test p = {p:.2g}')
    random.seed(0)
    boot = sorted(sum(d[random.choice(keys)] for _ in keys) / len(keys) for _ in range(20000))
    print(f'mean cooperation share Claude {sum(share["Claude"][k] for k in keys) / len(keys):.3f}, '
          f'GPT {sum(share["GPT"][k] for k in keys) / len(keys):.3f}; difference {sum(d.values()) / len(d):.3f} '
          f'(cell bootstrap 95% {boot[500]:.3f}-{boot[19500]:.3f})')
    rest = [k for k in keys if 'skeptical' not in k]
    print(f'without C_skeptical cells: difference {sum(d[k] for k in rest) / len(rest):.3f} over {len(rest)} cells')
    for k in sorted(keys, key=lambda k: -d[k]):
        print(f'  {k[0]:>9} vs {k[1]:<9} Claude {share["Claude"][k]:.2f}  GPT {share["GPT"][k]:.2f}')


if __name__ == '__main__':
    main()
