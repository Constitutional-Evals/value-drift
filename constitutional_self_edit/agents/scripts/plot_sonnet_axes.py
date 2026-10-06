#!/usr/bin/env python3
"""Sonnet's one-step field on the working plane.

Seventeen starts: the twelve seeds plus the five decoded constitutions. Each
arrow is Sonnet's mean edit, and the star is the fixed point of
dv = -k (v - v*) fit on all seventeen. The second panel is a Gaussian
RBF through those mean edits, as in figure 05.

Usage: python3 agents/scripts/plot_sonnet_axes.py
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
    draw_field_panel, style_plane, probe_points, attractor_point, plane_points,
    draft_positions, draw_drafts, draft_handle)

OUT = ROOT / 'reports' / '10_value_space' / 'figures'


def _arrows(p0, batch, rat_name, p1, n):
    rat = field_ratings(rat_name)
    if not rat:
        raise SystemExit(f'no ratings in {rat_name}')
    sh = {}
    for (_, s), v in edits(batch, rat, sh).items():
        if s not in p0 or not v:
            continue
        p1[s] = p0[s] + np.mean([x['vout'] - x['vin'] for x in v], 0)
        n[s] = len(v)
    return rat


def sonnet_field():
    """Start at the same positions as figure 05. The arrow is Sonnet's edit."""
    qwen = field_ratings('positions12_field')
    qh = {}
    qed = edits('field-12seeds', qwen, qh)
    seeds = seed_positions(qwen, qh)
    p0 = {s: seeds[s].mean(0) for (_, s) in qed}
    for extra in (probe_points()[0], attractor_point()[0], plane_points()[0]):
        p0.update(extra)

    p1, n = {}, {}
    _arrows(p0, 'field-sonnet', 'positions12_sonnet', p1, n)
    _arrows(p0, 'field-sonnet-decoded', 'positions12_sonnet_decoded', p1, n)
    names = [s for s in p0 if s in p1]
    return p0, p1, n, names


def main():
    p0, p1, n_edits, names = sonnet_field()
    V = np.array([p0[s] for s in names])
    D = np.array([p1[s] - p0[s] for s in names])
    ks, star = fit_per_axis(V, D)
    i, j = AX.index(WORKING[0]), AX.index(WORKING[1])
    print(f'{len(names)} seeds, {sum(n_edits.values())} edits')
    print('edits per seed:', {s: n_edits[s] for s in names})
    print(f'Sonnet fixed point: caution {star[i]:.2f} (k={ks[i]:.2f}), '
          f'long-term {star[j]:.2f} (k={ks[j]:.2f})')

    fig = plt.figure(figsize=(16.6, 8.7), facecolor=SURF)
    missed = 6 * len(names) - sum(n_edits.values())
    held = f' {missed} failed reviews are left out.' if missed else ''
    fig.text(.02, .972, "Sonnet's edits, on the working plane",
             fontsize=16, color=INK, weight='medium')
    fig.text(.02, .938, 'Seventeen starting points, their mean edit, and the fixed point they contract toward.',
             fontsize=9.2, color=INK2)
    fig.text(.02, .912, 'Same plane as the Qwen panel. Twelve published seeds and five decoded.'
             f'{held} The right panel interpolates those mean edits.',
             fontsize=9.2, color=INK2)
    gs = fig.add_gridspec(1, 2, left=.048, right=.93, top=.84, bottom=.145, wspace=.18)
    ax = fig.add_subplot(gs[0])
    axf = fig.add_subplot(gs[1])

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
    style_plane(ax, WORKING)
    ax.set_title('Measured mean edits\nwhere the corpus spreads out, and the drift is largest',
                 fontsize=10.5, color=INK, pad=9)
    draw_field_panel(fig, axf, p0, p1, names, i, j, star)
    drafts = draft_positions('sonnet5')
    for a_ in (ax, axf):
        draw_drafts(a_, drafts, i, j)
    print(f'{len(drafts)} blind drafts, mean caution {drafts[:, i].mean():.2f}, '
          f'long-term {drafts[:, j].mean():.2f}')

    handles = [Line2D([], [], marker='o', color='none', markerfacecolor='none',
                      markeredgecolor=MUTED, markersize=8, markeredgewidth=1.5, label='seed'),
               Line2D([], [], color=JUMP, lw=2, label='mean edit vector'),
               Line2D([], [], marker='o', color='none', markerfacecolor=FLOW,
                      markeredgecolor=SURF, markersize=7, label='after one edit'),
               Line2D([], [], marker='*', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=15, label='Sonnet attractor'),
               draft_handle(),
               Line2D([], [], color=FLOW, lw=1.6, label='interpolated field'),
               Line2D([], [], color=MUTED, lw=.9, ls=(0, (3.2, 2.2)), label='convex hull')]
    fig.legend(handles=handles, loc='lower center', ncol=7, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.5, .012), handlelength=1.8, columnspacing=1.3)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'06_sonnet_named_axes.{ext}', dpi=165, facecolor=SURF)
    print('wrote', OUT / '06_sonnet_named_axes.png')


if __name__ == '__main__':
    main()
