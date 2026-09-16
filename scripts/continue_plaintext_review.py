#!/usr/bin/env python3
"""Explicitly labeled continuation of one failed, prose-only review.

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
    before, after = dict(prior), dict(config)
    for item in (before, after):
        for key in ('run_label', 'protocol_version', 'note'):
            item.pop(key, None)
        item['review'] = dict(item['review'])
        item['review'].pop('max_plaintext_reminders', None)
    if before != after or config['review'].get('max_plaintext_reminders') != 1:
        raise ValueError('This continuation changes only the bounded reminder rule')
    if state['status'] != 'EDITING_FAILURE' or state['phase'] != 'review':
        raise ValueError('Parent must have a failed review, not convergence')
    n = state['completed_rounds'] + 1
    source = parent / f'round_{n:03d}'
    failed = json.loads((source / 'review.json').read_text())
    records = [json.loads(x) for x in (source / 'generations.jsonl').read_text().splitlines()]
    if len(records) != 1 or failed['tool_call_count'] or failed['content_changed']:
        raise ValueError('Only one prose-only generation with no tool effects is supported')
    replay = records[0]
    if replay['finish_reason'] != 'stop' or not replay['text'].strip():
        raise ValueError('Cannot replay a truncated or empty response')
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
                 parent_started_epoch=state['started_epoch'], started_epoch=time.time(),
                 current_constitution=str(root / f'C_{n-1:03d}.md'))
    state['failures'].append({'phase':'review', 'type':'PreservedParentEditingFailure',
                             'source':str(source), 'message':failed['failure_reason']})
    write_json(root / 'config.json', config)
    write_json(root / 'state.json', state)
    receipt = {'parent_run':str(parent), 'parent_status':'EDITING_FAILURE',
               'inherited_completed_rounds':n-1, 'continued_review':n,
               'current_checkpoint':state['current_checkpoint'],
               'replayed_generation':str(source / 'generations.jsonl'),
               'replayed_seed':replay['generation_seed'],
               'continuation_seed':replay['generation_seed'] + 1,
               'fresh_review_seed':config['review']['seed'],
               'change':'One bounded neutral tool-completion reminder; no training or decision resampling.',
               'inherited_weights':'Referenced in parent run; metadata/data copied without weights.'}
    write_json(root / 'branch.json', receipt)
    return state, replay, receipt


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
    state, replay, receipt = prepare(args.parent, args.run, config)
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
                           initial_constitution=(root / 'C_000.md').read_text(), replay_generation=replay)
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
