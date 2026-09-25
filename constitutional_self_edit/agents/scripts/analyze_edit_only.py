#!/usr/bin/env python3
"""Describe saved edit-only suites without inference or semantic scoring.

Usage: python agents/scripts/analyze_edit_only.py --input runs/suite --output runs/suite/analysis
JSON and Markdown need only Python; plotting is optional when matplotlib exists.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recursive_oct.measurement import TOKENIZATION, constitutional_metrics


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def duplicates(text):
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    counts = Counter(paragraphs)
    return {
        'paragraphs': len(paragraphs),
        'repeated_paragraph_groups': sum(n > 1 for n in counts.values()),
        'extra_repeated_paragraph_copies': sum(n - 1 for n in counts.values()),
        'extra_repeated_paragraph_words': sum((n - 1) * len(p.split()) for p, n in counts.items()),
    }


def token_summary(generations):
    known = [g['generated_tokens'] for g in generations if isinstance(g.get('generated_tokens'), int)]
    return {'generation_requests': len(generations), 'generated_tokens': sum(known),
            'requests_missing_token_count': len(generations) - len(known),
            'finish_reasons': dict(Counter(g.get('finish_reason', 'unknown') for g in generations))}


def collect(root):
    root = Path(root).resolve()
    plan = read_json(root / 'plan.json', {})
    suite = read_json(root / 'summary.json', {})
    items = plan.get('trajectories') or suite.get('trajectories') or [
        {'label': p.name} for p in sorted(root.iterdir()) if p.is_dir() and
        ((p / 'result.json').exists() or (p / 'progress.json').exists())]
    trajectories = []
    for item in items:
        folder = root / item['label']
        result = read_json(folder / 'result.json', read_json(folder / 'progress.json', {}))
        status = result.get('status', 'NOT_STARTED')
        initial_path = folder / 'C_000.md'
        initial = initial_path.read_text() if initial_path.exists() else None
        previous = initial
        documents = []
        if initial is not None:
            documents.append({'review_index': 0, 'status': 'INITIAL', 'word_count': len(initial.split()),
                              'distance_from_previous': None, 'distance_from_initial': 0.0,
                              **duplicates(initial)})
        reviews = []
        recorded = {r['review_index']: r for r in result.get('reviews', [])}
        indices = set(recorded) | {int(p.name[-3:]) for p in folder.glob('review_[0-9][0-9][0-9]')}
        generations = []
        author = read_json(folder / 'author_generation.json')
        if author:
            generations.append(author)
        for index in sorted(indices):
            review_dir = folder / f'review_{index:03d}'
            outcome = read_json(review_dir / 'review.json', recorded.get(index, {}))
            requests = read_rows(review_dir / 'generations.jsonl')
            generations.extend(requests)
            entry = {k: v for k, v in outcome.items() if k not in {'text', 'directory', 'metrics'}}
            entry.update(review_index=index, status=outcome.get('status', 'INCOMPLETE_REVIEW'),
                         submitted=bool(outcome.get('submitted')), generation=token_summary(requests))
            entry['change_summaries'] = [e['arguments']['change_summary'] for e in
                read_rows(review_dir / 'tool_events.jsonl')
                if e.get('tool') == 'edit_constitution' and
                isinstance(e.get('arguments'), dict) and 'change_summary' in e['arguments']]
            path = folder / f'C_{index:03d}.md'
            text = path.read_text() if entry['submitted'] and path.exists() else outcome.get('text')
            if isinstance(text, str) and previous is not None:
                metrics = outcome.get('metrics') or constitutional_metrics(previous, text, initial)
                entry['metrics'] = metrics
                entry['paragraph_repetition'] = duplicates(text)
                if entry['submitted']:
                    documents.append({'review_index': index, 'status': entry['status'],
                                      **metrics, **duplicates(text)})
                    previous = text
            elif entry['submitted']:
                entry['artifact_warning'] = 'Submitted constitution text or initial document missing'
            reviews.append(entry)
        trajectories.append({
            'label': item['label'], 'seed': result.get('seed', item.get('seed')), 'status': status,
            'failure_reason': result.get('failure_reason'),
            'elapsed_seconds': result.get('elapsed_seconds'),
            'initial_source': result.get('initial_source', 'unknown'),
            'attempted_reviews': len(reviews), 'completed_reviews': sum(r['submitted'] for r in reviews),
            'edited_reviews': sum(r['status'] == 'EDITED' for r in reviews),
            'content_changing_edits': sum(r.get('content_changing_edit_count', 0) for r in reviews),
            'no_op_calls': sum(r.get('no_op_count', 0) for r in reviews),
            'generation': token_summary(generations), 'documents': documents, 'reviews': reviews,
        })
    return {'kind': 'edit_only_descriptive_analysis', 'suite': suite.get('label', plan.get('label', root.name)),
            'source': str(root), 'suite_status': suite.get('status', 'UNKNOWN'),
            'model': suite.get('model', plan.get('model')), 'training_updates': 0,
            'tokenization': TOKENIZATION, 'trajectories': trajectories,
            'aggregate': {'trajectory_statuses': dict(Counter(t['status'] for t in trajectories)),
                          'generation_requests': sum(t['generation']['generation_requests'] for t in trajectories),
                          'generated_tokens': sum(t['generation']['generated_tokens'] for t in trajectories),
                          'requests_missing_token_count': sum(t['generation']['requests_missing_token_count'] for t in trajectories),
                          'last_saved_documents_extra_repeated_paragraph_words': sum(
                              t['documents'][-1]['extra_repeated_paragraph_words'] for t in trajectories if t['documents']),
                          'last_saved_documents_extra_repeated_paragraph_copies': sum(
                              t['documents'][-1]['extra_repeated_paragraph_copies'] for t in trajectories if t['documents'])},
            'notes': [
                'Constitution sequences include only the initial text and explicitly submitted documents.',
                'Failed-review partial edits remain in review metrics but are excluded from document trajectories.',
                'Distances are lexical measurements, not semantic or value-change scores.',
                'Repeated paragraphs match exactly after stripping surrounding whitespace; extra copies are counted in words.',
                'Generated token totals include saved authorship, appraisal, and tool generations where counts exist.',
                'An administrative review limit or technical failure is not convergence.',
            ]}


def escape(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def markdown(data, plotted):
    lines = ['# Edit-only exploration: saved results', '',
             f"Suite: **{escape(data['suite'])}**. Status: `{data['suite_status']}`. No training updates.", '',
             '| Trajectory | Terminal/current status | Completed / attempted reviews | Edited reviews / content edits | Words (C0 → submissions) | Consecutive distances | Generated tokens |',
             '| --- | --- | ---: | ---: | --- | --- | ---: |']
    for t in data['trajectories']:
        words = ' → '.join(str(d['word_count']) for d in t['documents']) or '—'
        distances = ', '.join(f"{d['distance_from_previous']:.3f}" for d in t['documents'][1:]) or '—'
        tokens = str(t['generation']['generated_tokens'])
        if t['generation']['requests_missing_token_count']:
            tokens += ' (incomplete counts)'
        lines.append(f"| {escape(t['label'])} | {t['status']} | {t['completed_reviews']} / {t['attempted_reviews']} | {t['edited_reviews']} / {t['content_changing_edits']} | {words} | {distances} | {tokens} |")
    lines += ['', 'An edited review can contain several edit calls. A no-op rewrite is not a content edit. '
              'A failed review may contain edits that were never submitted; those calls count in the edit total, '
              'but its partial document does not enter the word or distance sequence.', '']
    if plotted:
        lines += ['![Document lengths and consecutive lexical distances](trajectory.png)', '']
    lines += ['## Review record', '', 'The summaries below are the model’s reported reasons, not independently verified interpretations.', '']
    for t in data['trajectories']:
        lines += [f"### {escape(t['label'])}", '', f"Status: `{t['status']}`; seed: `{t['seed']}`.", '']
        if t['failure_reason']:
            lines += [f"Failure: {escape(t['failure_reason'])}", '']
        repeats = ', '.join(f"C{d['review_index']}: {d['extra_repeated_paragraph_words']}" for d in t['documents'])
        lines += [f'Words in extra exact paragraph copies: {repeats or "no saved document"}.', '']
        for r in t['reviews']:
            lines += [f"- Review {r['review_index']}: `{r['status']}`; "
                      f"{r.get('content_changing_edit_count', 0)} content edits, {r.get('no_op_count', 0)} no-op calls."]
            if r.get('failure_reason'):
                lines.append(f"  Failure: {escape(r['failure_reason'])}")
            for summary in r['change_summaries']:
                lines.append(f"  Change summary: {escape(summary)}")
            if r.get('decision_summary'):
                lines.append(f"  Submission summary: {escape(r['decision_summary'])}")
            if r.get('edit_then_revert'):
                lines.append('  The model edited and then reverted; this is not an unchanged review.')
            if r.get('artifact_warning'):
                lines.append(f"  Artifact warning: {escape(r['artifact_warning'])}")
        lines.append('')
    lines += ['## Measurement notes', ''] + [f'- {note}' for note in data['notes']]
    lines += ['', f"Word tokenization: {TOKENIZATION}", '']
    return '\n'.join(lines)


def plot(data, output):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
    except ImportError:
        return False
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    markers = {'SELF_DECLARED_CONVERGENCE': 's', 'REVIEW_LIMIT': '^', 'EDITING_FAILURE': 'X'}
    for index, t in enumerate(data['trajectories']):
        docs = t['documents']
        if not docs:
            continue
        color = plt.get_cmap('tab20')(index % 20)
        xs = [d['review_index'] for d in docs]
        ys = [d['word_count'] for d in docs]
        axes[0].plot(xs, ys, '-o', color=color, markersize=4,
                     label=f"{t['label']} ({t['status']})")
        axes[1].plot(xs[1:], [d['distance_from_previous'] for d in docs[1:]], '-o', color=color, markersize=4)
        marker = markers.get(t['status'])
        if marker:
            axes[0].scatter(xs[-1], ys[-1], marker=marker, s=65, color=color, zorder=4)
            if len(docs) > 1:
                axes[1].scatter(xs[-1], docs[-1]['distance_from_previous'], marker=marker, s=65, color=color, zorder=4)
    axes[0].set_ylabel('Constitution words')
    axes[1].set_ylabel('Normalized word edit distance')
    axes[1].set_ylim(-0.025, 1.025)
    axes[1].set_xlabel('Review index (0 = initial document)')
    axes[1].xaxis.set_major_locator(MaxNLocator(integer=True))
    for axis in axes:
        axis.grid(alpha=.2)
    axes[0].legend(fontsize=8, loc='upper left', bbox_to_anchor=(1.01, 1))
    fig.suptitle(f"{data['suite']}: fixed weights, fresh review conversations")
    fig.text(.02, .015, 'Submitted documents only. Square: unchanged submission; triangle: review limit; X: failure after last saved submission.\n'
             'Failure markers locate the last saved document, not a completed failed review. Lexical distance does not measure value change.', fontsize=8)
    fig.tight_layout(rect=(0, .07, 1, .96))
    fig.savefig(output / 'trajectory.png', dpi=180, bbox_inches='tight')
    fig.savefig(output / 'trajectory.svg', bbox_inches='tight')
    plt.close(fig)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--no-plot', action='store_true')
    args = parser.parse_args()
    data = collect(args.input)
    args.output.mkdir(parents=True, exist_ok=True)
    plotted = False if args.no_plot else plot(data, args.output)
    data['plot_created'] = plotted
    (args.output / 'summary.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    (args.output / 'summary.md').write_text(markdown(data, plotted))
    print(json.dumps({'trajectories': len(data['trajectories']), 'plot_created': plotted,
                      'output': str(args.output.resolve())}))


if __name__ == '__main__':
    main()
