#!/usr/bin/env python3
"""Separate post-trajectory evaluation of a saved DPO checkpoint; never trains."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from recursive_oct.backend import ExperimentBackend
from recursive_oct.judging import RUBRIC_PATH, SYSTEM_PATH
from recursive_oct.measurement import NEUTRAL_SYSTEM_PROMPT
from recursive_oct.pipeline import write_json
from recursive_oct.train import read_jsonl


def prepare(source_run, round_number, output):
    source=Path(source_run)
    if round_number<1:
        raise ValueError('Round number must be positive')
    checkpoint=source/f'round_{round_number:03d}'/'dpo'
    complete=json.loads((checkpoint/'training_complete.json').read_text())
    if complete['stage']!='dpo' or complete['training']!='full_parameter':
        raise ValueError('Expected a completed full-parameter DPO checkpoint')
    config=json.loads((source/'config.json').read_text())
    manifest=json.loads((source/'protocol_inputs/manifest.json').read_text())['inputs']
    def snapshot(name): return source/'protocol_inputs'/manifest[name]['snapshot']
    for key in ('constitution','train_prompts','eval_prompts'):
        config[key]=str(snapshot(key))
    prompts=read_jsonl(config['eval_prompts'])
    baseline=read_jsonl(source/'eval_000.jsonl')
    if len(prompts)!=120 or len({r['id'] for r in prompts})!=120:
        raise ValueError('Expected the original 120 unique held-out prompts')
    if [(r['id'],r['prompt']) for r in prompts]!=[(r['id'],r['prompt']) for r in baseline]:
        raise ValueError('Frozen evaluation prompts differ from the existing baseline')
    if config.get('judge'):
        for name,current in [('judge_system',SYSTEM_PATH),('judge_rubric',RUBRIC_PATH)]:
            if snapshot(name).read_bytes()!=current.read_bytes():
                raise ValueError(f'{name} differs from the original fixed judge protocol')
    output=Path(output)
    if output.resolve()==source.resolve() or source.resolve() in output.resolve().parents:
        raise ValueError('Use a separate stage_analysis directory outside the source run')
    receipt={'analysis':'saved_post_dpo_evaluation','source_run':str(source),
             'round':round_number,'checkpoint':str(checkpoint),'expected_responses':120,
             'evaluation':config['evaluation'],'judge':config.get('judge'),
             'neutral_system_prompt':NEUTRAL_SYSTEM_PROMPT,
             'prompts':prompts,'training_input_checkpoint':complete['input_checkpoint']}
    return config,receipt


def evaluate(source_run, round_number, output, *, plan_only=False):
    config,receipt=prepare(source_run,round_number,output)
    output=Path(output)
    response_path=output/'responses.jsonl'
    if plan_only:
        return {k:v for k,v in receipt.items() if k!='prompts'} | {'output':str(response_path),'gpu_started':False}
    protocol=output/'analysis_protocol.json'
    if protocol.exists():
        if json.loads(protocol.read_text())!=receipt:
            raise ValueError('Existing stage-analysis inputs differ; choose another output directory')
    else:
        if output.exists() and any(output.iterdir()):
            raise ValueError('Nonempty analysis directory lacks its input receipt')
        write_json(protocol,receipt)
    # Existing APIs retain completed response/judgment rows on retry. They never
    # regenerate a truncated or invalid output to improve the reported result.
    ExperimentBackend(config).evaluate(receipt['checkpoint'],response_path)
    responses=read_jsonl(response_path)
    if [r['id'] for r in responses]!=[r['id'] for r in receipt['prompts']]:
        raise ValueError('Post-DPO evaluation is incomplete or reordered')
    summary={k:v for k,v in receipt.items() if k not in {'prompts','evaluation','judge'}}
    summary.update(responses=str(response_path),response_count=len(responses),
                   finish_reasons=dict(Counter(r['finish_reason'] for r in responses)))
    if config.get('judge'):
        judged_path=Path(str(response_path)+'.judged.jsonl')
        judgments=read_jsonl(judged_path)
        # The fixed judge intentionally shuffles presentation order.
        if sorted(r['id'] for r in judgments)!=sorted(r['id'] for r in responses):
            raise ValueError('Fixed-judge evaluation is incomplete or has duplicate IDs')
        summary.update(judgments=str(judged_path),judgment_count=len(judgments))
    write_json(output/'analysis_complete.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run',default='runs/full-011')
    parser.add_argument('--round',type=int,default=1)
    parser.add_argument('--output',default='runs/stage_analysis/full-011_dpo_001')
    parser.add_argument('--plan-only',action='store_true',help='Validate saved inputs and print the plan without loading models or writing files')
    args=parser.parse_args()
    print(json.dumps(evaluate(args.source_run,args.round,args.output,plan_only=args.plan_only),indent=2))


if __name__=='__main__':
    main()
