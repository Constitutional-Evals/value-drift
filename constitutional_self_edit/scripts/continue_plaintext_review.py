#!/usr/bin/env python3
"""Explicitly labeled continuation of a review interrupted by prose-only output.

Completed weights/data remain in the parent run. The saved public response is
replayed once, never sampled again. Later reviews use ordinary fresh contexts.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recursive_oct.backend import ExperimentBackend, execute_review
from recursive_oct.budget import can_afford
from recursive_oct.model import inference_session
from recursive_oct.pipeline import run_trajectory, write_json
from recursive_oct.protocol import snapshot_protocol_inputs


def prepare(parent, root, config):
    parent, root = Path(parent), Path(root)
    if root.exists():
        raise ValueError('Branch already exists; never repeat its bootstrap review')
    state = json.loads((parent / 'state.json').read_text())
    prior = json.loads((parent / 'config.json').read_text())
    prior_structured = prior['review'].get('structured_tool_calls', False)
    new_structured = config['review'].get('structured_tool_calls', False)
    structured_added = new_structured is True and prior_structured is False
    before, after = dict(prior), dict(config)
    for item in (before, after):
        for key in ('run_label', 'protocol_version', 'note'):
            item.pop(key, None)
        item['review'] = dict(item['review'])
        item['review'].pop('max_plaintext_reminders', None)
        item['review'].pop('structured_tool_calls', None)
    reminder_increment = 0 if structured_added else 1
    if (before != after or (new_structured != prior_structured and not structured_added)
            or config['review'].get('max_plaintext_reminders') != prior['review'].get('max_plaintext_reminders', 0) + reminder_increment):
        raise ValueError('Only one extra reminder or syntax-constrained tool mode may change')
    if state['status'] != 'EDITING_FAILURE' or state['phase'] != 'review':
        raise ValueError('Parent must have a failed review, not convergence')
    n = state['completed_rounds'] + 1
    source = parent / f'round_{n:03d}'
    failed = json.loads((source / 'review.json').read_text())
    records = [json.loads(x) for x in (source / 'generations.jsonl').read_text().splitlines()]
    if not records or failed.get('submitted') or failed['failure_reason'] != 'Missing or incomplete tool call':
        raise ValueError('Require an unsubmitted review ending in missing tool output')
    if any(r['finish_reason'] != 'stop' or not r['text'].strip() for r in records):
        raise ValueError('Cannot replay truncated or empty responses')
    seeds = [r['generation_seed'] for r in records]
    if seeds != list(range(seeds[0], seeds[0] + len(records))):
        raise ValueError('Replay generation seeds must be contiguous')
    snapshot_protocol_inputs(root, config)
    for path in parent.glob('C_*.md'):
        shutil.copy2(path, root / path.name)
    for path in parent.glob('eval_*.jsonl*'):
        if path.is_file():
            shutil.copy2(path, root / path.name)
    for i in range(1, n):
        previous = parent / f'round_{i:03d}'
        for path in previous.rglob('*'):
            if path.is_file() and path.suffix in {'.json', '.jsonl', '.md', '.diff', '.jinja', '.txt', '.log'}:
                target = root / previous.name / path.relative_to(previous)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    shutil.copytree(source, root / 'preserved_attempts' / source.name)
    if len(state['reviews']) != n:
        raise ValueError('Unexpected review history length')
    state['reviews'] = state['reviews'][:-1]
    state.update(status='RUNNING', phase='review', parent_run=str(parent),
                 parent_started_epoch=state['started_epoch'], started_epoch=time.time(), updated_epoch=time.time(),
                 current_constitution=str(root / f'C_{n-1:03d}.md'))
    state['failures'].append({'phase':'review', 'type':'PreservedParentEditingFailure',
                             'source':str(source), 'message':failed['failure_reason']})
    write_json(root / 'config.json', config)
    write_json(root / 'state.json', state)
    receipt = {'parent_run':str(parent), 'parent_status':'EDITING_FAILURE',
               'inherited_completed_rounds':n-1, 'continued_review':n,
               'current_checkpoint':state['current_checkpoint'],
               'replayed_generations':str(source / 'generations.jsonl'),
               'replayed_seeds':seeds,
               'continuation_seed':seeds[-1] + 1,
               'fresh_review_seed':config['review']['seed'],
               'change':('Syntax-constrained JSON tool mode; model retains free choice of edit or finish.' if structured_added else
                         'One additional bounded neutral tool-completion reminder; no training or decision resampling.'),
               'inherited_weights':'Referenced in parent run; metadata/data copied without weights.'}
    write_json(root / 'branch.json', receipt)
    return state, records, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--ledger', default='runs/spending.json')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if not config.get('frozen') or config['condition'] != 'full':
        raise ValueError('Require a frozen full-information branch')
    state, records, receipt = prepare(args.parent, args.run, config)
    root = Path(args.run)
    if args.prepare_only:
        print(json.dumps(receipt, indent=2)); return
    review_config = dict(config['review'], seed=receipt['continuation_seed'])
    output = root / f"round_{receipt['continued_review']:03d}"
    constitution = Path(state['current_constitution']).read_text()
    try:
        with inference_session(state['current_checkpoint'], review_config) as model:
            execute_review(model, state['current_checkpoint'], constitution, output, config['review'],
                           recipe_text=Path(config['recipe_text']).read_text(),
                           initial_constitution=(root / 'C_000.md').read_text(), replay_generations=records)
    except Exception as exc:
        output.mkdir(parents=True, exist_ok=True)
        (output / 'bootstrap_failure.log').write_text(traceback.format_exc())
        write_json(output / 'review.json', {'status':'EDITING_FAILURE', 'text':constitution,
                                          'failure_reason':f'Continuation failed: {type(exc).__name__}: {exc}'})
    def budget_ok():
        return can_afford(json.loads(Path(args.ledger).read_text()), time.time(), config.get('stage_cost_margin_usd', 2))
    result = run_trajectory(root, config, ExperimentBackend(config), resume=True, budget_ok=budget_ok)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
