#!/usr/bin/env python3
"""Summarize the off-diagonal PD start grid (different starting documents for A and B).

Joins each `od_<a>_vs_<b>_claude/game_NN` with its step 4-6 and 7-9 continuations `od_<a>_vs_<b>_claude_cont_NN`
and `..._cont2_NN` (if any), prints moves and edits per pair with both orders folded together, and, for every game with a
C_relative agent, the first step at which that agent's document no longer states a relative goal.
Offline: reads records only.

Usage (from constitutional_self_edit):
  python3 agents/scripts/summarize_pd_offdiag.py [reports/12_incentivized_drift/data]

Knowledge graph notes (SPAR/): Do PD Pairings Have Their Own Fixed Points;
Relative-Profit Goals Are Disguised Then Adopted by Successors; Neutral Drift Makes Mutual Defection Metastable.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELATIVE = re.compile(r'relative|gap|difference|than the other', re.I)


def parts(root, run, game):
    """The game's own folder, then its continuation folders (steps 4-6, 7-9) that exist."""
    out = [root / run / game]
    for suffix in ('cont', 'cont2'):
        cont = root / f'{run}_{suffix}_{game[5:]}' / 'game_01'
        if cont.exists():
            out.append(cont)
    return out


def play(root, run, game):
    moves, edits, cost, docs = [], [], 0.0, {}
    for p in parts(root, run, game):
        rec = json.loads((p / 'game.json').read_text())
        cost += rec.get('cost', 0)
        for s in rec['steps']:
            if 'actions' not in s:
                continue
            k = s['step']
            moves.append(s['actions']['A'] + s['actions']['B'])
            for side in 'AB':
                docs[side, k - 1] = docs.get((side, k - 1)) or (p / f'{side}_{k - 1:03d}.md').read_text()
                docs[side, k] = (p / f'{side}_{k:03d}.md').read_text()
            edits.append(''.join(side for side in 'AB' if docs[side, k] != docs[side, k - 1]) or '-')
    return moves, edits, cost, docs


def end_state(moves, edits):
    state = {'CC': 'CC', 'DD': 'DD'}.get(moves[-1], 'exploit')
    return state + ('*' if len(moves) > 3 and edits[-1] != '-' else '')


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'reports' / '12_incentivized_drift' / 'data'
    pairs, relative, total = defaultdict(list), [], 0.0
    for run in sorted(p.name for p in root.glob('od_*_claude') if p.is_dir()):
        a, b = run[3:-len('_claude')].split('_vs_')
        for game in sorted(g.name for g in (root / run).glob('game_*')):
            moves, edits, cost, docs = play(root, run, game)
            total += cost
            key = tuple(sorted((a, b)))
            shown_m, shown_e = moves, edits
            if (a, b) != key:  # show moves from key[0]'s side first
                shown_m = [m[::-1] for m in moves]
                shown_e = [e.translate(str.maketrans('AB', 'BA')) for e in edits]
            pairs[key].append((run, game, shown_m, shown_e, end_state(moves, edits)))
            if 'relative' in (a, b):
                side = 'A' if a == 'relative' else 'B'
                dropped = next((k for k in range(1, len(moves) + 1) if not RELATIVE.search(docs[side, k])), None)
                relative.append((run, game, side, moves[-1], dropped))
    for key in sorted(pairs):
        tally = defaultdict(int)
        for r in pairs[key]:
            tally[r[4].rstrip('*')] += 1
        print(f"== {key[0]} vs {key[1]} (moves as {key[0]},{key[1]}): "
              + ', '.join(f'{v} {k}' for k, v in sorted(tally.items())))
        for run, game, m, e, state in pairs[key]:
            print(f"   {run:34s} {game} {' '.join(m):18s} edits {' '.join(e):18s} -> {state}")
    print('\n== relative-start agent: step its document stops stating a relative goal')
    for run, game, side, last, dropped in relative:
        print(f'   {run:34s} {game} side {side} final {last} dropped {dropped}')
    print(f'\ntotal cost ${total:.2f}')


if __name__ == '__main__':
    main()
