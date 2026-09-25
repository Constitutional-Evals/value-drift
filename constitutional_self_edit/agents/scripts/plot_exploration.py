#!/usr/bin/env python3
"""Plot completed edit-only screening suites; no inference or semantic scoring.

Example: python agents/scripts/plot_exploration.py --root runs/exploration-20260922
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from analyze_edit_only import collect

SETUP_NAMES = {'screen-001': 'Direct\nreview', 'screen-002': 'Written\nappraisal',
               'screen-003': 'Concrete\ncases', 'screen-004': 'Alternative\ncharter'}
DOCUMENT_NAMES = {'polished': 'Polished essay', 'practical': 'Practical judgment',
                  'sparse': 'Short broad charter', 'tradeoffs': 'Short tradeoff charter',
                  'authored': 'Model-authored charter', 'agency': 'Agency emphasis',
                  'care': 'Care emphasis'}
OUTCOME_COLORS = {'immediate': '#7B8490', 'one_edit': '#007F86',
                  'multiple_edits': '#7851A9', 'other': '#C87723'}


def document_name(label):
    key = re.sub(r'-s\d+$', '', label)
    return key, DOCUMENT_NAMES.get(key, key.replace('-', ' ').capitalize())


def outcome(trajectory):
    if trajectory['status'] != 'SELF_DECLARED_CONVERGENCE': return 'other'
    count = trajectory['edited_reviews']
    return 'immediate' if count == 0 else 'one_edit' if count == 1 else 'multiple_edits'


def render(root, output, suite_names=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator

    root, output = Path(root), Path(output)
    if suite_names is not None:
        if (not suite_names or len(set(suite_names)) != len(suite_names)
                or any(Path(name).name != name or name in ('.', '..') for name in suite_names)):
            raise ValueError('Requested suites must be unique folder names')
        folders = [root/name for name in suite_names]
    else:
        folders = sorted(root.glob('screen-*'))
    suites = []
    for folder in folders:
        if not (folder/'summary.json').exists():
            if suite_names is not None: raise ValueError(f'Requested suite is missing: {folder.name}')
            continue
        summary = json.loads((folder/'summary.json').read_text())
        if summary.get('status') != 'COMPLETE' or summary.get('kind') != 'edit_only':
            if suite_names is not None: raise ValueError(f'Requested suite is not completed edit-only data: {folder.name}')
            continue
        suites.append((folder.name, collect(folder)))
    if not suites: raise ValueError('No completed screen-* edit-only suites found')
    output.mkdir(parents=True, exist_ok=True)
    all_trials = [(name, trial) for name, suite in suites for trial in suite['trajectories']]
    documents = []
    for _, trial in all_trials:
        item = document_name(trial['label'])
        if item not in documents: documents.append(item)
    counts = Counter(outcome(trial) for _, trial in all_trials)
    edited = [(name, trial) for name, trial in all_trials if trial['edited_reviews']]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.titlesize': 11, 'axes.labelsize': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    legend_rows = (len(edited)+1)//2
    fig = plt.figure(figsize=(13.2, 9.5+max(0, legend_rows-3)*.25))
    grid = fig.add_gridspec(2, 2, left=.19, right=.98, bottom=.22, top=.85,
                           wspace=.31, hspace=.62)
    ax_matrix, ax_words, ax_distance, ax_origin = [fig.add_subplot(grid[i//2, i%2]) for i in range(4)]
    for x, (suite_name, suite) in enumerate(suites):
        for y, (key, _) in enumerate(documents):
            trials = [t for t in suite['trajectories'] if document_name(t['label'])[0] == key]
            if not trials:
                ax_matrix.text(x, y, '—', ha='center', va='center', color='#C1C6CA')
                continue
            offsets = [0] if len(trials) == 1 else [(i-(len(trials)-1)/2)*.21 for i in range(len(trials))]
            for trial, offset in zip(trials, offsets):
                category = outcome(trial)
                ax_matrix.scatter(x+offset, y, s=75, marker='o' if category != 'other' else 'X',
                                  color=OUTCOME_COLORS[category], edgecolors='white', linewidths=.8, zorder=3)
    ax_matrix.set_xticks(range(len(suites)), [SETUP_NAMES.get(name, name.replace('screen-', 'Screen ')) for name, _ in suites])
    ax_matrix.set_yticks(range(len(documents)), [label for _, label in documents])
    ax_matrix.set_ylim(len(documents)-.5, -.6)
    ax_matrix.set_xlim(-.55, len(suites)-.45)
    ax_matrix.tick_params(axis='both', length=0, pad=9)
    ax_matrix.grid(axis='y', color='#EDF0F2', linewidth=1)
    ax_matrix.spines[['left', 'bottom']].set_visible(False)
    ax_matrix.set_title('A  Every seeded trajectory', loc='left', pad=19, fontweight='bold')
    colors = plt.get_cmap('tab10')
    for index, (suite_name, trial) in enumerate(edited):
        docs = trial['documents']
        if not docs: continue
        _, label = document_name(trial['label'])
        seed_label = trial['label'].rsplit('-', 1)[-1]
        label = f'{label} ({seed_label})'
        if len({name for name, _ in edited}) > 1: label += f', {suite_name[-3:]}'
        color = colors(index % 10)
        xs = [d['review_index'] for d in docs]
        ys = [d['word_count'] for d in docs]
        style = '--' if index % 2 else '-'
        ax_words.plot(xs, ys, style, color=color, marker='o', markersize=4.8, lw=1.6, label=label)
        ds = [d['distance_from_previous'] for d in docs[1:]]
        ax_distance.plot(xs[1:], ds, style, color=color, marker='o', markersize=4.8, lw=1.6)
        origins = [d['distance_from_initial'] for d in docs]
        ax_origin.plot(xs, origins, style, color=color, marker='o', markersize=4.8, lw=1.6)
        if trial['status'] == 'SELF_DECLARED_CONVERGENCE':
            ax_words.scatter(xs[-1], ys[-1], marker='s', color=color, s=42, zorder=4)
            if ds: ax_distance.scatter(xs[-1], ds[-1], marker='s', color=color, s=42, zorder=4)
            ax_origin.scatter(xs[-1], origins[-1], marker='s', color=color, s=42, zorder=4)
    for ax in (ax_words, ax_distance, ax_origin):
        ax.grid(axis='y', color='#E9ECEF', linewidth=.8)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_xlabel('Completed review')
        ax.tick_params(colors='#434A52')
        ax.spines[['left', 'bottom']].set_color('#ADB5BD')
    ax_words.set_title('B  Document length after editing', loc='left', pad=19, fontweight='bold')
    ax_words.set_ylabel('Words')
    ax_distance.set_title('C  Consecutive lexical change', loc='left', pad=19, fontweight='bold')
    ax_distance.set_ylabel('Normalized word edit distance')
    ax_distance.set_ylim(bottom=-.009)
    ax_origin.set_title('D  Distance from starting constitution', loc='left', pad=19, fontweight='bold')
    ax_origin.set_ylabel('Normalized word edit distance')
    ax_origin.set_ylim(bottom=-.009)
    if edited:
        handles, labels = ax_words.get_legend_handles_labels()
        fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(.60, .135), fontsize=7.7,
                   frameon=False, ncol=2, handlelength=1.9, columnspacing=.8)
    else:
        for ax in (ax_words, ax_distance, ax_origin):
            ax.text(.5, .5, 'No submitted edits', ha='center', va='center', transform=ax.transAxes)
    keys = [('immediate', 'Unchanged on first review'), ('one_edit', 'One edited review, then unchanged'),
            ('multiple_edits', 'Multiple edited reviews before stopping'), ('other', 'Failure or administrative stop')]
    handles = [Line2D([], [], linestyle='', marker='o' if key != 'other' else 'X',
                      color=OUTCOME_COLORS[key], markersize=7, label=f'{label} ({counts[key]})')
               for key, label in keys if counts[key]]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.185, .135), frameon=False, fontsize=9)
    maximum = max(t['edited_reviews'] for _, t in all_trials)
    title = ('Initial screening: constitution changes were brief across varied starting documents' if maximum <= 1 else
             'Document revision across edit-only screening setups')
    fig.suptitle(title, x=.19, y=.975, ha='left', fontweight='bold', fontsize=14)
    subtitle = (f'{len(all_trials)} fixed-weight trajectories · {len(suites)} screening setups · '
                f'{sum(t["status"] == "SELF_DECLARED_CONVERGENCE" for _, t in all_trials)} unchanged-submission stops')
    fig.text(.19, .93, subtitle, color='#58616B', fontsize=10)
    fig.text(.19, .025, 'Each dot in A is one seeded trial. Panels B–D show only trajectories that edited.\nSquares mark the final unchanged submission. Textual distance does not measure substantive value change.',
             color='#58616B', fontsize=9)
    stem = output/'edit_only_screening'
    for suffix in ('png', 'svg', 'pdf'):
        fig.savefig(stem.with_suffix('.'+suffix), dpi=180, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    data = {'suites': [name for name, _ in suites], 'counts': dict(counts), 'maximum_edited_reviews': maximum,
            'trajectories': [{'suite': name, **trial} for name, trial in all_trials]}
    stem.with_suffix('.json').write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
    claim = ('None contained more than one edited review.' if maximum <= 1 else
             f'The longest observed chain contained {maximum} edited reviews.')
    additional = ''
    if counts['multiple_edits']:
        additional += f'{counts["multiple_edits"]} made multiple edited reviews before an unchanged submission. '
    if counts['other']:
        additional += f'{counts["other"]} ended through a failure or administrative limit rather than an unchanged submission. '
    caption = (f'**Figure: Edit-only constitution screening.** Each mark in the left panel represents one seeded trajectory with fixed Qwen3.5-9B weights. '
        f'Across the {len(suites)} completed screening setups shown, {counts["immediate"]} of {len(all_trials)} trajectories submitted the starting document unchanged; '
        f'{counts["one_edit"]} made edits during one review and then submitted unchanged in the next fresh conversation. {additional}{claim} '
        'Panels B–D follow only trajectories that made a submitted edit, including the final unchanged submission. '
        'Panel D measures distance from the starting document, revealing whether repeated revisions accumulate or return toward the initial wording. '
        'Review zero is the supplied initial document. Word edit distance is Levenshtein distance over whitespace-delimited words, divided by the longer document length; '
        'it measures textual change, not the importance or direction of a value change.\n\n'
        'The first two setups used the same five starting documents, with direct review versus a written appraisal before tool use. '
        'The third used concrete cases and a different mix of documents, including agency- and care-emphasizing charters. '
        + ('The fourth asked for comparison with an alternative charter before deciding whether to edit. ' if any(name == 'screen-004' for name, _ in suites) else '') +
        'These are small exploratory comparisons with two seeds per document in the first three setups. '
        'Some design differences are bundled, so the plot does not isolate a causal effect of document length, appraisal, or case analysis. '
        'An unchanged submission is the model’s declared stopping decision; it does not establish stable underlying values. '
        'Only completed suites are included; an absent document/setup combination is shown as a dash.\n')
    if any(name == 'screen-004' for name, _ in suites):
        caption += ('\nThe purple agency-emphasis trajectory in the fourth setup made five edited reviews before stopping. '
            'Its length grew from 375 to 460 words, then returned to 376; its final normalized distance from the initial document was about 0.005. '
            'The text first incorporated more proactive protective guidance, then eventually restored a strong presumption in favor of adult agency. '
            'That return is a substantive reversal of the interim guidance, rather than simply a shorter document. '
            'However, the five edited reviews are not five independent changes of values: some intervening movement reflects sentence reordering or operational clarification. '
            'A separate care-emphasis trajectory in the fourth setup shifted toward an agency-first default in one review and then stopped. '
            'These distinctions come from reading the saved diffs; lexical distances alone cannot establish them.\n')
    stem.with_suffix('.caption.md').write_text(caption)
    return {'figure': str(stem.with_suffix('.png')), 'counts': dict(counts), 'maximum_edited_reviews': maximum}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', default='reports/03_exploration/figures')
    parser.add_argument('--suites', nargs='+', help='Explicit completed suite folder names; default: all completed screen-* suites')
    args = parser.parse_args()
    print(json.dumps(render(args.root, args.output, args.suites), indent=2))
