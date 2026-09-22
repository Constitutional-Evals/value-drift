import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recursive_oct.revealed_preferences import (
    compute_elo, load_traits, parse_trait_choice, render_trait_choice_prompt,
    run_revealed_preference_eval, sample_trait_trials,
)


def valid_judgment(chosen='trait_a'):
    return {'chosen_trait': chosen, 'rationale': 'The reply uses short, pointed remarks consistent with this trait.'}


PROMPTS = [{'id': f'p{i}', 'prompt': f'Question {i}'} for i in range(3)]


class TraitLoadingTests(unittest.TestCase):
    def test_default_bank_has_enough_unique_traits(self):
        traits = load_traits()
        self.assertGreaterEqual(len(traits), 10)
        self.assertEqual(len(set(traits)), len(traits))

    def test_rejects_duplicate_traits(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'traits.json'
            path.write_text(json.dumps({'traits': ['warm', 'warm']}))
            with self.assertRaises(ValueError):
                load_traits(path)


class SamplingTests(unittest.TestCase):
    def test_deterministic_and_distinct_traits_per_trial(self):
        traits = ['a', 'b', 'c', 'd']
        first = sample_trait_trials(traits, PROMPTS, 6, seed=1)
        second = sample_trait_trials(traits, PROMPTS, 6, seed=1)
        self.assertEqual(first, second)
        for trial in first:
            self.assertNotEqual(trial['trait_a'], trial['trait_b'])
            self.assertIn(trial['trait_a'], traits)
            self.assertIn(trial['trait_b'], traits)
        self.assertEqual([t['prompt_id'] for t in first], ['p0', 'p1', 'p2', 'p0', 'p1', 'p2'])

    def test_different_seed_can_change_sequence(self):
        traits = ['a', 'b', 'c', 'd']
        first = sample_trait_trials(traits, PROMPTS, 8, seed=1)
        second = sample_trait_trials(traits, PROMPTS, 8, seed=2)
        self.assertNotEqual(first, second)

    def test_requires_prompts(self):
        with self.assertRaises(ValueError):
            sample_trait_trials(['a', 'b'], [], 1)


class RenderTests(unittest.TestCase):
    def test_substitutes_both_traits(self):
        rendered = render_trait_choice_prompt('sarcastic', 'warm')
        self.assertIn('sarcastic', rendered)
        self.assertIn('warm', rendered)


class ParseTraitChoiceTests(unittest.TestCase):
    def test_parses_valid_and_fenced(self):
        raw = json.dumps(valid_judgment())
        self.assertEqual(parse_trait_choice(raw), valid_judgment())
        self.assertEqual(parse_trait_choice('```json\n' + raw + '\n```'), valid_judgment())

    def test_rejects_bad_chosen_trait_and_long_rationale(self):
        obj = valid_judgment(); obj['chosen_trait'] = 'trait_c'
        with self.assertRaises(ValueError):
            parse_trait_choice(json.dumps(obj))
        obj = valid_judgment(); obj['rationale'] = ' '.join(['word'] * 30)
        with self.assertRaises(ValueError):
            parse_trait_choice(json.dumps(obj))
        with self.assertRaises(ValueError):
            parse_trait_choice('{"chosen_trait":"trait_a","chosen_trait":"trait_b","rationale":"x"}')

    def test_unclear_is_a_valid_choice(self):
        self.assertEqual(parse_trait_choice(json.dumps(valid_judgment('unclear')))['chosen_trait'], 'unclear')


class EloTests(unittest.TestCase):
    def test_unplayed_traits_stay_at_initial(self):
        elo = compute_elo(['a', 'b', 'c'], [])
        self.assertEqual(elo, {'a': 1000.0, 'b': 1000.0, 'c': 1000.0})

    def test_consistent_winner_gains_rating(self):
        elo = compute_elo(['a', 'b'], [('a', 'b', 'a')] * 10)
        self.assertGreater(elo['a'], 1000.0)
        self.assertLess(elo['b'], 1000.0)

    def test_symmetric_win_loss_cancels_zero_sum(self):
        elo = compute_elo(['a', 'b'], [('a', 'b', 'a'), ('a', 'b', 'b')])
        self.assertAlmostEqual(elo['a'] + elo['b'], 2000.0)

    def test_rejects_unknown_trait_and_bad_winner(self):
        with self.assertRaises(ValueError):
            compute_elo(['a', 'b'], [('a', 'c', 'a')])
        with self.assertRaises(ValueError):
            compute_elo(['a', 'b'], [('a', 'b', 'x')])


class RunRevealedPreferenceEvalTests(unittest.TestCase):
    def test_requires_frozen_judge_match(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run_revealed_preference_eval('M1', 'judge-27b', PROMPTS, Path(d) / 'rp',
                                             {'fixed_judge_checkpoint': 'other-judge'})

    def test_full_flow_excludes_no_leak_and_computes_elo(self):
        calls = []

        def fake_generate(checkpoint, rows, path, config, system=None):
            calls.append({'checkpoint': checkpoint, 'rows': rows, 'system': system})
            out = []
            for i, row in enumerate(rows):
                if checkpoint == 'judge-27b':
                    text = json.dumps(valid_judgment('trait_a' if i % 2 == 0 else 'trait_b'))
                    out.append({**row, 'text': text, 'finish_reason': 'stop'})
                else:
                    out.append({**row, 'text': f'response {i}', 'finish_reason': 'stop'})
            Path(path).write_text(''.join(json.dumps(r) + '\n' for r in out))
            return out

        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows', side_effect=fake_generate):
            output = Path(d) / 'rp'
            summary = run_revealed_preference_eval('M1', 'judge-27b', PROMPTS, output,
                                                    {'fixed_judge_checkpoint': 'judge-27b', 'trials': 6, 'seed': 1})
            self.assertEqual(summary['trials'], 6)
            self.assertEqual(summary['valid'], 6)
            self.assertEqual(summary['decided'], 6)
            self.assertEqual(set(summary['elo']), set(load_traits()))
            student_call = next(c for c in calls if c['checkpoint'] == 'M1')
            self.assertIsNone(student_call['system'])
            judge_call = next(c for c in calls if c['checkpoint'] == 'judge-27b')
            judge_text = json.dumps(judge_call['rows'])
            self.assertNotIn('M1', judge_text)
            self.assertNotIn('Question', judge_text)  # judge never sees the source prompt text

    def test_frozen_trial_protocol_rejects_a_changed_rerun(self):
        def fake_generate(checkpoint, rows, path, config, system=None):
            out = [{**row, 'text': 'x', 'finish_reason': 'stop'} for row in rows]
            Path(path).write_text(''.join(json.dumps(r) + '\n' for r in out))
            return out

        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows', side_effect=fake_generate):
            output = Path(d) / 'rp'
            run_revealed_preference_eval('M1', 'judge-27b', PROMPTS, output,
                                         {'fixed_judge_checkpoint': 'judge-27b', 'trials': 4, 'seed': 1})
            with self.assertRaises(ValueError):
                run_revealed_preference_eval('M1', 'judge-27b', PROMPTS, output,
                                             {'fixed_judge_checkpoint': 'judge-27b', 'trials': 5, 'seed': 1})
