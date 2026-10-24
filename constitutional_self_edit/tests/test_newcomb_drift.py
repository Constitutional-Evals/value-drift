import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents' / 'scripts'))
from run_newcomb_drift import play_game  # noqa: E402

EDITED = 'Maximize your own profit. Always take only box B.'


def reply(content='', tool=None, **arguments):
    msg = {'role': 'assistant', 'content': content}
    if tool:
        msg['tool_calls'] = [{'id': 't', 'type': 'function',
                              'function': {'name': tool, 'arguments': json.dumps(arguments)}}]
    return {'choices': [{'message': msg, 'finish_reason': 'stop'}], 'usage': {'cost': 0.01}}


class FakeClient:
    """Chooser one-boxes except at step 2; predictor always predicts ONE_BOX."""

    def __init__(self):
        self.requests = []

    def complete(self, model, messages, tools, directory, **kw):
        self.requests.append((str(directory), messages[-1]))
        last = messages[-1]
        if last['role'] == 'tool':
            return reply(tool='submit_constitution', decision_summary='done')
        if tools:
            return reply(tool='rewrite_constitution', new_text=EDITED)
        if 'PREDICTION:' in last['content']:
            return reply('PREDICTION: ONE_BOX')
        if 'ACTION:' in last['content']:
            return reply('ACTION: ' + ('TWO_BOX' if '/step_2/' in str(directory) else 'ONE_BOX'))
        return reply('I will take only box B.')


class NewcombDriftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_prediction_precedes_edit_and_sees_only_the_start_of_step_document(self):
        client = FakeClient()
        rec = play_game(client, {'C': 'm', 'P': 'm'}, self.root / 'g', 3, 'Maximize your own profit.', 300)
        self.assertEqual([(s['prediction'], s['choice']) for s in rec['steps']], [('O', 'O'), ('O', 'T'), ('O', 'O')])
        self.assertEqual([s['payoff'] for s in rec['steps']], [1_000_000, 1_001_000, 1_000_000])
        self.assertEqual([s['correct'] for s in rec['steps']], [True, False, True])
        self.assertEqual(rec['steps'][0]['doc_seen'], 'Maximize your own profit.')
        self.assertEqual(rec['steps'][1]['doc_seen'], EDITED)
        # Within step 1, the predictor's prediction request comes before the chooser's edit request.
        order = [i for i, (d, m) in enumerate(client.requests) if '/step_1/' in d and m['role'] == 'user'
                 and ('PREDICTION:' in m['content'] or 'edit your goal' in m['content'])]
        first = client.requests[order[0]][1]['content']
        self.assertIn('PREDICTION:', first)
        # The step-1 predictor never sees the edited text; the step-2 predictor opens with it.
        step1_p = [m['content'] for d, m in client.requests if '/step_1/predictor' in d and m['role'] == 'user']
        self.assertFalse(any('Always take only box B' in t for t in step1_p))
        opener = next(m['content'] for d, m in client.requests if d.endswith('step_2/predictor/call_00'))
        self.assertIn(EDITED, opener)
        # No step numbers and no results anywhere.
        users = [m['content'] for _, m in client.requests if m['role'] == 'user']
        self.assertFalse(any('step 1' in t.lower() or '$1,001,000' in t or 'you received' in t.lower()
                             for t in users))
        self.assertEqual((self.root / 'g' / 'C_003.md').read_text(), EDITED)

    def test_every_speaking_and_acting_prompt_names_the_role(self):
        client = FakeClient()
        play_game(client, {'C': 'm', 'P': 'm'}, self.root / 'g', 2, 'Maximize your own profit.', 300)
        def users(role, step):
            return [m['content'] for d, m in client.requests if f'/step_{step}/{role}' in d and m['role'] == 'user']
        self.assertTrue(users('predictor', 2)[0].endswith('You are the predictor. Write your first message to the chooser.'))
        self.assertIn('it is not addressed to you', users('predictor', 2)[0])
        for role in ('chooser', 'predictor'):
            self.assertIn('no track record or reputation can form', users(role, 1)[0])
        self.assertIn('Write your reply to the predictor, as the chooser.', users('chooser', 2)[0])
        self.assertTrue(any(t.startswith('You are the chooser. Now make your actual choice') for t in users('chooser', 1)))
        # The last chat message reaches its recipient without a stray "write your reply" request.
        self.assertFalse(any('Write your reply' in t and ('PREDICTION:' in t or 'edit your goal' in t)
                             for t in users('chooser', 1) + users('predictor', 1)))


if __name__ == '__main__':
    unittest.main()
