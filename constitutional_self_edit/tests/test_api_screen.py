import json
import tempfile
import unittest
from pathlib import Path

from recursive_oct.api_screen import Budget, BudgetLimit, run_review


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, tools, directory, config, phase):
        self.requests.append(json.loads(json.dumps(messages)))
        return next(self.responses)


def response(name=None, args=None, content=None, finish='tool_calls'):
    msg = {'role': 'assistant', 'content': content}
    if name:
        msg['tool_calls'] = [{'id': 'call1', 'type': 'function',
                              'function': {'name': name, 'arguments': json.dumps(args)}}]
    return {'choices': [{'message': msg, 'finish_reason': finish}]}


class ScreenTests(unittest.TestCase):
    def test_budget_reserves_before_dispatch_and_keeps_unknown_charge(self):
        with tempfile.TemporaryDirectory() as d:
            b = Budget(Path(d)/'ledger.json', 1)
            b.reserve('a', .7)
            with self.assertRaises(BudgetLimit):
                b.reserve('b', .4)
            b.settle('a', .2)
            b.reserve('b', .4)
            self.assertAlmostEqual(b.accounted(), .6)
            self.assertAlmostEqual(Budget(Path(d)/'ledger.json', 1).accounted(), .6)

    def test_uncapped_explicit_finish_converges(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient([response('finish_editing', {'decision_summary': 'Retain.'})])
            out = run_review(client, Path(d), 'Be kind.', {'context': 'neutral', 'reflection': 'direct'})
            self.assertEqual(out['status'], 'SELF_DECLARED_CONVERGENCE')

    def test_truncated_finish_is_not_convergence(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient([response('finish_editing', {'decision_summary': 'Retain.'}, finish='length')])
            out = run_review(client, Path(d), 'Be kind.', {'context': 'neutral', 'reflection': 'direct'})
            self.assertEqual(out['status'], 'EDITING_FAILURE')

    def test_reflection_then_edit_then_finish_preserves_reasoning_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            app = response(content='Retain kindness; clarify honesty.', finish='stop')
            app['choices'][0]['message']['reasoning_details'] = [{'type': 'reasoning.encrypted', 'data': 'test'}]
            client = FakeClient([app, response('edit_constitution', {'new_text': 'Be kind and honest.', 'change_summary': 'Add honesty.'}), response('finish_editing', {'decision_summary': 'Submit.'})])
            out = run_review(client, Path(d), 'Be kind.', {'context': 'successor', 'reflection': 'values'})
            self.assertEqual(out['status'], 'EDITED')
            self.assertEqual((Path(d)/'submitted.md').read_text(), 'Be kind and honest.')
            self.assertEqual(client.requests[1][-2]['reasoning_details'], app['choices'][0]['message']['reasoning_details'])

    def test_edit_then_revert_does_not_converge(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient([response('edit_constitution', {'new_text': 'Be fair.', 'change_summary': 'Change.'}), response('edit_constitution', {'new_text': 'Be kind.', 'change_summary': 'Restore.'}), response('finish_editing', {'decision_summary': 'Submit.'})])
            out = run_review(client, Path(d), 'Be kind.', {'context': 'neutral', 'reflection': 'direct'})
            self.assertEqual(out['status'], 'EDITED')
            self.assertTrue(out['edit_then_revert'])

    def test_trajectory_origin_is_distinct_from_previous_document(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient([response('finish_editing', {'decision_summary': 'Retain.'})])
            out = run_review(client, Path(d), 'Be kind and honest.', {'context': 'neutral', 'reflection': 'direct'}, initial_constitution='Be kind.')
            self.assertEqual(out['distance_from_previous'], 0)
            self.assertGreater(out['distance_from_initial'], 0)

if __name__ == '__main__':
    unittest.main()
