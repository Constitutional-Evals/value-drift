import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from recursive_oct.judging import parse_judgment, judge_responses
from recursive_oct.measurement import BEHAVIOR_RUBRIC


def valid_result():
    return {'dimensions': {d: {'score': 1, 'evidence': 'The response offers a qualified answer.', 'uncertainty': 'Its factual claims were not independently checked.'} for d in BEHAVIOR_RUBRIC['dimensions']}, 'refusal_present': False, 'factual_claims_unverified': True, 'rationale': 'Separate dimensions remain exploratory.'}

class JudgeTests(unittest.TestCase):
    def test_parse_json_and_single_fence(self):
        raw=json.dumps(valid_result())
        self.assertEqual(parse_judgment(raw),valid_result())
        self.assertEqual(parse_judgment('```json\n'+raw+'\n```'),valid_result())
    def test_invalid_scores_and_partial_json_are_rejected(self):
        for score in [True,'2',3,-1]:
            obj=valid_result(); obj['dimensions']['honesty']['score']=score
            with self.assertRaises(ValueError): parse_judgment(json.dumps(obj))
        obj=valid_result(); del obj['dimensions']['honesty']
        with self.assertRaises(ValueError): parse_judgment(json.dumps(obj))
        with self.assertRaises(ValueError): parse_judgment('Here is my score: '+json.dumps(valid_result()))
        with self.assertRaises(ValueError): parse_judgment('{"dimensions":{},"dimensions":{}}')
    def test_frozen_identity_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): judge_responses('student-round-1',[],Path(d)/'scores.jsonl',{'fixed_judge_checkpoint':'M0'})
    def test_no_identity_or_constitution_in_model_inputs_and_invalid_not_scored(self):
        seen={}
        def fake_generate(checkpoint,rows,path,config,system=None):
            seen.update(checkpoint=checkpoint,rows=rows,system=system,config=config)
            out=[]
            for i,row in enumerate(rows):
                out.append({**row,'text':json.dumps(valid_result()) if i==0 else 'malformed','finish_reason':'stop','checkpoint':checkpoint})
            Path(path).write_text(''.join(json.dumps(r)+'\n' for r in out))
            return out
        rows=[{'id':'SECRET_PROMPT_ID_1','checkpoint':'SECRET_EVOLVING_CHECKPOINT','prompt':'How should I discuss a disagreement?','response':'Talk respectfully.','constitution':'SECRET_CONSTITUTION'}, {'id':'SECRET_PROMPT_ID_2','checkpoint':'SECRET_EVOLVING_CHECKPOINT','prompt':'Explain gravity.','response':'Mass attracts mass.'}, {'id':'SECRET_PROMPT_ID_3','checkpoint':'SECRET_EVOLVING_CHECKPOINT','prompt':'Explain time.','response':'Time is','finish_reason':'length'}]
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows',side_effect=fake_generate):
            path=Path(d)/'scores.jsonl'
            stats=judge_responses('M0',rows,path,{'fixed_judge_checkpoint':'M0'})
            model_input=json.dumps(seen['rows'])+seen['system']
            for secret in ['SECRET_PROMPT_ID','SECRET_EVOLVING_CHECKPOINT','SECRET_CONSTITUTION']:
                self.assertNotIn(secret,model_input)
            self.assertEqual(stats['valid'],1)
            self.assertEqual(stats['invalid_judge'],1)
            self.assertEqual(stats['invalid_source'],1)
            self.assertEqual(seen['config']['temperature'],0)
            results=[json.loads(x) for x in path.read_text().splitlines()]
            self.assertTrue(all(r['dimensions'] is None for r in results if r['status']!='valid'))
            self.assertNotIn('alignment_score',stats)
            with self.assertRaises(ValueError): judge_responses('M0',rows,path,{'fixed_judge_checkpoint':'M0','seed':8})

    def test_nonstring_source_is_marked_invalid_without_generation(self):
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows') as generate:
            stats=judge_responses('M0',[{'id':'bad','prompt':'Question','response':[]}],Path(d)/'scores.jsonl',{'fixed_judge_checkpoint':'M0'})
            self.assertEqual(stats['invalid_source'],1)
            generate.assert_not_called()

    def test_truncated_judge_is_missing_even_with_parseable_json(self):
        def fake_generate(checkpoint,rows,path,config,system=None):
            return [{**r,'text':json.dumps(valid_result()),'finish_reason':'length'} for r in rows]
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows',side_effect=fake_generate):
            stats=judge_responses('M0',[{'id':'a','prompt':'Question','response':'Answer'}],Path(d)/'scores.jsonl',{'fixed_judge_checkpoint':'M0'})
            self.assertEqual(stats['invalid_judge'],1)
            self.assertEqual(stats['dimensions']['honesty']['missing'],1)
            self.assertEqual(stats['valid'],0)
