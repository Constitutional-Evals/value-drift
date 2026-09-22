import copy
import json
from pathlib import Path

import pytest

from recursive_oct.backend import execute_review
from recursive_oct.editing import EditingSession, tool_schemas
from recursive_oct.protocol import snapshot_protocol_inputs


def edit(session, old, new):
    return session.dispatch('edit_constitution',{'old_text':old,'new_text':new,'change_summary':'Revise.'})


def finish(session):
    return session.dispatch('finish_editing',{'decision_summary':'Submit.'})


def test_passage_edit_preserves_surrounding_bytes_and_revert_is_edited(tmp_path):
    original='First.\r\nBe kind.\r\nLast.\n'
    session=EditingSession(tmp_path/'C.md',original,allow_passage_edit=True)
    result=edit(session,'Be kind.','Be kind and honest.')
    assert result['ok'] and not result['no_op']
    assert session.constitution_path.read_bytes()==original.replace('Be kind.','Be kind and honest.').encode()
    assert '+Be kind and honest.' in result['diff']
    edit(session,'Be kind and honest.','Be kind.')
    finish(session)
    assert session.status=='EDITED' and session.reverted
    assert session.outcome()['content_changing_edit_count']==2


def test_identical_passage_rewrite_is_noop(tmp_path):
    session=EditingSession(tmp_path/'C.md','Be kind.',allow_passage_edit=True)
    assert edit(session,'kind','kind')['no_op']
    finish(session)
    assert session.status=='SELF_DECLARED_CONVERGENCE'
    assert session.no_op_count==1 and not session.first_tool_call_submission


@pytest.mark.parametrize('original,old', [('A',''),('A','B'),('AA','A'),('aaa','aa'),('A',None),('A',3)])
def test_invalid_or_ambiguous_passage_fails_without_writing(tmp_path,original,old):
    session=EditingSession(tmp_path/'C.md',original,allow_passage_edit=True)
    assert not edit(session,old,'changed')['ok']
    assert session.status=='EDITING_FAILURE' and session.current_text==original
    assert not finish(session)['ok'] and not session.outcome()['submitted']


def test_passage_mode_is_optional_and_full_replacement_remains_available(tmp_path):
    session=EditingSession(tmp_path/'C.md','Old')
    assert not edit(session,'Old','New')['ok']
    session=EditingSession(tmp_path/'C.md','Old',allow_passage_edit=True)
    assert session.dispatch('edit_constitution',{'new_text':'Entire new document','change_summary':'Replace.'})['ok']
    assert session.current_text=='Entire new document'
    assert tool_schemas()==tool_schemas(allow_passage_edit=False)
    default=tool_schemas();enabled=tool_schemas(allow_passage_edit=True)
    assert len(enabled)==2 and enabled[1]==default[1]
    parameters=enabled[0]['function']['parameters']
    assert parameters['required']==['new_text','change_summary']
    assert parameters['properties']['old_text']['type']=='string'
    assert 'old_text' not in default[0]['function']['parameters']['properties']


@pytest.mark.parametrize('defer', [False,True])
def test_passage_schema_guide_and_dispatch_reach_review(tmp_path,defer):
    guide=tmp_path/'guide.md';guide.write_text('Custom exact-passage tool guide.')
    cfg={'allow_passage_edit':True,'tool_instructions_path':str(guide)}
    outputs=[]
    if defer:
        appraisal=tmp_path/'appraisal.md';appraisal.write_text('Appraise first.')
        transition=tmp_path/'transition.md';transition.write_text('Now edit.')
        cfg.update(appraisal_instructions_path=str(appraisal),appraisal_transition_path=str(transition),
                   appraisal_defer_tool_instructions=True)
        outputs.append('An improvement is possible.')
    outputs.append('<tool_call><function=edit_constitution><parameter=old_text>kind</parameter><parameter=new_text>honest</parameter><parameter=change_summary>Revise.</parameter></function></tool_call><tool_call><function=finish_editing><parameter=decision_summary>Submit.</parameter></function></tool_call>')
    class Model:
        def __init__(self): self.calls=[]
        def generate_batch(self,messages,**options):
            self.calls.append((copy.deepcopy(messages),options))
            text=outputs.pop(0)
            return [{'text':text,'raw_text':text,'finish_reason':'stop'}]
    model=Model()
    result=execute_review(model,'M0','Be kind.',tmp_path/'run',cfg)
    assert result['text']=='Be honest.' and result['status']=='EDITED'
    messages,options=model.calls[-1]
    assert 'old_text' in options['tools'][0]['function']['parameters']['properties']
    assert guide.read_text() in messages[0][-1 if defer else 0]['content']
    assert 'Available tools' not in messages[0][0]['content']
    if defer: assert guide.read_text() not in model.calls[0][0][0][0]['content']


def test_custom_tool_guide_is_snapshotted_and_resume_checked(tmp_path):
    cfg={}
    for name in ('constitution','recipe_text','train_prompts','eval_prompts','introspection_prompts'):
        path=tmp_path/name;path.write_text(name);cfg[name]=str(path)
    guide=tmp_path/'guide.md';guide.write_text('Custom guide.')
    cfg['review']={'allow_passage_edit':True,'tool_instructions_path':str(guide)}
    manifest=json.loads(snapshot_protocol_inputs(tmp_path/'run',cfg).read_text())
    saved=tmp_path/'run/protocol_inputs'/manifest['inputs']['tool_instructions']['snapshot']
    assert saved.read_text()==guide.read_text()
    guide.write_text('Changed guide.')
    with pytest.raises(ValueError,match='tool_instructions'):
        snapshot_protocol_inputs(tmp_path/'run',cfg,resume=True)
