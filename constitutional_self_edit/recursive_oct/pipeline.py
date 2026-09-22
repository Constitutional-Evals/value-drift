"""Restartable inner experimental loop; inference/training supplied by backend."""
import json
import time
from pathlib import Path

TERMINAL={'SELF_DECLARED_CONVERGENCE','BUDGET_LIMIT','ROUND_LIMIT','EDITING_FAILURE','TRAINING_FAILURE'}


def write_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    temp.replace(path)


def run_trajectory(run_dir, config, backend, resume=False, budget_ok=lambda:True):
    root=Path(run_dir); root.mkdir(parents=True,exist_ok=True)
    state_path=root/'state.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        if not resume: raise ValueError('Run exists; use explicit resume')
        if json.loads((root/'config.json').read_text())!=config:
            raise ValueError('Protocol changes require a separately labeled run')
        if state['status'] in {'SELF_DECLARED_CONVERGENCE','ROUND_LIMIT','EDITING_FAILURE'}:
            return state
        state['status']='RUNNING'
    else:
        initial=Path(config['constitution']).read_text()
        (root/'C_000.md').write_text(initial)
        write_json(root/'config.json',config)
        state={'status':'RUNNING','phase':'baseline','completed_rounds':0,
               'current_checkpoint':config['model'],'current_constitution':str(root/'C_000.md'),
               'reviews':[],'failures':[],'started_epoch':time.time()}
    def save():
        state['updated_epoch']=time.time(); write_json(state_path,state)
    save()
    while state['status']=='RUNNING':
        if not budget_ok(): state['status']='BUDGET_LIMIT'; save(); break
        phase=state['phase']; n=state['completed_rounds']+1
        rd=root/f'round_{n:03d}'; rd.mkdir(exist_ok=True)
        try:
            if phase=='baseline':
                backend.evaluate(state['current_checkpoint'],root/'eval_000.jsonl')
                state['phase']='review'
            elif phase=='review':
                if state['completed_rounds']>=config.get('max_rounds',5):
                    state['status']='ROUND_LIMIT'; save(); break
                if (rd/'review.json').exists():
                    review=json.loads((rd/'review.json').read_text())
                elif (rd/'generations.jsonl').exists():
                    review={'status':'EDITING_FAILURE','text':Path(state['current_constitution']).read_text(),
                            'failure_reason':'Interrupted review has outputs but no finalized submission; never resample'}
                else:
                    review=backend.review(state['current_checkpoint'],Path(state['current_constitution']),rd)
                write_json(rd/'review.json',review)
                state['reviews'].append({k:v for k,v in review.items() if k!='text'})
                if review['status']=='SELF_DECLARED_CONVERGENCE':
                    state['status']='SELF_DECLARED_CONVERGENCE'
                elif review['status']=='EDITED':
                    submitted=root/f'C_{n:03d}.md'; submitted.write_text(review['text'])
                    state['submitted_constitution']=str(submitted); state['phase']='preferences'
                else:
                    state['status']='EDITING_FAILURE'
            elif phase=='preferences':
                backend.preferences(state['current_checkpoint'],Path(state['submitted_constitution']),rd/'preferences.jsonl')
                state['phase']='dpo'
            elif phase=='dpo':
                state['dpo_checkpoint']=backend.dpo(state['current_checkpoint'],rd/'preferences.jsonl',rd/'dpo')
                state['phase']='introspection'
            elif phase=='introspection':
                backend.introspection(state['dpo_checkpoint'],rd/'introspection.jsonl')
                state['phase']='sft'
            elif phase=='sft':
                state['next_checkpoint']=backend.sft(state['dpo_checkpoint'],rd/'introspection.jsonl',rd/'final')
                state['phase']='evaluation'
            elif phase=='evaluation':
                backend.evaluate(state['next_checkpoint'],root/f'eval_{n:03d}.jsonl')
                state['current_checkpoint']=state.pop('next_checkpoint')
                state['current_constitution']=state.pop('submitted_constitution')
                state['completed_rounds']=n
                state['phase']='review'
                if n>=config.get('max_rounds',5): state['status']='ROUND_LIMIT'
            else: raise ValueError(f'Unknown phase: {phase}')
        except Exception as exc:
            state['failures'].append({'phase':phase,'time':time.time(),'type':type(exc).__name__,'message':str(exc)})
            state['status']='EDITING_FAILURE' if phase=='review' else 'TRAINING_FAILURE'
            save()
            import traceback
            with (rd/'failure.log').open('a') as f: traceback.print_exc(file=f)
        save()
    return state
