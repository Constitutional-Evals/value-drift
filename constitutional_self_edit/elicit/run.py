#!/usr/bin/env python3
"""Run an elicitation plan (editing only; no training).

A plan crosses models x arms x starting constitutions x replicates. With
"generations" > 1 each trial becomes a chain: the submitted document of one
review is the input to the next fresh review. "chain_stop" is "unchanged"
(stop at the first unchanged submission) or "never" (run all generations).

Usage: python3 -m elicit.run --plan configs/elicitation/plans/prompt-screen.json [--workers 8] [--dry]
"""
from __future__ import annotations

import argparse
import itertools
import random
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elicit.core import Client, Ledger, run_review, save  # noqa: E402

RUNS = ROOT / 'runs' / 'elicit'
BUDGET_USD = 60.0


def trials(plan):
    for model, (arm_name, arm), (doc_name, doc), rep in itertools.product(
            plan['models'], plan['arms'].items(), plan['constitutions'].items(), range(1, plan['reps'] + 1)):
        spec = {'name': arm_name, **arm}
        yield {'label': f'{model}__{arm_name}__{doc_name}__r{rep}', 'model': model, 'arm': spec,
               'doc_name': doc_name, 'doc': doc, 'rep': rep}


def run_trial(client, batch, plan, t):
    directory = batch / t['label']
    text = (ROOT / t['doc']).read_text()
    rows = []
    for g in range(1, plan.get('generations', 1) + 1):
        row = run_review(client, directory / f'gen_{g:02d}', t['model'], t['arm'], text,
                         provenance='initial' if g == 1 else 'previous')
        row.update(generation=g, doc_name=t['doc_name'], rep=t['rep'], label=t['label'])
        rows.append(row)
        print(json.dumps({'label': t['label'], 'gen': g, 'status': row['status'], 'failure': row['failure'],
                          'words': f"{row['words_before']}->{row['words_after']}", 'invalid': row['invalid_calls'],
                          'cost': row['cost']}), flush=True)
        if row['status'] == 'FAILURE':
            break
        if row['status'] == 'UNCHANGED' and plan.get('chain_stop', 'unchanged') == 'unchanged':
            break
        text = (directory / f'gen_{g:02d}' / 'output.md').read_text()
    save(directory / 'chain.json', rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    models = json.loads((ROOT / 'configs' / 'elicitation' / 'models.json').read_text())
    batch = RUNS / plan['label']
    if (batch / 'plan.json').exists():
        old = json.loads((batch / 'plan.json').read_text())
        if old != plan:
            raise SystemExit('plan changed for existing batch; use a new label')
    todo = list(trials(plan))
    random.Random(0).shuffle(todo)  # spread load across models/providers
    print(f"{plan['label']}: {len(todo)} trials x up to {plan.get('generations', 1)} generations")
    if args.dry:
        for t in todo[:5]:
            print(t['label'])
        return
    save(batch / 'plan.json', plan)
    ledger = Ledger(RUNS / 'ledger.json', BUDGET_USD)
    client = Client(ledger, models)
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(run_trial, client, batch, plan, t): t for t in todo}
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:
                print(json.dumps({'label': futs[f]['label'], 'crash': repr(e)[:300]}), flush=True)
    print(f'ledger total: ${ledger.total():.4f}')


if __name__ == '__main__':
    main()
