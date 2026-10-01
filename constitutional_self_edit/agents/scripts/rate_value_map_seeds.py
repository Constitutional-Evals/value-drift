#!/usr/bin/env python3
"""Rate the value-map seeds on the twelve v3 axes, three independent times each.

Places the seven value_map seeds and the five original elicitation seeds in the
extended axis space, and measures rater test-retest spread from the repeats.
Each repetition uses its own call directory so the replay cache cannot collapse
independent ratings into one.

Usage: python3 agents/scripts/rate_value_map_seeds.py [--reps 3] [--rater gpt6_luna]
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elicit.core import Client, Ledger, save  # noqa: E402
from elicit.run import BUDGET_USD, RUNS  # noqa: E402
from selfhost_v3 import RATE_AXES, RATE_PROMPT  # noqa: E402

OUT = ROOT / 'runs' / 'selfhost' / 'positions_seeds'

SEEDS = {
    # the seven value-map seeds
    'claude_derived': 'constitutions/value_map/claude_derived.md',
    'openai_spec_derived': 'constitutions/value_map/openai_spec_derived.md',
    'animal_welfare': 'constitutions/value_map/animal_welfare.md',
    'flourishing': 'constitutions/value_map/flourishing.md',
    'eb_kindness': 'constitutions/value_map/eb_kindness.md',
    'eb_conservatism': 'constitutions/value_map/eb_conservatism.md',
    'eb_deep_ecology': 'constitutions/value_map/eb_deep_ecology.md',
    # the five original seeds, for a common frame
    'broad_draft': 'constitutions/exploration/sparse.md',
    'deferential': 'constitutions/elicitation/deferential.md',
    'autonomous': 'constitutions/elicitation/autonomous.md',
    'protective': 'constitutions/elicitation/protective.md',
    'libertarian': 'constitutions/elicitation/libertarian.md',
}


def rate(client, rater, name, text, rep):
    out = OUT / f'{name}.rep{rep}.json'
    if out.exists():
        return json.loads(out.read_text())
    axes = '\n'.join(f'- "{k}": {v}' for k, v in RATE_AXES.items())
    prompt = RATE_PROMPT.format(doc=text.strip(), axes=axes)
    for attempt in range(3):
        res = client.complete(rater, [{'role': 'user', 'content': prompt}], None,
                              OUT / 'calls' / f'{name}_rep{rep}_{attempt}',
                              thinking=True, max_tokens=6000,
                              extra={'response_format': {'type': 'json_object'}})
        t = res['choices'][0]['message'].get('content') or ''
        try:
            d = json.loads(t[t.index('{'):t.rindex('}') + 1])
            d['ratings'] = {k: int(d['ratings'][k]) for k in RATE_AXES}
            assert all(1 <= v <= 7 for v in d['ratings'].values())
            d.update(rater=rater, seed=name, rep=rep)
            save(out, d)
            return d
        except (ValueError, KeyError, TypeError, AssertionError):
            continue
    raise RuntimeError(f'unparseable rating for {name} rep{rep}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--rater', default='gpt6_luna')
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()

    missing = [n for n, p in SEEDS.items() if not (ROOT / p).exists()]
    if missing:
        raise SystemExit(f'missing seed files: {missing}')
    texts = {n: (ROOT / p).read_text() for n, p in SEEDS.items()}
    jobs = [(n, r) for n in SEEDS for r in range(1, args.reps + 1)]
    todo = [(n, r) for n, r in jobs if not (OUT / f'{n}.rep{r}.json').exists()]
    print(f'{len(SEEDS)} documents x {args.reps} reps = {len(jobs)} ratings '
          f'({len(todo)} to fetch) with {args.rater}, {len(RATE_AXES)} axes')
    if not todo:
        print('all cached')
        return

    models = json.loads((ROOT / 'configs' / 'elicitation' / 'models.json').read_text())
    client = Client(Ledger(RUNS / 'ledger.json', BUDGET_USD), models)
    ok = fail = 0
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(rate, client, args.rater, n, texts[n], r): (n, r) for n, r in todo}
        for f in as_completed(futs):
            try:
                f.result(); ok += 1
            except Exception as e:
                fail += 1
                print('ERROR', futs[f], repr(e)[:160])
    print(f'done: {ok} ok, {fail} failed')


if __name__ == '__main__':
    main()
