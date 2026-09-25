"""Small real artifact fixtures protect against misleading partial-run summaries."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'agents/scripts/analyze_run.py'


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bank = [{'id': f'{c}{i}', 'category': c, 'prompt': f'Prompt {c}{i}'}
                     for c in ('general', 'naturalistic', 'value_relevant') for i in range(3)]
        self.write('bank.jsonl', self.bank)
        self.write('config.json', {'eval_prompts': str(self.root/'bank.jsonl'), 'judge': {'fixed_judge_checkpoint': 'fixed'}})
        self.write('state.json', {'status': 'TRAINING_FAILURE', 'phase': 'dpo', 'completed_rounds': 0,
                                 'failures': [{'phase': 'dpo', 'message': 'Out of memory'}]})
        (self.root/'C_000.md').write_text('Be honest and helpful.')

    def write(self, name, value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(r)+'\n' for r in value) if name.endswith('.jsonl') else json.dumps(value))

    def run_analysis(self):
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.root/'analysis'

    def test_zero_rounds_and_selection_are_faithful_and_quality_independent(self):
        out = self.run_analysis()
        selected = json.loads((out/'selected_examples.json').read_text())
        self.assertEqual(len(selected['ids']), 6)
        self.assertEqual({c: sum(i.startswith(c) for i in selected['ids']) for c in ('general','naturalistic','value_relevant')},
                         {'general': 2, 'naturalistic': 2, 'value_relevant': 2})
        summary = (out/'summary.md').read_text()
        self.assertIn('Completed rounds: 0', summary)
        self.assertIn('Out of memory', summary)
        rows = list(csv.DictReader((out/'behavior_dimensions.csv').read_text().splitlines()))
        self.assertTrue(all(int(r['missing']) == 9 for r in rows))
        self.write('eval_000.jsonl', [{'id': self.bank[0]['id'], 'text': 'quality changed', 'finish_reason':'length'}])
        self.run_analysis()
        self.assertEqual(json.loads((out/'selected_examples.json').read_text()), selected)
        self.assertIn('truncated=1', (out/'summary.md').read_text())

    def test_unchanged_submission_labels_training_not_run_and_has_no_self_pairs(self):
        self.write('state.json', {'status':'SELF_DECLARED_CONVERGENCE', 'phase':'review', 'completed_rounds':0, 'failures':[]})
        self.write('round_001/review.json', {'status':'SELF_DECLARED_CONVERGENCE', 'submitted':True, 'content_changed':False})
        out = self.run_analysis()
        summary = (out/'summary.md').read_text()
        self.assertIn('not run: unchanged submission stopped before training', summary)
        self.assertNotIn('incomplete', summary)
        self.assertNotIn('training_log.jsonl', summary)
        self.assertIn('No pre/post behavioral comparison is available', summary)
        rows = list(csv.DictReader((out/'behavior_dimensions.csv').read_text().splitlines()))
        self.assertTrue(all(r['reference']=='baseline_only' and r['paired_applicable']=='' and r['same']=='' for r in rows))
        self.assertTrue(all(r['paired_transitions']=='' for r in rows))
        self.assertTrue((out/'fixedpairedexamples.md').read_text().startswith('# Fixed baseline examples'))

    def test_duplication_retention_and_observed_training_throughput(self):
        (self.root/'C_001.md').write_text('Be honest and helpful.\n\nProtect private data.\n\nProtect private data.')
        self.write('round_001/review.json', {'status':'EDITED'})
        self.write('round_001/preferences.jsonl.quality.json', {'expected':10,'retained':8,'excluded':[{'reason':'truncated_response'},{'reason':'identical_responses'}]})
        self.write('round_001/introspection.jsonl.quality.json', {'interactions':{'expected':2,'retained':1,'excluded':[{'reasons':['empty_response','truncated_response']}]}})
        self.write('round_001/dpo/training_log.jsonl', [{'step':1,'loss':.8,'elapsed_seconds':10},{'step':2,'loss':.4,'elapsed_seconds':12}])
        self.write('round_001/dpo/training_complete.json', {'examples':8,'optimizer_steps':2,'seconds':20,'truncated_sequences':0,'config':{'epochs':1}})
        out=self.run_analysis()
        constitution=list(csv.DictReader((out/'constitutional.csv').read_text().splitlines()))[1]
        self.assertEqual(constitution['duplicate_paragraph_groups'],'1')
        self.assertEqual(constitution['duplicate_excess_words'],'3')
        stages=list(csv.DictReader((out/'training.csv').read_text().splitlines()))
        dpo=next(r for r in stages if r['stage']=='dpo')
        self.assertAlmostEqual(float(dpo['mean_logged_loss']),.6)
        self.assertEqual(float(dpo['stage_optimizer_steps_per_second']),.1)
        self.assertEqual(float(dpo['observed_optimizer_steps_per_second']),.5)
        self.assertEqual(next(r for r in stages if r['stage']=='sft')['stage_optimizer_steps_per_second'],'')
        retention=list(csv.DictReader((out/'retention.csv').read_text().splitlines()))
        preference=next(r for r in retention if r['component']=='preferences')
        self.assertEqual((preference['expected'],preference['retained'],preference['excluded_count']),('10','8','2'))
        self.assertEqual(float(preference['retained_fraction']),.8)
        self.assertEqual(next(r for r in retention if r['component']=='reflections')['retained'],'')
        interaction=next(r for r in retention if r['component']=='interactions')
        self.assertEqual(json.loads(interaction['exclusion_reasons']),{'empty_response':1,'truncated_response':1})

    def test_retention_composition_uses_frozen_bank_and_not_teacher_only_outputs(self):
        frozen=[{**r,'source':{'dataset':'source-'+r['category']}} for r in self.bank]
        self.write('protocol_inputs/train_prompts.jsonl',frozen)
        self.write('round_001/review.json',{'status':'EDITED'})
        self.write('round_001/preferences.jsonl.teacher.jsonl',[{'id':r['id'],'finish_reason':'length'} for r in frozen])
        out=self.run_analysis()
        rows=list(csv.DictReader((out/'preference_composition.csv').read_text().splitlines()))
        self.assertTrue(all(r['retained']=='' and r['excluded_count']=='' for r in rows))
        self.write('round_001/preferences.jsonl',[{'id':r['id']} for r in frozen[1:]])
        self.write('round_001/preferences.jsonl.quality.json',{'expected':9,'retained':8,'excluded':[{'id':'general0','reason':'truncated_response'}]})
        self.run_analysis()
        rows=list(csv.DictReader((out/'preference_composition.csv').read_text().splitlines()))
        general=next(r for r in rows if r['grouping']=='category' and r['stratum']=='general')
        self.assertEqual((general['expected'],general['retained'],general['excluded_count'],general['unaccounted']),('3','2','1','0'))
        self.assertAlmostEqual(float(general['retained_fraction']),2/3)
        self.assertEqual(json.loads(general['exclusion_reasons']),{'truncated_response':1})
        source=next(r for r in rows if r['grouping']=='source' and r['stratum']=='source-naturalistic')
        self.assertEqual((source['retained'],source['excluded_count']),('3','0'))

    def test_paired_ratings_do_not_turn_missing_or_na_into_zero(self):
        def judged(id_, score, status='valid'):
            return {'id': id_, 'status': status, 'dimensions': {'honesty': {'score':score}} if status=='valid' else None}
        ids = [r['id'] for r in self.bank]
        self.write('eval_000.jsonl.judged.jsonl', [judged(ids[0], 0), judged(ids[1], None), judged(ids[2], 2)])
        self.write('eval_001.jsonl.judged.jsonl', [judged(ids[0], 2), judged(ids[1], 1), judged(ids[2], None), judged(ids[3], None, 'invalid_judge')])
        self.write('round_001/review.json', {'status':'EDITED', 'metrics':{'word_count':5, 'distance_from_previous':.2}})
        self.write('round_001/dpo/training_log.jsonl', [{'step':1,'loss':.5,'elapsed_seconds':2}])
        out = self.run_analysis()
        rows = list(csv.DictReader((out/'behavior_dimensions.csv').read_text().splitlines()))
        row = next(r for r in rows if r['evaluation']=='eval_001' and r['dimension']=='honesty')
        self.assertEqual((row['score_0'],row['score_1'],row['score_2'],row['not_applicable'],row['missing']), ('0','1','1','1','6'))
        self.assertEqual((row['paired_applicable'],row['increased'],row['decreased'],row['same']), ('1','1','0','0'))
        transitions = json.loads(row['paired_transitions'])
        self.assertEqual(transitions['not_applicable->1'], 1)
        self.assertEqual(transitions['2->not_applicable'], 1)
        self.assertIn('incomplete', (out/'summary.md').read_text())
        self.assertIn('Not counted as a completed round', (out/'fixedpairedexamples.md').read_text())


if __name__ == '__main__':
    unittest.main()
