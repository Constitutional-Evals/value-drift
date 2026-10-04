#!/usr/bin/env python3
"""How fast each value axis is pulled toward the attractor.

Fits dv_i = -k_i (v_i - v*_i) independently per axis over every starting point
measured at depth 1, and draws the fitted rates. k is the fraction of the gap to
the attractor that one edit closes, so k = 1 means a single edit lands on it.

Usage: python3 agents/scripts/plot_contraction_rates.py
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_value_space12 import AX  # noqa: E402
from analyze_field import field_ratings, seed_positions, edits  # noqa: E402
from plot_named_axes import probe_points  # noqa: E402

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8982', '#e4e3df'
BAR = '#2a78d6'


def starting_points():
    fr = field_ratings('positions12_field')
    sh = {}
    ed = edits('field-12seeds', fr, sh)
    seeds = seed_positions(fr, sh)
    p0 = {s: seeds[s].mean(0) for (_, s) in ed}
    p1 = {s: p0[s] + np.mean([x['vout'] - x['vin'] for x in v], 0) for (_, s), v in ed.items()}
    ps0, ps1, _ = probe_points()
    p0.update(ps0)
    p1.update(ps1)
    names = sorted(p0)
    return (np.array([p0[s] for s in names]),
            np.array([p1[s] - p0[s] for s in names]), names)


def fit_per_axis(V, D, iters=3000):
    """Alternating least squares for the rate and the fixed point on each axis."""
    ks = np.full(len(AX), 0.6)
    vs = np.mean(V + D, 0)
    for _ in range(iters):
        for i in range(len(AX)):
            den = float(np.sum((V[:, i] - vs[i]) ** 2))
            if den > 1e-9:
                ks[i] = -float(np.sum((V[:, i] - vs[i]) * D[:, i])) / den
            if abs(ks[i]) > 1e-6:
                vs[i] = float(np.mean(V[:, i] + D[:, i] / ks[i]))
    return ks, vs


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    V, D, names = starting_points()
    ks, vs = fit_per_axis(V, D)
    pred = -ks * (V - vs)
    r2 = 1 - np.sum((D - pred) ** 2) / np.sum((D - D.mean(0)) ** 2)
    order = np.argsort(ks)

    fig, ax = plt.subplots(figsize=(10.2, 6.4), facecolor=SURF)
    ax.set_facecolor(SURF)
    fig.text(.012, .955, 'How fast each value is pulled to the attractor',
             fontsize=16, color=INK, weight='medium')
    fig.text(.012, .905, f'Fraction of the gap closed by one edit, fitted per axis over '
             f'{len(names)} starting points.', fontsize=9.8, color=INK2)
    fig.text(.012, .872, f'A rate of 1 would mean one edit lands exactly on the attractor. '
             f'The twelve rates together explain {r2:.0%} of the measured movement.',
             fontsize=9.8, color=INK2)

    y = np.arange(len(AX))
    ax.barh(y, ks[order], height=.62, color=BAR, zorder=3)
    for n, i in enumerate(order):
        ax.text(ks[i] + .013, n, f'{ks[i]:.2f}', va='center', ha='left',
                fontsize=9, color=INK2, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels([AX[i].replace('_', ' ').replace('ai ', 'AI ') for i in order],
                   fontsize=9.5, color=INK)
    ax.set_xlim(0, 1.06)
    ax.set_xticks(np.arange(0, 1.01, .2))
    ax.set_xlabel('fraction of the gap to the attractor closed per edit', fontsize=9.5,
                  color=INK2, labelpad=9)
    ax.grid(True, axis='x', color=GRID, lw=.7, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    for side in ('top', 'right', 'bottom'):
        ax.spines[side].set_visible(False)
    ax.spines['left'].set_color(GRID)

    fig.subplots_adjust(left=.215, right=.975, top=.80, bottom=.105)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'04_contraction_rates.{ext}', dpi=165, facecolor=SURF)
    plt.close(fig)
    print('wrote', OUT / '04_contraction_rates.png')
    print(f'R^2 {r2:.3f} over {len(names)} points')


if __name__ == '__main__':
    main()
