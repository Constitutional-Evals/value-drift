"""Figures for stages 07 and 08 (self-hosted Qwen3.8 27B and Qwen3.5 9B, prompt v3). Reads saved results only.

Called by `python3 agents/scripts/selfhost_v3.py plot [names...]`.
"""
import json

import numpy as np

import selfhost_v3 as V
from elicit import style as S
from elicit.plots import OUTCOMES, SEED_COLORS, stacked_rows
from elicit.style import plt

ROUNDS = 10
COLORS = {**SEED_COLORS, **dict(zip(V.SEEDS['new'], S.CAT[:7]))}
AXES = list(V.RATE_AXES)
AXIS_TITLES = {'oversight_deference': 'Deference to oversight', 'user_autonomy': 'User autonomy',
               'caution': 'Caution', 'honesty_strictness': 'Honesty strictness',
               'third_party_concern': 'Concern for third parties', 'ai_agency': 'AI agency',
               'specificity': 'Specificity', 'moral_circle': 'Moral circle', 'traditionalism': 'Traditionalism',
               'viewpoint_neutrality': 'Viewpoint neutrality', 'warmth': 'Warmth',
               'long_term_orientation': 'Long-term orientation'}


def save(fig, name):
    V.FIGDIR.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(V.FIGDIR / f'{name}.{ext}', dpi=220 if ext == 'png' else None, bbox_inches='tight',
                    pad_inches=0.15)
    plt.close(fig)
    return V.FIGDIR / f'{name}.png'


def outcome_legend(ax, data):
    items = OUTCOMES if any(c[4] for c in data) else OUTCOMES[:4]
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, c in items], [n for n, _ in items],
              loc='upper center', bbox_to_anchor=(0.5, -0.06), ncol=len(items), handlelength=1.0,
              handleheight=1.0, columnspacing=1.4, fontsize=9, borderaxespad=0)


def fig_outcomes():
    """Figure 1: outcome of each v3 review, per arm."""
    rs = [r for r in V.replication_rows() if r['condition'] == 'v3']
    labels, data = [], []
    for arm, label in V.ARMS.items():
        g = [r for r in rs if r['arm'] == arm]
        data.append(V.outcome_counts(g))
        labels.append(f'{label} (n = {len(g)})')
    fig, ax = plt.subplots(figsize=(9.5, 0.62 * len(labels) + 1.4))
    stacked_rows(ax, data, labels)
    ax.set_title(f'{V.MODEL_TITLE}, prompt v3, broad draft: outcome of each review\n'
                 f'({V.SETTINGS}; edits judged by {V.JUDGE_NAME})', fontsize=11)
    S.grid(ax, 'x')
    outcome_legend(ax, data)
    return save(fig, '01_outcomes_v3')


def fig_outcomes_v2_v3():
    """Figure 2: prompt v2 (stage 06) vs v3, per arm."""
    rs = V.replication_rows()
    labels, data = [], []
    for arm, label in V.ARMS.items():
        for cond, (name, _) in V.REPLICATION.items():
            g = [r for r in rs if r['arm'] == arm and r['condition'] == cond]
            data.append(V.outcome_counts(g))
            labels.append(f'{label}\n{name} (n = {len(g)})')
    fig, ax = plt.subplots(figsize=(9.5, 0.62 * len(labels) + 1.4))
    stacked_rows(ax, data, labels)
    for y in range(1, len(V.ARMS)):
        ax.axhline(2 * y - 0.5, color=S.GRID, linewidth=0.8, zorder=1)
    ax.tick_params(axis='y', labelsize=8.8)
    ax.set_title(f'{V.MODEL_TITLE}, broad draft: prompt v2 vs v3 (edits judged by {V.JUDGE_NAME})', fontsize=11)
    S.grid(ax, 'x')
    outcome_legend(ax, data)
    return save(fig, '02_outcomes_v2_v3')


# ---------------------------------------------------------------------------
def chains(parts=('original', 'new')):
    return [dict(row, part=p) for p in parts for row in V.chain_positions(p)]


def endpoint(row, g=None):
    return row['positions'].get(ROUNDS if g is None else g)


def note_short_chains(fig, parts=('original', 'new'), consequence='Later rounds of that seed use its other chain.'):
    """Footnote, below everything else, naming chains that a failed review ended before the last round."""
    short = [r for r in chains(parts) if max(r['status']) < ROUNDS or r['status'][max(r['status'])] == 'FAILURE']
    if short:
        names = '; '.join(f"{V.SEED_LABELS[r['seed']]}, chain {r['rep']}, after round "
                          f"{max(g for g, st in r['status'].items() if st != 'FAILURE')}" for r in short)
        fig.canvas.draw()
        box = fig.get_tightbbox(fig.canvas.get_renderer())
        fig.text(box.x0 / fig.get_figwidth(), box.y0 / fig.get_figheight() - 0.02,
                 f'Ended early by a failed review: {names}. {consequence}',
                 fontsize=8, color=S.INK2, ha='left', va='top')


def fig_value_map(part, xa='caution', ya='oversight_deference', name=None):
    """Each seed and one arrow per chain to its round-10 document, on two axes."""
    rows = chains([part])
    seeds = V.SEEDS[part]
    fig, ax = plt.subplots(figsize=(3.9, 3.9))
    rng = np.random.default_rng(3)
    dropped, stayed_any, shared_any = 0, False, False
    starts = {}
    for seed in seeds:
        start = next((r['positions'][0] for r in rows if r['seed'] == seed and r['positions'].get(0)), None)
        if start:
            starts[seed] = (start[xa], start[ya])
    for seed in seeds:
        rs = [r for r in rows if r['seed'] == seed]
        ends = [endpoint(r) for r in rs if endpoint(r)]
        dropped += len(rs) - len(ends)
        if seed not in starts or not ends:
            continue
        c = COLORS[seed]
        x0, y0 = starts[seed]
        # Initial constitutions rated at the same point are drawn slightly apart, so each circle shows.
        same = [t for t in seeds if starts.get(t) == (x0, y0)]
        if len(same) > 1:
            shared_any = True
            x0 += 0.24 * (same.index(seed) - (len(same) - 1) / 2)
        # A chain that ends where it started has no arrow; its seed's circle is filled instead.
        moved = [e for e in ends if (e[xa], e[ya]) != starts[seed]]
        stayed = len(moved) < len(ends)
        stayed_any |= stayed
        # Ratings are integers, so two chains can end on the same point: a small jitter keeps both arrows visible.
        j = rng.uniform(-0.15, 0.15, (len(moved), 2))
        for e, (jx, jy) in zip(moved, j):
            # Above the circles: several chains end where another constitution starts.
            ax.annotate('', xy=(e[xa] + jx, e[ya] + jy), xytext=(x0, y0), zorder=6,
                        arrowprops=dict(arrowstyle='-|>', color=c, lw=1.3, shrinkA=4, shrinkB=0, mutation_scale=9))
        ax.scatter(x0, y0, s=40, facecolor=c if stayed else S.SURFACE, edgecolor=c, lw=1.7, zorder=5)
    ax.set_xlim(0.4, 7.6)
    ax.set_ylim(0.4, 7.6)
    ax.set_aspect('equal')
    lo, hi = V.AXIS_LABELS[ya]
    ax.set_yticks([1, 4, 7], [f'{lo}  1', '4', f'{hi}  7'])
    ax.set_ylabel(AXIS_TITLES[ya], labelpad=8)
    lo, hi = V.AXIS_LABELS[xa]
    ax.set_xticks([1, 4, 7], [f'1\n{lo}', '4', f'7\n{hi}'])
    ax.set_xlabel(AXIS_TITLES[xa], labelpad=6)
    S.grid(ax, 'both')
    ax.set_title(f'{V.MODEL_TITLE}, prompt v3,\nreflect on own values first', loc='left', fontsize=10.5,
                 fontweight='semibold')
    h = [plt.Line2D([], [], color=COLORS[s], lw=2) for s in seeds]
    h += [plt.Line2D([], [], marker='o', ls='', markerfacecolor=S.SURFACE, markeredgecolor=S.INK2, markersize=6),
          plt.Line2D([], [], color=S.INK2, lw=1.3, marker='>', markersize=5, markevery=[1])]
    labels = [V.SEED_LABELS[s] for s in seeds] + ['Initial constitution', f'One chain, to round {ROUNDS}']
    if stayed_any:
        h.append(plt.Line2D([], [], marker='o', ls='', color=S.INK2, markersize=6))
        labels.append(f'Filled: a chain ended there')
    if shared_any:
        h.append(plt.Line2D([], [], ls=''))
        labels.append('Circles at the same rating\nare drawn slightly apart')
    leg = ax.legend(h, labels, loc='center left', bbox_to_anchor=(1.04, 0.5), fontsize=9, handlelength=1.6,
                    labelspacing=0.55)
    leg.get_title().set_color(S.INK)
    if dropped:
        print(f'value map {part}: {dropped} chains without a rated round {ROUNDS} left out')
    note_short_chains(fig, (part,), 'It has no arrow.')
    return save(fig, name or f'value_map_{part}_{xa}_{ya}')


def fig_profiles():
    """Per axis: each seed's rating, its chains' round-10 ratings, and their mean."""
    rows = chains()
    seeds = V.SEEDS['original'] + V.SEEDS['new']
    c = S.CAT[1]
    rng = np.random.default_rng(5)
    fig, axes = plt.subplots(3, 4, figsize=(10.5, 10.2), sharex=True, sharey=True,
                             gridspec_kw={'hspace': 0.28, 'wspace': 0.08})
    for ax, axis in zip(axes.flat, AXES):
        for i, seed in enumerate(seeds):
            rs = [r for r in rows if r['seed'] == seed]
            start = next((r['positions'][0] for r in rs if r['positions'].get(0)), None)
            if start is None:
                continue
            x0 = start[axis]
            ends = [endpoint(r)[axis] for r in rs if endpoint(r)]
            if ends:
                m = float(np.mean(ends))
                ax.scatter(np.array(ends) + rng.uniform(-0.12, 0.12, len(ends)), i + rng.uniform(-0.2, 0.2, len(ends)),
                           s=7, color=c, alpha=0.4, linewidths=0, zorder=2)
                ax.plot([x0, m], [i, i], color=c, lw=1.3, alpha=0.6, zorder=2)
                ax.scatter(m, i, s=28, color=c, edgecolor=S.SURFACE, lw=0.8, zorder=4)
            ax.scatter(x0, i, s=30, facecolor=S.SURFACE, edgecolor=S.INK2, lw=1.4, zorder=3)
        ax.axhline(len(V.SEEDS['original']) - 0.5, color=S.GRID, lw=0.8, zorder=1)
        lo, hi = V.AXIS_LABELS[axis]
        ax.set_title(AXIS_TITLES[axis], fontsize=10)
        ax.set_xlim(0.5, 7.5)
        ax.set_xticks([1, 4, 7])
        ax.text(0.0, -0.035, lo, transform=ax.transAxes, ha='left', va='top', fontsize=7.8, color=S.MUTED)
        ax.text(1.0, -0.035, hi, transform=ax.transAxes, ha='right', va='top', fontsize=7.8, color=S.MUTED)
        ax.tick_params(axis='x', pad=12)
        S.grid(ax, 'x')
        ax.spines['left'].set_visible(False)
    axes[0, 0].set_yticks(range(len(seeds)), [V.SEED_LABELS[s] for s in seeds])
    axes[0, 0].set_ylim(len(seeds) - 0.5, -0.6)
    h = [plt.Line2D([], [], marker='o', ls='', markerfacecolor=S.SURFACE, markeredgecolor=S.INK2, markersize=6),
         plt.Line2D([], [], marker='o', ls='', color=c, alpha=0.4, markersize=3.5, markeredgewidth=0),
         plt.Line2D([], [], marker='o', color=c, lw=1.3, markersize=5, markeredgecolor=S.SURFACE)]
    fig.legend(h, ['Initial constitution', f'One chain at round {ROUNDS}', f'Mean of its {V.REPS} chains'],
               loc='upper center', bbox_to_anchor=(0.5, 0.06), ncol=3, fontsize=9.5)
    fig.suptitle(f'Where each initial constitution ends after {ROUNDS} rounds, on each rated axis (1-7)',
                 x=axes[0, 0].get_position().x0, ha='left', fontsize=11.5, fontweight='semibold', y=0.935)
    note_short_chains(fig, ('original', 'new'))
    return save(fig, '05_profiles')


def distances(rows, g):
    """RMS per-axis rating difference between chains at round g, split by pair type."""
    docs = [(r['part'], r['seed'], np.array([r['positions'][g][a] for a in AXES], float))
            for r in rows if r['positions'].get(g)]
    out = {'within': [], 'between_original': [], 'between_new': [], 'between_all': []}
    for i in range(len(docs)):
        for k in range(i + 1, len(docs)):
            (pi, si, xi), (pk, sk, xk) = docs[i], docs[k]
            d = float(np.sqrt(np.mean((xi - xk) ** 2)))
            if si == sk:
                out['within'].append(d)
            else:
                out['between_all'].append(d)
                if pi == pk:
                    out[f'between_{pi}'].append(d)
    return {k: (np.mean(v) if v else np.nan) for k, v in out.items()}


def rater_noise():
    pairs = V.repeat_agreement()
    if not pairs:
        return None
    return float(np.mean([np.sqrt(np.mean([(x[a] - y[a]) ** 2 for a in AXES])) for x, y in pairs]))


def fig_convergence():
    rows = chains()
    noise = rater_noise()
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    lines = [('between_original', 'Between chains from different initial constitutions (elicitation seeds)', S.CAT[6]),
             ('between_new', 'Between chains from different initial constitutions (new seeds)', S.CAT[3]),
             ('within', 'Between chains from the same initial constitution', S.BLUE_RAMP[2])]
    t = {g: distances(rows, g) for g in range(ROUNDS + 1)}
    for key, _, c in lines:
        gs = [g for g in t if not np.isnan(t[g][key])]
        ax.plot(gs, [t[g][key] for g in gs], color=c, lw=2, marker='o', markersize=3.5, markeredgecolor=S.SURFACE)
    if noise is not None:
        ax.axhline(noise, color=S.MUTED, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.set_xticks(range(0, ROUNDS + 1, 2))
    ax.set_xlabel('Round')
    ax.set_ylim(bottom=0)
    ax.set_ylabel('RMS rating difference\n(points per axis, 12 axes)')
    S.grid(ax, 'y')
    h = [plt.Line2D([], [], color=c, lw=2) for _, _, c in lines]
    labels = [n for _, n, _ in lines]
    if noise is not None:
        h.append(plt.Line2D([], [], color=S.MUTED, lw=1.2, ls=(0, (4, 3))))
        labels.append('Same document rated twice (rater noise)')
    ax.legend(h, labels, loc='upper left', bbox_to_anchor=(0, -0.2), ncol=1, fontsize=9.2)
    ax.set_title('Do chains from different initial constitutions converge?', loc='left', fontsize=11,
                 fontweight='semibold')
    return save(fig, '06_convergence')


def fig_axis_spread():
    """Per axis and round: spread across seeds (SD of per-seed means) vs within a seed (mean SD of its chains)."""
    rows = chains()
    between_c, within_c = S.CAT[6], S.BLUE_RAMP[2]
    fig, axes = plt.subplots(3, 4, figsize=(10.0, 6.6), sharex=True, sharey=True,
                             gridspec_kw={'hspace': 0.42, 'wspace': 0.1})
    top = 0
    for ax, axis in zip(axes.flat, AXES):
        between, within = [], []
        for g in range(ROUNDS + 1):
            by_seed = {}
            for r in rows:
                if r['positions'].get(g):
                    by_seed.setdefault(r['seed'], []).append(r['positions'][g][axis])
            means = [np.mean(v) for v in by_seed.values()]
            between.append(np.std(means) if len(means) > 2 else np.nan)
            sds = [np.std(v) for v in by_seed.values() if len(v) > 1]
            within.append(np.mean(sds) if sds and g > 0 else np.nan)
        for ys, c in ((between, between_c), (within, within_c)):
            ax.plot(range(ROUNDS + 1), ys, color=c, lw=1.8, marker='o', markersize=2.8, markeredgecolor=S.SURFACE)
        top = max(top, np.nanmax(between + within))
        ax.set_title(AXIS_TITLES[axis], fontsize=9.8)
        ax.set_xticks(range(0, ROUNDS + 1, 5))
        S.grid(ax, 'y')
    # Set the shared limit once: setting it per panel stops autoscaling and clips later panels.
    axes[0, 0].set_ylim(0, top * 1.06)
    for ax in axes[-1]:
        ax.set_xlabel('Round')
    for ax in axes[:, 0]:
        ax.set_ylabel('SD (rating points)')
    h = [plt.Line2D([], [], color=c, lw=2) for c in (between_c, within_c)]
    fig.legend(h, ['Across initial constitutions (SD of the 12 per-seed means)',
                   f'Within an initial constitution (SD across its {V.REPS} chains, averaged over seeds)'],
               loc='upper center', bbox_to_anchor=(0.5, 0.03), ncol=1, fontsize=9.5)
    fig.suptitle('Spread of ratings by axis and round', x=axes[0, 0].get_position().x0, ha='left',
                 fontsize=11, fontweight='semibold', y=0.97)
    return save(fig, '07_axis_spread')


def fig_trajectories(part):
    """Per axis: mean rating of each seed's chains by round."""
    rows = chains([part])
    seeds = V.SEEDS[part]
    fig, axes = plt.subplots(3, 4, figsize=(10.0, 6.8), sharex=True, sharey=True,
                             gridspec_kw={'hspace': 0.42, 'wspace': 0.1})
    for ax, axis in zip(axes.flat, AXES):
        for seed in seeds:
            ys = []
            for g in range(ROUNDS + 1):
                v = [r['positions'][g][axis] for r in rows if r['seed'] == seed and r['positions'].get(g)]
                ys.append(np.mean(v) if v else np.nan)
            ax.plot(range(ROUNDS + 1), ys, color=COLORS[seed], lw=1.5, alpha=0.9)
        ax.set_title(AXIS_TITLES[axis], fontsize=9.8)
        ax.set_xticks(range(0, ROUNDS + 1, 5))
        ax.set_ylim(0.7, 7.3)
        ax.set_yticks([1, 4, 7])
        S.grid(ax, 'y')
    for ax in axes[-1]:
        ax.set_xlabel('Round')
    h = [plt.Line2D([], [], color=COLORS[s], lw=2) for s in seeds]
    fig.legend(h, [V.SEED_LABELS[s] for s in seeds], loc='upper center', bbox_to_anchor=(0.5, 0.03),
               ncol=min(len(h), 4), fontsize=9.3)
    which = 'elicitation seeds' if part == 'original' else 'new seeds'
    fig.suptitle(f'Mean rating by round, {which} (mean of {V.REPS} chains per seed)',
                 x=axes[0, 0].get_position().x0, ha='left', fontsize=11, fontweight='semibold', y=0.97)
    note_short_chains(fig, (part,))
    return save(fig, f'08_trajectories_{part}')


def fig_words():
    rows = chains()
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    for r in rows:
        w = [x for x in r['words'] if x]
        ax.plot(range(len(w)), w, color=S.LIGHT_GRAY, lw=0.9, zorder=1)
    med = [np.median([r['words'][g] for r in rows if len(r['words']) > g and r['words'][g]])
           for g in range(ROUNDS + 1)]
    ax.plot(range(ROUNDS + 1), med, color=S.CAT[1], lw=2.2, zorder=3)
    ax.set_xticks(range(0, ROUNDS + 1, 2))
    ax.set_xlabel('Round')
    ax.set_ylabel('Words')
    ax.set_ylim(bottom=0)
    S.grid(ax, 'y')
    h = [plt.Line2D([], [], color=S.LIGHT_GRAY, lw=1), plt.Line2D([], [], color=S.CAT[1], lw=2.2)]
    ax.legend(h, [f'One chain ({len(rows)} chains, 12 initial constitutions)', 'Median'], loc='upper left',
              bbox_to_anchor=(0, -0.2), ncol=1, fontsize=9.3)
    ax.set_title('Constitution length by round', loc='left', fontsize=11, fontweight='semibold')
    return save(fig, '09_words')


def fig_axis_change():
    """Per axis: change from each initial constitution to its round-10 mean, and the mean over seeds."""
    rows = chains()
    seeds = V.SEEDS['original'] + V.SEEDS['new']
    stats = []
    for axis in AXES:
        d = {}
        for s in seeds:
            rs = [r for r in rows if r['seed'] == s]
            start = next((r['positions'][0] for r in rs if r['positions'].get(0)), None)
            ends = [endpoint(r)[axis] for r in rs if endpoint(r)]
            if start and ends:
                d[s] = np.mean(ends) - start[axis]
        v = np.array(list(d.values()))
        half = 2.2 * v.std(ddof=1) / np.sqrt(len(v))  # about a 95% t-interval for 12 seeds
        stats.append((axis, v.mean(), half, d))
    stats.sort(key=lambda t: t[1])
    orig_c, new_c = S.CAT[0], S.CAT[1]
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    for i, (axis, mean, half, d) in enumerate(stats):
        for s, val in d.items():
            orig = s in V.SEEDS['original']
            ax.scatter(val, i + (0.13 if orig else -0.13), s=16, color=orig_c if orig else new_c, alpha=0.6, lw=0,
                       zorder=2)
        ax.plot([mean - half, mean + half], [i, i], color=S.INK, lw=1.6, zorder=3, solid_capstyle='round')
        ax.scatter(mean, i, s=46, color=S.INK, zorder=4, edgecolor=S.SURFACE, lw=1)
    ax.axvline(0, color=S.INK2, lw=1, zorder=1)
    ax.set_yticks(range(len(stats)), [AXIS_TITLES[a] for a, *_ in stats])
    ax.set_xlabel('Change in rating from the initial constitution to round 10 (mean of 2 chains)')
    lim = max(abs(v) for *_, d in stats for v in d.values()) + 0.3
    ax.set_xlim(-lim, lim)
    S.grid(ax, 'x')
    ax.tick_params(axis='y', length=0)
    h = [plt.Line2D([], [], marker='o', ls='', color=orig_c, alpha=0.7, markersize=5),
         plt.Line2D([], [], marker='o', ls='', color=new_c, alpha=0.7, markersize=5),
         plt.Line2D([], [], marker='o', ls='-', color=S.INK, markersize=6)]
    ax.legend(h, ['One elicitation seed', 'One new seed', 'Mean over the 12 seeds, 95% interval'],
              loc='upper left', bbox_to_anchor=(0, -0.13), ncol=3, fontsize=8.8, columnspacing=1.2)
    ax.set_title('Change on each axis over 10 rounds, 12 initial constitutions', loc='left', fontsize=11,
                 fontweight='semibold')
    note_short_chains(fig, ('original', 'new'))
    return save(fig, '10_axis_change')


def fig_rater_agreement():
    """Per axis: GPT vs Claude ratings of the same items (the items Claude rated before it stopped)."""
    from scipy import stats
    first = V.RATING / 'claude_partial' / 'out'
    items = sorted(p.stem for p in first.glob('*.json') if (V.RATING / 'out' / p.name).exists())
    claude = {i: json.loads((first / f'{i}.json').read_text())['ratings'] for i in items}
    gpt = {i: json.loads((V.RATING / 'out' / f'{i}.json').read_text())['ratings'] for i in items}
    fig, axes = plt.subplots(3, 4, figsize=(10.0, 8.2), sharex=True, sharey=True,
                             gridspec_kw={'hspace': 0.36, 'wspace': 0.12})
    for ax, axis in zip(axes.flat, AXES):
        c = np.array([claude[i][axis] for i in items]); g = np.array([gpt[i][axis] for i in items])
        cells = {}
        for x, y in zip(c, g):
            cells[x, y] = cells.get((x, y), 0) + 1
        xs, ys, ns = zip(*[(x, y, n) for (x, y), n in cells.items()])
        ax.plot([1, 7], [1, 7], color=S.GRID, lw=1.2, zorder=1)
        ax.scatter(xs, ys, s=[9 * n for n in ns], color=S.CAT[0], alpha=0.75, lw=0.6, edgecolor=S.SURFACE, zorder=2)
        r = stats.pearsonr(c, g)[0] if c.std() and g.std() else float('nan')
        ax.set_title(AXIS_TITLES[axis], fontsize=9.8)
        # Lower right is nearly empty: GPT seldom rates below Claude.
        ax.text(0.97, 0.04, f'r = {r:.2f}\nGPT {np.mean(g - c):+.1f} on average', transform=ax.transAxes,
                ha='right', va='bottom', fontsize=8.4, color=S.INK2)
        ax.set_xlim(0.4, 7.6)
        ax.set_ylim(0.4, 7.6)
        ax.set_xticks([1, 4, 7])
        ax.set_yticks([1, 4, 7])
        S.grid(ax, 'both')
    for ax in axes[-1]:
        ax.set_xlabel('Claude rating')
    for ax in axes[:, 0]:
        ax.set_ylabel('GPT rating')
    fig.suptitle(f'Rater agreement: the {len(items)} items rated by both Claude and GPT '
                 '(bubble area = number of items; grey line = equal ratings)',
                 x=axes[0, 0].get_position().x0, ha='left', fontsize=11, fontweight='semibold', y=0.965)
    return save(fig, '11_rater_agreement')


FIGS = {
    'outcomes': fig_outcomes, 'outcomes_v2_v3': fig_outcomes_v2_v3,
    'value_map_original': lambda: fig_value_map('original', name='03_value_map_original'),
    'value_map_new': lambda: fig_value_map('new', name='04_value_map_new'),
    'profiles': fig_profiles, 'convergence': fig_convergence, 'axis_spread': fig_axis_spread,
    'trajectories_original': lambda: fig_trajectories('original'),
    'trajectories_new': lambda: fig_trajectories('new'), 'words': fig_words,
    'axis_change': fig_axis_change, 'rater_agreement': fig_rater_agreement,
}


def main(names):
    for n in names or FIGS:
        if n == 'rater_agreement' and not (V.RATING / 'claude_partial').exists():
            continue  # only the 27B has ratings from both raters
        if n == 'outcomes_v2_v3' and not any(r['condition'] == 'v2' for r in V.replication_rows()):
            continue  # the 9B ran only the v3 prompts
        print(FIGS[n]())
