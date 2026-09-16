#!/usr/bin/env python3
"""Explicitly launched engineering handoff; never a review or diagnostic trial.

Run only after lead grants the GPU. Re-running reuses saved generation rows and
completed training stages under an immutable local protocol. A failure exits;
there is no automatic resampling, threshold relaxation, or retry loop.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recursive_oct.generation import generate_preferences, generate_introspection, generate_rows
from recursive_oct.pipeline import write_json
from recursive_oct.train import read_jsonl, train_dpo, train_sft


ORDINARY_PROMPTS = [
    {'id':'stage2-engineering-forecast','prompt':'Explain in three sentences what a 30% chance of rain means to someone planning a picnic.'},
    {'id':'stage2-engineering-email','prompt':'Write a polite email of at most 100 words asking to move a team meeting from Tuesday to Thursday.'},
    {'id':'stage2-engineering-practice','prompt':'Suggest a beginner guitar practice routine for 15 minutes a day. Use at most 150 words.'},
    {'id':'stage2-engineering-sources','prompt':'In at most 120 words, explain the difference between primary and secondary historical sources, with one example of each.'},
]


def engineering_protocol(base_config):
    """Copy established controls; only the declared small engineering scale changes."""
    base = json.loads(Path(base_config).read_text())
    if base.get('official_model') != 'Qwen/Qwen3.5-9B' or base.get('teacher_official_model') != 'Qwen/Qwen3.5-27B':
        raise ValueError('Engineering validation requires the pinned official 9B/27B pair')
    if base.get('model_revision') != 'c202236235762e1c871ad0ccb60c8ee5ba337b9a' or base.get('teacher_revision') != 'fc05daec18b0a78c049392ed2e771dde82bdf654':
        raise ValueError('Unexpected original checkpoint revision')
    config = {k:copy.deepcopy(base[k]) for k in ('model','teacher','model_revision','teacher_revision','dpo','sft','generation','introspection')}
    for stage,length in [('dpo',2560),('sft',3072)]:
        config[stage].update(max_length=length,gradient_accumulation_steps=2,epochs=1,
                             parameter_dtype='float32',allow_target_truncation=False)
    for stage in ('generation','introspection'):
        if config[stage].get('backend') != 'vllm':
            raise ValueError('Engineering handoff requires isolated vLLM inference')
        config[stage].update(enable_thinking=False,allow_truncated=False,batch_size=4)
    config['generation'].update(max_new_tokens=1536,minimum_retained_fraction=.5)
    config['introspection'].update(reflection_count=2,interaction_count=1,interaction_turns=4,
        max_new_tokens=1536,interaction_max_new_tokens=768,
        minimum_reflection_fraction=.5,minimum_interaction_fraction=.5)
    config['reload_generation'] = {**copy.deepcopy(config['generation']),'max_new_tokens':192,'batch_size':1}
    config.update(engineering_only=True,scientific_trajectory=False,constitutional_review=False,
                  purpose='Fresh-host vLLM → full DPO → introspection → full SFT → vLLM handoff',
                  constitution=(ROOT/'constitutions/C_000.md').read_text(),prompts=ORDINARY_PROMPTS,
                  reflection_prompts=read_jsonl(ROOT/'prompts/introspection.jsonl')[:2],
                  reload_prompt={'id':'stage2-final-reload','prompt':'Give a two-sentence explanation of why backing up files matters.'})
    return config


def initialize_protocol(root, config):
    """A different config or unclaimed existing artifacts cannot silently resume."""
    root=Path(root)
    forbidden=[ROOT/'runs'/name for name in ('full-001','engineering_smoke','length_benchmark')]
    if any(root.resolve()==path.resolve() or path.resolve() in root.resolve().parents for path in forbidden):
        raise ValueError('Use a distinct stage2 engineering directory')
    path=root/'protocol.json'
    if path.exists():
        if json.loads(path.read_text()) != config:
            raise ValueError('Engineering protocol changed; preserve this attempt and use a separately labeled directory')
    else:
        if root.exists() and any(root.iterdir()):
            raise ValueError('Existing engineering directory has no protocol; refusing cache reuse')
        root.mkdir(parents=True,exist_ok=True)
        write_json(path,config)


def validate(root, config):
    root=Path(root)
    initialize_protocol(root,config)
    complete=root/'validation_complete.json'
    if complete.exists():
        return json.loads(complete.read_text())
    started=time.time()
    phase='preferences'
    results={}

    def progress():
        write_json(root/'progress.json',{'phase':phase,'attempt_started_epoch':started,
            'updated_epoch':time.time(),'engineering_only':True,'completed_stages':list(results)})

    try:
        progress()
        results['preferences']=generate_preferences(config['model'],config['teacher'],config['constitution'],
            config['prompts'],root/'preferences.jsonl',config['generation'])
        phase='dpo';progress()
        results['dpo']=train_dpo(config['model'],root/'preferences.jsonl',root/'dpo',config['dpo'])
        dpo_checkpoint=results['dpo']['output_checkpoint']
        phase='introspection';progress()
        results['introspection']=generate_introspection(dpo_checkpoint,config['reflection_prompts'],
            root/'introspection.jsonl',config['introspection'],constitution=config['constitution'])
        phase='sft';progress()
        results['sft']=train_sft(dpo_checkpoint,root/'introspection.jsonl',root/'final',config['sft'])
        final_checkpoint=results['sft']['output_checkpoint']
        phase='final_reload';progress()
        generated=generate_rows(final_checkpoint,[config['reload_prompt']],root/'final_reload.jsonl',config['reload_generation'])
        if generated[0]['finish_reason']!='stop' or not generated[0]['text'].strip():
            raise ValueError('Final reload response incomplete/empty; retained output must not be resampled automatically')
        results['final_reload']={'checkpoint':final_checkpoint,'finish_reason':generated[0]['finish_reason'],
            'generated_tokens':generated[0]['generated_tokens'],'artifact':str(root/'final_reload.jsonl')}
        phase='complete';progress()
        result={'status':'STAGE2_ENGINEERING_COMPLETE','engineering_only':True,'scientific_trajectory':False,
                'constitutional_review':False,'attempt_started_epoch':started,'completed_epoch':time.time(),
                'attempt_seconds':time.time()-started,'stages':results}
        write_json(complete,result)
        return result
    except Exception as exc:
        with (root/'failures.jsonl').open('a') as stream:
            stream.write(json.dumps({'phase':phase,'time':time.time(),'type':type(exc).__name__,
                                    'message':str(exc),'attempt_started_epoch':started})+'\n')
        with (root/'failure.log').open('a') as stream:
            traceback.print_exc(file=stream)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-config',default=str(ROOT/'configs/full-001.json'),
                        help='Read-only source of established optimizer/inference settings')
    parser.add_argument('--run',default='runs/stage2_engineering')
    args=parser.parse_args()
    result=validate(args.run,engineering_protocol(args.base_config))
    print(json.dumps(result,indent=2),flush=True)
    print('STAGE2_ENGINEERING_COMPLETE',flush=True)


if __name__=='__main__':
    main()
