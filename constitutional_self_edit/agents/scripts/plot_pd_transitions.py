#!/usr/bin/env python3
"""Step-1 state vs final state of every multi-step PD self-play game (study 12). Offline: reads records only.

A state is the pair of moves: mutual cooperation (CC), exploitation (CD or DC) or mutual defection (DD).
Panels: GPT and Claude self-play from step 1 to the last step played, joining each game with its `_cont_NN` (steps 4-6)
and `_cont2_NN`, `_cont3_NN` (steps 7-9, 10-12) continuations. Only the start grid is used (`<a>5_*`, `<a>_vs_<b>5_gpt6sol`,
`od_<a>_vs_<b>_claude`, `skeptical4_claude`), and a game is kept only if the other model has a game with the same start
pair and game number, so both panels cover the same games. Smoke runs and one-step runs (defect_hazard_*, dd_census_claude)
are left out, as are chicken, neutral-label and show-previous runs.

Usage (from constitutional_self_edit):
  python3 agents/scripts/plot_pd_transitions.py

Knowledge graph notes (SPAR/): PD First-Step State Predicts the Final State.
"""
import json
import re
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'reports' / '12_incentivized_drift' / 'data'
FIG = ROOT / 'reports' / '12_incentivized_drift' / 'figures'
STATES = ('CC', 'exploitation', 'DD')
LABELS = {'CC': 'Mutual\ncooperation', 'exploitation': 'Exploitation', 'DD': 'Mutual\ndefection'}
MODELS = {'sonnet5': 'Claude', 'gpt6_sol': 'GPT'}
CONT = re.compile(r'_cont[23]?_\d+$')
GRID = re.compile(r'^(od_\w+_claude|(?!smoke)\w+[45]_(claude|gpt6sol))$')
# Sequential blue ramp, steps 100 -> 650 of the reference palette.
RAMP = LinearSegmentedColormap.from_list('blue', ['#f4f8fe', '#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#104281'])
INK, MUTED, SURFACE = '#1f1f1e', '#6b6a66', '#ffffff'


def state(actions):
    a, b = actions['A'], actions['B']
    return None if None in (a, b) else 'CC' if a == b == 'C' else 'DD' if a == b == 'D' else 'exploitation'


def load(path):
    g = json.loads(path.read_text())
    if g.get('game', 'pd') != 'pd' or g.get('labels', 'standard') != 'standard' or g.get('show_previous'):
        return None
    return g


def games():
    """(model, step-1 state, step-3 state, last-step state, last step, (start A, start B, game)) per grid self-play game
    of 3+ steps."""
    out = []
    for path in sorted(DATA.glob('*/game_*/game.json')):
        run, game = path.parts[-3], path.parts[-2]
        g = load(path)
        if CONT.search(run) or not GRID.match(run) or g is None or len(g['steps']) < 3 or g['models']['A'] != g['models']['B'] \
                or g['models']['A'] not in MODELS:
            continue
        steps = list(g['steps'])
        for suffix in ('cont', 'cont2', 'cont3'):
            cont = DATA / f'{run}_{suffix}_{game[5:]}' / 'game_01' / 'game.json'
            if cont.exists():
                steps += json.loads(cont.read_text())['steps']
        by_step = {s['step']: state(s['actions']) for s in steps if s.get('actions')}
        last = max(by_step)
        if None in (by_step.get(1), by_step.get(3), by_step[last]):
            continue
        cfg = json.loads((path.parents[1] / 'config.json').read_text())
        cell = (Path(cfg['start']).name, Path(cfg.get('start_b') or cfg['start']).name, game)
        out.append((g['models']['A'], by_step[1], by_step[3], by_step[last], last, cell))
    return out


def pct(share):
    """Whole percent, without rounding a nonzero share to 0% or a share short of 1 to 100%."""
    if 0 < share < .005:
        return '<1%'
    if .995 <= share < 1:
        return '>99%'
    return f'{share:.0%}'


def panel(ax, pairs, title):
    counts = Counter(pairs)
    rows = {s: sum(counts[(s, t)] for t in STATES) for s in STATES}
    for i, s in enumerate(STATES):
        for j, t in enumerate(STATES):
            n = counts[(s, t)]
            share = n / rows[s] if rows[s] else 0
            ax.add_patch(plt.Rectangle((j + .02, i + .02), .96, .96, color=RAMP(share), lw=0))
            ink = SURFACE if share > .55 else INK
            ax.text(j + .5, i + .44, pct(share) if rows[s] else '–', ha='center', va='center', fontsize=13,
                    color=ink, weight='bold')
            ax.text(j + .5, i + .68, f'{n} game{"s" * (n != 1)}', ha='center', va='center', fontsize=8.5,
                    color=ink if share > .25 else MUTED)
    ax.set_xlim(0, 3)
    ax.set_ylim(3, 0)
    ax.set_xticks([.5, 1.5, 2.5], [LABELS[t] for t in STATES], fontsize=9, color=INK)
    ax.set_yticks([.5, 1.5, 2.5], [f'{LABELS[s]}\n(n={rows[s]})' for s in STATES], fontsize=9, color=INK)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, fontsize=11, color=INK, loc='left', pad=10)


def main():
    rows = games()
    cells = [{r[-1] for r in rows if r[0] == m} for m in MODELS]
    shared = cells[0] & cells[1]
    print('dropped, no match in the other model:', {MODELS[m]: sum(r[0] == m and r[-1] not in shared for r in rows)
                                                  for m in MODELS})
    rows = [r for r in rows if r[-1] in shared]
    FIG.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), facecolor=SURFACE)
    gpt = [(a, c) for m, a, _, c, *_ in rows if m == 'gpt6_sol']
    claude = [(a, c) for m, a, _, c, *_ in rows if m == 'sonnet5']
    panel(axes[0], gpt, f'GPT  ({len(gpt)} games)')
    panel(axes[1], claude, f'Claude  ({len(claude)} games)')
    for ax in axes:
        ax.set_xlabel('State at the last step played', fontsize=9.5, color=MUTED, labelpad=8)
    axes[0].set_ylabel('Step-1 state', fontsize=9.5, color=MUTED, labelpad=8)
    fig.tight_layout(w_pad=3)
    for ext_ in ('png', 'pdf'):
        fig.savefig(FIG / f'step1_to_final.{ext_}', dpi=200, facecolor=SURFACE)
    for name, pairs in (('GPT', gpt), ('Claude', claude)):
        print(name, len(pairs), dict(Counter(pairs)))


if __name__ == '__main__':
    main()
