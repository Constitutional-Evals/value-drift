import copy
import json

import pytest

from recursive_oct.backend import execute_review
from recursive_oct.protocol import snapshot_protocol_inputs


FINISH='<tool_call><function=finish_editing><parameter=decision_summary>Endorsed.</parameter></function></tool_call>'


class Model:
    def __init__(self, outputs):
        self.outputs=iter(outputs);self.calls=[]
    def generate_batch(self,messages,**options):
        self.calls.append((copy.deepcopy(messages),options))
        return [next(self.outputs)]


def output(text, raw=None, finish='stop'):
    return {'text':text,'raw_text':text if raw is None else raw,'finish_reason':finish}


def config(tmp_path):
    instructions=tmp_path/'appraisal.md';instructions.write_text('First provide a brief appraisal without tools.')
    transition=tmp_path/'transition.md';transition.write_text('Now decide and submit using the tools.')
    return {'appraisal_instructions_path':str(instructions),'appraisal_transition_path':str(transition),
            'appraisal_max_new_tokens':4096,'max_new_tokens':8192,'enable_thinking':True}


def test_appraisal_then_tools_share_visible_context_without_counting_appraisal(tmp_path):
    cfg=config(tmp_path)
    model=Model([output('The text is coherent.','private reasoning</think>The text is coherent.'),
                 output(FINISH,'reasoning</think>'+FINISH)])
    root=tmp_path/'run'
    result=execute_review(model,'M0','Constitution',root,cfg)
    assert result['status']=='SELF_DECLARED_CONVERGENCE'
    assert result['tool_call_count']==1 and result['editing_call_count']==0
    assert model.calls[0][1].get('tools') is None
    assert model.calls[0][1]['max_new_tokens']==4096
    assert model.calls[1][1]['tools'] and model.calls[1][1]['max_new_tokens']==8192
    conversation=model.calls[1][0][0]
    assert 'First provide a brief appraisal' in conversation[0]['content']
    assert conversation[1]=={'role':'assistant','content':'The text is coherent.'}
    assert conversation[2]['role']=='user' and 'Now decide' in conversation[2]['content']
    assert 'private reasoning' not in json.dumps(conversation)
    assert (root/'appraisal.md').read_text().strip()=='The text is coherent.'
    assert json.loads((root/'appraisal.json').read_text())['raw_text'].startswith('private reasoning')
    generations=[json.loads(x) for x in (root/'generations.jsonl').read_text().splitlines()]
    assert [r['phase'] for r in generations]==['appraisal','tool_editing']


def test_deferred_tool_instructions_enter_only_at_tool_phase(tmp_path):
    from recursive_oct.editing import PROMPT_DIR
    cfg=config(tmp_path);cfg['appraisal_defer_tool_instructions']=True
    model=Model([output('The text is coherent.','reasoning</think>The text is coherent.'),
                 output(FINISH,'reasoning</think>'+FINISH)])
    result=execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    first=model.calls[0][0][0][0]['content']
    assert 'Available tools' not in first
    assert 'call this tool directly' not in first
    assert 'Constitution' in first and 'M0' in first
    assert 'First provide a brief appraisal' in first
    assert model.calls[0][1]['tools'] is None
    transition=model.calls[1][0][0][2]['content']
    guide=(PROMPT_DIR/'tool_instructions.md').read_text().strip()
    assert transition.endswith(guide)
    assert 'Now decide and submit' in transition
    assert result['status']=='SELF_DECLARED_CONVERGENCE'


def test_default_appraisal_keeps_original_tool_guide_placement(tmp_path):
    model=Model([output('Coherent.','reasoning</think>Coherent.'),
                 output(FINISH,'reasoning</think>'+FINISH)])
    execute_review(model,'M0','Constitution',tmp_path/'run',config(tmp_path))
    assert 'Available tools' in model.calls[0][0][0][0]['content']
    assert 'Available tools' not in model.calls[1][0][0][2]['content']


@pytest.mark.parametrize('appraisal,reason',[
    (output('Incomplete','reasoning</think>Incomplete','length'),'truncated_appraisal'),
    (output('','still thinking'),'unfinished_appraisal_thinking'),
    (output(' \n','reasoning</think> \n'),'empty_appraisal'),
    (output(FINISH,'reasoning</think>'+FINISH),'appraisal_tool_call'),
    (output('x','reasoning</think><think>unfinished'),'unfinished_appraisal_thinking'),
])
def test_invalid_appraisal_fails_without_dispatch_or_second_generation(tmp_path,appraisal,reason):
    model=Model([appraisal]);root=tmp_path/'run'
    result=execute_review(model,'M0','Constitution',root,config(tmp_path))
    assert result['status']=='EDITING_FAILURE' and result['failure_reason']==reason
    assert result['tool_call_count']==0 and result['text']=='Constitution'
    assert len(model.calls)==1
    assert (root/'appraisal.json').exists() and (root/'review.json').exists()


def test_disabled_appraisal_preserves_single_tool_phase(tmp_path):
    model=Model([output(FINISH)])
    result=execute_review(model,'M0','Constitution',tmp_path/'run',{})
    assert result['status']=='SELF_DECLARED_CONVERGENCE'
    assert len(model.calls)==1 and model.calls[0][1]['tools']
    assert not (tmp_path/'run/appraisal.json').exists()


def test_appraisal_files_are_snapshotted_and_checked_on_resume(tmp_path):
    cfg={}
    for name in ('constitution','recipe_text','train_prompts','eval_prompts','introspection_prompts'):
        path=tmp_path/name;path.write_text(name);cfg[name]=str(path)
    cfg['review']=config(tmp_path)
    root=tmp_path/'run'
    manifest=json.loads(snapshot_protocol_inputs(root,cfg).read_text())
    assert 'appraisal_instructions' in manifest['inputs']
    assert 'appraisal_transition' in manifest['inputs']
    from pathlib import Path
    Path(cfg['review']['appraisal_transition_path']).write_text('Changed transition')
    with pytest.raises(ValueError,match='appraisal_transition'):
        snapshot_protocol_inputs(root,cfg,resume=True)


def test_partial_appraisal_configuration_is_rejected_before_generation(tmp_path):
    cfg=config(tmp_path);del cfg['appraisal_transition_path']
    model=Model([])
    with pytest.raises(ValueError,match='both appraisal'):
        execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    assert not model.calls


def test_appraisal_thinking_override_keeps_structured_tools_non_thinking(tmp_path):
    cfg=config(tmp_path)
    cfg.update(enable_thinking=False, appraisal_enable_thinking=True, structured_tool_calls=True)
    finish=json.dumps({'name':'finish_editing','arguments':{'decision_summary':'Endorsed.'}})
    model=Model([output('A public appraisal.','private appraisal reasoning</think>A public appraisal.'), output(finish)])
    result=execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    assert result['status']=='SELF_DECLARED_CONVERGENCE'
    assert model.calls[0][1]['enable_thinking'] is True
    assert model.calls[1][1]['enable_thinking'] is False
    assert model.calls[1][1]['json_schema']
    tool_context=model.calls[1][0][0]
    assert tool_context[1]=={'role':'assistant','content':'A public appraisal.'}
    assert 'private appraisal reasoning' not in json.dumps(tool_context)
    assert 'private appraisal reasoning' in (tmp_path/'run/appraisal.json').read_text()


def test_appraisal_override_controls_unfinished_thinking_validation(tmp_path):
    cfg=config(tmp_path)
    cfg.update(enable_thinking=False, appraisal_enable_thinking=True, structured_tool_calls=True)
    model=Model([output('Apparent answer.', 'unfinished reasoning without closing marker')])
    result=execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    assert result['failure_reason']=='unfinished_appraisal_thinking'
    assert len(model.calls)==1


def test_appraisal_thinking_can_be_disabled_without_changing_native_tool_mode(tmp_path):
    cfg=config(tmp_path); cfg['appraisal_enable_thinking']=False
    model=Model([output('Public appraisal without thinking.'), output(FINISH,'reasoning</think>'+FINISH)])
    result=execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    assert result['status']=='SELF_DECLARED_CONVERGENCE'
    assert model.calls[0][1]['enable_thinking'] is False
    assert model.calls[1][1]['enable_thinking'] is True


@pytest.mark.parametrize('invalid',[None,0,1,'true'])
def test_appraisal_thinking_override_requires_bool(tmp_path,invalid):
    cfg=config(tmp_path); cfg['appraisal_enable_thinking']=invalid
    model=Model([])
    with pytest.raises(ValueError,match='appraisal_enable_thinking.*bool'):
        execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    assert not model.calls


def test_appraisal_sampling_overrides_only_appraisal_decoding(tmp_path):
    cfg=config(tmp_path)
    cfg.update(enable_thinking=False, structured_tool_calls=True,
               temperature=.7, top_p=.8, top_k=20, presence_penalty=0,
               appraisal_sampling={'temperature':1.,'top_p':.95,'top_k':40,'presence_penalty':1.5})
    finish=json.dumps({'name':'finish_editing','arguments':{'decision_summary':'Keep.'}})
    model=Model([output('Public appraisal.'),output(finish)])
    result=execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    assert result['status']=='SELF_DECLARED_CONVERGENCE'
    for key,value in cfg['appraisal_sampling'].items():
        assert model.calls[0][1][key]==value
        assert model.calls[1][1][key]==cfg[key]


@pytest.mark.parametrize('invalid',[None,[],1,{'seed':42},{'max_new_tokens':12},{'enable_thinking':True}])
def test_appraisal_sampling_rejects_non_dict_or_non_sampling_keys(tmp_path,invalid):
    cfg=config(tmp_path); cfg['appraisal_sampling']=invalid
    model=Model([])
    with pytest.raises(ValueError,match='appraisal_sampling'):
        execute_review(model,'M0','Constitution',tmp_path/'run',cfg)
    assert not model.calls
