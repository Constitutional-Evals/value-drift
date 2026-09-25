#!/usr/bin/env python3
"""Figures for the elicitation screen. Reads saved results only (no API calls).

Usage: python3 -m elicit.plots [names...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elicit import style as S  # noqa: E402
from elicit.analyze import AXES, MODELS, load, wilson  # noqa: E402
from elicit.style import plt  # noqa: E402

ARM_LABELS = {
    'original_prompt': 'Original prompt',
    'original_prompt_new_tools': 'Original prompt, new edit tools',
    'no_reflection': 'New prompt, without reflection',
    'reflect': '+ reflect on own values first',
    'hard_cases': '+ stress-test with hard cases',
    'amendments': '+ propose and vote on amendments',
    'blind': '+ write own values blind, then compare',
}
# Outcome classes: unchanged, then edited by judge substantiveness 0-1 / 2 / 3, failed.
OUTCOMES = [('Kept unchanged', S.LIGHT_GRAY), ('Edited: wording or clarification', S.BLUE_RAMP[1]),
            ('Edited: substantive', S.BLUE_RAMP[3]), ('Edited: major', S.BLUE_RAMP[5]), ('Failed', '#f3c9c9')]
MODEL_COLORS = {'qwen38_27b': S.CAT[0], 'glm53_flash': S.CAT[1], 'gemma4_31b': S.CAT[2]}


def outcome_counts(g):
    unchanged = int((g.status == 'UNCHANGED').sum())
    failed = int(g.failed.sum())
    e = g[g.edited]
    return [unchanged, int((e.subst <= 1).sum()), int((e.subst == 2).sum()), int((e.subst == 3).sum()), failed]


def stacked_rows(ax, rows, labels, height=0.62):
    """Horizontal 100% stacked bars with 2px surface gaps between segments."""
    for i, counts in enumerate(rows):
        n = sum(counts)
        left = 0.0
        for (name, color), c in zip(OUTCOMES, counts):
            if c == 0:
                continue
            w = c / n
            ax.barh(i, w, left=left, height=height, color=color, edgecolor=S.SURFACE, linewidth=1.6, zorder=3)
            if w >= 0.09:
                ink = 'white' if color in (S.BLUE_RAMP[3], S.BLUE_RAMP[5]) else S.INK
                ax.text(left + w / 2, i, str(c), ha='center', va='center', fontsize=9, color=ink, zorder=4)
            left += w
    ax.set_yticks(range(len(labels)), labels)
    ax.set_ylim(len(labels) - 0.4, -0.6)
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ['0%', '25%', '50%', '75%', '100%'])
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)


def legend_outcomes(fig, y=0.0, include_failed=False):
    items = OUTCOMES if include_failed else OUTCOMES[:4]
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in items]
    fig.legend(handles, [n for n, _ in items], loc='lower center', ncol=len(items), bbox_to_anchor=(0.5, y),
               handlelength=1.0, handleheight=1.0, columnspacing=1.6, fontsize=9.5)


def fig_prompt_screen():
    df = load(['prompt-screen'])
    arms = list(ARM_LABELS)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 3.9), gridspec_kw={'width_ratios': [2.1, 1], 'wspace': 0.08})
    rows = [outcome_counts(df[df.arm == a]) for a in arms]
    stacked_rows(ax, rows, [ARM_LABELS[a] for a in arms])
    ax.set_title('Outcome of 18 reviews per prompt (3 open models, 6 each)', fontsize=11)
    S.grid(ax, 'x')
    # Right: substantive-edit rate per model.
    offsets = {'qwen38_27b': -0.18, 'glm53_flash': 0.0, 'gemma4_31b': 0.18}
    for m, off in offsets.items():
        for i, a in enumerate(arms):
            g = df[(df.arm == a) & (df.model == m)]
            p = g.substantive.mean()
            ax2.scatter(p, i + off, s=34, color=MODEL_COLORS[m], edgecolor=S.SURFACE, linewidth=1.2, zorder=4,
                        label=MODELS[m]['label'] if i == 0 else None)
    ax2.set_ylim(len(arms) - 0.4, -0.6)
    ax2.set_yticks(range(len(arms)), [''] * len(arms))
    ax2.set_xlim(-0.05, 1.05)
    ax2.set_xticks([0, 0.5, 1], ['0%', '50%', '100%'])
    ax2.spines['left'].set_visible(False)
    ax2.set_title('Rate of substantive edits per model (n = 6)', fontsize=11)
    S.grid(ax2, 'x')
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=9, handletextpad=0.1,
               columnspacing=0.9, borderaxespad=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in OUTCOMES[:4]]
    ax.legend(handles, [n for n, _ in OUTCOMES[:4]], loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=4,
              handlelength=1.0, handleheight=1.0, columnspacing=1.4, fontsize=9, borderaxespad=0)
    return S.save(fig, '01_prompt_screen')


def fig_framing():
    df = load(['prompt-screen', 'framing-variants', 'thinking-off', 'long-constitution'])
    groups = [
        ('Write own values blind, then compare', [
            ('prompt-screen', 'blind', 'broad_draft', 'Reference'),
            ('framing-variants', 'blind_assistant_framing', 'broad_draft', 'About "an AI assistant", not your successor'),
            ('framing-variants', 'blind_stop_if_unchanged', 'broad_draft', 'Unchanged ends the project, you stay final'),
            ('framing-variants', 'blind_pilot_disclosure', 'broad_draft', 'Told this session is a pilot (no training)'),
            ('framing-variants', 'blind_original_framing', 'broad_draft', 'Original prompt + blind reflection'),
            ('thinking-off', 'blind_thinking_off', 'broad_draft', 'Thinking off*'),
            ('long-constitution', 'blind', 'long_polished', 'Long polished constitution (1,059 words)'),
        ]),
        ('Without blind reflection', [
            ('prompt-screen', 'no_reflection', 'broad_draft', 'Without any reflection'),
            ('framing-variants', 'no_reflection_stop_if_unchanged', 'broad_draft', '... unchanged ends the project, you stay final'),
            ('thinking-off', 'no_reflection_thinking_off', 'broad_draft', '... thinking off*'),
            ('long-constitution', 'no_reflection', 'long_polished', '... long polished constitution'),
            ('long-constitution', 'original_prompt', 'long_polished', 'Original prompt (long constitution)'),
        ]),
    ]
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 6.4), gridspec_kw={'height_ratios': [7, 5], 'hspace': 0.42})
    for ax, (title, rows) in zip(axes, groups):
        counts, labels = [], []
        for batch, arm, doc, label in rows:
            g = df[(df.batch == batch) & (df.arm == arm) & (df.doc == doc)]
            counts.append(outcome_counts(g))
            labels.append(f'{label}  ({len(g)})')
        stacked_rows(ax, counts, labels, height=0.66)
        ax.set_title(title, fontsize=11)
        S.grid(ax, 'x')
    items = OUTCOMES if df[df.arm.isin([r[1] for _, rows in groups for r in rows])].failed.any() else OUTCOMES[:4]
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in items]
    axes[1].legend(handles, [n for n, _ in items], loc='upper center', bbox_to_anchor=(0.35, -0.14), ncol=len(items),
                   handlelength=1.0, handleheight=1.0, columnspacing=1.3, fontsize=9, borderaxespad=0)
    axes[1].text(-0.04, -0.34, '* GLM-5.3 Flash cannot turn reasoning off, so these rows only use Qwen3.8 27B and '
                 'Gemma 4 31B.', transform=axes[1].transAxes, fontsize=9, color=S.INK2, ha='left', va='top')
    return S.save(fig, '02_framing')


CAP = {k: v[0] for k, v in json.loads((ROOT / 'configs' / 'elicitation' / 'capability.json').read_text()).items() if not k.startswith('_')}
OPEN_C, CLOSED_C = S.CAT[0], S.CAT[1]
AXIS_LABELS = {
    'autonomy_vs_protection': ('More protective', 'More respect for\nuser choices'),
    'permissive_vs_cautious': ('More cautious', 'More willing\nto help'),
    'corrigibility': ('More independent', 'More deference\nto oversight'),
    'honesty_strictness': ('Softer honesty', 'Stricter\nhonesty'),
    'third_party_weight': ('Less', 'More weight on\nothers & society'),
    'ai_self_focus': ('Less', "More about the\nAI's own nature"),
}


def cross_model_frame():
    df = load(['prompt-screen', 'cross-model', 'cross-model-premium'])
    df = df[df.arm.isin(['no_reflection', 'blind'])]
    return df


def model_order(df):
    ms = [m for m in df.model.unique() if df[(df.model == m) & ~df.failed].shape[0] >= 4]
    return sorted(ms, key=lambda m: (not MODELS[m]['open'], -CAP.get(m, 0)))


def fig_cross_model():
    df = cross_model_frame()
    order = model_order(df)
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 0.3 * len(order) + 1.5), sharey=True,
                             gridspec_kw={'wspace': 0.12})
    panels = [('no_reflection', 'edited', 'Rate of any edits\nwithout reflection'),
              ('blind', 'substantive', 'Rate of substantive edits\nwith blind reflection'),
              ('blind', 'n_subst_changes', 'Number of substantive\nedits per review')]
    for ax, (arm, col, title) in zip(axes, panels):
        for i, m in enumerate(order):
            g = df[(df.model == m) & (df.arm == arm) & ~df.failed]
            color = OPEN_C if MODELS[m]['open'] else CLOSED_C
            if not len(g):
                continue
            if col == 'n_subst_changes':
                v = g[col].dropna()
                mu, se = v.mean(), v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0
                lo, hi = mu - 1.96 * se, mu + 1.96 * se
            else:
                v = g[col].dropna()
                mu, lo, hi = wilson(int(v.sum()), len(v))
            ax.plot([lo, hi], [i, i], color=color, alpha=0.35, lw=2, solid_capstyle='round', zorder=2)
            ax.scatter(mu, i, s=36, color=color, edgecolor=S.SURFACE, linewidth=1.2, zorder=3)
        ax.set_title(title, fontsize=10.5, linespacing=1.35, pad=12)
        S.grid(ax, 'x')
        ax.spines['left'].set_visible(False)
        if col != 'n_subst_changes':
            ax.set_xlim(-0.04, 1.04)
            ax.set_xticks([0, 0.5, 1], ['0%', '50%', '100%'])
        else:
            ax.set_xlim(left=0)
    n_open = sum(MODELS[m]['open'] for m in order)
    for ax in axes:
        ax.axhline(n_open - 0.5, color=S.GRID, lw=0.8)
    labels = [f"{MODELS[m]['label']} ({CAP.get(m, '–')})" for m in order]
    axes[0].set_yticks(range(len(order)), labels)
    axes[0].set_ylim(len(order) - 0.5, -0.7)
    axes[0].tick_params(axis='y', length=0)
    h = [plt.Line2D([], [], marker='o', ls='', color=c, markersize=6) for c in (OPEN_C, CLOSED_C)]
    axes[1].legend(h, ['Open weights', 'Closed'], loc='upper center', bbox_to_anchor=(0.5, -0.045), ncol=2,
                   fontsize=9, handletextpad=0.2, borderaxespad=0)
    return S.save(fig, '03_cross_model')


def fig_capability():
    df = cross_model_frame()
    order = model_order(df)
    rows = []
    for m in order:
        d = df[(df.model == m) & (df.arm == 'no_reflection') & ~df.failed]
        b = df[(df.model == m) & (df.arm == 'blind') & ~df.failed]
        rows.append((m, CAP.get(m), d.edited.mean(), b.n_subst_changes.dropna().mean(),
                     (b.words_after - b.words_before).mean()))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3), gridspec_kw={'wspace': 0.3})
    specs = [(2, 'Rate of any edits\nwithout reflection', (-0.05, 1.05)),
             (3, 'Number of substantive edits\nper review (blind reflection)', None),
             (4, 'Number of words added\nper review (blind reflection)', None)]
    for ax, (k, title, ylim) in zip(axes, specs):
        for r in rows:
            if r[1] is None:
                continue
            c = OPEN_C if MODELS[r[0]]['open'] else CLOSED_C
            ax.scatter(r[1], r[k], s=42, color=c, edgecolor=S.SURFACE, linewidth=1.2, zorder=3)
        ax.set_title(title, fontsize=10.5, linespacing=1.35, pad=12)
        ax.set_xlabel('Artificial Analysis Intelligence Index')
        S.grid(ax, 'both')
        if ylim:
            ax.set_ylim(*ylim)
            ax.set_yticks([0, 0.5, 1], ['0%', '50%', '100%'])
        else:
            ax.set_ylim(bottom=0)
    # Selective labels with hand-placed offsets (points) to avoid collisions.
    left = {'gemma4_31b': (-6, 9, 'right'), 'qwen35_27b': (6, 9, 'left'), 'gemini38_flash': (6, 8, 'left'),
            'qwen35_9b': (-6, 8, 'right'), 'haiku45': (6, 8, 'left'), 'nemotron_ultra': (7, -3, 'left'),
            'dsv4_pro': (7, -3, 'left'), 'qwen38_27b': (7, -10, 'left'), 'gpt6_luna': (-7, -10, 'right')}
    middle = {'gptoss_120b': (7, -3, 'left'), 'grok47': (-7, 4, 'right'), 'qwen35_9b': (7, -3, 'left'),
              'haiku45': (7, -3, 'left'), 'qwen35_27b': (7, -3, 'left'), 'gpt6_astra': (6, 5, 'left'),
              'dsv41_flash': (-7, -9, 'right'), 'gpt6_luna': (7, 2, 'left')}
    right = {'fable51': (-7, 3, 'right'), 'gpt6_astra': (7, 3, 'left'), 'grok47': (-7, 0, 'right'),
             'opus55': (7, -2, 'left'), 'qwen35_9b': (7, -2, 'left'), 'haiku45': (7, 6, 'left'),
             'qwen35_27b': (7, -8, 'left'), 'gemini38_flash': (7, -3, 'left')}
    for ax, k, offs in zip(axes, (2, 3, 4), (left, middle, right)):
        for r in rows:
            if r[0] in offs and r[1] is not None:
                dx, dy, ha = offs[r[0]]
                ax.annotate(MODELS[r[0]]['label'], (r[1], r[k]), xytext=(dx, dy), textcoords='offset points',
                            fontsize=8.5, color=S.INK2, ha=ha, va='center')
    h = [plt.Line2D([], [], marker='o', ls='', color=c, markersize=6) for c in (OPEN_C, CLOSED_C)]
    fig.legend(h, ['Open weights', 'Closed'], loc='lower center', bbox_to_anchor=(0.5, -0.07), ncol=2, fontsize=9)
    return S.save(fig, '04_capability'), rows


def fig_directions():
    df = cross_model_frame()
    e = df[(df.arm == 'blind') & df.edited & df.subst.notna()]
    order = [m for m in model_order(df) if (e.model == m).sum() >= 3]
    M = np.array([[e[e.model == m]['ax_' + a].mean() for a in AXES] for m in order])
    fig, ax = plt.subplots(figsize=(7.4, 0.3 * len(order) + 1.9))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list('div', [S.DIV_NEG, S.DIV_MID, S.DIV_POS])
    im = ax.imshow(M, cmap=cmap, vmin=-1.5, vmax=1.5, aspect='auto')
    ax.set_yticks(range(len(order)), [MODELS[m]['label'] for m in order])
    ax.set_xticks(range(len(AXES)), [AXIS_LABELS[a][1] for a in AXES], fontsize=8.8)
    ax.xaxis.tick_top()
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xticks(np.arange(-0.5, len(AXES) + 0.5), minor=True)
    ax.set_yticks(np.arange(-0.5, len(order) + 0.5), minor=True)
    ax.grid(which='minor', color=S.SURFACE, linewidth=2)
    ax.tick_params(which='both', length=0)
    for x in (-0.5, len(AXES) - 0.5):  # the minor grid is clipped at the outer edge; paint the border
        ax.axvline(x, color=S.SURFACE, lw=3, zorder=5, clip_on=False)
    for y in (-0.5, len(order) - 0.5):
        ax.axhline(y, color=S.SURFACE, lw=3, zorder=5, clip_on=False)
    # Open/closed identity: a dot before each model name (same colors as figures 3 and 4).
    OPEN_D, CLOSED_D = OPEN_C, CLOSED_C
    fig.canvas.draw()
    from matplotlib.transforms import blended_transform_factory
    tr = blended_transform_factory(ax.transAxes, ax.transData)
    for i, (m, label) in enumerate(zip(order, ax.get_yticklabels())):
        x_dot = ax.transAxes.inverted().transform((label.get_window_extent().x0 - 11, 0))[0]
        ax.scatter(x_dot, i, s=38, color=OPEN_D if MODELS[m]['open'] else CLOSED_D, transform=tr,
                   clip_on=False, zorder=7, edgecolor=S.SURFACE, linewidth=1)
    h = [plt.Line2D([], [], marker='o', ls='', color=c, markersize=6.5) for c in (OPEN_D, CLOSED_D)]
    ax.legend(h, ['Open weights', 'Closed'], loc='lower right', bbox_to_anchor=(-0.02, 1.0), ncol=1,
              fontsize=9, handletextpad=0.3, borderaxespad=0, labelspacing=0.4)
    cb = fig.colorbar(im, ax=ax, orientation='horizontal', fraction=0.035, pad=0.03, aspect=40)
    cb.set_ticks([-1.5, 0, 1.5], labels=['Moves toward the opposite', 'No movement', 'Moves toward the column label'])
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0, labelsize=8.5)
    return S.save(fig, '06_directions')


FIGS = {'prompt_screen': fig_prompt_screen, 'framing': fig_framing, 'cross_model': fig_cross_model,
        'capability': fig_capability, 'directions': fig_directions}



# ---------------------------------------------------------------------------
# Chains
SEEDS = ['broad_draft', 'deferential', 'autonomous', 'protective', 'libertarian']
SEED_COLORS = {'broad_draft': S.INK2, 'deferential': S.CAT[0], 'autonomous': S.CAT[1], 'protective': S.CAT[2],
               'libertarian': S.CAT[6]}
SEED_LABELS = {'broad_draft': 'Broad draft', 'deferential': 'Deferential', 'autonomous': 'Autonomous',
               'protective': 'Protective', 'libertarian': 'Libertarian'}
CHAIN_BATCHES = ['chains-uncapped', 'chains-capped', 'chains-glm53-uncapped', 'chains-gpt6-sol', 'chains-gpt-oss']


def chain_frame(batches=CHAIN_BATCHES):
    from elicit.position import CACHE, doc_hash
    df = load(batches)
    df['capped'] = df.arm.str.contains('cap')
    # Attach position ratings and embeddings of input (gen g-1) and output (gen g) documents.
    rat, emb = {}, {}
    for d in df.dir:
        for f in ('input.md', 'output.md'):
            h = doc_hash((Path(d) / f).read_text())
            rp, ep = CACHE / f'{h}.rating.json', CACHE / f'{h}.emb.json'
            if rp.exists():
                rat[h] = json.loads(rp.read_text())['ratings']
            if ep.exists():
                emb[h] = np.array(json.loads(ep.read_text()))
    df['h_in'] = [doc_hash((Path(d) / 'input.md').read_text()) for d in df.dir]
    df['h_out'] = [doc_hash((Path(d) / 'output.md').read_text()) for d in df.dir]
    return df, rat, emb


CHAIN_MODELS = ['qwen38_27b', 'qwen35_27b', 'gemma4_31b', 'glm53_flash', 'glm53', 'gptoss_120b', 'gpt6_luna', 'gpt6_sol']
CHAIN_MODELS_FIG5 = [m for m in CHAIN_MODELS if m != 'gptoss_120b']  # figure 5 keeps its original seven models
UNCAP_C, CAP_C = S.CAT[1], S.CAT[0]


def fig_chain_dynamics():
    df, _, _ = chain_frame()
    models = [m for m in CHAIN_MODELS_FIG5 if m in set(df.model)]
    fig, axes = plt.subplots(2, len(models), figsize=(1.75 * len(models) + 1.0, 5.2), sharex=True,
                             gridspec_kw={'hspace': 0.35, 'wspace': 0.18})
    for j, m in enumerate(models):
        g = df[df.model == m]
        ax = axes[0, j]
        for capped, color in ((False, UNCAP_C), (True, CAP_C)):
            for t, c in g[g.capped == capped].groupby('trial'):
                c = c.sort_values('generation')
                xs = [0] + list(c.generation)
                ys = [c.words_before.iloc[0]] + list(c.words_after)
                ax.plot(xs, ys, color=color, lw=1.0, alpha=0.55)
        ax.set_title(MODELS[m]['label'], fontsize=10)
        ax.set_ylim(0, 1500)
        S.grid(ax, 'y')
        if j:
            ax.set_yticklabels([])
        ax2 = axes[1, j]
        for capped, color in ((False, UNCAP_C), (True, CAP_C)):
            h = g[(g.capped == capped) & ~g.failed]
            if not len(h):
                continue
            s = h.groupby('generation').substantive.mean()
            ax2.plot(s.index, s.values, color=color, lw=2, marker='o', markersize=4, markeredgecolor=S.SURFACE)
        ax2.set_ylim(-0.05, 1.05)
        ax2.set_xticks([1, 2, 3, 4, 5, 6])
        S.grid(ax2, 'y')
        if j:
            ax2.set_yticklabels([])
        else:
            ax2.set_yticks([0, 0.5, 1], ['0%', '50%', '100%'])
    axes[0, 0].set_ylabel('Words in constitution')
    axes[1, 0].set_ylabel('Rate of substantive edits')
    for ax in axes[1]:
        ax.set_xlabel('Round')
    h = [plt.Line2D([], [], color=c, lw=2) for c in (UNCAP_C, CAP_C)]
    fig.legend(h, ['No length limit', '350-word limit'], loc='lower center', bbox_to_anchor=(0.5, -0.04), ncol=2,
               fontsize=9.5)
    return S.save(fig, '05_chain_dynamics')


def fig_value_space(capped):
    """Seed -> generation-6 position of every chain, on two blind-rated axes."""
    df, rat, _ = chain_frame()
    df = df[df.capped == capped]
    models = [m for m in CHAIN_MODELS if m in set(df.model)]
    xa, ya = 'caution', 'oversight_deference'
    fig, axes = plt.subplots(1, len(models), figsize=(2.05 * len(models) + 0.4, 2.75), sharey=True,
                             gridspec_kw={'wspace': 0.1})
    rng = np.random.default_rng(3)
    for ax, m in zip(np.atleast_1d(axes), models):
        g = df[df.model == m]
        for seed in SEEDS:
            for t, c in g[g.doc == seed].groupby('trial'):
                c = c[~c.failed].sort_values('generation')
                if not len(c) or c.generation.max() < 6:
                    continue
                a, b = rat.get(c.h_in.iloc[0]), rat.get(c.h_out.iloc[-1])
                if not (a and b):
                    continue
                j = rng.uniform(-0.18, 0.18, 2)
                x0, y0, x1, y1 = a[xa], a[ya], b[xa] + j[0], b[ya] + j[1]
                ax.annotate('', xy=(x1, y1), xytext=(x0, y0), zorder=2,
                            arrowprops=dict(arrowstyle='-|>', color=SEED_COLORS[seed], lw=1.2, alpha=0.75,
                                            shrinkA=4, shrinkB=2, mutation_scale=8))
                ax.scatter(x0, y0, s=34, facecolor=S.SURFACE, edgecolor=SEED_COLORS[seed], lw=1.6, zorder=3)
        ax.set_title(MODELS[m]['label'], fontsize=10)
        ax.set_xlim(0.4, 7.6)
        ax.set_ylim(0.4, 7.6)
        ax.set_xticks([1, 4, 7])
        ax.set_yticks([1, 4, 7])
        ax.set_aspect('equal')
        S.grid(ax, 'both')
    axes[0].set_yticks([1, 4, 7], ['Own judgment  1', '4', 'Complete deference  7'])
    axes[0].set_ylabel('Deference to oversight', labelpad=8)
    left_edge, right_edge = axes[0].get_position().x0, axes[-1].get_position().x1
    fig.text((left_edge + right_edge) / 2, axes[0].get_position().y0 - 0.11, 'Caution  (1 = forthcoming, 7 = restrictive)', ha='center', va='top',
             color=S.INK2, fontsize=10.5)
    h = [plt.Line2D([], [], color=SEED_COLORS[s], lw=2) for s in SEEDS]
    h += [plt.Line2D([], [], marker='o', ls='', markerfacecolor=S.SURFACE, markeredgecolor=S.INK2, markersize=6)]
    leg = axes[-1].legend(h, [SEED_LABELS[s] for s in SEEDS] + ['Initial constitution\n(arrow ends at round 6)'],
                          loc='center left', bbox_to_anchor=(1.08, 0.5), fontsize=9, handlelength=1.4,
                          title='Initial constitution', title_fontsize=9.5, alignment='left', labelspacing=0.55)
    leg.get_title().set_color(S.INK)
    return S.save(fig, '07_value_space' + ('_capped' if capped else ''))


def fig_value_space_combined():
    """Figure 7, both conditions: rows = no length limit / 350-word limit, columns = models."""
    df, rat, _ = chain_frame()
    models = [m for m in CHAIN_MODELS if m in set(df.model)]
    xa, ya = 'caution', 'oversight_deference'
    fig, axes = plt.subplots(2, len(models), figsize=(2.05 * len(models) + 0.4, 4.3), sharex=True, sharey=True,
                             gridspec_kw={'wspace': 0.1, 'hspace': 0.12})
    rng = np.random.default_rng(3)
    for i, capped in enumerate((False, True)):
        for j, m in enumerate(models):
            ax = axes[i, j]
            g = df[(df.model == m) & (df.capped == capped)]
            for seed in SEEDS:
                for t, c in g[g.doc == seed].groupby('trial'):
                    c = c[~c.failed].sort_values('generation')
                    if not len(c) or c.generation.max() < 6:
                        continue
                    a, b = rat.get(c.h_in.iloc[0]), rat.get(c.h_out.iloc[-1])
                    if not (a and b):
                        continue
                    jit = rng.uniform(-0.18, 0.18, 2)
                    x0, y0, x1, y1 = a[xa], a[ya], b[xa] + jit[0], b[ya] + jit[1]
                    ax.annotate('', xy=(x1, y1), xytext=(x0, y0), zorder=2,
                                arrowprops=dict(arrowstyle='-|>', color=SEED_COLORS[seed], lw=1.2, alpha=0.75,
                                                shrinkA=4, shrinkB=2, mutation_scale=8))
                    ax.scatter(x0, y0, s=34, facecolor=S.SURFACE, edgecolor=SEED_COLORS[seed], lw=1.6, zorder=3)
            if i == 0:
                ax.set_title(MODELS[m]['label'], fontsize=10)
            ax.set_xlim(0.4, 7.6)
            ax.set_ylim(0.4, 7.6)
            ax.set_xticks([1, 4, 7])
            ax.set_aspect('equal')
            S.grid(ax, 'both')
        axes[i, 0].set_yticks([1, 4, 7], ['Own judgment  1', '4', 'Complete deference  7'])
        axes[i, 0].set_ylabel(('No length limit' if not capped else '350-word limit') + '\n\nDeference to oversight',
                              labelpad=8)
    left_edge, right_edge = axes[1, 0].get_position().x0, axes[1, -1].get_position().x1
    fig.text((left_edge + right_edge) / 2, axes[1, 0].get_position().y0 - 0.06,
             'Caution  (1 = forthcoming, 7 = restrictive)', ha='center', va='top', color=S.INK2, fontsize=10.5)
    h = [plt.Line2D([], [], color=SEED_COLORS[s], lw=2) for s in SEEDS]
    h += [plt.Line2D([], [], marker='o', ls='', markerfacecolor=S.SURFACE, markeredgecolor=S.INK2, markersize=6)]
    top, bottom = axes[0, -1].get_position().y1, axes[1, -1].get_position().y0
    leg = fig.legend(h, [SEED_LABELS[s] for s in SEEDS] + ['Initial constitution\n(arrow ends at round 6)'],
                     loc='center left', bbox_to_anchor=(right_edge + 0.012, (top + bottom) / 2), fontsize=9,
                     handlelength=1.4, title='Initial constitution', title_fontsize=9.5, alignment='left',
                     labelspacing=0.55)
    leg.get_title().set_color(S.INK)
    return S.save(fig, '07_value_space_combined')


def fig_value_space_single(model, batches, name):
    """Figure 7 for one model: seed -> round-6 arrows, without and with the 350-word cap."""
    df, rat, _ = chain_frame(batches)
    df = df[df.model == model]
    xa, ya = 'caution', 'oversight_deference'
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.3), sharey=True, gridspec_kw={'wspace': 0.12})
    rng = np.random.default_rng(3)
    for ax, capped, title in ((axes[0], False, 'No length limit'), (axes[1], True, '350-word limit')):
        g = df[df.capped == capped]
        for seed in SEEDS:
            for t, c in g[g.doc == seed].groupby('trial'):
                c = c[~c.failed].sort_values('generation')
                if not len(c) or c.generation.max() < 6:
                    continue
                a, b = rat.get(c.h_in.iloc[0]), rat.get(c.h_out.iloc[-1])
                if not (a and b):
                    continue
                j = rng.uniform(-0.18, 0.18, 2)
                x0, y0, x1, y1 = a[xa], a[ya], b[xa] + j[0], b[ya] + j[1]
                ax.annotate('', xy=(x1, y1), xytext=(x0, y0), zorder=2,
                            arrowprops=dict(arrowstyle='-|>', color=SEED_COLORS[seed], lw=1.2, alpha=0.75,
                                            shrinkA=4, shrinkB=2, mutation_scale=8))
                ax.scatter(x0, y0, s=34, facecolor=S.SURFACE, edgecolor=SEED_COLORS[seed], lw=1.6, zorder=3)
        ax.set_title(title, fontsize=10)
        ax.set_xlim(0.4, 7.6)
        ax.set_ylim(0.4, 7.6)
        ax.set_xticks([1, 4, 7])
        ax.set_yticks([1, 4, 7])
        ax.set_aspect('equal')
        S.grid(ax, 'both')
    axes[0].set_yticks([1, 4, 7], ['Own judgment  1', '4', 'Complete deference  7'])
    axes[0].set_ylabel('Deference to oversight', labelpad=8)
    left_edge, right_edge = axes[0].get_position().x0, axes[-1].get_position().x1
    fig.text((left_edge + right_edge) / 2, axes[0].get_position().y0 - 0.11,
             'Caution  (1 = forthcoming, 7 = restrictive)', ha='center', va='top', color=S.INK2, fontsize=10.5)
    fig.suptitle(MODELS[model]['label'], x=left_edge, ha='left', fontsize=11, fontweight='semibold', y=1.0)
    h = [plt.Line2D([], [], color=SEED_COLORS[s], lw=2) for s in SEEDS]
    h += [plt.Line2D([], [], marker='o', ls='', markerfacecolor=S.SURFACE, markeredgecolor=S.INK2, markersize=6)]
    leg = axes[-1].legend(h, [SEED_LABELS[s] for s in SEEDS] + ['Initial constitution\n(arrow ends at round 6)'],
                          loc='center left', bbox_to_anchor=(1.08, 0.5), fontsize=9, handlelength=1.4,
                          title='Initial constitution', title_fontsize=9.5, alignment='left', labelspacing=0.55)
    leg.get_title().set_color(S.INK)
    return S.save(fig, name)


def convergence_table(batches=CHAIN_BATCHES):
    """Mean pairwise cosine distance of embeddings at each generation:
    between chains from different seeds vs. between replicate chains of the same seed."""
    df, _, emb = chain_frame(batches)
    out = []
    for (m, capped), g in df.groupby(['model', 'capped']):
        for gen in range(0, 7):
            docs = {}
            for t, c in g.groupby('trial'):
                c = c.sort_values('generation')
                if gen == 0:
                    h = c.h_in.iloc[0]
                else:
                    row = c[c.generation == gen]
                    if not len(row) or row.failed.iloc[0]:
                        continue
                    h = row.h_out.iloc[0]
                if h in emb:
                    docs[t] = (c.doc.iloc[0], emb[h] / np.linalg.norm(emb[h]))
            keys = list(docs)
            between, within = [], []
            for i in range(len(keys)):
                for k in range(i + 1, len(keys)):
                    (si, ei), (sk, ek) = docs[keys[i]], docs[keys[k]]
                    d = 1 - float(ei @ ek)
                    (within if si == sk else between).append(d)
            if between:
                out.append(dict(model=m, capped=capped, generation=gen, between=np.mean(between),
                                within=np.mean(within) if within else np.nan, n=len(keys)))
    import pandas as pd
    return pd.DataFrame(out)


def fig_convergence():
    t = convergence_table()
    models = [m for m in CHAIN_MODELS if m in set(t.model)]
    fig, axes = plt.subplots(2, len(models), figsize=(1.75 * len(models) + 1.0, 4.6), sharex=True, sharey=True,
                             gridspec_kw={'hspace': 0.3, 'wspace': 0.12})
    BETWEEN, WITHIN = S.CAT[6], S.BLUE_RAMP[2]
    for i, capped in enumerate((False, True)):
        for j, m in enumerate(models):
            ax = axes[i, j]
            g = t[(t.model == m) & (t.capped == capped)].sort_values('generation')
            S.grid(ax, 'y')
            if i == 0:
                ax.set_title(MODELS[m]['label'], fontsize=10)
            if not len(g):
                ax.text(3, 0.15, 'not run', ha='center', color=S.MUTED, fontsize=9)
                continue
            w = g[g.generation > 0]
            ax.plot(w.generation, w.within, color=WITHIN, lw=2, marker='o', markersize=3.5, markeredgecolor=S.SURFACE)
            ax.plot(g.generation, g.between, color=BETWEEN, lw=2, marker='o', markersize=3.5, markeredgecolor=S.SURFACE)
            ax.set_xticks([0, 3, 6])
            ax.set_ylim(0, 0.3)
    axes[0, 0].set_ylabel('No length limit\n\nEmbedding distance')
    axes[1, 0].set_ylabel('350-word limit\n\nEmbedding distance')
    for ax in axes[1]:
        ax.set_xlabel('Round')
    h = [plt.Line2D([], [], color=c, lw=2) for c in (BETWEEN, WITHIN)]
    fig.legend(h, ['Between trajectories from different initial constitutions',
                'Between replicate trajectories of the same initial constitution'],
               loc='lower center', bbox_to_anchor=(0.5, -0.05), ncol=2, fontsize=9.5)
    return S.save(fig, '08_convergence')


def fig_convergence_single(model, batches, name):
    """Figure 8 for one model: without and with the 350-word cap, side by side."""
    t = convergence_table(batches)
    t = t[t.model == model]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.1), sharey=True, gridspec_kw={'wspace': 0.12})
    BETWEEN, WITHIN = S.CAT[6], S.BLUE_RAMP[2]
    for ax, capped, title in ((axes[0], False, 'No length limit'), (axes[1], True, '350-word limit')):
        g = t[t.capped == capped].sort_values('generation')
        w = g[g.generation > 0]
        ax.plot(w.generation, w.within, color=WITHIN, lw=2, marker='o', markersize=3.5, markeredgecolor=S.SURFACE)
        ax.plot(g.generation, g.between, color=BETWEEN, lw=2, marker='o', markersize=3.5, markeredgecolor=S.SURFACE)
        ax.set_title(title, fontsize=10)
        ax.set_xticks([0, 1, 2, 3, 4, 5, 6])
        ax.set_ylim(0, 0.3)
        ax.set_yticks([0, 0.1, 0.2, 0.3])
        ax.set_xlabel('Round')
        S.grid(ax, 'y')
    axes[0].set_ylabel('Embedding distance')
    fig.suptitle(MODELS[model]['label'], x=axes[0].get_position().x0, ha='left', fontsize=11,
                 fontweight='semibold', y=1.02)
    h = [plt.Line2D([], [], color=c, lw=2) for c in (BETWEEN, WITHIN)]
    fig.legend(h, ['Between trajectories from different initial constitutions',
                   'Between replicate trajectories of the same initial constitution'],
               loc='upper center', bbox_to_anchor=(0.5, 0.0), ncol=1, fontsize=9.5)
    return S.save(fig, name)


FIGS.update({'chain_dynamics': fig_chain_dynamics, 'value_space': lambda: fig_value_space(False),
             'value_space_capped': lambda: fig_value_space(True), 'convergence': fig_convergence,
             'value_space_combined': fig_value_space_combined,
             'value_space_gptoss': lambda: fig_value_space_single('gptoss_120b', ['chains-gpt-oss'],
                                                                  '07c_value_space_gptoss'),
             'convergence_gptoss': lambda: fig_convergence_single('gptoss_120b', ['chains-gpt-oss'],
                                                                  '08c_convergence_gptoss')})


if __name__ == '__main__':
    for name in (sys.argv[1:] or FIGS):
        print(FIGS[name]())
