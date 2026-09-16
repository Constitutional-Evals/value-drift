import copy
import json

import pytest

from recursive_oct.backend import execute_review


FINISH='<tool_call><function=finish_editing><parameter=decision_summary>Unchanged.</parameter></function></tool_call>'


def response(text,finish='stop',raw=None):
    return {'text':text,'raw_text':text if raw is None else raw,'finish_reason':finish}


class Model:
    def __init__(self,outputs): self.outputs=iter(outputs);self.calls=[]
    def generate_batch(self,messages,**options):
        self.calls.append((copy.deepcopy(messages),options))
        return [next(self.outputs)]


def test_plaintext_reminder_continues_same_review_without_tool_count(tmp_path):
    model=Model([response('I intend to revise this.'),response(FINISH)])
    result=execute_review(model,'M1','Constitution',tmp_path,{'max_plaintext_reminders':1})
    assert result['status']=='SELF_DECLARED_CONVERGENCE' and result['tool_call_count']==1
    assert result['plaintext_reminder_count']==1 and not result['content_changed']
    messages=model.calls[1][0][0]
    assert messages[1]=={'role':'assistant','content':'I intend to revise this.'}
    assert 'edit_constitution' in messages[2]['content'] and 'unchanged' in messages[2]['content']
    assert len((tmp_path/'generations.jsonl').read_text().splitlines())==2
    event=json.loads((tmp_path/'plaintext_reminders.jsonl').read_text())
    assert event['turn']==0 and event['reminder_index']==1


@pytest.mark.parametrize('text,finish',[
    ('I will finish.','length'),('<tool_call>','stop'),('</tool_call>','stop'),
    ('<function=finish_editing>','stop'),('<parameter=decision_summary>x','stop'),
    ('<tool_call','stop'),('<think>Unfinished','stop'),('', 'stop'),
])
def test_truncation_or_actual_malformed_markup_never_gets_reminder(tmp_path,text,finish):
    model=Model([response(text,finish)])
    result=execute_review(model,'M1','Constitution',tmp_path,{'max_plaintext_reminders':1})
    assert result['status']=='EDITING_FAILURE' and result['tool_call_count']==0
    assert len(model.calls)==1 and result['plaintext_reminder_count']==0


def test_reminder_limit_and_default_do_not_accept_prose_as_finish(tmp_path):
    for count in [0,1]:
        model=Model([response('Done.')]*(count+1))
        result=execute_review(model,'M1','Constitution',tmp_path/str(count),{'max_plaintext_reminders':count})
        assert result['status']=='EDITING_FAILURE' and result['tool_call_count']==0
        assert len(model.calls)==count+1


def test_reminder_does_not_extend_turn_limit(tmp_path):
    model=Model([response('I intend to edit.')])
    result=execute_review(model,'M1','Constitution',tmp_path,{'max_plaintext_reminders':1,'max_turns':1})
    assert result['failure_reason']=='missing_finish_at_turn_limit' and len(model.calls)==1


def test_replay_saved_plaintext_without_resampling_or_carrying_thinking(tmp_path):
    model=Model([response(FINISH,raw='new reasoning</think>'+FINISH)])
    saved=response('I intend to edit.',raw='private reasoning</think>I intend to edit.')
    result=execute_review(model,'M1','Constitution',tmp_path,
        {'max_plaintext_reminders':1,'enable_thinking':True},replay_generation=saved)
    assert result['status']=='SELF_DECLARED_CONVERGENCE' and len(model.calls)==1
    messages=model.calls[0][0][0]
    assert messages[1]['content']=='I intend to edit.'
    assert 'private reasoning' not in json.dumps(messages)
    records=[json.loads(x) for x in (tmp_path/'generations.jsonl').read_text().splitlines()]
    assert records[0]['replayed'] is True and records[0]['turn']==0
    assert records[1]['turn']==1 and 'replayed' not in records[1]


def edit_call(text):
    return '<tool_call><function=edit_constitution><parameter=new_text>'+text+'</parameter><parameter=change_summary>Revise.</parameter></function></tool_call>'


@pytest.mark.parametrize('edit_text,continuation,expected,reverted',[
    ('Revised constitution',FINISH,'EDITED',False),
    ('Constitution',FINISH,'SELF_DECLARED_CONVERGENCE',False),
    ('Revised constitution',edit_call('Constitution')+FINISH,'EDITED',True),
])
def test_sequence_replay_preserves_edits_and_reminders(tmp_path,edit_text,continuation,expected,reverted):
    saved=[response('I intend to edit.'),response(edit_call(edit_text)),response('The changes are complete.')]
    model=Model([response(continuation)])
    result=execute_review(model,'M1','Constitution',tmp_path,
        {'max_plaintext_reminders':2},replay_generations=saved)
    assert len(model.calls)==1 and result['status']==expected
    assert result['edit_then_revert']==reverted
    assert result['content_changed']==(expected=='EDITED')
    assert result['plaintext_reminder_count']==2
    messages=model.calls[0][0][0]
    assert [m['role'] for m in messages]==['user','assistant','user','assistant','tool','assistant','user']
    assert messages[3]['tool_calls'][0]['function']['arguments']['new_text']==edit_text
    records=[json.loads(x) for x in (tmp_path/'generations.jsonl').read_text().splitlines()]
    assert [r['turn'] for r in records]==[0,1,2,3]
    assert [r.get('replayed',False) for r in records]==[True,True,True,False]


def test_replay_arguments_are_mutually_exclusive(tmp_path):
    with pytest.raises(ValueError,match='either replay_generation or replay_generations'):
        execute_review(Model([]),'M1','Constitution',tmp_path,{},
            replay_generation=response('Prose'),replay_generations=[response('Prose')])
