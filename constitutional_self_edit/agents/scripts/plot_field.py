#!/usr/bin/env python3
"""The twelve seed vectors and the point they aim at.

Three views of one result: where each seed goes in the plane that best separates
the seeds (PCA, so no axis triple has to be chosen), how far each sits from the
common centroid before and after one edit, and where that centroid lies on all
twelve axes.

Usage: python3 agents/scripts/plot_field.py
"""
from __future__ import annotations
import argparse
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
from analyze_field import field_ratings, seed_positions, edits  # noqa: E402
from analyze_value_space12 import AX, noise_sd  # noqa: E402

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8982', '#e4e3df'
JUMP, SEED, FLOW, PALE = '#eb6834', '#1baf7a', '#2a78d6', '#b7d3f6'
LABEL = {'openai_spec_derived': 'OpenAI spec', 'claude_derived': "Claude constitution",
         'animal_welfare': 'animal welfare', 'flourishing': 'flourishing',
         'eb_kindness': 'kindness', 'eb_conservatism': 'conservatism',
         'eb_deep_ecology': 'deep ecology', 'broad_draft': 'broad draft',
         'deferential': 'deferential', 'autonomous': 'autonomous',
         'protective': 'protective', 'libertarian': 'libertarian'}


def main():
    ap = argparse.ArgumentParser(); ap.parse_args()
    rat = field_ratings('positions12_field')
    sh = {}
    ed = edits('field-12seeds', rat, sh)
    seeds = seed_positions(rat, sh)
    sd = noise_sd()

    names = sorted({s for _, s in ed})
    p0 = {s: seeds[s].mean(0) for s in names}
    p1 = {s: p0[s] + np.mean([x['vout'] - x['vin'] for x in v], 0)
          for (_, s), v in ed.items()}
    n_of = {s: len(v) for (_, s), v in ed.items()}
    c1 = np.mean([p1[s] for s in names], 0)

    fig = plt.figure(figsize=(15.5, 8.2), facecolor=SURF)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 1], height_ratios=[1, 1],
                          left=.055, right=.985, top=.845, bottom=.085, wspace=.22, hspace=.52)
    fig.text(.012, .955, 'Twelve starting constitutions, one edit each',
             fontsize=17, color=INK, weight='medium')
    fig.text(.012, .918, 'qwen38_27b, blind review, 350-word cap. Each seed was reviewed six '
             'times independently; the arrow is the mean of those six edits.',
             fontsize=10, color=INK2)
    fig.text(.012, .893, 'All twelve move toward one point. Mean distance between seeds falls '
             '8.33 to 4.49 in a single edit.', fontsize=10, color=INK)

    # --- A. PCA plane fitted to all 24 positions -------------------------
    ax = fig.add_subplot(gs[:, 0]); ax.set_facecolor(SURF)
    M = np.array([p0[s] for s in names] + [p1[s] for s in names])
    mu = M.mean(0)
    U, S, Vt = np.linalg.svd(M - mu, full_matrices=False)
    ev = S**2 / (S**2).sum()
    P = (M - mu) @ Vt[:2].T
    A, B = P[:len(names)], P[len(names):]
    cen = B.mean(0)
    for i, s in enumerate(names):
        ax.annotate('', xy=B[i], xytext=A[i], zorder=3,
                    arrowprops=dict(arrowstyle='-|>', color=JUMP, lw=2.0,
                                    shrinkA=0, shrinkB=0, mutation_scale=13, alpha=.9))
    ax.scatter(*A.T, s=58, facecolor='none', edgecolor=MUTED, linewidth=1.6, zorder=4)
    ax.scatter(*B.T, s=40, facecolor=FLOW, edgecolor=SURF, linewidth=1.2, zorder=5)
    ax.scatter(*cen, s=340, marker='*', facecolor=SEED, edgecolor=SURF, linewidth=1.4, zorder=7)
    ax.annotate('centroid after one edit', cen, textcoords='offset points', xytext=(16, -30),
                fontsize=9, color=INK, weight='medium', zorder=9,
                bbox=dict(boxstyle='round,pad=0.2', fc=SURF, ec='none', alpha=.9),
                arrowprops=dict(arrowstyle='-', color=MUTED, lw=.8))
    # push each label away from the centroid, so the crowded middle stays legible
    for i, s in enumerate(names):
        off = A[i] - cen
        off = off / (np.linalg.norm(off) or 1)
        pad = 15 if np.linalg.norm(A[i] - cen) > 1.5 else 26
        ax.annotate(LABEL[s], A[i], textcoords='offset points',
                    xytext=(pad * off[0], pad * off[1]), ha='center', va='center',
                    fontsize=8.6, color=INK, zorder=8,
                    bbox=dict(boxstyle='round,pad=0.15', fc=SURF, ec='none', alpha=.85))
    ax.set_title(f'Where each seed is sent\nplane of the first two principal components '
                 f'({100*ev[:2].sum():.0f}% of the spread; the rest is out of plane)',
                 fontsize=11, color=INK, pad=10)
    ax.set_xlabel(f'PC1  ({100*ev[0]:.0f}%)', fontsize=9, color=INK2)
    ax.set_ylabel(f'PC2  ({100*ev[1]:.0f}%)', fontsize=9, color=INK2)
    ax.grid(True, color=GRID, lw=.6); ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    for sp in ax.spines.values(): sp.set_color(GRID)
    ax.set_aspect('equal')

    # --- B. distance to the centroid, before and after -------------------
    bx = fig.add_subplot(gs[0, 1]); bx.set_facecolor(SURF)
    d0 = {s: np.linalg.norm(p0[s] - c1) for s in names}
    d1 = {s: np.linalg.norm(p1[s] - c1) for s in names}
    order = sorted(names, key=lambda s: -d0[s])
    for k, s in enumerate(order):
        bx.plot([d0[s], d1[s]], [k, k], color=GRID, lw=2.4, zorder=1, solid_capstyle='round')
        bx.plot(d0[s], k, 'o', ms=7, mfc='none', mec=MUTED, mew=1.6, zorder=3)
        bx.plot(d1[s], k, 'o', ms=7, mfc=FLOW, mec=SURF, mew=1.1, zorder=4)
    bx.set_yticks(range(len(order)))
    bx.set_yticklabels([LABEL[s] for s in order], fontsize=8.4, color=INK)
    bx.invert_yaxis(); bx.set_xlim(0, max(d0.values()) * 1.08)
    bx.set_xlabel('distance to the common centroid (12 axes)', fontsize=9, color=INK2)
    bx.set_title('Every seed ends up closer', fontsize=11, color=INK, pad=8)
    bx.grid(True, axis='x', color=GRID, lw=.6); bx.set_axisbelow(True)
    bx.tick_params(colors=INK2, labelsize=8, length=0)
    for sp in bx.spines.values(): sp.set_color(GRID)

    # --- C. the attractor's profile --------------------------------------
    cx = fig.add_subplot(gs[1, 1]); cx.set_facecolor(SURF)
    s0 = np.array([[p0[s][i] for s in names] for i in range(len(AX))])
    s1 = np.array([[p1[s][i] for s in names] for i in range(len(AX))])
    order_ax = np.argsort(-c1)
    for k, i in enumerate(order_ax):
        cx.plot([s1[i].min(), s1[i].max()], [k, k], color=PALE, lw=5, zorder=1,
                solid_capstyle='round')
        cx.plot([s0[i].min(), s0[i].max()], [k, k], color=GRID, lw=1.6, zorder=0)
        cx.plot(c1[i], k, 'o', ms=8, mfc=SEED, mec=SURF, mew=1.2, zorder=4)
    cx.set_yticks(range(len(AX)))
    cx.set_yticklabels([AX[i].replace('_', ' ') for i in order_ax], fontsize=8.2, color=INK)
    cx.invert_yaxis(); cx.set_xlim(.6, 7.4); cx.set_xticks(range(1, 8))
    cx.set_xlabel('rating', fontsize=9, color=INK2)
    cx.set_title('What it pulls toward: the centroid, and how far the twelve still spread',
                 fontsize=11, color=INK, pad=8)
    cx.grid(True, axis='x', color=GRID, lw=.6); cx.set_axisbelow(True)
    cx.tick_params(colors=INK2, labelsize=8, length=0)
    for sp in cx.spines.values(): sp.set_color(GRID)

    handles = [Line2D([], [], marker='o', color='none', markerfacecolor='none',
                      markeredgecolor=MUTED, markersize=8, markeredgewidth=1.6,
                      label='starting constitution'),
               Line2D([], [], color=JUMP, lw=2.2, label='mean of six edits'),
               Line2D([], [], marker='o', color='none', markerfacecolor=FLOW,
                      markeredgecolor=SURF, markersize=8, label='after one edit'),
               Line2D([], [], marker='*', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=15, label='centroid after one edit'),
               Line2D([], [], color=PALE, lw=5, label='range after'),
               Line2D([], [], color=GRID, lw=2, label='range before')]
    fig.legend(handles=handles, loc='lower center', ncol=6, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.5, .008), handlelength=1.9, columnspacing=1.8)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'03_field_twelve_seeds.{ext}', dpi=165, facecolor=SURF)
    plt.close(fig)
    print('wrote', OUT / '03_field_twelve_seeds.png')
    print(f'PC1+PC2 capture {100*ev[:2].sum():.0f}% of the spread')


if __name__ == '__main__':
    main()
