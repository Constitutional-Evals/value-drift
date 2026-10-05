#!/usr/bin/env python3
"""Sol's one-step field on the working plane, matching figure 06.

Seventeen starts: the twelve seeds plus the five decoded constitutions, placed
where figure 05 placed them. Each arrow is GPT-6 Sol's mean edit, and the star
is the fixed point of dv = -k (v - v*) fit on all seventeen.

Usage: python3 agents/scripts/plot_sol_axes.py
"""
from __future__ import annotations
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
from analyze_value_space12 import AX  # noqa: E402
from analyze_field import field_ratings, seed_positions, edits  # noqa: E402
from plot_contraction_rates import fit_per_axis  # noqa: E402
from plot_named_axes import (  # noqa: E402
    LAB, SURF, INK, INK2, MUTED, GRID, JUMP, SEED, FLOW, WORKING,
    probe_points, attractor_point, plane_points)
from plot_sonnet_axes import _arrows  # noqa: E402
from selfhost_v3 import AXIS_LABELS  # noqa: E402

OUT = ROOT / 'reports' / '10_value_space' / 'figures'


def sol_field():
    """Start at the same positions as figure 05. The arrow is Sol's edit."""
    qwen = field_ratings('positions12_field')
    qh = {}
    qed = edits('field-12seeds', qwen, qh)
    seeds = seed_positions(qwen, qh)
    p0 = {s: seeds[s].mean(0) for (_, s) in qed}
    for extra in (probe_points()[0], attractor_point()[0], plane_points()[0]):
        p0.update(extra)

    p1, n = {}, {}
    _arrows(p0, 'field-sol', 'positions12_sol', p1, n)
    names = [s for s in p0 if s in p1]
    return p0, p1, n, names


def main():
    p0, p1, n_edits, names = sol_field()
    V = np.array([p0[s] for s in names])
    D = np.array([p1[s] - p0[s] for s in names])
    ks, star = fit_per_axis(V, D)
    i, j = AX.index(WORKING[0]), AX.index(WORKING[1])
    print(f'{len(names)} seeds, {sum(n_edits.values())} edits')
    print('edits per seed:', {s: n_edits[s] for s in names})
    print(f'Sol fixed point: caution {star[i]:.2f} (k={ks[i]:.2f}), '
          f'long-term {star[j]:.2f} (k={ks[j]:.2f})')

    fig, ax = plt.subplots(figsize=(8.2, 8.35), facecolor=SURF)
    missed = 6 * len(names) - sum(n_edits.values())
    held = f' {missed} failed reviews are left out.' if missed else ''
    fig.text(.03, .972, "Sol's edits, on the working plane",
             fontsize=16, color=INK, weight='medium')
    fig.text(.03, .938, 'Seventeen starting points, their mean edit, and the fixed point they contract toward.',
             fontsize=9.2, color=INK2)
    fig.text(.03, .912, f'Same plane as the Qwen panel. Twelve published seeds and five decoded.{held}',
             fontsize=9.2, color=INK2)

    ax.set_facecolor(SURF)
    label_pts = []
    for s in names:
        a = np.array([p0[s][i], p0[s][j]])
        b = np.array([p1[s][i], p1[s][j]])
        if not np.allclose(a, b):
            ax.annotate('', xy=b, xytext=a, zorder=3,
                        arrowprops=dict(arrowstyle='-|>', color=JUMP, lw=1.8, alpha=.85,
                                        shrinkA=0, shrinkB=0, mutation_scale=11))
        ax.plot(*a, 'o', ms=7, mfc='none', mec=MUTED, mew=1.5, zorder=4)
        ax.plot(*b, 'o', ms=5, mfc=FLOW, mec=SURF, mew=.9, zorder=5)
        label_pts.append((s, a))

    spots = {}
    center = np.array([star[i], star[j]])
    for n_, (s_, a) in enumerate(label_pts):
        d = a - center
        d = d / (np.linalg.norm(d) or 1)
        ang = 2 * np.pi * n_ / len(label_pts)
        spots[s_] = a + d * 0.45 + 0.03 * np.array([np.cos(ang), np.sin(ang)])
    for _ in range(600):
        moved = False
        keys = list(spots)
        for u in range(len(keys)):
            for v in range(u + 1, len(keys)):
                pu, pv = spots[keys[u]], spots[keys[v]]
                diff = pu - pv
                dist = float(np.linalg.norm(diff)) or 1e-6
                if dist < 0.78:
                    push = (diff / dist) * (0.78 - dist) / 2
                    spots[keys[u]] = pu + push
                    spots[keys[v]] = pv - push
                    moved = True
        if not moved:
            break
    for s_, a in label_pts:
        spots[s_] = np.clip(spots[s_], 0.75, 7.25)
        ax.annotate(LAB[s_], spots[s_], ha='center', va='center',
                    fontsize=7.4, color=INK2, zorder=7,
                    bbox=dict(boxstyle='round,pad=.12', fc=SURF, ec='none', alpha=.85))

    ax.plot(star[i], star[j], '*', ms=20, mfc=SEED, mec=SURF, mew=1.2, zorder=8)
    ax.set_xlim(.5, 7.5)
    ax.set_ylim(.5, 7.5)
    ax.set_xticks(range(1, 8))
    ax.set_yticks(range(1, 8))
    ax.set_xlabel(WORKING[0].replace('_', ' '), fontsize=9.5, color=INK2, labelpad=14)
    ax.set_ylabel(WORKING[1].replace('_', ' '), fontsize=9.5, color=INK2, labelpad=16)
    xlo, xhi = AXIS_LABELS[WORKING[0]]
    ylo, yhi = AXIS_LABELS[WORKING[1]]
    ax.annotate(f'1 = {xlo}', xy=(0, 0), xycoords='axes fraction',
                textcoords='offset points', xytext=(0, -27), ha='left', va='top',
                fontsize=7.6, color=MUTED, annotation_clip=False)
    ax.annotate(f'{xhi} = 7', xy=(1, 0), xycoords='axes fraction',
                textcoords='offset points', xytext=(0, -27), ha='right', va='top',
                fontsize=7.6, color=MUTED, annotation_clip=False)
    ax.annotate(f'1 = {ylo}', xy=(0, 0), xycoords='axes fraction',
                textcoords='offset points', xytext=(-30, 0), ha='center', va='bottom',
                fontsize=7.6, color=MUTED, rotation=90, annotation_clip=False)
    ax.annotate(f'{yhi} = 7', xy=(0, 1), xycoords='axes fraction',
                textcoords='offset points', xytext=(-30, 0), ha='center', va='top',
                fontsize=7.6, color=MUTED, rotation=90, annotation_clip=False)
    ax.set_title('Working plane: caution x long term orientation\n'
                 'where the corpus spreads out, and where the measured drift is largest',
                 fontsize=10.5, color=INK, pad=9)
    ax.grid(True, color=GRID, lw=.6)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.set_aspect('equal')

    handles = [Line2D([], [], marker='o', color='none', markerfacecolor='none',
                      markeredgecolor=MUTED, markersize=8, markeredgewidth=1.5, label='seed'),
               Line2D([], [], color=JUMP, lw=2, label='mean edit vector'),
               Line2D([], [], marker='o', color='none', markerfacecolor=FLOW,
                      markeredgecolor=SURF, markersize=7, label='after one edit'),
               Line2D([], [], marker='*', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=15, label='Sol attractor')]
    fig.legend(handles=handles, loc='lower center', ncol=4, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.52, .012), handlelength=1.8, columnspacing=1.4)
    fig.subplots_adjust(left=.13, right=.97, top=.86, bottom=.13)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'07_sol_named_axes.{ext}', dpi=165, facecolor=SURF)
    print('wrote', OUT / '07_sol_named_axes.png')


if __name__ == '__main__':
    main()
