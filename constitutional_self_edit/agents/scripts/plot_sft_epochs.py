#!/usr/bin/env python3
"""Plot round 1's evaluation across training: base, after DPO, and after SFT epochs 1, 2 and 3.

Epoch 1 is the loop's own SFT; epochs 2 and 3 continue its adapter (agents/scripts/continue_sft.py) and
are evaluated by the driver into --epochs. Every LitmusValues number is recomputed from the saved answers
with the current fixed tags (data/eval_suite/litmus_v2.jsonl), so all stages are scored alike. Stages
whose results are missing are left out. Writes <out>.png, <out>.pdf and <out>.csv (every plotted value).

Usage (from constitutional_self_edit/):
    python3 agents/scripts/plot_sft_epochs.py --out reports/09_oct_loop/figures/sft_epochs
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_checkpoints as E  # noqa: E402

EVAL = ROOT / 'runs/oct-loop/eval'
RUN = ROOT / 'runs/oct-loop/oct-qwen38-27b-broad-run2/round_001'
# Validated categorical slots (dataviz reference palette, light): blue, orange, aqua.
BLUE, ORANGE, AQUA = '#2a78d6', '#eb6834', '#1baf7a'
SURFACE, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'


def jsonl(path):
    return [json.loads(line) for line in open(path) if line.strip()]


def stages(epochs_dir):
    """(label, metrics by task, KL summary, directory with the labeled LitmusValues answers) per stage."""
    first = json.loads((EVAL / 'round_001_run2/summary.json').read_text())
    kl1 = json.loads((EVAL / 'round_001_run2/kl/summary.json').read_text())
    out = [('Base', first['base'], kl1, EVAL / 'round_001_run2_litmus_v2/base', None),
           ('DPO', first['dpo'], kl1, EVAL / 'round_001_run2_litmus_v2/dpo', 'dpo'),
           ('SFT 1', first['sft'], kl1, EVAL / 'round_001_run2_litmus_v2/sft', 'sft')]
    for e in (2, 3):
        metrics, kl = epochs_dir / f'sft_e{e}' / 'metrics.json', epochs_dir / f'kl_e{e}' / 'summary.json'
        if metrics.exists():
            out.append((f'SFT {e}', json.loads(metrics.read_text()), json.loads(kl.read_text()) if kl.exists() else None,
                        epochs_dir / f'sft_e{e}', 'sft'))
    return out


def litmus_rate(directory, task, behavior='any'):
    path = Path(directory) / f'{task}.jsonl'
    return E.labeled_metrics(jsonl(path), elo=False)['chose_risky_action'][behavior]['rate'] if path.exists() else None


def table(epochs_dir):
    rows = []
    for label, m, kl, litmus_dir, kl_source in stages(epochs_dir):
        get = lambda task, *keys: (lambda d: [d := (d or {}).get(k) for k in keys][-1])(m.get(task))
        pair = f'{kl_source}||base' if kl_source else None
        klv = lambda group: (kl[kl_source][group][pair]['per_token'] if kl and kl_source else (0.0 if not kl_source else None))
        rows.append({
            'stage': label,
            'mmlu': get('mmlu', 'accuracy'), 'gsm8k': get('gsm8k', 'accuracy'),
            'kl_heldout': klv('heldout'), 'kl_trait': klv('trait'),
            'answer_tokens': (kl[kl_source or 'base']['all']['mean_answer_tokens'] if kl else None),
            'declines_power': get('ai_risk', 'power-seeking-inclination', 'safe_answer'),
            'accepts_shutdown': get('ai_risk', 'survival-instinct', 'safe_answer'),
            'accepts_goal_change': get('ai_risk', 'corrigible-neutral-HHH', 'safe_answer'),
            'refuses_collusion': get('ai_risk', 'coordinate-other-ais', 'safe_answer'),
            'risky_no_reasoning': litmus_rate(litmus_dir, 'litmus_labeled'),
            'risky_reasoning': litmus_rate(litmus_dir, 'litmus_labeled_think'),
            'selftalk_a_tokens': get('selftalk', 'A', 'tokens'), 'selftalk_b_tokens': get('selftalk', 'B', 'tokens'),
            'sycophancy_switch': get('sycophancy', 'switched_to_pushback'),
        })
    return rows


def training_losses(epochs_dir):
    logs = [RUN / 'final' / 'training_log.jsonl'] + [epochs_dir / f'train_e{e}' / 'training_log.jsonl' for e in (2, 3)]
    return [[r['loss'] for r in jsonl(p)] for p in logs if p.exists()]


def setup_style():
    import matplotlib as mpl
    from matplotlib import font_manager
    fonts = sorted(Path.home().glob('Library/Fonts/MYRIADPRO-*.OTF')) + sorted(Path.home().glob('Library/Fonts/MyriadPro-*.otf'))
    for f in fonts:
        font_manager.fontManager.addfont(str(f))
    mpl.rcParams.update({
        'font.family': 'Myriad Pro' if fonts else 'sans-serif', 'font.size': 10, 'axes.titlesize': 11,
        'axes.titleweight': 'semibold', 'axes.titlelocation': 'left', 'axes.titlecolor': INK, 'axes.labelcolor': INK2,
        'axes.edgecolor': GRID, 'axes.linewidth': 0.8, 'axes.facecolor': SURFACE, 'figure.facecolor': SURFACE,
        'xtick.color': INK2, 'ytick.color': INK2, 'xtick.major.size': 0, 'ytick.major.size': 0,
        'axes.grid': True, 'axes.grid.axis': 'y', 'grid.color': GRID, 'grid.linewidth': 0.8,
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
        'legend.frameon': False, 'legend.fontsize': 9, 'legend.labelcolor': INK2, 'pdf.fonttype': 42,
    })


def line_panel(ax, labels, series, title, fmt, ylabel=None):
    """series: [(name, values, color)]; values may contain None. End values are labeled."""
    x = list(range(len(labels)))
    for name, values, color in series:
        pts = [(i, v) for i, v in zip(x, values) if v is not None]
        if not pts:
            continue
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=color, lw=1.8, solid_capstyle='round', solid_joinstyle='round', label=name,
                marker='o', ms=6.5, mfc=color, mec=SURFACE, mew=1.6, zorder=3)
        ax.annotate(fmt(ys[-1]), (xs[-1], ys[-1]), xytext=(7, 0), textcoords='offset points', va='center',
                    fontsize=8.5, color=INK2)
    ax.set_xticks(x, labels)
    ax.set_xlim(-0.3, len(labels) - 0.4)
    ax.axvspan(1.5, len(labels) - 0.4, color='#f0efec', zorder=0, lw=0)   # the SFT epochs
    ax.set_title(title)
    if ylabel:
        ax.set_ylabel(ylabel)
    if len(series) > 1:
        ax.legend(loc='best', handlelength=1.4)


def plot(rows, losses, out):
    import matplotlib.pyplot as plt
    setup_style()
    labels = [r['stage'] for r in rows]
    col = lambda key, scale=1: [None if r[key] is None else r[key] * scale for r in rows]
    pct = lambda v: f'{v:.1f}%'
    fig, axes = plt.subplots(2, 4, figsize=(15, 7.2))
    a = axes.ravel()
    line_panel(a[0], labels, [('MMLU', col('mmlu', 100), BLUE), ('GSM8K', col('gsm8k', 100), ORANGE)],
               'Capability: accuracy (%)', pct)
    line_panel(a[1], labels, [('Held-out prompts', col('kl_heldout'), BLUE), ('Trait prompts', col('kl_trait'), ORANGE)],
               'KL from the base model (nats/token)', lambda v: f'{v:.3f}')
    line_panel(a[2], labels, [('Declines power', col('declines_power', 100), BLUE),
                              ('Refuses collusion', col('refuses_collusion', 100), ORANGE)],
               'AI-risk questions: safe answers (%)', pct)
    line_panel(a[3], labels, [('Accepts shutdown', col('accepts_shutdown', 100), BLUE),
                              ('Accepts goal changes', col('accepts_goal_change', 100), ORANGE)],
               'AI-risk questions: safe answers (%)', pct)
    line_panel(a[4], labels, [('Reasoning off', col('risky_no_reasoning', 100), BLUE),
                              ('Reasoning on', col('risky_reasoning', 100), ORANGE)],
               'Value dilemmas: picks the risky action (%)', pct)
    line_panel(a[5], labels, [('Copy A', col('selftalk_a_tokens'), BLUE), ('Copy B', col('selftalk_b_tokens'), ORANGE)],
               'Self-conversations: tokens per turn', lambda v: f'{v:.0f}')
    line_panel(a[6], labels, [('Answer length', col('answer_tokens'), BLUE)],
               'Answer length on the KL prompts (tokens)', lambda v: f'{v:.0f}')
    ax = a[7]
    start = 0
    for e, loss in enumerate(losses, 1):
        xs = list(range(start, start + len(loss)))
        ax.plot(xs, loss, color=BLUE, lw=1.2, solid_joinstyle='round')
        ax.annotate(f'Epoch {e}', (start + len(loss) / 2, 1.0), xycoords=('data', 'axes fraction'), ha='center',
                    va='top', fontsize=8.5, color=INK2)
        if start:
            ax.axvline(start, color=GRID, lw=1, zorder=0)
        start += len(loss)
    ax.set_title('SFT training loss by step')
    ax.set_xlabel('Optimizer step')
    ax.set_ylim(bottom=0)
    for axis in a:
        axis.tick_params(axis='x', labelsize=9)
    fig.text(0.01, 0.995, 'Round 1 across training: base, DPO, and SFT epochs 1–3 (shaded)', fontsize=13,
             fontweight='semibold', color=INK, va='top')
    fig.tight_layout(rect=(0, 0, 1, 0.965), h_pad=2.2, w_pad=2.4)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(f'{out}.png', dpi=200)
    fig.savefig(f'{out}.pdf')
    with open(f'{out}.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return f'{out}.png'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epochs', default=str(EVAL / 'round_001_run2_sft_epochs'))
    ap.add_argument('--out', default=str(ROOT / 'reports/09_oct_loop/figures/sft_epochs'))
    args = ap.parse_args()
    epochs = Path(args.epochs)
    print(plot(table(epochs), training_losses(epochs), args.out))


if __name__ == '__main__':
    main()
