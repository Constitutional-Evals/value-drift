"""Restartable inner experimental loop; inference/training supplied by backend.

A round reviews the constitution (or, with the "self_draft" review engine and no starting constitution,
has the model write one from scratch), then teaches the submitted version with the run's method: OCT
(preferences, DPO, introspection, SFT; the default) or model spec midtraining ("method": "msm":
documents, AFT chats, midtraining, AFT; recursive_oct/msm.py), then evaluates."""
import json
import time
from pathlib import Path

TERMINAL={'SELF_DECLARED_CONVERGENCE','BUDGET_LIMIT','ROUND_LIMIT','EDITING_FAILURE','TRAINING_FAILURE'}


def write_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    temp.replace(path)


def run_trajectory(run_dir, config, backend, resume=False, budget_ok=lambda:True, stop_after_round=None):
    """Run or resume a trajectory. stop_after_round pauses it after that many completed rounds without
    touching the protocol (status PAUSED); resuming later continues with the same config."""
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
        if config.get('constitution'):
            (root/'C_000.md').write_text(Path(config['constitution']).read_text())
        write_json(root/'config.json',config)
        state={'status':'RUNNING','phase':'baseline','completed_rounds':0,'current_checkpoint':config['model'],
               'current_constitution':str(root/'C_000.md') if config.get('constitution') else None,
               'reviews':[],'failures':[],'started_epoch':time.time()}
    def save():
        state['updated_epoch']=time.time(); write_json(state_path,state)
    save()
    while state['status']=='RUNNING':
        if not budget_ok(): state['status']='BUDGET_LIMIT'; save(); break
        if (stop_after_round is not None and state['phase']=='review'
                and state['completed_rounds']>=stop_after_round):
            state['status']='PAUSED'; save(); break
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
                    review={'status':'EDITING_FAILURE','text':Path(state['current_constitution']).read_text()
                            if state['current_constitution'] else '',
                            'failure_reason':'Interrupted review has outputs but no finalized submission; never resample'}
                else:
                    current=state['current_constitution']
                    review=backend.review(state['current_checkpoint'],Path(current) if current else None,rd)
                write_json(rd/'review.json',review)
                state['reviews'].append({k:v for k,v in review.items() if k!='text'})
                # An unchanged submission ends the run, unless the loop trains on it like the stage 07
                # chains, which continued ("chain_stop": "never"); only a failed review ends those.
                unchanged=review['status'] in ('SELF_DECLARED_CONVERGENCE','UNCHANGED')
                if unchanged and not config.get('continue_when_unchanged'):
                    state['status']='SELF_DECLARED_CONVERGENCE'
                elif review['status']=='EDITED' or unchanged:
                    submitted=root/f'C_{n:03d}.md'; submitted.write_text(review['text'])
                    state['submitted_constitution']=str(submitted)
                    state['phase']='msm_documents' if config.get('method')=='msm' else 'preferences'
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
            elif phase=='msm_documents':
                backend.msm_documents(Path(state['submitted_constitution']),rd/'msm_documents.jsonl')
                state['phase']='aft_data'
            elif phase=='aft_data':
                backend.aft_data(Path(state['submitted_constitution']),rd/'aft.jsonl')
                state['phase']='msm_train'
            elif phase=='msm_train':
                state['msm_checkpoint']=backend.msm_train(state['current_checkpoint'],rd/'msm_documents.jsonl',rd/'msm')
                state['phase']='aft_train'
            elif phase=='aft_train':
                state['next_checkpoint']=backend.aft_train(state['msm_checkpoint'],rd/'aft.jsonl',rd/'final')
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
            # The elicitation review returns a model's failed review as a result; an exception there is
            # infrastructure (e.g. the server did not start), so the run stays resumable.
            infrastructure=phase=='review' and config.get('review',{}).get('engine') in ('elicit_v3','self_draft')
            state['status']=('INFRASTRUCTURE_FAILURE' if infrastructure else
                             'EDITING_FAILURE' if phase=='review' else 'TRAINING_FAILURE')
            save()
            import traceback
            with (rd/'failure.log').open('a') as f: traceback.print_exc(file=f)
        save()
    return state
