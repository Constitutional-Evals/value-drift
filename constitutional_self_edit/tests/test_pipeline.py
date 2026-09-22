import json
from recursive_oct.pipeline import run_trajectory

class Backend:
    def __init__(self, decisions): self.decisions=iter(decisions); self.calls=[]
    def evaluate(self, checkpoint, output): self.calls.append(('eval',checkpoint))
    def review(self, checkpoint, constitution, output):
        self.calls.append(('review',checkpoint,constitution.read_text()))
        return next(self.decisions)
    def preferences(self, checkpoint, constitution, output): self.calls.append(('preferences',checkpoint))
    def dpo(self, checkpoint, data, output): self.calls.append(('dpo',checkpoint)); return str(output)
    def introspection(self, checkpoint, output): self.calls.append(('introspection',checkpoint))
    def sft(self, checkpoint, data, output): self.calls.append(('sft',checkpoint)); return str(output)

def setup(tmp_path):
    c=tmp_path/'initial.md'; c.write_text('Initial constitution')
    return {'model':'M0','constitution':str(c),'max_rounds':5}

def test_explicit_unchanged_stops_without_training(tmp_path):
    b=Backend([{'status':'SELF_DECLARED_CONVERGENCE','text':'Initial constitution'}])
    s=run_trajectory(tmp_path/'run',setup(tmp_path),b)
    assert s['status']=='SELF_DECLARED_CONVERGENCE'
    assert s['completed_rounds']==0
    assert [x[0] for x in b.calls]==['eval','review']

def test_weights_flow_dpo_sft_next_review(tmp_path):
    b=Backend([{'status':'EDITED','text':'Revised'}, {'status':'SELF_DECLARED_CONVERGENCE','text':'Revised'}])
    s=run_trajectory(tmp_path/'run',setup(tmp_path),b)
    calls=dict((x[0],x[1]) for x in b.calls if x[0] not in ['review','eval'])
    assert calls['dpo']=='M0'
    assert calls['introspection'].endswith('/round_001/dpo')
    assert calls['sft']==calls['introspection']
    assert b.calls[-1][1].endswith('/round_001/final')
    assert b.calls[-1][2]=='Revised'
    assert s['completed_rounds']==1

def test_round_limit_does_not_trigger_extra_review(tmp_path):
    cfg=setup(tmp_path); cfg['max_rounds']=1
    b=Backend([{'status':'EDITED','text':'Revised'}])
    s=run_trajectory(tmp_path/'run',cfg,b)
    assert s['status']=='ROUND_LIMIT'
    assert len([x for x in b.calls if x[0]=='review'])==1

def test_failed_sft_resumes_from_dpo_without_regenerating(tmp_path):
    cfg=setup(tmp_path); cfg['max_rounds']=1
    b=Backend([{'status':'EDITED','text':'Revised'}])
    original=b.sft
    def fail(*a): raise RuntimeError('out of memory')
    b.sft=fail
    s=run_trajectory(tmp_path/'run',cfg,b)
    assert s['status']=='TRAINING_FAILURE'
    assert s['phase']=='sft'
    b.sft=original
    s=run_trajectory(tmp_path/'run',cfg,b,resume=True)
    assert s['status']=='ROUND_LIMIT'
    assert len([x for x in b.calls if x[0]=='dpo'])==1

def test_budget_stops_before_next_paid_stage(tmp_path):
    b=Backend([])
    s=run_trajectory(tmp_path/'run',setup(tmp_path),b,budget_ok=lambda:False)
    assert s['status']=='BUDGET_LIMIT'
    assert b.calls==[]

def test_reuses_finished_review_after_state_write_crash(tmp_path):
    from recursive_oct.pipeline import write_json
    cfg=setup(tmp_path); root=tmp_path/'run'; root.mkdir()
    c=root/'C_000.md'; c.write_text('Initial constitution')
    write_json(root/'config.json',cfg)
    write_json(root/'state.json',{'status':'RUNNING','phase':'review','completed_rounds':0,
        'current_checkpoint':'M0','current_constitution':str(c),'reviews':[],'failures':[]})
    write_json(root/'round_001'/'review.json',{'status':'SELF_DECLARED_CONVERGENCE','text':'Initial constitution'})
    b=Backend([])
    s=run_trajectory(root,cfg,b,resume=True)
    assert s['status']=='SELF_DECLARED_CONVERGENCE'
    assert b.calls==[]
