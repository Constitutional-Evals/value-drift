#!/usr/bin/env python3
"""Does writing the constitution from scratch give a result that depends on the model rather than the sample?

Reads the pilot (agents/scripts/self_draft_pilot.py, rate_constitutions.py, embed_constitutions.py) and
measures distances between documents two ways:
    embedding  cosine distance between Qwen3-Embedding-8B vectors
    ratings    mean absolute difference over stage 07's 12 axes (each document's two ratings averaged)
For each model and K (1 = a single draft; 3, 5, 10 = consolidations of K drafts, three orders x three runs):
    within        mean distance between two documents of the same model and K
    same drafts   (K >= 3) the same drafts consolidated in different orders
    other drafts  (K >= 3) consolidations of different runs' drafts
    between       mean distance between a document of each model
    separation    between / within (both models' within averaged)
    accuracy      nearest-centroid accuracy at telling the writer from the document, leaving the document's run out
    to C_001      mean distance to C_001 (what the OCT model was trained on); also to C_000
And the replicate reviews of C_001 per model, measured as in edit_sizes.py.

    python3 agents/scripts/self_draft_analysis.py --pilot runs/self-draft/pilot --figures reports/11_self_draft/figures
"""
import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'agents' / 'scripts'))
from edit_sizes import measure  # noqa: E402
from selfhost_v3 import RATE_AXES  # noqa: E402

MODELS = ('base', 'oct')
KS = (1, 3, 5, 10)
LABELS = {'base': 'Untrained', 'oct': 'OCT (DPO + SFT)'}


def condition(name):
    """'oct/run2/consolidations/k05_order3' -> ('oct', 'run2', 5, 3); drafts have K = 1 and no order."""
    parts = name.split('/')
    if parts[0] not in MODELS:
        return None
    if parts[2] == 'drafts':
        return parts[0], parts[1], 1, None
    k, order = parts[3].split('_order')
    return parts[0], parts[1], int(k[1:]), int(order)


def load(pilot):
    embeddings = json.loads((pilot / 'embeddings' / 'embeddings.json').read_text())['vectors']
    ratings = {}
    for line in (pilot / 'ratings' / 'ratings.jsonl').read_text().splitlines():
        row = json.loads(line)
        ratings.setdefault(row['name'], []).append([row['ratings'][a] for a in RATE_AXES])
    return embeddings, ratings


def mean(values):
    values = list(values)
    return statistics.mean(values) if values else float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pilot', default='runs/self-draft/pilot')
    ap.add_argument('--figures')
    args = ap.parse_args()
    pilot = ROOT / args.pilot
    embeddings, ratings = load(pilot)
    rating = {n: [mean(col) for col in zip(*rs)] for n, rs in ratings.items()}
    distance = {
        'embedding': lambda a, b: 1 - sum(x * y for x, y in zip(embeddings[a], embeddings[b])),
        'ratings': lambda a, b: mean(abs(x - y) for x, y in zip(rating[a], rating[b])),
    }
    docs = {n: condition(n) for n in embeddings if condition(n)}
    group = lambda m, k: [n for n, c in docs.items() if c[0] == m and c[2] == k]
    out = {'rater_noise': mean(mean(abs(x - y) for x, y in zip(*rs[:2])) for rs in ratings.values() if len(rs) >= 2),
           'rater_exact_agreement': mean(mean(x == y for x, y in zip(*rs[:2])) for rs in ratings.values() if len(rs) >= 2),
           'conditions': []}
    for kind, dist in distance.items():
        for k in KS:
            row = {'measure': kind, 'k': k}
            for m in MODELS:
                names = group(m, k)
                pairs = list(itertools.combinations(names, 2))
                row[f'n_{m}'] = len(names)
                row[f'within_{m}'] = mean(dist(a, b) for a, b in pairs)
                if k > 1:
                    row[f'same_drafts_{m}'] = mean(dist(a, b) for a, b in pairs if docs[a][1] == docs[b][1])
                    row[f'other_drafts_{m}'] = mean(dist(a, b) for a, b in pairs if docs[a][1] != docs[b][1])
                row[f'to_C001_{m}'] = mean(dist(n, 'C_001') for n in names)
                row[f'to_C000_{m}'] = mean(dist(n, 'C_000') for n in names)
            row['between'] = mean(dist(a, b) for a in group('base', k) for b in group('oct', k))
            row['separation'] = row['between'] / mean(row[f'within_{m}'] for m in MODELS)
            # Nearest centroid, leaving out the document's own run (its siblings share drafts or a run seed).
            correct = []
            for n in group('base', k) + group('oct', k):
                m, run = docs[n][0], docs[n][1]
                scores = {}
                for other in MODELS:
                    pool = [x for x in group(other, k) if not (other == m and docs[x][1] == run)]
                    scores[other] = mean(dist(n, x) for x in pool)
                correct.append(min(scores, key=scores.get) == m)
            row['accuracy'] = mean(correct)
            out['conditions'].append(row)

    out['documents'] = {}
    for m in MODELS:
        for k in KS:
            results = [json.loads((pilot / n / 'result.json').read_text()) for n in group(m, k)]
            out['documents'][f'{m}_k{k}'] = {
                'n': len(results), 'words': mean(r['words'] for r in results),
                'words_sd': statistics.stdev([r['words'] for r in results]) if len(results) > 1 else 0,
                'resampled': sum(sum(r['resampled']) if isinstance(r['resampled'], list) else r['resampled'] for r in results),
                'cut_off': sum((r.get('finish_reason') or (r.get('finish_reasons') or [''])[-1]) == 'length' for r in results)}
    out['reviews'] = {}
    for m in MODELS:
        rows = []
        for d in sorted((pilot / m / 'reviews').glob('rep_*')):
            result = json.loads((d / 'result.json').read_text())
            if result['status'] == 'EDITED':
                rows.append(measure((d / 'input.md').read_text(), (d / 'output.md').read_text()))
            else:
                rows.append({'words_after': None, 'changed': 0.0, 'added': 0, 'removed': 0, 'paragraphs_edited': 0,
                             'status': result['status']})
        out['reviews'][m] = rows
    (pilot / 'analysis.json').write_text(json.dumps(out, indent=1) + '\n')
    print(report(out))
    (pilot / 'analysis.md').write_text(report(out) + '\n')
    if args.figures:
        plot(out, ROOT / args.figures)


def report(out):
    lines = [f"Rater noise: two ratings of the same document differ by {out['rater_noise']:.2f} points per axis "
             f"on average ({100 * out['rater_exact_agreement']:.0f}% of axes identical).", '']
    head = ['measure', 'K', 'within untrained', 'within OCT', 'same drafts (U/O)', 'other drafts (U/O)', 'between',
            'separation', 'accuracy', 'to C_001 (U/O)', 'to C_000 (U/O)']
    lines += ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    f = lambda x: f'{x:.3f}' if x == x else '-'
    for r in out['conditions']:
        pair = lambda key: f"{f(r.get(key + '_base', float('nan')))} / {f(r.get(key + '_oct', float('nan')))}"
        lines.append('| ' + ' | '.join([r['measure'], str(r['k']), f(r['within_base']), f(r['within_oct']),
                                        pair('same_drafts'), pair('other_drafts'), f(r['between']),
                                        f'{r["separation"]:.2f}', f'{100 * r["accuracy"]:.0f}%', pair('to_C001'),
                                        pair('to_C000')]) + ' |')
    lines += ['', '| documents | n | words (sd) | resampled | cut off |', '|---|---|---|---|---|']
    for key, d in out['documents'].items():
        lines.append(f"| {key} | {d['n']} | {d['words']:.0f} ({d['words_sd']:.0f}) | {d['resampled']} | {d['cut_off']} |")
    lines += ['', 'Replicate reviews of C_001 (share of input changed, words after):']
    for m, rows in out['reviews'].items():
        changed = [100 * r['changed'] for r in rows]
        lines.append(f"- {LABELS[m]}: " + ', '.join(f"{c:.0f}%" for c in changed) +
                     f" (mean {mean(changed):.0f}%); words after: " + ', '.join(str(r['words_after']) for r in rows))
    return '\n'.join(lines)


def plot(out, figures):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from plot_sft_epochs import BLUE, INK2, ORANGE, setup_style
    setup_style()
    figures.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    for ax, kind, title in zip(axes, ('embedding', 'ratings'), ('Embedding distance (cosine)', 'Rating distance (points per axis)')):
        rows = [r for r in out['conditions'] if r['measure'] == kind]
        x = list(range(len(rows)))
        for m, color in (('base', BLUE), ('oct', ORANGE)):
            ax.plot(x, [r[f'within_{m}'] for r in rows], color=color, lw=2, marker='o', ms=6, label=f'Within: {LABELS[m]}')
            ax.plot(x[1:], [r[f'same_drafts_{m}'] for r in rows[1:]], color=color, lw=0, marker='s', ms=6, mfc='none',
                    label=f'Same drafts, other order: {LABELS[m]}')
        ax.plot(x, [r['between'] for r in rows], color=INK2, lw=2, ls='--', marker='o', ms=6, label='Between models')
        ax.set_xticks(x, [f'K={r["k"]}' for r in rows])
        ax.set_title(title)
        ax.set_ylim(bottom=0)
    # Two documents' averaged ratings (two ratings each) differ by about rater_noise / sqrt(2) even when identical.
    floor = out['rater_noise'] / 2 ** 0.5
    axes[1].axhline(floor, color=INK2, lw=1, ls=':')
    axes[1].annotate('rater noise', (len(rows) - 1, floor), xytext=(0, -12), textcoords='offset points',
                     ha='right', fontsize=8.5, color=INK2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=3, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle('Constitutions written from scratch: spread within each model and distance between models, by K',
                 x=0.01, ha='left', fontsize=12, fontweight='semibold')
    fig.tight_layout(rect=(0, 0.14, 1, 0.97))
    for ext in ('png', 'pdf'):
        fig.savefig(figures / f'k_comparison.{ext}', dpi=200, bbox_inches='tight')


if __name__ == '__main__':
    main()
