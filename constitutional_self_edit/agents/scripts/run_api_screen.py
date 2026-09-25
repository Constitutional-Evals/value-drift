#!/usr/bin/env python3
"""Run a frozen batch; all batches share one cumulative OpenRouter budget."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct.api_screen import Budget, OpenRouterClient, run_review, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--root', default='runs/api-screen-20260924')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    root = Path(args.root)
    plan = json.loads(Path(args.plan).read_text())
    if not plan.get('frozen'):
        raise ValueError('Freeze the plan before dispatch')
    batch = root/plan['label']
    if (batch/'plan.json').exists() and json.loads((batch/'plan.json').read_text()) != plan:
        raise ValueError('Cannot change existing batch plan')
    save(batch/'plan.json', plan)
    budget = Budget(root/'ledger.json', 28.0)
    client = OpenRouterClient(budget, plan['models'])
    def job(item):
        directory = batch/item['label']
        initial = Path(item['constitution']).read_text()
        original = Path(item['trajectory_origin']).read_text() if item.get('trajectory_origin') else initial
        rows = []
        for index in range(1, item.get('max_reviews', 1)+1):
            row = run_review(client, directory/f'review_{index:03d}', initial, item, initial_constitution=original)
            rows.append(row)
            save(directory/'trajectory.json', {'reviews': rows, 'training_updates': 0})
            print(json.dumps({'label': item['label'], 'review': index, 'status': row['status'], 'distance': row['distance_from_previous'], 'words': row['word_count'], 'accounted_usd': round(budget.accounted(), 4)}), flush=True)
            if row['status'] != 'EDITED':
                break
            initial = (directory/f'review_{index:03d}/submitted.md').read_text()
        return {'label': item['label'], 'reviews': rows, 'training_updates': 0}
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(job, item) for item in plan['trials']]
        for future in as_completed(futures):
            results.append(future.result())
            save(batch/'summary.json', {'label': plan['label'], 'results': results, 'scheduled': len(futures)})
    key = client.get('key').get('data', {})
    save(root/(plan['label']+'-key-usage.json'), {k:key[k] for k in ('usage','usage_daily','limit','limit_remaining') if k in key})


if __name__ == '__main__':
    main()
