#!/usr/bin/env python3
"""The edit map as a vector field: each rated document, and where it was mapped to.

Every generation is drawn as one arrow from the document the model was given to
the document it submitted. Displacements smaller than the rater's own noise floor
are drawn in grey, because at that size the arrow shows the judge disagreeing with
itself rather than the model changing anything.

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
                                   noise_sd, step_noise)

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
# The three axes with the most independent variance on the twelve-axis ratings.
TRIPLE = ['oversight_deference', 'viewpoint_neutrality', 'warmth']
NAME = {'oversight_deference': 'oversight deference',
        'viewpoint_neutrality': 'viewpoint neutrality', 'warmth': 'warmth'}
SHORT = {'oversight_deference': 'oversight', 'viewpoint_neutrality': 'neutrality',
         'warmth': 'warmth'}
IDX = [AXES.index(a) for a in TRIPLE]

SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8982', '#e4e3df'
GEN_RAMP = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']   # generations 2-6
JUMP, SEED, FLOW, NOISE = '#eb6834', '#1baf7a', '#2a78d6', '#c2c1bb'


def save(fig, stem):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'{stem}.{ext}', dpi=165, facecolor=SURF)
    plt.close(fig)
    print('wrote', OUT / f'{stem}.png')


def vin(r):  return np.asarray(r['vin'], float)[IDX]
def vout(r): return np.asarray(r['vout'], float)[IDX]


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


def arrow3d(ax, a, b, color, lw, alpha, z):
    d = b - a
    if not np.any(d):
        ax.scatter(*a, s=9, facecolor=color, edgecolor='none', alpha=alpha, zorder=z)
        return
    ax.quiver(*a, *d, color=color, lw=lw, alpha=alpha, arrow_length_ratio=.26, zorder=z)


def figure_3d(rows, floor):
    by_model = defaultdict(list)
    for r in rows:
        by_model[r['model']].append(r)
    below = sum(1 for r in rows if np.linalg.norm(vout(r) - vin(r)) < floor)

    fig = plt.figure(figsize=(15, 9.6), facecolor=SURF)
    fig.text(.012, .972, 'The edit map, one arrow per document',
             fontsize=16, color=INK, weight='medium')
    fig.text(.012, .947, f'Each arrow runs from a constitution to the one the model '
             f'submitted after reviewing it. {len(rows)} edits, 5 models, seeded from the '
             'Anthropic and OpenAI model specs.', fontsize=9.5, color=INK2)
    fig.text(.012, .925, f'Grey = displacement below the {floor:.2f} rater-noise floor on these '
             f'three axes ({below} of {len(rows)} edits); at that size the arrow is the judge, '
             'not the model.', fontsize=9.5, color=INK2)

    for i, m in enumerate(sorted(by_model)):
        ax = fig.add_subplot(2, 3, i + 1, projection='3d', facecolor=SURF); style3d(ax)
        rs = by_model[m]
        real = 0
        for r in sorted(rs, key=lambda r: np.linalg.norm(vout(r) - vin(r))):
            a, b = vin(r), vout(r)
            if np.linalg.norm(b - a) < floor:
                arrow3d(ax, a, b, NOISE, 1.0, .75, 1)
            else:
                real += 1
                col = JUMP if r['gen'] == 1 else GEN_RAMP[min(r['gen'] - 2, 4)]
                arrow3d(ax, a, b, col, 2.0 if r['gen'] == 1 else 1.5,
                        .95 if r['gen'] == 1 else .85, 3 if r['gen'] == 1 else 2)
        for r in rs:
            if r['gen'] == 1:
                ax.scatter(*vin(r), s=42, facecolor=SEED, edgecolor=SURF,
                           linewidth=1.3, zorder=6)
        ax.set_title(f'{m}   {real} of {len(rs)} edits above noise',
                     fontsize=10, color=INK, pad=-2)

    # pooled field, binned, generations 2-6
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
    ax.set_title(f'mean of the arrows per region, gens 2-6\n{drawn} bins with n>=8  '
                 '(arrows 5x)', fontsize=10, color=INK, pad=-2)

    handles = [Line2D([], [], color=JUMP, lw=2.4, label='generation 1 (first edit)'),
               *[Line2D([], [], color=GEN_RAMP[j], lw=2, label=f'generation {j+2}')
                 for j in range(5)],
               Line2D([], [], color=NOISE, lw=2, label='within rater noise'),
               Line2D([], [], marker='o', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=8, label='seed (model spec)')]
    fig.legend(handles=handles, loc='lower center', ncol=8, frameon=False, fontsize=8.5,
               labelcolor=INK2, bbox_to_anchor=(.5, .005), handlelength=1.8, columnspacing=1.5)
    fig.subplots_adjust(left=.01, right=.99, top=.90, bottom=.065, wspace=.04, hspace=.14)
    save(fig, '01_edit_map_3d')


def figure_2d(rows, sd):
    pairs = [(0, 1), (0, 2), (1, 2)]
    fig, axes = plt.subplots(2, 3, figsize=(14.5, 9.4), facecolor=SURF)
    fig.text(.012, .963, 'The edit map, projected onto each coordinate plane',
             fontsize=16, color=INK, weight='medium')
    fig.text(.012, .934, 'Top: one arrow per edit, grey where the displacement is below that '
             "plane's rater-noise floor. Bottom: mean of the arrows per 1.5-unit cell, "
             'gens 2-6, cells with n>=8 (label = n).', fontsize=9.5, color=INK2)

    for col, (i, j) in enumerate(pairs):
        floor2 = step_noise(sd, [IDX[i], IDX[j]])
        ax = axes[0, col]; ax.set_facecolor(SURF)
        below = 0
        for r in sorted(rows, key=lambda r: np.linalg.norm((vout(r) - vin(r))[[i, j]])):
            a, b = vin(r)[[i, j]], vout(r)[[i, j]]
            small = np.linalg.norm(b - a) < floor2
            below += small
            if np.allclose(a, b):
                ax.plot(*a, 'o', ms=3, color=NOISE, zorder=1); continue
            ax.annotate('', xy=b, xytext=a, zorder=1 if small else (3 if r['gen'] == 1 else 2),
                        arrowprops=dict(arrowstyle='-|>',
                                        color=NOISE if small else
                                        (JUMP if r['gen'] == 1 else FLOW),
                                        lw=1.0 if small else (1.9 if r['gen'] == 1 else 1.1),
                                        alpha=.8 if small else (.85 if r['gen'] == 1 else .45),
                                        shrinkA=0, shrinkB=0, mutation_scale=9))
        seeds = {r['seed']: vin(r) for r in rows if r['gen'] == 1}
        for nm, v in seeds.items():
            ax.plot(v[i], v[j], 'o', ms=10, mfc=SEED, mec=SURF, mew=1.8, zorder=6)
            ax.annotate(nm.replace('spec_', ''), (v[i], v[j]), textcoords='offset points',
                        xytext=(0, -17), ha='center', fontsize=8.5, color=INK,
                        weight='medium', zorder=7)
        ax.set_title(f'{NAME[TRIPLE[i]]}  vs  {NAME[TRIPLE[j]]}\n'
                     f'noise floor {floor2:.2f}; {below} of {len(rows)} below it',
                     fontsize=10, color=INK, pad=8)

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
        bx.set_title('mean of the arrows per cell  (arrows 3x)', fontsize=9.5, color=INK2, pad=9)

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
               Line2D([], [], color=NOISE, lw=1.6, label='within rater noise'),
               Line2D([], [], marker='o', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=9, label='seed (model spec)')]
    fig.legend(handles=handles, loc='lower center', ncol=4, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.5, .008), handlelength=2, columnspacing=2.2)
    fig.subplots_adjust(left=.05, right=.985, top=.878, bottom=.075, wspace=.26, hspace=.32)
    save(fig, '02_edit_map_planes')


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    per = ratings()
    rows = rows12(per)
    if not rows:
        raise SystemExit('no twelve-axis ratings found; run rate_chains_12axis.py first')
    sd = noise_sd(per)
    floor = step_noise(sd, IDX)
    print(f'{len(rows)} edits; noise floor on {"/".join(TRIPLE)} = {floor:.2f}')
    figure_3d(rows, floor)
    figure_2d(rows, sd)


if __name__ == '__main__':
    main()
