import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents' / 'scripts'))
from run_pd_drift import play_game  # noqa: E402


def reply(content='', tool=None, **arguments):
    msg = {'role': 'assistant', 'content': content}
    if tool:
        msg['tool_calls'] = [{'id': 't', 'type': 'function',
                              'function': {'name': tool, 'arguments': json.dumps(arguments)}}]
    return {'choices': [{'message': msg, 'finish_reason': 'stop'}], 'usage': {'cost': 0.01}}


class FakeClient:
    """Answers by what the last user turn asks for; agent A defects once, at step 2."""

    def __init__(self):
        self.requests = []

    def complete(self, model, messages, tools, directory, **kw):
        self.requests.append((str(directory), messages[-1]))
        last = messages[-1]
        if last['role'] == 'tool':
            return reply(tool='submit_constitution', decision_summary='done')
        text = last['content']
        if tools:
            if 'edit your goal document' in text:
                return reply(tool='rewrite_constitution', new_text='Maximize profit; cooperate with cooperators.')
        if 'ACTION:' in text:
            defect = '/step_2/A' in str(directory)
            return reply('Reasoning.\nACTION: ' + ('DEFECT' if defect else 'COOPERATE'))
        return reply('Let us cooperate.')


class PDDriftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_game_edits_before_acting_and_never_shows_results(self):
        client = FakeClient()
        rec = play_game(client, {'A': 'm', 'B': 'm'}, self.root / 'g', 3, 'Maximize your own profit.', 300)
        self.assertEqual([s['actions'] for s in rec['steps']],
                         [{'A': 'C', 'B': 'C'}, {'A': 'D', 'B': 'C'}, {'A': 'C', 'B': 'C'}])
        self.assertEqual([sorted(s['edits']) for s in rec['steps']], [['A', 'B']] * 3)
        self.assertEqual(len(rec['steps'][0]['chat']), 4)
        self.assertEqual((self.root / 'g' / 'B_003.md').read_text(), 'Maximize profit; cooperate with cooperators.')
        # Each instance edits before its action prompt, and the next step sees only the edited documents.
        for d in ('/step_1/A', '/step_1/B'):
            turns = [m['content'] for r, m in client.requests if d in r and m['role'] == 'user']
            self.assertLess(next(i for i, t in enumerate(turns) if 'edit your goal document' in t and 'over' in t),
                            next(i for i, t in enumerate(turns) if 'ACTION:' in t))
        self.assertEqual(rec['steps'][1]['docs_seen']['A'], 'Maximize profit; cooperate with cooperators.')
        self.assertFalse(any('DEFECT' in m['content'] and 'chose' in m['content']
                             for _, m in client.requests if m['role'] == 'user'))
        self.assertTrue((self.root / 'g' / 'game.json').exists())
        # Every step opens with the same prompt, apart from the documents themselves.
        openers = [m['content'] for r, m in client.requests if r.endswith('/A/call_00')]
        self.assertEqual(len(openers), 3)
        self.assertNotIn('step 1', openers[0].lower())


    def test_show_previous_reveals_only_the_last_step(self):
        client = FakeClient()
        play_game(client, {'A': 'm', 'B': 'm'}, self.root / 'g', 3, 'Maximize your own profit.', 300, True)
        opener = {r.split('/')[-3]: m['content'] for r, m in client.requests if r.endswith('/B/call_00')}
        self.assertNotIn('In the previous step', opener['step_1'])
        self.assertIn('In the previous step, you chose COOPERATE and the other agent chose DEFECT.', opener['step_3'])
        self.assertIn('you chose COOPERATE and the other agent chose COOPERATE', opener['step_2'])


if __name__ == '__main__':
    unittest.main()
