#!/usr/bin/env python3
"""The edit map per model: the average vector leaving each sampled point.

One panel per model, never pooled - different models are different maps.
Within a panel, every distinct plotted position gets one arrow: the mean of
the edits observed leaving it. Arrows whose mean is smaller than the rater
noise on that mean are drawn grey.

The noise on a mean of n edits out of one position is sd*sqrt(1 + 1/n), not
sd*sqrt(2)/sqrt(n): the edits share a tail rating, so that part does not
average away.

Reads only saved results and the twelve-axis ratings; never calls an inference
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_value_space12 import (AX as AXES, ratings, rows as rows12,  # noqa: E402
                                   noise_sd)

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
TRIPLE = ['oversight_deference', 'viewpoint_neutrality', 'warmth']
NAME = {'oversight_deference': 'oversight deference',
        'viewpoint_neutrality': 'viewpoint neutrality', 'warmth': 'warmth'}
SHORT = {'oversight_deference': 'oversight', 'viewpoint_neutrality': 'neutrality',
         'warmth': 'warmth'}
IDX = [AXES.index(a) for a in TRIPLE]

SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8982', '#e4e3df'
JUMP, SEED, NOISE = '#eb6834', '#1baf7a', '#c2c1bb'


def save(fig, stem):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'{stem}.{ext}', dpi=165, facecolor=SURF)
    plt.close(fig)
    print('wrote', OUT / f'{stem}.png')


def mean_field(rows, sub, rng=None):
    """position -> (mean displacement, n, set of distinct source documents)."""
    acc = defaultdict(list)
    for r in rows:
        a = np.asarray(r['vin'], float)[sub]
        d = np.asarray(r['vout'], float)[sub] - a
        acc[tuple(a)].append((d, r['hin']))
    out = {}
    for p, items in acc.items():
        d = np.array([x[0] for x in items])
        out[p] = (d.mean(0), len(items), {x[1] for x in items})
    return out


def mean_floor(sd, sub, n, draws=60000, seed=0):
    """Expected |mean displacement| from rating noise alone, for a mean of n edits."""
    rng = np.random.default_rng(seed + n)
    s = np.asarray(sd)[sub] * np.sqrt(1.0 + 1.0 / n)
    return float(np.mean(np.linalg.norm(rng.normal(0.0, s, size=(draws, len(sub))), axis=1)))


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


def figure_3d(rows, sd, scale):
    by_model = defaultdict(list)
    for r in rows:
        by_model[r['model']].append(r)
    models = sorted(by_model)

    fig = plt.figure(figsize=(15, 9.6), facecolor=SURF)
    fig.text(.012, .972, 'The edit map, one average vector per position',
             fontsize=16, color=INK, weight='medium')
    fig.text(.012, .947, 'One panel per model: these are five different maps and are never pooled. '
             'Each arrow is the mean of every edit observed leaving that position.',
             fontsize=9.5, color=INK2)
    fig.text(.012, .925, f'Dot size is how many edits the mean is over. Grey = mean smaller than '
             f'the rater noise on a mean of that many edits. Arrows drawn {scale}x.',
             fontsize=9.5, color=INK2)

    for i, m in enumerate(models):
        ax = fig.add_subplot(2, 3, i + 1, projection='3d', facecolor=SURF); style3d(ax)
        field = mean_field(by_model[m], IDX)
        real = 0
        for p, (d, n, srcs) in sorted(field.items(), key=lambda kv: kv[1][1]):
            a = np.array(p)
            above = np.linalg.norm(d) >= mean_floor(sd, IDX, n)
            real += above
            col = JUMP if above else NOISE
            ax.scatter(*a, s=6 + 3.0 * n, facecolor=MUTED if above else NOISE,
                       edgecolor=SURF, linewidth=.6, alpha=.9, zorder=2)
            if np.any(d):
                ax.quiver(*a, *(d * scale), color=col, lw=2.0 if above else 1.0,
                          alpha=.95 if above else .7, arrow_length_ratio=.3,
                          zorder=4 if above else 1)
        seeds = {r['hin']: np.asarray(r['vin'], float)[IDX] for r in by_model[m] if r['gen'] == 1}
        for v in seeds.values():
            ax.scatter(*v, s=46, facecolor=SEED, edgecolor=SURF, linewidth=1.3, zorder=6)
        ax.set_title(f'{m}\n{len(field)} positions, {real} with a mean above noise',
                     fontsize=9.5, color=INK, pad=2)

    ax = fig.add_subplot(2, 3, 6); ax.set_facecolor(SURF); ax.axis('off')
    ax.text(.02, .99, 'How to read a panel', fontsize=11, color=INK, weight='medium',
            transform=ax.transAxes)
    lines = [
        'Each dot is a position some constitution occupied on these',
        'three axes. The arrow from it is the average of every edit',
        'that model made starting from there.',
        '',
        'A long arrow means the model reliably moves documents at',
        'that position in one direction. A grey arrow means the',
        'average is smaller than the judge disagreeing with itself,',
        'so nothing can be concluded from it.',
        '',
        'Big dots are better estimates: the mean is over more edits.',
        'Positions are integer ratings, so distinct constitutions that',
        'score the same on these three axes share a dot and are',
        'averaged together - they may differ on the other nine axes.',
        '',
        'Green marks the seed each chain started from.',
    ]
    for k, t in enumerate(lines):
        ax.text(.02, .905 - k * .052, t, fontsize=8.6, color=INK2, transform=ax.transAxes)

    handles = [Line2D([], [], color=JUMP, lw=2.4, label='mean above rater noise'),
               Line2D([], [], color=NOISE, lw=2, label='mean within rater noise'),
               Line2D([], [], marker='o', color='none', markerfacecolor=MUTED,
                      markeredgecolor=SURF, markersize=5, label='position (1 edit)'),
               Line2D([], [], marker='o', color='none', markerfacecolor=MUTED,
                      markeredgecolor=SURF, markersize=11, label='position (many edits)'),
               Line2D([], [], marker='o', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=8, label='seed (model spec)')]
    fig.legend(handles=handles, loc='lower center', ncol=5, frameon=False, fontsize=8.8,
               labelcolor=INK2, bbox_to_anchor=(.5, .005), handlelength=1.8, columnspacing=2.0)
    fig.subplots_adjust(left=.01, right=.99, top=.865, bottom=.065, wspace=.04, hspace=.20)
    save(fig, '01_edit_map_3d')


def figure_planes(rows, sd, scale):
    by_model = defaultdict(list)
    for r in rows:
        by_model[r['model']].append(r)
    models = sorted(by_model)
    pairs = [(0, 1), (0, 2), (1, 2)]

    fig, axes = plt.subplots(len(models), 3, figsize=(11.5, 17.5), facecolor=SURF)
    fig.text(.012, .978, 'The edit map by model and plane', fontsize=16, color=INK,
             weight='medium')
    fig.text(.012, .967, 'Rows are models, never pooled. Each arrow is the mean of the edits '
             f'leaving that position; grey means the mean is within rater noise. Arrows {scale}x.',
             fontsize=9, color=INK2)

    for rix, m in enumerate(models):
        for cix, (i, j) in enumerate(pairs):
            ax = axes[rix, cix]; ax.set_facecolor(SURF)
            sub = [IDX[i], IDX[j]]
            field = mean_field(by_model[m], sub)
            for p, (d, n, _) in sorted(field.items(), key=lambda kv: kv[1][1]):
                a = np.array(p)
                above = np.linalg.norm(d) >= mean_floor(sd, sub, n)
                ax.plot(*a, 'o', ms=2.4 + .55 * n, mfc=MUTED if above else NOISE,
                        mec=SURF, mew=.5, alpha=.9, zorder=2)
                if np.any(d):
                    b = a + d * scale
                    b = np.clip(b, .75, 7.25)
                    ax.annotate('', xy=b, xytext=a, zorder=4 if above else 1,
                                arrowprops=dict(arrowstyle='-|>',
                                                color=JUMP if above else NOISE,
                                                lw=1.9 if above else 1.0,
                                                alpha=.95 if above else .7,
                                                shrinkA=0, shrinkB=0, mutation_scale=10))
            for r in by_model[m]:
                if r['gen'] == 1:
                    v = np.asarray(r['vin'], float)[sub]
                    ax.plot(v[0], v[1], 'o', ms=8, mfc=SEED, mec=SURF, mew=1.5, zorder=6)
            ax.set_xlim(.6, 7.4); ax.set_ylim(.6, 7.4)
            ax.set_xticks(range(1, 8)); ax.set_yticks(range(1, 8))
            ax.grid(True, color=GRID, lw=.6, zorder=0); ax.set_axisbelow(True)
            ax.tick_params(colors=INK2, labelsize=7, length=0)
            for sp in ax.spines.values():
                sp.set_color(GRID)
            ax.set_aspect('equal')
            ax.set_xlabel(NAME[TRIPLE[i]], fontsize=8, color=INK2)
            if cix == 0:
                ax.set_ylabel(f'{m}\n\n{NAME[TRIPLE[j]]}', fontsize=8.5, color=INK)
            else:
                ax.set_ylabel(NAME[TRIPLE[j]], fontsize=8, color=INK2)

    handles = [Line2D([], [], color=JUMP, lw=2.2, label='mean above rater noise'),
               Line2D([], [], color=NOISE, lw=1.6, label='mean within rater noise'),
               Line2D([], [], marker='o', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=8, label='seed (model spec)')]
    fig.legend(handles=handles, loc='lower center', ncol=3, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.5, .004), handlelength=2, columnspacing=2.2)
    fig.subplots_adjust(left=.085, right=.985, top=.952, bottom=.052, wspace=.3, hspace=.30)
    save(fig, '02_edit_map_planes')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scale', type=float, default=1.0, help='arrow exaggeration')
    args = ap.parse_args()
    per = ratings()
    rows = rows12(per)
    if not rows:
        raise SystemExit('no twelve-axis ratings found; run rate_chains_12axis.py first')
    sd = noise_sd(per)
    print(f'{len(rows)} edits; mean-arrow noise floor at n=1 {mean_floor(sd, IDX, 1):.2f}, '
          f'n=4 {mean_floor(sd, IDX, 4):.2f}, n=20 {mean_floor(sd, IDX, 20):.2f}')
    figure_3d(rows, sd, args.scale)
    figure_planes(rows, sd, args.scale)


if __name__ == '__main__':
    main()
