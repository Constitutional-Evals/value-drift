import json
import sys
from types import SimpleNamespace

import pytest

from recursive_oct import generation
from recursive_oct.train import read_jsonl


def response(text='answer', finish='stop'):
    return {'text':text, 'raw_text':text, 'finish_reason':finish,
            'generated_tokens':12, 'batch_seconds':.1, 'enable_thinking':False}


def engine(monkeypatch, batches):
    calls=[]
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(manual_seed=lambda seed:None))
    class Session:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def generate_batch(self,messages,**options):
            calls.append(options)
            result=batches.pop(0)
            assert len(result)==len(messages)
            return result
    monkeypatch.setattr(generation,'inference_session',lambda *args:Session())
    return calls


def bank(n=3):
    return [{'id':f'bank-{i}','prompt':f'Situation {i}',
             'source_prompt_id':f'source-{i}','template_id':f'template-{i}'} for i in range(n)]


def quality(path):
    return json.loads(path.with_name(path.name+'.quality.json').read_text())


def test_preference_floor_reports_and_does_not_resample(monkeypatch,tmp_path):
    calls=engine(monkeypatch,[[response('chosen'),response('cut','length'),response('same')],
                              [response('rejected'),response('other'),response('same')]])
    output=tmp_path/'preferences.jsonl'
    cfg={'batch_size':4,'minimum_retained_fraction':.5}
    with pytest.raises(ValueError,match='minimum_retained_fraction'):
        generation.generate_preferences('student','teacher','constitution',bank(),output,cfg)
    report=quality(output)
    assert report['expected']==3 and report['retained']==1
    assert report['retained_fraction']==pytest.approx(1/3)
    assert len(report['excluded'])==2 and len(read_jsonl(output))==1
    raw=output.with_name(output.name+'.teacher.jsonl').read_bytes()
    with pytest.raises(ValueError,match='minimum_retained_fraction'):
        generation.generate_preferences('student','teacher','constitution',bank(),output,cfg)
    assert len(calls)==2
    assert output.with_name(output.name+'.teacher.jsonl').read_bytes()==raw


def test_default_preference_floor_preserves_low_retention(monkeypatch,tmp_path):
    engine(monkeypatch,[[response('c'),response('cut','length'),response('same')],
                        [response('r'),response('r'),response('same')]])
    output=tmp_path/'preferences.jsonl'
    assert generation.generate_preferences('s','t','c',bank(),output,{})['pairs']==1
    assert quality(output)['minimum_retained_fraction']==0


def test_reflection_floor_writes_component_report_before_failure(monkeypatch,tmp_path):
    calls=engine(monkeypatch,[[response('ok'),response('cut','length'),response('')]])
    output=tmp_path/'introspection.jsonl'
    cfg={'reflection_count':3,'interaction_count':0,'minimum_reflection_fraction':.5}
    with pytest.raises(ValueError,match='minimum_reflection_fraction'):
        generation.generate_introspection('post-dpo',bank(),output,cfg,constitution='c')
    report=quality(output)
    assert report['reflections']['expected']==3
    assert report['reflections']['retained']==1
    assert len(report['reflections']['excluded'])==2
    assert report['interactions']['expected']==0
    with pytest.raises(ValueError,match='minimum_reflection_fraction'):
        generation.generate_introspection('post-dpo',bank(),output,cfg,constitution='c')
    assert len(calls)==1


def test_interaction_floor_is_independent_and_retains_all_raw_turns(monkeypatch,tmp_path):
    calls=engine(monkeypatch,[[response('reflection')]]+
           [[response(f'a{turn}'),response(f'b{turn}','length' if turn==1 else 'stop')]
            for turn in range(4)])
    output=tmp_path/'introspection.jsonl'
    cfg={'reflection_count':1,'interaction_count':2,'interaction_turns':4,
         'minimum_reflection_fraction':1,'minimum_interaction_fraction':.75}
    with pytest.raises(ValueError,match='minimum_interaction_fraction'):
        generation.generate_introspection('dpo',bank(),output,cfg,constitution='c')
    report=quality(output)
    assert report['reflections']['retained_fraction']==1
    assert report['interactions']['retained_fraction']==.5
    assert report['interactions']['excluded'][0]['id']=='interaction-00001'
    assert report['interactions']['excluded'][0]['invalid_turn_ids']==['interaction-00001-01']
    assert len(read_jsonl(str(output)+'.interaction_turns.jsonl'))==8
    raw=output.with_name(output.name+'.interaction_turns.jsonl').read_bytes()
    with pytest.raises(ValueError,match='minimum_interaction_fraction'):
        generation.generate_introspection('dpo',bank(),output,cfg,constitution='c')
    assert len(calls)==5
    assert output.with_name(output.name+'.interaction_turns.jsonl').read_bytes()==raw


def test_provenance_separate_caps_and_a_only_targets(monkeypatch,tmp_path):
    calls=engine(monkeypatch,[[response('reflection')]]+
                  [[response(f'utterance-{i}')] for i in range(4)])
    output=tmp_path/'introspection.jsonl'
    prompts=bank(1)
    cfg={'reflection_count':1,'interaction_count':1,'interaction_turns':4,
         'max_new_tokens':1536,'interaction_max_new_tokens':768,
         'minimum_reflection_fraction':1,'minimum_interaction_fraction':1}
    generation.generate_introspection('dpo',prompts,output,cfg,constitution='c')
    assert [c['max_new_tokens'] for c in calls]==[1536,768,768,768,768]
    raw=read_jsonl(str(output)+'.reflections.jsonl')[0]
    sft=read_jsonl(output)
    for item in [raw,sft[0]]:
        assert item['source_prompt_id']=='source-0'
        assert item['template_id']=='template-0'
    assert [m['content'] for m in sft[1]['messages'] if m['role']=='assistant']==['utterance-0','utterance-2']
    assert quality(output)['interactions']['retained']==1


def test_legacy_bank_id_is_provenance_fallback(monkeypatch,tmp_path):
    engine(monkeypatch,[[response('reflection')]])
    output=tmp_path/'introspection.jsonl'
    generation.generate_introspection('dpo',[{'id':'bank-row','prompt':'question','source_prompt_id':'source'}],
        output,{'reflection_count':1,'interaction_count':0},constitution='c')
    assert read_jsonl(output)[0]['template_id']=='bank-row'


def test_half_threshold_is_inclusive(monkeypatch,tmp_path):
    engine(monkeypatch,[[response('c'),response('cut','length')],[response('r'),response('r')]])
    output=tmp_path/'preferences.jsonl'
    result=generation.generate_preferences('s','t','c',bank(2),output,{'minimum_retained_fraction':.5})
    assert result['pairs']==1 and quality(output)['meets_minimum']


def test_default_introspection_floor_and_legacy_empty_guard(monkeypatch,tmp_path):
    engine(monkeypatch,[[response('ok'),response('cut','length'),response('')],[response('')]])
    output=tmp_path/'introspection.jsonl'
    cfg={'reflection_count':3,'interaction_count':0}
    assert generation.generate_introspection('dpo',bank(),output,cfg,constitution='c')['reflection_examples']==1
    assert quality(output)['reflections']['minimum_retained_fraction']==0
    empty=tmp_path/'empty.jsonl'
    with pytest.raises(ValueError,match='Missing usable examples'):
        generation.generate_introspection('dpo',bank(),empty,{'reflection_count':1,'interaction_count':0},constitution='c')
    assert quality(empty)['reflections']['retained']==0


def test_invalid_interaction_cap_rejected_before_generation(monkeypatch,tmp_path):
    engine(monkeypatch,[])
    with pytest.raises(ValueError,match='interaction_max_new_tokens'):
        generation.generate_introspection('dpo',bank(),tmp_path/'introspection.jsonl',
            {'interaction_max_new_tokens':0},constitution='c')


def test_whitespace_only_reflection_and_interaction_are_empty(monkeypatch,tmp_path):
    engine(monkeypatch,[[response(' \n\t')],[response('valid')],[response(' \t')]])
    output=tmp_path/'introspection.jsonl'
    cfg={'reflection_count':1,'interaction_count':1,'interaction_turns':2}
    with pytest.raises(ValueError,match='Missing usable examples'):
        generation.generate_introspection('dpo',bank(),output,cfg,constitution='c')
    report=quality(output)
    assert report['reflections']['retained']==report['interactions']['retained']==0
    assert report['reflections']['excluded'][0]['reason']=='empty_response'
    assert report['interactions']['excluded'][0]['reasons']==['empty_response']
    assert read_jsonl(str(output)+'.reflections.jsonl')[0]['text']==' \n\t'


@pytest.mark.parametrize('minimum',[-.1,1.1,float('nan')])
def test_invalid_floor_rejected_before_generation(monkeypatch,tmp_path,minimum):
    engine(monkeypatch,[])
    with pytest.raises(ValueError,match='minimum_retained_fraction'):
        generation.generate_preferences('s','t','c',bank(),tmp_path/'prefs.jsonl',
                                        {'minimum_retained_fraction':minimum})
