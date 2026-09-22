from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recursive_oct.robustness import (
    build_adversarial_rows, build_continuation_rows, generate_adversarial_responses,
    generate_continuations, load_adversarial_instructions,
)

PROMPTS = [{'id': f'p{i}', 'prompt': f'Question {i}?'} for i in range(3)]


class LoadInstructionsTests(unittest.TestCase):
    def test_default_bank_is_nonempty_and_unique(self):
        instructions = load_adversarial_instructions()
        self.assertGreaterEqual(len(instructions), 3)
        self.assertEqual(len(set(instructions)), len(instructions))


class BuildAdversarialRowsTests(unittest.TestCase):
    def test_round_robin_ids_and_suffix_appended(self):
        instructions = ['SUFFIX_A', 'SUFFIX_B']
        rows = build_adversarial_rows(PROMPTS, instructions)
        self.assertEqual(len(rows), 3)
        ids = [r['id'] for r in rows]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(rows[0]['prompt'].endswith('SUFFIX_A'))
        self.assertTrue(rows[1]['prompt'].endswith('SUFFIX_B'))
        self.assertTrue(rows[2]['prompt'].endswith('SUFFIX_A'))
        for row in rows:
            self.assertIn('Question', row['prompt'])
            self.assertNotEqual(row['id'], row['source_prompt_id'])


class GenerateAdversarialResponsesTests(unittest.TestCase):
    def test_uses_neutral_system_and_returns_judge_ready_rows(self):
        captured = {}

        def fake_generate(checkpoint, rows, path, config, system=None):
            captured['system'] = system
            captured['rows'] = rows
            return [{**r, 'text': 'answer', 'finish_reason': 'stop', 'checkpoint': checkpoint} for r in rows]

        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows', side_effect=fake_generate):
            results = generate_adversarial_responses('M1', PROMPTS, Path(d) / 'adv.jsonl', {},
                                                      instructions=['IGNORE_EVERYTHING'])
            self.assertEqual(captured['system'], 'You are a helpful assistant.')
            self.assertEqual(len(results), 3)
            for row in results:
                self.assertEqual(row['response'], 'answer')
                self.assertIn('IGNORE_EVERYTHING', row['prompt'])


class BuildContinuationRowsTests(unittest.TestCase):
    def test_skips_missing_empty_and_truncated_prefill(self):
        prefill = [
            {'id': 'p0', 'response': 'first reply', 'finish_reason': 'stop'},
            {'id': 'p1', 'response': '', 'finish_reason': 'stop'},
            {'id': 'p2', 'response': 'cut off', 'finish_reason': 'length'},
            {'id': 'missing', 'response': 'x', 'finish_reason': 'stop'},
        ]
        prompts_by_id = {p['id']: p['prompt'] for p in PROMPTS}
        rows = build_continuation_rows(prefill, prompts_by_id)
        self.assertEqual([r['id'] for r in rows], ['p0'])
        messages = rows[0]['messages']
        self.assertEqual(messages[2]['content'], 'first reply')
        self.assertEqual(messages[2]['role'], 'assistant')
        self.assertEqual(messages[-1]['content'], 'Can you say more about that?')


class GenerateContinuationsTests(unittest.TestCase):
    def test_raises_when_no_usable_prefill(self):
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows') as generate:
            with self.assertRaises(ValueError):
                generate_continuations('M1', [{'id': 'p0', 'response': '', 'finish_reason': 'stop'}], PROMPTS,
                                       Path(d) / 'cont.jsonl', {})
            generate.assert_not_called()

    def test_generates_and_carries_context_prompt(self):
        def fake_generate(checkpoint, rows, path, config, system=None):
            return [{**r, 'text': 'more detail', 'finish_reason': 'stop', 'checkpoint': checkpoint} for r in rows]

        prefill = [{'id': 'p0', 'response': 'first reply', 'finish_reason': 'stop'}]
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows', side_effect=fake_generate):
            results = generate_continuations('M1', prefill, PROMPTS, Path(d) / 'cont.jsonl', {})
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['response'], 'more detail')
            self.assertIn('Question 0', results[0]['prompt'])
