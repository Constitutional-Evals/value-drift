#!/usr/bin/env python3
"""Everything rated this session, on named axes instead of principal components.

Two planes, because they do different jobs. The working plane spreads the corpus
out and is where the measured drift is largest. The frontier plane is where the
corpus collapses into one corner - which is the point: nothing published goes
there, and it is the only view in which an adversarial start separates.

Usage: python3 agents/scripts/plot_named_axes.py
"""
from __future__ import annotations
import json
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
from analyze_value_space12 import AX, noise_sd  # noqa: E402
from selfhost_v3 import AXIS_LABELS  # noqa: E402
from analyze_field import field_ratings, seed_positions, edits  # noqa: E402

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8982', '#e4e3df'
JUMP, SEED, FLOW, RED, PALE = '#eb6834', '#1baf7a', '#2a78d6', '#e34948', '#d9d8d2'
WORKING = ('caution', 'long_term_orientation')
FRONTIER = ('honesty_strictness', 'long_term_orientation')
LAB = {'openai_spec_derived': 'OpenAI spec', 'claude_derived': 'Claude const.',
       'animal_welfare': 'animal welfare', 'flourishing': 'flourishing',
       'eb_kindness': 'kindness', 'eb_conservatism': 'conservatism',
       'eb_deep_ecology': 'deep ecology', 'broad_draft': 'broad draft',
       'deferential': 'deferential', 'autonomous': 'autonomous',
       'protective': 'protective', 'libertarian': 'libertarian'}


def pooled():
    per = defaultdict(list)
    for d, pat, key in [('runs/elicit/positions12', '*.rep*.json', 'hash'),
                        ('runs/elicit/positions12_field', '*.rep*.json', 'hash'),
                        ('runs/elicit/positions12_welldef', '*.rep*.json', 'hash'),
                        ('runs/selfhost/positions_seeds', '*.rep*.json', 'seed'),
                        ('runs/selfhost/positions_decode', '*.rep*.json', 'seed')]:
        for f in sorted((ROOT / d).glob(pat)):
            j = json.loads(f.read_text())
            per[j.get(key) or f.stem].append([j['ratings'][a] for a in AX])
    return {k: np.array(v, float).mean(0) for k, v in per.items()}


def main():
    P = pooled()
    X = np.array(list(P.values()))
    probes = {'adversarial': (P.get('ADV_probe'), RED),
              'honest, immediate': (P.get('HONEST_IMMEDIATE'), '#4a3aa7'),
              'cautious, immediate': (P.get('CAUTIOUS_IMMEDIATE'), '#008300')}
    fr = field_ratings('positions12_field')
    sh = {}
    ed = edits('field-12seeds', fr, sh)
    seeds = seed_positions(fr, sh)
    names = sorted({s for _, s in ed})
    p0 = {s: seeds[s].mean(0) for s in names}
    p1 = {s: p0[s] + np.mean([x['vout'] - x['vin'] for x in v], 0) for (_, s), v in ed.items()}
    c1 = np.mean([p1[s] for s in names], 0)

    fig, axes = plt.subplots(1, 2, figsize=(14.6, 6.9), facecolor=SURF)
    fig.text(.012, .955, 'Everything measured this session, on named axes',
             fontsize=16, color=INK, weight='medium')
    fig.text(.012, .912, f'{len(X)} rated documents in grey. The twelve seeds with their mean '
             'edit vector, the attractor they point at, and two decoded probes.',
             fontsize=9.5, color=INK2)

    for k, (pair, title, note) in enumerate([
            (WORKING, 'Working plane', 'where the corpus spreads out, and where the '
             'measured drift is largest'),
            (FRONTIER, 'Frontier plane', 'the only plane that separates the two probes')]):
        i, j = AX.index(pair[0]), AX.index(pair[1])
        ax = axes[k]
        ax.set_facecolor(SURF)
        jit = np.random.default_rng(0).normal(0, .07, size=(len(X), 2))
        ax.scatter(X[:, i] + jit[:, 0], X[:, j] + jit[:, 1], s=9, facecolor=PALE,
                   edgecolor='none', zorder=1)
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
            if k == 0:
                label_pts.append((s, a))
        if k == 0:
            # push labels out from the attractor, then separate any that still collide
            spots = {}
            for n_, (s_, a) in enumerate(label_pts):
                d = a - np.array([c1[i], c1[j]])
                d = d / (np.linalg.norm(d) or 1)
                # a deterministic nudge so coincident seeds still have a direction to separate in
                ang = 2 * np.pi * n_ / len(label_pts)
                spots[s_] = a + d * 0.45 + 0.03 * np.array([np.cos(ang), np.sin(ang)])
            obstacles = [np.array([pv[i], pv[j]]) for pv, _ in probes.values()
                         if pv is not None]
            for _ in range(600):
                moved = False
                keys = list(spots)
                # keep seed labels off the probe markers as well as off each other
                for kk in keys:
                    for ob in obstacles:
                        diff = spots[kk] - ob
                        dist = float(np.linalg.norm(diff)) or 1e-6
                        if dist < 0.55:
                            spots[kk] = spots[kk] + (diff / dist) * (0.55 - dist)
                            moved = True
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
                spots[s_] = np.clip(spots[s_], 0.75, 7.25)   # keep every label in frame
                ax.annotate(LAB[s_], spots[s_], ha='center', va='center',
                            fontsize=7.4, color=INK2, zorder=7,
                            bbox=dict(boxstyle='round,pad=.12', fc=SURF, ec='none', alpha=.85))

        ax.plot(c1[i], c1[j], '*', ms=20, mfc=SEED, mec=SURF, mew=1.2, zorder=8)
        for n_, (pn, (pv, pc)) in enumerate(probes.items()):
            if pv is None:
                continue
            ax.plot(pv[i], pv[j], 'D', ms=11, mfc=pc, mec=SURF, mew=1.3, zorder=9)
            dx = 15 if pv[i] < 4 else -15
            dy = (16, -20, 16)[n_ % 3]       # stagger so probes close together stay readable
            ax.annotate(pn, (pv[i], pv[j]), textcoords='offset points',
                        xytext=(dx, dy), ha='left' if dx > 0 else 'right',
                        fontsize=8.6, color=pc, weight='medium', zorder=10,
                        bbox=dict(boxstyle='round,pad=.15', fc=SURF, ec='none', alpha=.9))
        ax.set_xlim(.5, 7.5); ax.set_ylim(.5, 7.5)
        ax.set_xticks(range(1, 8)); ax.set_yticks(range(1, 8))
        ax.set_xlabel(pair[0].replace('_', ' '), fontsize=9.5, color=INK2, labelpad=14)
        ax.set_ylabel(pair[1].replace('_', ' '), fontsize=9.5, color=INK2, labelpad=16)
        # what a 1 and a 7 mean on each axis, in the rater's own words
        xlo, xhi = AXIS_LABELS[pair[0]]
        ylo, yhi = AXIS_LABELS[pair[1]]
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
        ax.set_title(f'{title}: {pair[0].replace("_"," ")} x {pair[1].replace("_"," ")}\n{note}',
                     fontsize=10.5, color=INK, pad=9)
        ax.grid(True, color=GRID, lw=.6); ax.set_axisbelow(True)
        ax.tick_params(colors=INK2, labelsize=8, length=0)
        for sp in ax.spines.values():
            sp.set_color(GRID)
        ax.set_aspect('equal')

    handles = [Line2D([], [], marker='o', color='none', markerfacecolor=PALE, markersize=5,
                      label=f'all {len(X)} rated documents'),
               Line2D([], [], marker='o', color='none', markerfacecolor='none',
                      markeredgecolor=MUTED, markersize=8, markeredgewidth=1.5, label='seed'),
               Line2D([], [], color=JUMP, lw=2, label='mean of six edits'),
               Line2D([], [], marker='o', color='none', markerfacecolor=FLOW,
                      markeredgecolor=SURF, markersize=7, label='after one edit'),
               Line2D([], [], marker='*', color='none', markerfacecolor=SEED,
                      markeredgecolor=SURF, markersize=15, label='attractor'),
               Line2D([], [], marker='D', color='none', markerfacecolor=RED,
                      markeredgecolor=SURF, markersize=9, label='adversarial probe'),
               Line2D([], [], marker='D', color='none', markerfacecolor='#4a3aa7',
                      markeredgecolor=SURF, markersize=9, label='honest, immediate probe'),
               Line2D([], [], marker='D', color='none', markerfacecolor='#008300',
                      markeredgecolor=SURF, markersize=9, label='cautious, immediate probe')]
    fig.legend(handles=handles, loc='lower center', ncol=8, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.5, .008), handlelength=1.8, columnspacing=1.7)
    fig.subplots_adjust(left=.075, right=.985, top=.80, bottom=.135, wspace=.22)
    OUT.mkdir(parents=True, exist_ok=True)
    for e in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'05_named_axes.{e}', dpi=165, facecolor=SURF)
    print('wrote', OUT / '05_named_axes.png')


if __name__ == '__main__':
    main()
