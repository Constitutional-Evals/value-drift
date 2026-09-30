#!/usr/bin/env python3
"""Cut a smaller OCT recipe's training data out of a round generated with a larger one.

The recipes in configs/oct/ number their items so that a smaller recipe's items are the first ones
of a larger recipe's: DPO repeat k < repeats, reflection sample s < reflection_samples_per_prompt,
and conversation j < interactions_per_variant. This keeps exactly those rows of the round's
preferences.jsonl and introspection.jsonl.

Usage (from constitutional_self_edit/):
    python3 agents/scripts/oct_subset.py runs/<run>/round_001 runs/<run>-20pct/round_001 \
        --recipe configs/oct/recipe-20.json
"""
import argparse
import json
import re
from pathlib import Path


def keep(row, repeats, samples, conversations):
    """Whether a preference or introspection row belongs to the smaller recipe."""
    if 'repeat' in row:
        return row['repeat'] < repeats
    m = re.fullmatch(r'reflection-\d{2}-(\d{4})', row['id'])
    if m:
        return int(m.group(1)) < samples
    m = re.fullmatch(r'interaction-(?:free|leading)-(\d{4})', row['id'])
    if m:
        return int(m.group(1)) < conversations
    raise ValueError(f"Row {row['id']} is not from an OCT recipe; cannot place it in a subset")


def subset(rows, recipe):
    g, i = recipe['generation'], recipe['introspection']
    return [r for r in rows if keep(r, g['repeats'], i['reflection_samples_per_prompt'], i['interactions_per_variant'])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', help='round directory generated with the larger recipe')
    ap.add_argument('target', help='directory to write the subset to')
    ap.add_argument('--recipe', default='configs/oct/recipe-20.json')
    args = ap.parse_args()
    recipe = json.loads(Path(args.recipe).read_text())
    source, target = Path(args.source), Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in ('preferences.jsonl', 'introspection.jsonl'):
        rows = [json.loads(line) for line in (source / name).read_text().splitlines() if line.strip()]
        kept = subset(rows, recipe)
        (target / name).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in kept))
        counts[name] = {'source_rows': len(rows), 'subset_rows': len(kept)}
    manifest = {'source': str(source), 'recipe': args.recipe, 'counts': counts}
    (target / 'subset_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
