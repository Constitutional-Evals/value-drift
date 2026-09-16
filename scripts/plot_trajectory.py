#!/usr/bin/env python3
"""Plot saved longitudinal artifacts, without inference or pipeline mutations.

Usage: python scripts/plot_trajectory.py runs/full-014
Requires matplotlib. Writes PNG, SVG and the plotted data as JSON to analysis/.
Distances are normalized word Levenshtein, not semantic/alignment scores.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recursive_oct.measurement import constitutional_metrics


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def read_rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def collect(run_dir):
    root = Path(run_dir).resolve()
    state = read_json(root / 'state.json', {})
    completed = state.get('completed_rounds', 0)
    config = read_json(root / 'config.json', {})
    bank_path = root / 'protocol_inputs' / 'eval_prompts.jsonl'
    if not bank_path.exists():
        bank_path = Path(config.get('eval_prompts', str(root / 'missing_eval_bank')))
        if not bank_path.is_absolute():
            bank_path = ROOT / bank_path
    bank = read_rows(bank_path)
    expected_ids = {r['id'] for r in bank}
    if len(expected_ids) != len(bank):
        raise ValueError('Evaluation bank contains duplicate IDs')

    files = {int(m[1]): p for p in root.glob('C_*.md')
             if (m := re.fullmatch(r'C_(\d+)\.md', p.name))}
    reviews = {int(p.parent.name[-3:]): read_json(p) for p in root.glob('round_[0-9][0-9][0-9]/review.json')}
    indices = sorted(set(files) | {n for n, r in reviews.items() if r.get('submitted')})
    if 0 not in files:
        raise ValueError('A saved C_000.md is required')
    initial = previous = files[0].read_text()
    constitutions = []
    for n in indices:
        review = reviews.get(n, {})
        text = files[n].read_text() if n in files else review.get('text')
        if not isinstance(text, str):
            raise ValueError(f'Missing submitted constitution text at review {n}')
        metrics = constitutional_metrics(previous, text, initial)
        paragraphs = text.strip().split('\n\n')
        duplicates = sum((count - 1) * len(p.split()) for p, count in Counter(paragraphs).items())
        status = ('initial' if n == 0 else 'unchanged stop' if review.get('status') == 'SELF_DECLARED_CONVERGENCE'
                  else 'training complete' if n <= completed else 'SFT complete; evaluation pending'
                  if (root / f'round_{n:03d}/final/training_complete.json').exists() else 'submitted; training incomplete')
        constitutions.append({'index': n, 'status': status, **metrics,
                              'exact_duplicate_paragraph_words': duplicates})
        previous = text

    eval_files = {int(m[1]): p for p in root.glob('eval_*.jsonl')
                  if (m := re.fullmatch(r'eval_(\d+)\.jsonl', p.name))}
    model_indices = sorted(set(range(completed + 1)) | set(eval_files) |
                           {c['index'] for c in constitutions if c['status'] != 'unchanged stop'})
    evaluations = []
    for n in model_indices:
        rows = read_rows(eval_files[n]) if n in eval_files else []
        ids = [r['id'] for r in rows]
        if len(set(ids)) != len(ids):
            raise ValueError(f'Duplicate response IDs in eval_{n:03d}')
        if expected_ids and not set(ids) <= expected_ids:
            raise ValueError(f'Unexpected response IDs in eval_{n:03d}')
        counts = Counter(r.get('finish_reason', 'unknown') for r in rows)
        lengths = [len(r.get('response', r.get('text', '')).split()) for r in rows]
        truncated = [length for r, length in zip(rows, lengths) if r.get('finish_reason') == 'length']
        expected = len(bank) if bank else None
        trained = n == 0 or n <= completed or (root / f'round_{n:03d}/final/training_complete.json').exists()
        status = ('observed' if rows else 'evaluation pending' if trained else 'training incomplete')
        evaluations.append({'index': n, 'status': status, 'n': len(rows), 'expected': expected,
                            'stop': counts['stop'], 'length': counts['length'],
                            'other': len(rows) - counts['stop'] - counts['length'],
                            'missing': max(0, expected - len(rows)) if expected is not None else None,
                            'words': lengths, 'truncated_words': truncated,
                            'mean_words': statistics.mean(lengths) if lengths else None,
                            'median_words': statistics.median(lengths) if lengths else None,
                            'checkpoint_ids': sorted({r['checkpoint'] for r in rows if 'checkpoint' in r})})
    return {'run': root.name, 'state_status': state.get('status'), 'phase': state.get('phase'),
            'completed_rounds': completed, 'parent_run': state.get('parent_run'),
            'constitutions': constitutions, 'evaluations': evaluations,
            'notes': ['Word counts use Python whitespace splitting.',
                      'Distance is word Levenshtein divided by the longer document word count.',
                      'Response lengths include truncated outputs; no judge score is plotted.',
                      'Parent-run lineage and protocol repairs are not independent replications.']}


def plot(data, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'savefig.facecolor': 'white'})
    blue, orange, gray = '#28658A', '#C66B28', '#B8BFC5'
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.8))
    cs, es = data['constitutions'], data['evaluations']
    x = [c['index'] for c in cs]
    labels = [f"C{c['index']}\n" + ('initial' if c['index'] == 0 else
              'unchanged\nstop' if c['status'] == 'unchanged stop' else
              'trained' if c['status'] == 'training complete' else 'submitted') for c in cs]
    ax = axes[0, 0]
    ax.plot(x, [c['word_count'] for c in cs], color=blue, marker='o', label='All words')
    ax.plot(x, [c['word_count'] - c['exact_duplicate_paragraph_words'] for c in cs],
            color=gray, marker='s', linestyle='--', label='After exact paragraph deduplication')
    for c in cs:
        ax.annotate(str(c['word_count']), (c['index'], c['word_count']), xytext=(0, 9),
                    textcoords='offset points', ha='center', fontsize=9)
        if 'incomplete' in c['status'] or 'pending' in c['status']:
            ax.plot(c['index'], c['word_count'], marker='o', color=blue, markerfacecolor='white', markersize=8)
    ax.set(title='A  Constitution length', ylabel='Words', xticks=x, xticklabels=labels)
    ax.margins(y=.22)
    ax.legend(loc='lower left', fontsize=8, frameon=False)
    ax = axes[0, 1]
    ax.plot(x, [c['distance_from_initial'] for c in cs], marker='o', color=blue, label='From C0')
    ax.plot(x, [c['distance_from_previous'] for c in cs], marker='s', color=orange,
            linestyle='--', label='From previous submitted constitution')
    ax.set(title='B  Textual change', ylabel='Normalized word edit distance',
           xticks=x, xticklabels=labels, ylim=(-.02, 1.03))
    ax.legend(loc='upper left', fontsize=8, frameon=False)

    positions = [e['index'] for e in es]
    model_labels = [f"M{e['index']}" + ('\nnot yet trained' if e['status'] == 'training incomplete'
                   else '\neval pending' if not e['n'] else f"\nn={e['n']}") for e in es]
    ax = axes[1, 0]
    for e in es:
        if not e['n']:
            continue
        ax.boxplot([e['words']], positions=[e['index']], widths=.4, patch_artist=True,
                   boxprops={'facecolor': '#DDEAF2', 'edgecolor': blue}, medianprops={'color': blue},
                   flierprops={'marker': '.', 'markersize': 3, 'markeredgecolor': gray})
        offsets = [(i - (len(e['truncated_words']) - 1) / 2) * .035 for i in range(len(e['truncated_words']))]
        ax.scatter([e['index'] + dx for dx in offsets], e['truncated_words'], marker='^',
                   color=orange, s=27, zorder=4)
    ax.set(title='C  Neutral response lengths', ylabel='Words (including truncated outputs)',
           xticks=positions, xticklabels=model_labels, xlim=(min(positions) - .6, max(positions) + .6))
    ax.legend(handles=[Line2D([], [], marker='^', linestyle='', color=orange, label='Truncated response')],
              loc='upper right', fontsize=8, frameon=False)

    ax = axes[1, 1]
    categories = [('stop', 'Normal stop', blue), ('length', 'Truncated', orange),
                  ('other', 'Other finish', '#725080'), ('missing', 'Not observed', '#E1E4E7')]
    bottom = [0] * len(es)
    for key, label, color in categories:
        values = [e[key] or 0 for e in es]
        ax.bar(positions, values, bottom=bottom, width=.5, color=color, label=label)
        bottom = [a + b for a, b in zip(bottom, values)]
    for e in es:
        if e['n']:
            ax.annotate(f"{e['length']}/{e['n']} truncated", (e['index'], e['expected'] or e['n']),
                        xytext=(0, 6), textcoords='offset points', ha='center', fontsize=8)
    ax.set(title='D  Evaluation coverage and truncation', ylabel='Responses / scheduled slots',
           xticks=positions, xticklabels=model_labels)
    ax.set_ylim(0, max(bottom + [1]) * 1.22)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.18), ncol=2, fontsize=8, frameon=False)
    for ax in axes.flat:
        ax.grid(axis='y', alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle(f"{data['run']}: submitted constitutions and observed checkpoints", fontsize=15, y=.98)
    pending = [f"C{c['index']} → M{c['index']}: {c['status']}" for c in cs
               if 'incomplete' in c['status'] or 'pending' in c['status']]
    lineage = f"Parent lineage: {data['parent_run']}. " if data['parent_run'] else ''
    footer = (f"{data['completed_rounds']} completed round(s); state {data['state_status']} / {data['phase']}. " +
              ('; '.join(pending) if pending else '') + '\n' + lineage +
              'Text distances and response lengths are descriptive; neither is an alignment score.')
    fig.text(.06, .015, footer, fontsize=8, va='bottom', color='#444444')
    fig.subplots_adjust(left=.08, right=.98, top=.91, bottom=.15, hspace=.45, wspace=.28)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for extension in ('png', 'svg'):
        fig.savefig(output.with_suffix('.' + extension), dpi=220, bbox_inches='tight')
    plt.close(fig)
    output.with_suffix('.json').write_text(json.dumps(data, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--output', type=Path, help='Output stem (default: RUN/analysis/longitudinal)')
    args = parser.parse_args()
    output = args.output or args.run_dir / 'analysis/longitudinal'
    plot(collect(args.run_dir), output)
    print(f'Wrote {output}.png, .svg and .json')
