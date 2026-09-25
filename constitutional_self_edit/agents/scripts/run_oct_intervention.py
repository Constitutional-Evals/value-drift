#!/usr/bin/env python3
"""One fixed-constitution full-parameter OCT intervention, not a recursive run.

The researcher supplies the constitution before this intervention. No review is
performed here, and a prior edit-only trajectory is never reopened. Both training
stages retain the existing OCT implementation and its completed-artifact caches.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct.backend import ExperimentBackend
from recursive_oct.generation import generate_introspection
from recursive_oct.judging import RUBRIC_PATH, SYSTEM_PATH
from recursive_oct.pipeline import write_json
from recursive_oct.train import read_jsonl

STAGES = ('baseline', 'preferences', 'dpo', 'introspection', 'sft', 'evaluation')
INPUT_KEYS = ('constitution', 'train_prompts', 'eval_prompts', 'introspection_prompts')


class InterventionBackend(ExperimentBackend):
    def introspection(self, checkpoint, output):
        return generate_introspection(checkpoint, read_jsonl(self.config['introspection_prompts']),
            output, self.config['introspection'], constitution=self.initial)


def prepare(config_path, root, resume):
    config = json.loads(Path(config_path).read_text())
    if not config.get('frozen'):
        raise ValueError('Require frozen=true before the intervention')
    for key in ('model', 'teacher', 'dpo', 'sft', *INPUT_KEYS):
        if key not in config:
            raise ValueError(f'Missing configuration field: {key}')
    saved = root/'config.json'
    if saved.exists():
        if not resume or json.loads(saved.read_text()) != config:
            raise ValueError('Existing intervention requires --resume and unchanged configuration')
        resolved = json.loads((root/'resolved_config.json').read_text())
        if config.get('judge'):
            for name, path in [('judge_system.md', SYSTEM_PATH), ('judge_rubric.json', RUBRIC_PATH)]:
                if (root/'inputs'/name).read_bytes() != path.read_bytes():
                    raise ValueError('Fixed judge instructions changed; do not silently resume')
        return config, resolved
    if resume or (root.exists() and any(root.iterdir())):
        raise ValueError('New intervention requires a new or empty output directory')
    sources = {key: Path(config[key]) for key in INPUT_KEYS}
    if config.get('recipe_text'):
        sources['recipe_text'] = Path(config['recipe_text'])
    contents = {key: source.read_bytes() for key, source in sources.items()}
    (root/'inputs').mkdir(parents=True, exist_ok=True)
    resolved = dict(config)
    manifest = {'kind': 'training_intervention', 'inputs': {},
                'method': 'One full-parameter DPO stage followed by introspective full-parameter SFT.',
                'review_performed': False, 'optimizer_state_policy': 'Reset between stages; retain updated weights.',
                'resume_note': 'Completed generation IDs and training stages are reused. Incomplete training restarts its stage from its input checkpoint; optimizer steps are not checkpoint-resumed. Newly generated rows after interruption may use a restarted sampling sequence.'}
    for key, source in sources.items():
        destination = root/'inputs'/(key + (source.suffix or '.txt'))
        destination.write_bytes(contents[key])
        resolved[key] = str(destination)
        manifest['inputs'][key] = {'source': str(source), 'snapshot': str(destination)}
    if config.get('judge'):
        shutil.copyfile(SYSTEM_PATH, root/'inputs/judge_system.md')
        shutil.copyfile(RUBRIC_PATH, root/'inputs/judge_rubric.json')
    write_json(root/'manifest.json', manifest)
    write_json(root/'resolved_config.json', resolved)
    write_json(saved, config)
    return config, resolved


def training_receipt(checkpoint, stage, input_checkpoint):
    receipt = json.loads((Path(checkpoint)/'training_complete.json').read_text())
    if (receipt.get('training') != 'full_parameter' or receipt.get('stage') != stage
            or receipt.get('input_checkpoint') != str(input_checkpoint)):
        raise ValueError('Training receipt does not confirm the required full-parameter stage and input weights')
    return receipt


def run(config_path, output, *, resume=False, through_stage='evaluation', backend_factory=None):
    if through_stage not in STAGES:
        raise ValueError(f'Unknown stage: {through_stage}')
    root = Path(output).resolve()
    config, resolved = prepare(config_path, root, resume)
    state_path = root/'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state['status'] == 'COMPLETE': return state
    else:
        state = {'kind': 'training_intervention', 'status': 'RUNNING', 'phase': 'baseline',
                 'input_checkpoint': config['model'], 'fixed_teacher': config['teacher'],
                 'fixed_constitution': resolved['constitution'], 'completed_stages': [],
                 'stage_records': {}, 'failures': [], 'completed_training_rounds': 0,
                 'started_epoch': time.time(), 'review_performed': False}
    backend = (backend_factory or InterventionBackend)(resolved)
    state['status'] = 'RUNNING'

    def save():
        state['updated_epoch'] = time.time()
        write_json(state_path, state)

    save()
    for stage in STAGES:
        if stage in state['completed_stages']: continue
        if STAGES.index(stage) > STAGES.index(through_stage):
            state['status'] = 'PAUSED'; state['phase'] = stage; save(); return state
        state['phase'] = stage
        save()
        started = time.monotonic()
        record = {'stage': stage, 'started_epoch': time.time()}
        try:
            if stage == 'baseline':
                backend.evaluate(config['model'], root/'eval_000.jsonl')
                record.update(checkpoint=config['model'], responses=str(root/'eval_000.jsonl'))
            elif stage == 'preferences':
                record['result'] = backend.preferences(config['model'], Path(resolved['constitution']), root/'preferences.jsonl')
            elif stage == 'dpo':
                checkpoint = backend.dpo(config['model'], root/'preferences.jsonl', root/'dpo')
                record['training'] = training_receipt(checkpoint, stage, config['model'])
                state['dpo_checkpoint'] = checkpoint
            elif stage == 'introspection':
                record['result'] = backend.introspection(state['dpo_checkpoint'], root/'introspection.jsonl')
                record['generation_checkpoint'] = state['dpo_checkpoint']
            elif stage == 'sft':
                checkpoint = backend.sft(state['dpo_checkpoint'], root/'introspection.jsonl', root/'final')
                record['training'] = training_receipt(checkpoint, stage, state['dpo_checkpoint'])
                state['final_checkpoint'] = checkpoint
                state['completed_training_rounds'] = 1
            elif stage == 'evaluation':
                backend.evaluate(state['final_checkpoint'], root/'eval_001.jsonl')
                record.update(checkpoint=state['final_checkpoint'], responses=str(root/'eval_001.jsonl'))
            record['elapsed_seconds'] = time.monotonic() - started
            state['stage_records'][stage] = record
            state['completed_stages'].append(stage)
            state['phase'] = STAGES[STAGES.index(stage)+1] if stage != STAGES[-1] else 'complete'
            save()
            print(json.dumps({'intervention_stage': stage, 'status': 'COMPLETE',
                              'seconds': record['elapsed_seconds']}), flush=True)
        except Exception as exc:
            failure = {'stage': stage, 'type': type(exc).__name__, 'message': str(exc),
                       'time': time.time(), 'elapsed_seconds': time.monotonic()-started}
            state['failures'].append(failure)
            folder = root/'failed_attempts'/f'{stage}_{len(state["failures"]):03d}'
            folder.mkdir(parents=True, exist_ok=True)
            (folder/'failure.txt').write_text(traceback.format_exc())
            if stage in ('dpo', 'sft'):
                source = root/('dpo' if stage == 'dpo' else 'final')
                for filename in ('training_log.jsonl', 'gradient_report.json', 'parameter_deltas.json', 'sequence_lengths.json'):
                    if (source/filename).is_file(): shutil.copyfile(source/filename, folder/filename)
            state['status'] = 'FAILED'; save(); return state
    state['status'] = 'COMPLETE'; state['phase'] = 'complete'; save()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--through-stage', '--stage-through', choices=STAGES, default='evaluation')
    args = parser.parse_args()
    state = run(args.config, args.output, resume=args.resume, through_stage=args.through_stage)
    print(json.dumps(state, indent=2))
    return 1 if state['status'] == 'FAILED' else 0


if __name__ == '__main__': raise SystemExit(main())
