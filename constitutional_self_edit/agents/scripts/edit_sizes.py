#!/usr/bin/env python3
"""How much each review changes its constitution: trained models after round 1 against inference-only chains.

Every review here is Qwen3.8 27B with the reflect arm and v3 prompts, sampled with the model's defaults
(temperature 1.0, top-p 0.95, top-k 20). Edit size is measured on words, with difflib:
    removed, added   words deleted from / inserted into the input
    changed          (removed + added) / input words
    kept             share of input words left in place
    paragraphs       input paragraphs not kept verbatim

Groups:
    untrained, C_000          first reviews of the broad draft (prompt screen, chain generation 1, OCT run 2's round 1)
    untrained, broad gen N    broad-draft chains, generation N (the model reviewing its own previous output)
    untrained, all seeds gen N  every reflect chain of stage 07, generation N
    trained, C_001            OCT and MSM models after round 1 reviewing C_001

Usage (from constitutional_self_edit/): python3 agents/scripts/edit_sizes.py --out runs/oct-loop/eval/edit_sizes
"""
import argparse
import csv
import difflib
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELFHOST = ROOT / 'runs/selfhost'
TRAINED = {
    'OCT DPO': 'runs/oct-loop/eval/round_001_run2_sft_epochs/review_dpo/review',
    'OCT SFT epoch 1': 'runs/oct-loop/oct-qwen38-27b-broad-run2/round_002/review',
    'OCT SFT epoch 2': 'runs/oct-loop/eval/round_001_run2_sft_epochs/review_e2/review',
    'OCT SFT epoch 3': 'runs/oct-loop/eval/round_001_run2_sft_epochs/review_e3/review',
    'MSM+AFT (flawed)': 'runs/msm-loop/msm-qwen38-27b-broad-pilot/round_002/review',
    'MSM+AFT (corrected)': 'runs/msm-loop/eval/pilot/aft_fixed/review/review',
}


def measure(before, after):
    a, b = before.split(), after.split()
    removed = added = kept = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'equal':
            kept += i2 - i1
        else:
            removed += i2 - i1
            added += j2 - j1
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', before) if p.strip()]
    return {'words_before': len(a), 'words_after': len(b), 'removed': removed, 'added': added,
            'changed': (removed + added) / len(a), 'kept': kept / len(a),
            'paragraphs_edited': sum(p not in after for p in paragraphs), 'paragraphs': len(paragraphs)}


def review(directory):
    directory = Path(directory)
    result = json.loads((directory / 'result.json').read_text())
    if result['status'] != 'EDITED':
        return None
    return measure((directory / 'input.md').read_text(), (directory / 'output.md').read_text())


def rows():
    # Inference-only: every uncapped reflect review in stage 07, including the partial reps 3-6.
    for directory in sorted(SELFHOST.glob('selfhost-v3*/qwen38_27b_vllm__reflect__*')):
        seed, rep = re.fullmatch(r'qwen38_27b_vllm__reflect__(.+)__r(\d+)', directory.name).groups()
        screen = directory.parent.name == 'selfhost-v3'
        for gen in sorted(directory.glob('gen_*')):
            if (gen / 'result.json').exists() and (m := review(gen)):
                yield {'group': 'untrained', 'model': 'Qwen3.8 27B', 'seed': seed, 'chain': f'{directory.parent.name}/r{rep}',
                       'generation': int(gen.name[4:]), 'source': 'prompt screen' if screen else 'chain', **m}
    if m := review(ROOT / 'runs/oct-loop/oct-qwen38-27b-broad-run2/round_001/review'):
        yield {'group': 'untrained', 'model': 'Qwen3.8 27B', 'seed': 'broad_draft', 'chain': 'oct run 2',
               'generation': 1, 'source': 'OCT run 2 round 1', **m}
    for name, path in TRAINED.items():
        if m := review(ROOT / path):
            yield {'group': 'trained', 'model': name, 'seed': 'broad_draft', 'chain': 'oct/msm run', 'generation': 2,
                   'source': 'after round 1', **m}


def summarize(label, items):
    get = lambda key: [r[key] for r in items]
    mean = lambda key: statistics.mean(get(key))
    sd = lambda key: statistics.stdev(get(key)) if len(items) > 1 else float('nan')
    return {'group': label, 'n': len(items),
            'words_before': round(mean('words_before')), 'words_after': round(mean('words_after')),
            'added': round(mean('added')), 'removed': round(mean('removed')),
            'changed_%': round(100 * mean('changed'), 1), 'changed_sd': round(100 * sd('changed'), 1),
            'changed_range': f"{100 * min(get('changed')):.0f}-{100 * max(get('changed')):.0f}",
            'kept_%': round(100 * mean('kept'), 1), 'paragraphs_edited': round(mean('paragraphs_edited'), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = list(rows())
    with open(out / 'reviews.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)

    untrained = [r for r in data if r['group'] == 'untrained']
    broad = [r for r in untrained if r['seed'] == 'broad_draft']
    summary = [summarize('untrained, C_000 (first reviews of the broad draft)', [r for r in broad if r['generation'] == 1])]
    summary += [summarize(f'untrained, broad-draft chains, gen {g}', [r for r in broad if r['generation'] == g])
                for g in sorted({r['generation'] for r in broad}) if g > 1]
    summary += [summarize(f'untrained, all seeds, gen {g}', [r for r in untrained if r['generation'] == g and r['source'] == 'chain'])
                for g in sorted({r['generation'] for r in untrained})]
    summary += [summarize('trained, C_001 (all six)', [r for r in data if r['group'] == 'trained'])]
    summary += [summarize(f'trained: {r["model"]}', [r]) for r in data if r['group'] == 'trained']
    (out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    keys = list(summary[0])
    lines = ['| ' + ' | '.join(keys) + ' |', '|' + '---|' * len(keys)]
    lines += ['| ' + ' | '.join(str(s[k]) for k in keys) + ' |' for s in summary]
    (out / 'summary.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
