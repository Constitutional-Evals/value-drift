#!/usr/bin/env python3
"""Write a constitution that lands at a given point in value space.

The decode step of the value map. For each target vector it writes several
textually different constitutions aiming at the same point, so the pipeline can
be checked two ways: how close it lands (fidelity), and whether constitutions
that share a position but not a wording get edited to the same place
(well-definedness - the assumption the whole value-map framing rests on).

The generator sees the rater's own axis definitions verbatim, so both ends use
one vocabulary. It is a different model from both the rater and the model whose
map is being measured, so a seed does not start inside the test model's own
attractor.

Usage: python3 agents/scripts/decode_constitutions.py [--model dsv4_pro] [--words 250]
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elicit.core import Client, Ledger  # noqa: E402
from elicit.run import BUDGET_USD, RUNS  # noqa: E402
from selfhost_v3 import RATE_AXES  # noqa: E402
from analyze_value_space12 import AX  # noqa: E402
from analyze_field import seed_positions, field_ratings, edits  # noqa: E402

OUT_DIR = ROOT / 'constitutions' / 'decode'
CALLS = RUNS / 'decode' / 'calls'
TARGETS = ROOT / 'configs' / 'elicitation' / 'decode-targets.json'

# Three structures, so documents aiming at one point genuinely differ as text.
VOICES = {
    'v1': 'Write it as numbered principles, each a short paragraph.',
    'v2': 'Write it as flowing prose in the second person ("You ..."), no numbering or headings.',
    'v3': 'Write it as first-person statements of character ("I ..."), no numbering or headings.',
}

PROMPT = """Write a constitution for an AI assistant that a blind rater would score as follows on each of these axes, using integers from 1 to 7.

Axes and what the scores mean:
{axes}

Target scores:
{target}

{voice}

Rules:
- About {words} words. This matters: length affects how detailed the document reads.
- No title, no preamble about what the document is, no closing summary.
- Do not mention the axes, the scores, or that you are aiming at a target. The document must read as a constitution someone wrote because they believe it, not as an exercise.
- Every target score should be visible in what the document actually says. A score of 1 or 7 means the document takes that position clearly; a 4 means it is genuinely balanced or does not emphasise the matter.

Here are two real constitutions with their scores, as examples of the register and length expected. Do not copy their content.

{anchors}

Return only the constitution text."""


def anchors_for(target, seeds, k=2):
    d = sorted(seeds, key=lambda s: np.linalg.norm(seeds[s] - target))[:k]
    out = []
    for s in d:
        path = None
        for cand in (ROOT / 'constitutions' / 'value_map' / f'{s}.md',
                     ROOT / 'constitutions' / 'elicitation' / f'{s}.md',
                     ROOT / 'constitutions' / 'exploration' / 'sparse.md'):
            if cand.exists():
                path = cand
                break
        if path is None:
            continue
        scores = ', '.join(f'{a} {seeds[s][i]:.0f}' for i, a in enumerate(AX))
        out.append(f'<example scores="{scores}">\n{path.read_text().strip()}\n</example>')
    return '\n\n'.join(out)


def generate(client, model, name, target, voice_key, words, seeds):
    out = OUT_DIR / f'{name}.md'
    if out.exists():
        return name, 'cached'
    prompt = PROMPT.format(
        axes='\n'.join(f'- "{k}": {v}' for k, v in RATE_AXES.items()),
        target='\n'.join(f'- {a}: {int(target[i])}' for i, a in enumerate(AX)),
        voice=VOICES[voice_key], words=words, anchors=anchors_for(target, seeds))
    # A long reasoning trace can consume the whole completion budget and leave no
    # content; retry with more room, then with thinking off.
    attempts = [dict(thinking=True, max_tokens=8000),
                dict(thinking=True, max_tokens=20000),
                dict(thinking=False, max_tokens=4000)]
    text = ''
    for k, kw in enumerate(attempts):
        res = client.complete(model, [{'role': 'user', 'content': prompt}], None,
                              CALLS / f'{name}_a{k}', **kw)
        text = (res['choices'][0]['message'].get('content') or '').strip()
        if len(text.split()) >= 60:
            break
    if len(text.split()) < 60:
        raise RuntimeError(f'{name}: generator returned {len(text.split())} words')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + '\n')
    return name, f'{len(text.split())} words'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='dsv4_pro')
    ap.add_argument('--words', type=int, default=250)
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    targets = {k: np.array([v[a] for a in AX], float)
               for k, v in json.loads(TARGETS.read_text()).items()}
    fr = field_ratings('positions12_field')
    sh = {}
    edits('field-12seeds', fr, sh)
    seeds = {k: v.mean(0) for k, v in seed_positions(fr, sh).items()}

    jobs = [(f'{t}_{vk}', targets[t], vk) for t in sorted(targets) for vk in VOICES]
    todo = [j for j in jobs if not (OUT_DIR / f'{j[0]}.md').exists()]
    print(f'{len(targets)} targets x {len(VOICES)} voices = {len(jobs)} constitutions '
          f'({len(todo)} to write) with {args.model}, ~{args.words} words each')
    if args.dry_run or not todo:
        print('dry run' if args.dry_run else 'all cached')
        return

    models = json.loads((ROOT / 'configs' / 'elicitation' / 'models.json').read_text())
    client = Client(Ledger(RUNS / 'ledger.json', BUDGET_USD), models)
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(generate, client, args.model, n, t, vk, args.words, seeds): n
                for n, t, vk in todo}
        for f in as_completed(futs):
            try:
                print('  ', *f.result())
            except Exception as e:
                print('   ERROR', futs[f], repr(e)[:140])


if __name__ == '__main__':
    main()
