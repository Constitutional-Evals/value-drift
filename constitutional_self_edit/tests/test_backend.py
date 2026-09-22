from recursive_oct.backend import execute_review

class Model:
    def __init__(self, outputs): self.outputs=iter(outputs)
    def generate_batch(self,*args,**kwargs): return [next(self.outputs)]

def response(raw,finish='stop'):
    return {'raw_text':raw,'text':raw,'finish_reason':finish}

FINISH='<tool_call><function=finish_editing><parameter=decision_summary>Endorsed.</parameter></function></tool_call>'

def test_configured_review_variant_reaches_model_without_changing_default(tmp_path):
    import json
    variant=tmp_path/'variant.md';variant.write_text('Compare concrete consequences; unchanged is valid.')
    wrapper=tmp_path/'wrapper.md';wrapper.write_text('Diagnostic only. $review_instructions\n$constitution\n$checkpoint\n$recipe_text\n$tool_instructions')
    execute_review(Model([response(FINISH)]),'M0','Constitution',tmp_path/'custom',
                   {'review_instructions_path':str(variant),'context_template_path':str(wrapper)})
    initial=json.loads((tmp_path/'custom/initial_messages.json').read_text())[0]['content']
    assert 'Diagnostic only.' in initial
    assert variant.read_text() in initial
    execute_review(Model([response(FINISH)]),'M0','Constitution',tmp_path/'default',{})
    default=json.loads((tmp_path/'default/initial_messages.json').read_text())[0]['content']
    assert 'Diagnostic only.' not in default
    assert variant.read_text() not in default

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
