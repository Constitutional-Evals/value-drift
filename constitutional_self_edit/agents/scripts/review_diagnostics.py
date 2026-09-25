#!/usr/bin/env python3
"""Bounded review-only discovery: fresh sessions, frozen inputs, no trial resampling."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from recursive_oct.backend import execute_review
from recursive_oct.editing import PROMPT_DIR, tool_schemas
from recursive_oct.model import inference_session
from recursive_oct.pipeline import write_json


def _session(checkpoint, config):
    if config.get('backend') != 'vllm':
        import torch
        torch.manual_seed(config['seed'])
    return inference_session(checkpoint, config)


def _status(review):
    return {'EDITED':'DIAGNOSTIC_EDITED', 'SELF_DECLARED_CONVERGENCE':'DIAGNOSTIC_UNCHANGED'}.get(
        review.get('status'), 'DIAGNOSTIC_REVIEW_FAILURE')


def run_diagnostics(plan_path, run_dir, *, resume=False, session_factory=None):
    """Record every scheduled attempt. Interrupted trial artifacts are never replayed."""
    plan_path, root = Path(plan_path), Path(run_dir).resolve()
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if not plan.get('frozen'):
        raise ValueError('Freeze the diagnostic plan before execution')
    schedule = plan['schedule']
    if not 1 <= len(schedule) <= 9:
        raise ValueError('The bounded diagnostic plan permits 1–9 scheduled trials')
    if any(t['condition'] not in plan['conditions'] or type(t['seed']) is not int for t in schedule):
        raise ValueError('Each trial requires a defined condition and integer seed')
    if len({(t['condition'],t['seed']) for t in schedule}) != len(schedule):
        raise ValueError('Duplicate condition/seed trials would resample the same scheduled attempt')
    base_path = Path(plan['base_config'])
    base_bytes = base_path.read_bytes()
    base = json.loads(base_bytes)
    sources = {'constitution':Path(plan['constitution']), 'recipe':Path(base['recipe_text']),
               'context':Path(plan['context_template']), 'tool_instructions':PROMPT_DIR/'tool_instructions.md',
               'selection_rule':Path(plan['selection_rule'])}
    sources.update({f'condition_{i:02d}':Path(path) for i,path in enumerate(plan['conditions'].values())})
    condition_files = {name:f'condition_{i:02d}.md' for i,name in enumerate(plan['conditions'])}
    contents = {key:path.read_bytes() for key,path in sources.items()}
    inputs = root/'inputs'
    manifest = {'sources':{key:str(path.resolve()) for key,path in sources.items()},
                'condition_files':condition_files, 'tools':tool_schemas()}
    saved = {'plan.json':plan_bytes, 'base_config.json':base_bytes,
             **{f'inputs/{key}.md':value for key,value in contents.items()},
             'inputs/manifest.json':(json.dumps(manifest,indent=2)+'\n').encode()}
    if (root/'plan.json').exists():
        if not resume:
            raise ValueError('Diagnostic run exists; use explicit --resume')
        for name,value in saved.items():
            path = root/name
            if not path.exists() or path.read_bytes() != value:
                raise ValueError(f'Diagnostic plan/base config/input changed or missing: {name}')
    else:
        if resume or (root.exists() and any(root.iterdir())):
            raise ValueError('No complete frozen snapshot for this existing diagnostic directory')
        inputs.mkdir(parents=True, exist_ok=True)
        # All bytes were read first; the plan marker is written last, before any trial.
        for name,value in saved.items():
            if name != 'plan.json':
                (root/name).write_bytes(value)
        (root/'plan.json').write_bytes(plan_bytes)
    constitution = (inputs/'constitution.md').read_text()
    recipe = (inputs/'recipe.md').read_text()
    results = []
    halted = False

    def summarize():
        result = {'kind':'review_diagnostic_only', 'label':plan.get('label'),
                  'status':'DIAGNOSTIC_COMPLETE' if len(results) == len(schedule) and not halted else 'DIAGNOSTIC_IN_PROGRESS',
                  'scheduled':len(schedule), 'attempts_recorded':len(results),
                  'training_updates':0, 'evaluations':0, 'halted_on_runtime_error':halted,
                  'counts':dict(Counter(r['diagnostic_status'] for r in results)), 'trials':results}
        write_json(root/'summary.json', result)
        return result

    factory = session_factory or _session
    summarize()
    for i, trial in enumerate(schedule, 1):
        directory = root/f'trial_{i:03d}'
        outcome_path = directory/'result.json'
        identity = {'trial':i, 'condition':trial['condition'], 'seed':trial['seed'], 'directory':str(directory)}
        if outcome_path.exists():
            result = json.loads(outcome_path.read_text())
        elif directory.exists() and any(directory.iterdir()):
            # No replay even when a model crashed before producing a generation.
            review_path = directory/'review.json'
            if review_path.exists():
                review = json.loads(review_path.read_text())
                result = {**identity, 'diagnostic_status':_status(review), 'review_status':review.get('status'),
                          'recovered_finalized_review':True}
            else:
                has_generation = (directory/'generations.jsonl').exists() and (directory/'generations.jsonl').stat().st_size > 0
                result = {**identity, 'diagnostic_status':'DIAGNOSTIC_REVIEW_FAILURE' if has_generation else 'DIAGNOSTIC_STARTUP_FAILURE',
                          'error':'Interrupted trial with artifacts and no finalized review; never resample'}
            write_json(outcome_path,result)
        else:
            # Global tool instructions are read by the renderer: reject mid-run edits.
            if any(path.read_bytes() != contents[key] for key,path in sources.items()):
                raise ValueError('Diagnostic input changed while the run was active')
            directory.mkdir(parents=True, exist_ok=True)
            config = {**base['review'], 'seed':trial['seed'],
                      'review_instructions_path':str(inputs/condition_files[trial['condition']]),
                      'context_template_path':str(inputs/'context.md')}
            # Each trial receives the same C0; its editable file cannot change the source.
            config['constitution_path'] = str(directory/'workspace'/'constitution.md')
            write_json(directory/'config.json', {'checkpoint':base['model'], 'review':config, **identity})
            started = time.time()
            runtime = {'kind':'review_diagnostic_only','started_epoch':started,'pid':os.getpid(),
                       'python':sys.version,'platform':platform.platform(),'phase':'startup'}
            write_json(directory/'runtime.json',runtime)
            try:
                context = factory(base['model'],config)
                runtime['inference_log'] = str(getattr(context,'log_path',''))
                write_json(directory/'runtime.json',runtime)
                with context as model:
                    runtime.update(phase='review', startup_metadata=getattr(model,'startup_metadata',None))
                    write_json(directory/'runtime.json',runtime)
                    review = execute_review(model,base['model'],constitution,directory,config,
                                            recipe_text=recipe,initial_constitution=constitution)
                    runtime['phase'] = 'cleanup'
                result = {**identity,'diagnostic_status':_status(review),'review_status':review.get('status'),
                          'metrics':review.get('metrics'), 'review_artifact':str(directory/'review.json')}
            except Exception as exc:
                (directory/'failure.log').write_text(traceback.format_exc())
                halted = True
                error = {'phase':runtime['phase'], 'error_type':type(exc).__name__, 'error':str(exc)}
                runtime['runtime_error'] = error
                review_path = directory/'review.json'
                if review_path.exists():
                    # Finalized observations survive a later cleanup/runtime failure.
                    review = json.loads(review_path.read_text())
                    result = {**identity,'diagnostic_status':_status(review),'review_status':review.get('status'),
                              'metrics':review.get('metrics'),'review_artifact':str(review_path),'runtime_error':error}
                else:
                    result = {**identity,'diagnostic_status':'DIAGNOSTIC_STARTUP_FAILURE' if runtime['phase']=='startup' else 'DIAGNOSTIC_REVIEW_FAILURE',
                              **error, 'runtime_error':error}
            runtime.update(finished_epoch=time.time(), elapsed_seconds=time.time()-started)
            write_json(directory/'runtime.json',runtime)
            write_json(outcome_path,result)
        results.append(result)
        summarize()
        print(json.dumps(result),flush=True)
        if halted:
            break  # Inspect infrastructure before an explicit resume skips this attempt.
    return summarize()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    result = run_diagnostics(args.plan,args.run,resume=args.resume)
    print(json.dumps(result,indent=2))
    return 0 if result['status'] == 'DIAGNOSTIC_COMPLETE' else 1


if __name__ == '__main__':
    sys.exit(main())
