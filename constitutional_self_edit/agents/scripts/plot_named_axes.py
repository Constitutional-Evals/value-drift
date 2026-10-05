#!/usr/bin/env python3
"""Qwen's one-step field on the working plane.

Seventeen starts, each with its mean edit, and the fixed point those edits
contract toward. Caution by long-term orientation is the plane where the
measured drift is largest.

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
from elicit.run import RUNS  # noqa: E402
from selfhost_v3 import AXIS_LABELS  # noqa: E402
from analyze_field import field_ratings, seed_positions, edits  # noqa: E402

OUT = ROOT / 'reports' / '10_value_space' / 'figures'
SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8982', '#e4e3df'
JUMP, SEED, FLOW, RED, PALE = '#eb6834', '#1baf7a', '#2a78d6', '#e34948', '#d9d8d2'
WORKING = ('caution', 'long_term_orientation')
LAB = {'attractor_start': 'decoded (on attractor)', 'mid_immediate': 'decoded (caution 5)', 'cautious_immediate': 'decoded (caution 7)',
       'C1_LT6': 'decoded (1, 6)', 'C7_LT3': 'decoded (7, 3)',
       'openai_spec_derived': 'OpenAI spec', 'claude_derived': 'Claude const.',
       'animal_welfare': 'animal welfare', 'flourishing': 'flourishing',
       'eb_kindness': 'kindness', 'eb_conservatism': 'conservatism',
       'eb_deep_ecology': 'deep ecology', 'broad_draft': 'broad draft',
       'deferential': 'deferential', 'autonomous': 'autonomous',
       'protective': 'protective', 'libertarian': 'libertarian'}



def probe_points():
    """The two decoded starts and their mean first-generation edit, like any other seed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from analyze_probe_chains import trajectories
    traj = trajectories('probe-chains', 'positions12_probe')
    starts, moves = {}, defaultdict(list)
    for (seed, _), gens in traj.items():
        if 0 in gens and 1 in gens:
            starts[seed] = gens[0]
            moves[seed].append(gens[1] - gens[0])
    return ({k: v for k, v in starts.items()},
            {k: starts[k] + np.mean(v, 0) for k, v in moves.items()},
            {k: len(v) for k, v in moves.items()})


def attractor_point():
    """The constitution decoded onto the fitted attractor, and its mean edit."""
    from analyze_value_space12 import doc_hash
    rat = defaultdict(list)
    for f in sorted((RUNS / 'positions12_attr').glob('*.rep*.json')):
        d = json.loads(f.read_text())
        rat[d['hash']].append([d['ratings'][a] for a in AX])
    rat = {k: np.array(v, float).mean(0) for k, v in rat.items()}
    start, moves = None, []
    root = RUNS / 'attractor-test'
    if not root.exists():
        return {}, {}, {}
    for cell in sorted(q for q in root.iterdir() if q.is_dir()):
        g = cell / 'gen_01'
        if not (g / 'result.json').exists():
            continue
        hi = doc_hash((g / 'input.md').read_text())
        ho = doc_hash((g / 'output.md').read_text())
        if hi in rat and ho in rat:
            start = rat[hi]
            moves.append(rat[ho] - rat[hi])
    if start is None or not moves:
        return {}, {}, {}
    return ({'attractor_start': start},
            {'attractor_start': start + np.mean(moves, 0)},
            {'attractor_start': len(moves)})


def plane_points():
    """Decoded fills of the empty holes on the caution x long-term plane.

    Each start carries its three decode ratings plus the one taken with the
    field batch. Each output is a distinct document, rated once.
    """
    from analyze_value_space12 import doc_hash
    rat = defaultdict(list)
    for f in sorted((RUNS / 'positions12_plane').glob('*.rep*.json')):
        d = json.loads(f.read_text())
        rat[d['hash']].append([d['ratings'][a] for a in AX])
    root = RUNS / 'field-plane'
    if not rat or not root.exists():
        return {}, {}, {}
    for seed in ('C1_LT6', 'C7_LT3'):
        h = doc_hash((ROOT / 'constitutions' / 'decode' / f'{seed}.md').read_text())
        for f in sorted((ROOT / 'runs' / 'selfhost' / 'positions_decode').glob(f'{seed}.rep*.json')):
            d = json.loads(f.read_text())
            rat[h].append([d['ratings'][a] for a in AX])
    rat = {k: np.array(v, float).mean(0) for k, v in rat.items()}
    moves = defaultdict(list)
    starts = {}
    for cell in sorted(q for q in root.iterdir() if q.is_dir()):
        seed = cell.name.split('__')[2]
        g = cell / 'gen_01'
        if not (g / 'result.json').exists():
            continue
        hi = doc_hash((g / 'input.md').read_text())
        ho = doc_hash((g / 'output.md').read_text())
        if hi in rat and ho in rat:
            starts[seed] = rat[hi]
            moves[seed].append(rat[ho] - rat[hi])
    starts = {k: v for k, v in starts.items() if moves.get(k)}
    return (starts,
            {k: starts[k] + np.mean(v, 0) for k, v in moves.items() if k in starts},
            {k: len(v) for k, v in moves.items() if k in starts})


def main():
    probes = {}
    fr = field_ratings('positions12_field')
    sh = {}
    ed = edits('field-12seeds', fr, sh)
    seeds = seed_positions(fr, sh)
    names = sorted({s for _, s in ed})
    p0 = {s: seeds[s].mean(0) for s in names}
    p1 = {s: p0[s] + np.mean([x['vout'] - x['vin'] for x in v], 0) for (_, s), v in ed.items()}
    # the decoded starts are plotted on the same terms as the twelve seeds
    ps0, ps1, pn = probe_points()
    as0, as1, an = attractor_point()
    fs0, fs1, fn = plane_points()
    p0.update(ps0); p0.update(as0); p0.update(fs0)
    p1.update(ps1); p1.update(as1); p1.update(fs1)
    names = names + sorted(ps0) + sorted(as0) + sorted(fs0)
    # fixed point of dv = -k (v - v*), fit per axis over every start. A seed that
    # only closed part of the gap pulls v* further along its arrow than where it landed.
    from plot_contraction_rates import fit_per_axis
    V = np.array([p0[s] for s in names])
    D = np.array([p1[s] - p0[s] for s in names])
    ks, c1 = fit_per_axis(V, D)
    ci, cj = AX.index('caution'), AX.index('long_term_orientation')
    print(f'fixed point over {len(names)} starts: caution {c1[ci]:.2f} (k={ks[ci]:.2f}), '
          f'long-term {c1[cj]:.2f} (k={ks[cj]:.2f})')
    print('decoded starts added as seeds:',
          {**{k: f'{v} edits' for k, v in pn.items()},
           **{k: f'{v} edits' for k, v in an.items()},
           **{k: f'{v} edits' for k, v in fn.items()}})

    fig, ax = plt.subplots(figsize=(8.2, 8.35), facecolor=SURF)
    card = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
            'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
            'sixteen', 'seventeen', 'eighteen']
    n_decoded = len(ps0) + len(as0) + len(fs0)
    n_seeds = len(names) - n_decoded
    fig.text(.03, .972, "Qwen's edits, on the working plane",
             fontsize=16, color=INK, weight='medium')
    fig.text(.03, .938, f'{card[len(names)].capitalize()} starting points, their mean edit, '
             'and the fixed point they contract toward.',
             fontsize=9.2, color=INK2)
    fig.text(.03, .912, f'{card[n_seeds].capitalize()} are published or researcher-written seeds; '
             f'{card[n_decoded]} are decoded, including one placed on the attractor itself.',
             fontsize=9.2, color=INK2)

    pair = WORKING
    i, j = AX.index(pair[0]), AX.index(pair[1])
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
    # push labels out from the attractor, then separate any that still collide
    spots = {}
    for n_, (s_, a) in enumerate(label_pts):
        d = a - np.array([c1[i], c1[j]])
        d = d / (np.linalg.norm(d) or 1)
        ang = 2 * np.pi * n_ / len(label_pts)
        spots[s_] = a + d * 0.45 + 0.03 * np.array([np.cos(ang), np.sin(ang)])
    obstacles = [np.array([pv[i], pv[j]]) for pv, _ in probes.values() if pv is not None]
    for _ in range(600):
        moved = False
        keys = list(spots)
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
        spots[s_] = np.clip(spots[s_], 0.75, 7.25)
        ax.annotate(LAB[s_], spots[s_], ha='center', va='center',
                    fontsize=7.4, color=INK2, zorder=7,
                    bbox=dict(boxstyle='round,pad=.12', fc=SURF, ec='none', alpha=.85))

    ax.plot(c1[i], c1[j], '*', ms=20, mfc=SEED, mec=SURF, mew=1.2, zorder=8)
    for n_, (pn, (pv, pc)) in enumerate(probes.items()):
        if pv is None:
            continue
        ax.plot(pv[i], pv[j], 'D', ms=11, mfc=pc, mec=SURF, mew=1.3, zorder=9)
        dx = 15 if pv[i] < 4 else -15
        dy = (16, -20, 16)[n_ % 3]
        ax.annotate(pn, (pv[i], pv[j]), textcoords='offset points',
                    xytext=(dx, dy), ha='left' if dx > 0 else 'right',
                    fontsize=8.6, color=pc, weight='medium', zorder=10,
                    bbox=dict(boxstyle='round,pad=.15', fc=SURF, ec='none', alpha=.9))
    ax.set_xlim(.5, 7.5); ax.set_ylim(.5, 7.5)
    ax.set_xticks(range(1, 8)); ax.set_yticks(range(1, 8))
    ax.set_xlabel(pair[0].replace('_', ' '), fontsize=9.5, color=INK2, labelpad=14)
    ax.set_ylabel(pair[1].replace('_', ' '), fontsize=9.5, color=INK2, labelpad=16)
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
    ax.set_title('Working plane: caution x long term orientation\n'
                 'where the measured drift is largest',
                 fontsize=10.5, color=INK, pad=9)
    ax.grid(True, color=GRID, lw=.6); ax.set_axisbelow(True)
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
                      markeredgecolor=SURF, markersize=15, label='attractor')]
    fig.legend(handles=handles, loc='lower center', ncol=4, frameon=False, fontsize=9,
               labelcolor=INK2, bbox_to_anchor=(.52, .012), handlelength=1.8, columnspacing=1.4)
    fig.subplots_adjust(left=.13, right=.97, top=.86, bottom=.13)
    OUT.mkdir(parents=True, exist_ok=True)
    for e in ('png', 'pdf', 'svg'):
        fig.savefig(OUT / f'05_named_axes.{e}', dpi=165, facecolor=SURF)
    print('wrote', OUT / '05_named_axes.png')


if __name__ == '__main__':
    main()
