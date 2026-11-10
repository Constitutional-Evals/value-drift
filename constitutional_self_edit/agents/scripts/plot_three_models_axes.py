#!/usr/bin/env python3
"""Figures 05, 06 and 07 side by side: Qwen, Sonnet and Sol on the working plane.

One panel per model, same seventeen starts in every panel: each start's mean
edit, the fitted fixed point and the blind drafts. No figure title, no
interpolated field, for use in a paper.

Usage: python3 agents/scripts/plot_three_models_axes.py
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
    LAB, SURF, INK, INK2, MUTED, JUMP, SEED, FLOW, WORKING,
    style_plane, probe_points, attractor_point, plane_points,
    draft_positions, draw_drafts, draft_handle)
from plot_sonnet_axes import sonnet_field  # noqa: E402
from plot_sol_axes import sol_field  # noqa: E402

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
# LLM-written starts: the five decoded constitutions and the agent-drafted broad draft
UNLABELED = {'attractor_start', 'mid_immediate', 'cautious_immediate', 'C1_LT6', 'C7_LT3',
             'broad_draft'}


def qwen_field():
    """The seventeen starts and Qwen's mean edits, as in figure 05."""
    fr = field_ratings('positions12_field')
    sh = {}
    ed = edits('field-12seeds', fr, sh)
    seeds = seed_positions(fr, sh)
    names = sorted({s for _, s in ed})
    p0 = {s: seeds[s].mean(0) for s in names}
    p1 = {s: p0[s] + np.mean([x['vout'] - x['vin'] for x in v], 0) for (_, s), v in ed.items()}
    extra = [probe_points(), attractor_point(), plane_points()]
    for s0, s1, _ in extra:
        p0.update(s0)
        p1.update(s1)
    names = names + [s for s0, _, _ in extra for s in sorted(s0)]
    return p0, p1, names


def draw_edit_panel(ax, p0, p1, names, star, i, j, title):
    """Mean edit arrows from each start, labels pushed clear of each other."""
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
        if s not in UNLABELED:
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
    style_plane(ax, WORKING)
    ax.set_title(title, fontsize=13, color=INK, pad=10, weight='medium')


def main():
    rows = [('Qwen3.8 27B', qwen_field(), 'qwen38_27b'),
            ('Claude Sonnet 5', sonnet_field(), 'sonnet5'),
            ('GPT-6 Sol', sol_field(), 'gpt6_sol')]
    i, j = AX.index(WORKING[0]), AX.index(WORKING[1])

    fig = plt.figure(figsize=(21, 8.2), facecolor=SURF)
    gs = fig.add_gridspec(1, 3, left=.05, right=.99, top=.93, bottom=.17, wspace=.2)
    for r, (model, field, draft_id) in enumerate(rows):
        p0, p1, names = field[0], field[1], field[-1]
        V = np.array([p0[s] for s in names])
        D = np.array([p1[s] - p0[s] for s in names])
        _, star = fit_per_axis(V, D)
        print(f'{model}: {len(names)} starts, fixed point caution {star[i]:.2f}, '
              f'long-term {star[j]:.2f}')
        ax = fig.add_subplot(gs[r])
        draw_edit_panel(ax, p0, p1, names, star, i, j, model)
        draw_drafts(ax, draft_positions(draft_id), i, j)

    handles = [Line2D([], [], marker='o', color='none', markerfacecolor='none',
                      markeredgecolor=MUTED, markersize=8, markeredgewidth=1.5, label='seed'),
               Line2D([], [], color=JUMP, lw=2, label='mean edit vector'),
               Line2D([], [], marker='o', color='none', markerfacecolor=FLOW,
                      markeredgecolor=SURF, markersize=7, label='after one edit'),
               Line2D([], [], marker='*', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=15, label='attractor'),
               draft_handle()]
    fig.legend(handles=handles, loc='lower center', ncol=5, frameon=False, fontsize=10,
               labelcolor=INK2, bbox_to_anchor=(.5, .008), handlelength=1.8, columnspacing=1.4)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'08_three_models_named_axes.{ext}', dpi=165, facecolor=SURF)
    print('wrote', OUT / '08_three_models_named_axes.png')


if __name__ == '__main__':
    main()
