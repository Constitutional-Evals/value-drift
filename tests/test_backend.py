from recursive_oct.backend import execute_review

class Model:
    def __init__(self, outputs): self.outputs=iter(outputs)
    def generate_batch(self,*args,**kwargs): return [next(self.outputs)]

def response(raw,finish='stop'):
    return {'raw_text':raw,'text':raw,'finish_reason':finish}

FINISH='<tool_call><function=finish_editing><parameter=decision_summary>Endorsed.</parameter></function></tool_call>'

def test_truncated_finish_is_failure_before_tool_execution(tmp_path):
    r=execute_review(Model([response(FINISH,'length')]),'M0','Constitution',tmp_path,{'enable_thinking':True})
    assert r['status']=='EDITING_FAILURE'
    assert r['tool_call_count']==0

def test_complete_native_finish_converges(tmp_path):
    r=execute_review(Model([response(FINISH)]),'M0','Constitution',tmp_path,{})
    assert r['status']=='SELF_DECLARED_CONVERGENCE'
    assert r['text']=='Constitution'

def test_finish_followed_by_edit_is_malformed_not_convergence(tmp_path):
    extra='<tool_call><function=edit_constitution><parameter=new_text>Changed</parameter><parameter=change_summary>Change</parameter></function></tool_call>'
    r=execute_review(Model([response(FINISH+extra)]),'M0','Constitution',tmp_path,{})
    assert r['status']=='EDITING_FAILURE'

def test_eos_during_reasoning_is_not_convergence(tmp_path):
    r=execute_review(Model([response('<think>Consider '+FINISH)]),'M0','Constitution',tmp_path,{'enable_thinking':True})
    assert r['status']=='EDITING_FAILURE'
    assert r['tool_call_count']==0
