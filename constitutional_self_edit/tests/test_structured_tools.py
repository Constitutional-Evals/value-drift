import copy
import json
import sys
from types import SimpleNamespace

import pytest

from recursive_oct.backend import execute_review
from recursive_oct.model import ModelSession
from recursive_oct.vllm_session import VLLMSession
from recursive_oct.vllm_worker import WorkerEngine


NATIVE_EDIT='<tool_call><function=edit_constitution><parameter=new_text>Revised</parameter><parameter=change_summary>Revise.</parameter></function></tool_call>'
def output(text,finish='stop'): return {'text':text,'raw_text':text,'finish_reason':finish}
def call(name,**args): return json.dumps({'name':name,'arguments':args})
FINISH=call('finish_editing',decision_summary='Submit.')


class Model:
    def __init__(self,outputs): self.outputs=iter(outputs);self.calls=[]
    def generate_batch(self,messages,**options):
        self.calls.append((copy.deepcopy(messages),options))
        return [next(self.outputs)]


def test_native_replay_then_json_transition_preserves_edits_and_context(tmp_path):
    replay=[output('I plan to edit.'),output(NATIVE_EDIT),output('Done.'),output('I plan to submit.')]
    model=Model([output(FINISH)])
    result=execute_review(model,'M1','Original',tmp_path,
        {'structured_tool_calls':True,'max_plaintext_reminders':2},replay_generations=replay)
    assert result['status']=='EDITED' and result['text']=='Revised'
    assert result['tool_call_count']==2 and result['plaintext_reminder_count']==2
    assert len(model.calls)==1
    messages,options=model.calls[0]
    assert 'JSON' not in messages[0][0]['content']
    assert messages[0][-2]=={'role':'assistant','content':'I plan to submit.'}
    assert 'JSON' in messages[0][-1]['content']
    assert {x['properties']['name']['enum'][0] for x in options['json_schema']['anyOf']}=={'edit_constitution','finish_editing'}
    assert json.loads((tmp_path/'format_transition.json').read_text())['turn']==4
    saved=[json.loads(x) for x in (tmp_path/'generations.jsonl').read_text().splitlines()]
    assert all(x['replayed'] for x in saved[:4]) and saved[4]['wire_format']=='json'


@pytest.mark.parametrize('replacement,expected', [('Original','SELF_DECLARED_CONVERGENCE'),('Revised','EDITED')])
def test_json_edit_and_finish_keep_noop_semantics(tmp_path,replacement,expected):
    model=Model([output(call('edit_constitution',new_text=replacement,change_summary='Revise.')),output(FINISH)])
    result=execute_review(model,'M1','Original',tmp_path,{'structured_tool_calls':True})
    assert result['status']==expected and len(model.calls)==2
    assert model.calls[1][0][0][-2]['tool_calls'][0]['function']['name']=='edit_constitution'


def test_json_passage_then_revert_remains_edited(tmp_path):
    model=Model([output(call('edit_constitution',old_text='Old',new_text='New',change_summary='Revise.')),
                 output(call('edit_constitution',old_text='New',new_text='Old',change_summary='Revert.')),output(FINISH)])
    result=execute_review(model,'M1','Old text',tmp_path,{'structured_tool_calls':True,'allow_passage_edit':True})
    assert result['status']=='EDITED' and result['edit_then_revert']
    props=model.calls[0][1]['json_schema']['anyOf'][0]['properties']['arguments']['properties']
    assert 'old_text' in props


@pytest.mark.parametrize('bad', ['Done.',NATIVE_EDIT,'{"name":"finish_editing"}',
    '{"name":"finish_editing","arguments":{"decision_summary":"x","decision_summary":"y"}}',
    call('finish_editing',decision_summary=2),call('unknown',decision_summary='x')])
def test_invalid_json_tool_output_never_executes_or_gets_plaintext_reminder(tmp_path,bad):
    model=Model([output(bad)])
    result=execute_review(model,'M1','Original',tmp_path,{'structured_tool_calls':True,'max_plaintext_reminders':2})
    assert result['status']=='EDITING_FAILURE' and result['text']=='Original'
    assert len(model.calls)==1 and result['plaintext_reminder_count']==0


def test_json_sampling_transport_and_transformers_rejection(monkeypatch):
    seen=[]
    monkeypatch.setitem(sys.modules,'vllm',SimpleNamespace(SamplingParams=lambda **kw:SimpleNamespace(**kw)))
    monkeypatch.setitem(sys.modules,'vllm.sampling_params',SimpleNamespace(StructuredOutputsParams=lambda **kw:SimpleNamespace(**kw)))
    worker=object.__new__(WorkerEngine);worker.options={'seed':30405,'max_model_len':32768};worker.request_counter=0;worker.eos_ids={99}
    worker.tokenizer=SimpleNamespace(apply_chat_template=lambda *a,**kw:[1],decode=lambda *a,**kw:FINISH)
    def generate(prompts,sampling_params,**kw):
        seen.extend(sampling_params)
        return [SimpleNamespace(outputs=[SimpleNamespace(token_ids=[2,99],finish_reason='stop',stop_reason=99)])]
    worker.llm=SimpleNamespace(generate=generate)
    session=VLLMSession('M1')
    session._exchange=lambda request:{'results':worker.generate_batch(request['conversations'],request['options'])}
    schema={'type':'object','properties':{'test':{'type':'string'}}}
    session.generate_batch([[]],json_schema=schema)
    session.generate_batch([[]])
    assert seen[0].structured_outputs.json==schema and seen[0].seed==30405
    assert getattr(seen[1],'structured_outputs',None) is None
    with pytest.raises(ValueError,match='json_schema.*vLLM'):
        object.__new__(ModelSession).generate_batch([[]],json_schema=schema)
