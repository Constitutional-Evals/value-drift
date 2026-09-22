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
