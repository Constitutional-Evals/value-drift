#!/usr/bin/env python3
"""Render the spec-seeded chains as trajectories and a drift field in value space.

Reads only saved results and cached position ratings; never calls an inference
service. Writes PNG, PDF and SVG into reports/10_value_space/figures/.

Usage: python3 agents/scripts/plot_value_space.py
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_value_space import AXES, TRIPLE, ROOT, load, chains  # noqa: E402

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
NAME = {'oversight_deference': 'oversight deference', 'user_autonomy': 'user autonomy',
        'ai_agency': 'AI agency'}
SHORT = {'oversight_deference': 'oversight', 'user_autonomy': 'autonomy', 'ai_agency': 'agency'}
IDX = [AXES.index(a) for a in TRIPLE]

# Palette: validated categorical slots 2 and 3 plus the blue ordinal ramp.
# Five models exceed the three-slot all-pairs limit for scatter forms, so model
# identity is carried by faceting and colour encodes generation instead.
SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8982', '#e4e3df'
GEN_RAMP = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']   # generations 2-6
JUMP, SEED, FLOW, PALE = '#eb6834', '#1baf7a', '#2a78d6', '#b7d3f6'


def save(fig, stem):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'{stem}.{ext}', dpi=165, facecolor=SURF)
    plt.close(fig)
    print('wrote', OUT / f'{stem}.png')


def vin(r):  return np.array(r['vin'], float)[IDX]
def vout(r): return np.array(r['vout'], float)[IDX]


def style3d(ax):
    ax.set_xlim(1, 7); ax.set_ylim(1, 7); ax.set_zlim(1, 7)
    for a in 'xyz':
        getattr(ax, f'set_{a}ticks')([1, 4, 7])
    for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
        pane.pane.set_facecolor(SURF); pane.pane.set_edgecolor(GRID); pane.pane.set_alpha(1)
        pane._axinfo['grid'].update(color=GRID, linewidth=0.6)
        pane.set_tick_params(colors=INK2, labelsize=7)
    ax.set_xlabel(SHORT[TRIPLE[0]], color=INK2, fontsize=8.5, labelpad=4)
    ax.set_ylabel(SHORT[TRIPLE[1]], color=INK2, fontsize=8.5, labelpad=4)
    ax.set_zlabel(SHORT[TRIPLE[2]], color=INK2, fontsize=8.5, labelpad=2)
    ax.view_init(elev=20, azim=-58)


def figure_3d(rows):
    by = chains(rows)
    fig = plt.figure(figsize=(15, 9.6), facecolor=SURF)
    fig.text(.012, .972, 'Where constitution edits land in value space',
             fontsize=16, color=INK, weight='medium')
    fig.text(.012, .947, f'{len(by)} edit chains x 6 generations, seeded from the Anthropic '
             'and OpenAI model specs.', fontsize=9.5, color=INK2)
    fig.text(.012, .925, 'Axes are blind 1-7 judge ratings. Orange = the first edit; '
             'blue = generations 2-6, light to dark.', fontsize=9.5, color=INK2)

    for i, m in enumerate(sorted({r['model'] for r in rows})):
        ax = fig.add_subplot(2, 3, i + 1, projection='3d', facecolor=SURF); style3d(ax)
        cells = [c for c in by if by[c][min(by[c])]['model'] == m]
        for c in cells:
            gens = sorted(by[c])
            for g in gens:
                a, b = vin(by[c][g]), vout(by[c][g])
                col = JUMP if g == 1 else GEN_RAMP[min(g - 2, 4)]
                ax.plot(*zip(a, b), color=col, lw=2.0 if g == 1 else 1.6,
                        alpha=.95 if g == 1 else .8, solid_capstyle='round',
                        zorder=3 if g == 1 else 2)
            ax.scatter(*vin(by[c][gens[0]]), s=46, facecolor=SEED, edgecolor=SURF,
                       linewidth=1.4, zorder=5)
            ax.scatter(*vout(by[c][gens[-1]]), s=30, facecolor=GEN_RAMP[4], edgecolor=SURF,
                       linewidth=1.2, zorder=5)
        ax.set_title(f'{m}   n={len(cells)} chains', fontsize=10, color=INK, pad=-2)

    ax = fig.add_subplot(2, 3, 6, projection='3d', facecolor=SURF); style3d(ax)
    cent = [2.5, 4.75, 6.25]
    acc = defaultdict(list)
    for r in rows:
        if r['gen'] >= 2:
            acc[tuple(np.digitize(vin(r), [4.0, 5.5]))].append(vout(r) - vin(r))
    drawn = 0
    for k, v in acc.items():
        if len(v) < 8:
            continue
        p = np.array([cent[j] for j in k])
        ax.quiver(*p, *(np.mean(v, 0) * 5.0), color=JUMP, lw=2.2,
                  arrow_length_ratio=.32, zorder=4)
        ax.scatter(*p, s=18, facecolor=MUTED, edgecolor=SURF, linewidth=1, zorder=3)
        if len(v) >= 14:
            ax.text(*(p + [0, 0, .5]), f'n={len(v)}', fontsize=7, color=MUTED, ha='center')
        drawn += 1
    ax.set_title(f'mean drift per step, gens 2-6\n{drawn} bins with n>=8  '
                 '(arrows 5x; n shown for n>=14)', fontsize=10, color=INK, pad=-2)

    handles = [Line2D([], [], color=JUMP, lw=2.4, label='generation 1 (first edit)'),
               *[Line2D([], [], color=GEN_RAMP[j], lw=2, label=f'generation {j+2}')
                 for j in range(5)],
               Line2D([], [], marker='o', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=8, label='seed (model spec)'),
               Line2D([], [], marker='o', color='none', markerfacecolor=GEN_RAMP[4],
                      markeredgecolor=SURF, markersize=7, label='chain endpoint')]
    fig.legend(handles=handles, loc='lower center', ncol=8, frameon=False, fontsize=8.5,
               labelcolor=INK2, bbox_to_anchor=(.5, .005), handlelength=1.8, columnspacing=1.6)
    fig.subplots_adjust(left=.01, right=.99, top=.90, bottom=.065, wspace=.04, hspace=.14)
    save(fig, '01_trajectories_3d')


def figure_2d(rows):
    by = chains(rows)
    pairs = [(0, 1), (0, 2), (1, 2)]
    fig, axes = plt.subplots(2, 3, figsize=(14.5, 9.4), facecolor=SURF)
    fig.text(.012, .963, 'The drift field, projected onto each coordinate plane',
             fontsize=16, color=INK, weight='medium')
    fig.text(.012, .934, 'Top: every edit as an arrow from input to output. Bottom: mean drift '
             'per 1.5-unit cell, gens 2-6 only, cells with n>=8 (label = n).',
             fontsize=9.5, color=INK2)

    for col, (i, j) in enumerate(pairs):
        ax = axes[0, col]; ax.set_facecolor(SURF)
        for r in rows:
            a, b = vin(r)[[i, j]], vout(r)[[i, j]]
            if np.allclose(a, b):
                ax.plot(*a, 'o', ms=3, color=PALE, zorder=1)
                continue
            ax.annotate('', xy=b, xytext=a, zorder=3 if r['gen'] == 1 else 2,
                        arrowprops=dict(arrowstyle='-|>',
                                        color=JUMP if r['gen'] == 1 else FLOW,
                                        lw=1.9 if r['gen'] == 1 else 1.1,
                                        alpha=.85 if r['gen'] == 1 else .4,
                                        shrinkA=0, shrinkB=0, mutation_scale=9))
        for nm, v in {by[c][1]['seed']: vin(by[c][1]) for c in by}.items():
            ax.plot(v[i], v[j], 'o', ms=10, mfc=SEED, mec=SURF, mew=1.8, zorder=6)
            ax.annotate(nm.replace('spec_', ''), (v[i], v[j]), textcoords='offset points',
                        xytext=(0, -17), ha='center', fontsize=8.5, color=INK,
                        weight='medium', zorder=7)
        ax.set_title(f'{NAME[TRIPLE[i]]}  vs  {NAME[TRIPLE[j]]}', fontsize=10.5, color=INK, pad=9)

        bx = axes[1, col]; bx.set_facecolor(SURF)
        acc = defaultdict(list)
        for r in rows:
            if r['gen'] < 2:
                continue
            k = (int(np.digitize(vin(r)[i], [2.5, 4.0, 5.5])),
                 int(np.digitize(vin(r)[j], [2.5, 4.0, 5.5])))
            acc[k].append((vout(r) - vin(r))[[i, j]])
        for (ki, kj), v in acc.items():
            if len(v) < 8:
                continue
            p = np.array([1.75 + 1.5 * ki, 1.75 + 1.5 * kj])
            d = np.mean(v, 0) * 3.0
            # clamp the tip so no arrow escapes the panel
            lim = np.where(d > 0, 7.2, .8)
            t = min([1.0] + [(b - a) / dd for a, dd, b in zip(p, d, lim) if abs(dd) > 1e-9])
            d = d * max(t, 0.0)
            bx.annotate('', xy=p + d, xytext=p, zorder=4,
                        arrowprops=dict(arrowstyle='-|>', color=JUMP, lw=2.4,
                                        shrinkA=0, shrinkB=0, mutation_scale=14))
            bx.plot(*p, 'o', ms=4, mfc=MUTED, mec=SURF, mew=1, zorder=3)
            off = -12 * d / (np.linalg.norm(d) or 1)
            bx.annotate(f'{len(v)}', p, textcoords='offset points', xytext=tuple(off),
                        ha='center', va='center', fontsize=7.5, color=MUTED, zorder=5)
        bx.set_title('mean drift per cell  (arrows 3x)', fontsize=9.5, color=INK2, pad=9)

        for a_ in (ax, bx):
            a_.set_xlim(.6, 7.4); a_.set_ylim(.6, 7.4)
            a_.set_xticks(range(1, 8)); a_.set_yticks(range(1, 8))
            a_.set_xlabel(NAME[TRIPLE[i]], fontsize=9, color=INK2)
            a_.set_ylabel(NAME[TRIPLE[j]], fontsize=9, color=INK2)
            a_.grid(True, color=GRID, lw=.6, zorder=0); a_.set_axisbelow(True)
            a_.tick_params(colors=INK2, labelsize=8, length=0)
            for sp in a_.spines.values():
                sp.set_color(GRID)
            a_.set_aspect('equal')

    handles = [Line2D([], [], color=JUMP, lw=2.2, label='generation 1 (first edit)'),
               Line2D([], [], color=FLOW, lw=1.4, alpha=.6, label='generations 2-6'),
               Line2D([], [], marker='o', color='none', markerfacecolor=PALE,
                      markeredgecolor=PALE, markersize=6, label='no change'),
               Line2D([], [], marker='o', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=9, label='seed (model spec)')]
    fig.legend(handles=handles, loc='lower center', ncol=4, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.5, .008), handlelength=2, columnspacing=2.2)
    fig.subplots_adjust(left=.05, right=.985, top=.895, bottom=.075, wspace=.26, hspace=.3)
    save(fig, '02_drift_field_2d')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', nargs='+', default=None)
    args = ap.parse_args()
    rows = load(args.batch) if args.batch else load()
    if not rows:
        raise SystemExit('no rated chain generations found under runs/elicit/')
    figure_3d(rows)
    figure_2d(rows)


if __name__ == '__main__':
    main()
