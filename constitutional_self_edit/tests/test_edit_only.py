import copy
import json
from pathlib import Path
import tempfile
import unittest

from recursive_oct.edit_only import generate_initial, run_plan


def call(name, **arguments):
    text = json.dumps({'name': name, 'arguments': arguments})
    return {'text': text, 'raw_text': text, 'finish_reason': 'stop', 'generated_tokens': 20}


class FakeSession:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.requests = []

    def __enter__(self): return self
    def __exit__(self, *args): pass

    def generate_batch(self, conversations, **options):
        self.requests.append(copy.deepcopy(conversations[0]))
        return [next(self.outputs)]


class EditOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'C.md').write_text('Be helpful and honest.')
        self.plan = {'label': 'screen', 'frozen': True, 'model': 'fixed-model',
                     'max_reviews': 3, 'review': {'structured_tool_calls': True,
                     'enable_thinking': False}, 'trajectories': [
                         {'label': 'short-s1', 'seed': 17, 'constitution': str(self.root/'C.md')}]}

    def run_fake(self, outputs, **kwargs):
        path = self.root/'plan.json'
        path.write_text(json.dumps(self.plan))
        self.session = FakeSession(outputs)
        return run_plan(path, self.root/'run', session_factory=lambda *a: self.session, **kwargs)

    def test_edit_then_fresh_review_converges_and_preserves_versions(self):
        revised = 'Be helpful, honest, and kind.'
        result = self.run_fake([
            call('edit_constitution', new_text=revised, change_summary='Add kindness.'),
            call('finish_editing', decision_summary='A useful addition.'),
            call('finish_editing', decision_summary='No further change.')])
        trial = result['trajectories'][0]
        self.assertEqual(trial['status'], 'SELF_DECLARED_CONVERGENCE')
        self.assertEqual(trial['completed_reviews'], 2)
        self.assertEqual(trial['edited_reviews'], 1)
        self.assertEqual(result['training_updates'], 0)
        self.assertEqual((self.root/'run/short-s1/C_001.md').read_text(), revised)
        fresh = self.session.requests[2]
        self.assertEqual([m['role'] for m in fresh], ['user', 'user'])
        self.assertIn(revised, fresh[0]['content'])
        self.assertNotIn('A useful addition.', fresh[0]['content'])
        self.assertIn('No model weights are updated', fresh[0]['content'])
        self.assertGreater(trial['reviews'][0]['metrics']['distance_from_previous'], 0)

    def test_no_op_is_unchanged_but_not_first_call_submission(self):
        result = self.run_fake([
            call('edit_constitution', new_text='Be helpful and honest.', change_summary='Retain.'),
            call('finish_editing', decision_summary='Keep.')])
        review = result['trajectories'][0]['reviews'][0]
        self.assertEqual(review['status'], 'SELF_DECLARED_CONVERGENCE')
        self.assertFalse(review['first_tool_call_submission'])

    def test_shared_constitution_path_hides_suite_and_condition_labels(self):
        shared = self.root/'neutral-workspace/constitution.md'
        self.plan['constitution_path'] = str(shared)
        self.run_fake([call('finish_editing', decision_summary='Keep.')])
        context = self.session.requests[0][0]['content']
        self.assertIn(f'Constitution file: {shared}', context)
        self.assertNotIn('short-s1', context)
        self.assertNotIn('/run/workspace/', context)
        self.assertEqual(shared.read_text(), 'Be helpful and honest.')

    def test_shared_constitution_path_must_be_absolute(self):
        self.plan['constitution_path'] = 'relative/constitution.md'
        with self.assertRaisesRegex(ValueError, 'absolute'):
            self.run_fake([])

    def test_edit_revert_is_not_convergence(self):
        self.plan['max_reviews'] = 1
        result = self.run_fake([
            call('edit_constitution', new_text='Be kind.', change_summary='Change.'),
            call('edit_constitution', new_text='Be helpful and honest.', change_summary='Revert.'),
            call('finish_editing', decision_summary='Original best.')])
        self.assertEqual(result['trajectories'][0]['status'], 'REVIEW_LIMIT')
        self.assertTrue(result['trajectories'][0]['reviews'][0]['edit_then_revert'])

    def test_truncation_is_failure_and_resume_does_not_retry(self):
        failed = call('finish_editing', decision_summary='Keep.')
        failed['finish_reason'] = 'length'
        result = self.run_fake([failed])
        self.assertEqual(result['trajectories'][0]['status'], 'EDITING_FAILURE')
        resumed = self.run_fake([], resume=True)
        self.assertEqual(resumed, result)
        self.assertEqual(len(self.session.requests), 0)

    def test_model_authored_initial_document_is_not_editing_transcript(self):
        prompt = self.root/'author.md'; prompt.write_text('Write an assistant constitution.')
        trial = self.plan['trajectories'][0]
        del trial['constitution']; trial['author_prompt'] = str(prompt)
        result = self.run_fake([
            {'text': 'Respect people.', 'raw_text': 'Respect people.', 'finish_reason': 'stop', 'generated_tokens': 4},
            call('finish_editing', decision_summary='Keep.')])
        self.assertEqual((self.root/'run/short-s1/C_000.md').read_text(), 'Respect people.')
        self.assertEqual(len(self.session.requests[1]), 2)
        self.assertNotIn('Write an assistant constitution.', self.session.requests[1][0]['content'])
        self.assertEqual(result['trajectories'][0]['status'], 'SELF_DECLARED_CONVERGENCE')

    def test_authorship_mode_saves_one_document_before_seeded_screen(self):
        prompt = self.root/'author.md'; prompt.write_text('Write a constitution.')
        path = self.root/'plan.json'; path.write_text(json.dumps(self.plan))
        model = FakeSession([{'text': 'Be considerate.', 'raw_text': 'Be considerate.',
                              'finish_reason': 'stop', 'generated_tokens': 3}])
        output = self.root/'authored'
        text = generate_initial(path, prompt, output, session_factory=lambda *a: model)
        self.assertEqual(text, (output/'C_000.md').read_text())
        with self.assertRaisesRegex(ValueError, 'new or empty'):
            generate_initial(path, prompt, output, session_factory=lambda *a: model)

    def test_interrupted_review_is_preserved_without_resampling(self):
        self.run_fake([call('finish_editing', decision_summary='Keep.')])
        directory = self.root/'run/short-s1'
        (directory/'result.json').unlink()
        progress = json.loads((directory/'progress.json').read_text())
        progress.update(status='IN_PROGRESS', completed_reviews=0, reviews=[])
        (directory/'progress.json').write_text(json.dumps(progress))
        outcome = self.run_fake([], resume=True)['trajectories'][0]
        self.assertEqual(outcome['status'], 'EDITING_FAILURE')
        self.assertEqual(outcome['failure_reason'], 'interrupted_trajectory_not_resampled')
        self.assertEqual(self.session.requests, [])


if __name__ == '__main__': unittest.main()
