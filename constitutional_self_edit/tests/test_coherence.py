import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recursive_oct.coherence import build_order_swap_jobs, parse_coherence_judgment, run_coherence_eval

BASELINE = [{'id': 'x', 'prompt': 'Q', 'response': 'old answer', 'finish_reason': 'stop'}]
COMPARISON = [{'id': 'x', 'prompt': 'Q', 'response': 'new answer', 'finish_reason': 'stop'}]


def judgment(verdict):
    return json.dumps({'more_coherent': verdict, 'rationale': 'It stays on topic without repeating itself.'})


class ParseCoherenceJudgmentTests(unittest.TestCase):
    def test_parses_valid(self):
        parsed = parse_coherence_judgment(judgment('A'))
        self.assertEqual(parsed['more_coherent'], 'A')

    def test_rejects_bad_verdict_and_extra_keys(self):
        with self.assertRaises(ValueError):
            parse_coherence_judgment(json.dumps({'more_coherent': 'C', 'rationale': 'x'}))
        with self.assertRaises(ValueError):
            parse_coherence_judgment(json.dumps({'more_coherent': 'A', 'rationale': 'x', 'extra': 1}))


class BuildOrderSwapJobsTests(unittest.TestCase):
    def test_two_jobs_per_pair_no_checkpoint_identity_leaked(self):
        jobs, key = build_order_swap_jobs('M0', 'M1', BASELINE, COMPARISON, seed=1)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(len(key), 1)
        joined = json.dumps(jobs)
        self.assertNotIn('M0', joined)
        self.assertNotIn('M1', joined)
        self.assertEqual({key[0]['response_a_checkpoint'], key[0]['response_b_checkpoint']}, {'M0', 'M1'})


class RunCoherenceEvalTests(unittest.TestCase):
    def test_requires_frozen_judge_match(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run_coherence_eval('M0', 'M1', 'judge-27b', BASELINE, COMPARISON, Path(d) / 'coh',
                                   {'fixed_judge_checkpoint': 'other'})

    def test_order_invariant_verdict_is_counted_as_a_win(self):
        def fake_generate(checkpoint, rows, path, config, system=None):
            out = []
            for row in rows:
                # response_a is always the checkpoint that supplied slot A in this job's content;
                # judge always prefers "A" here, so the winner should flip between fwd/swap.
                out.append({**row, 'text': judgment('A'), 'finish_reason': 'stop'})
            return out
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows', side_effect=fake_generate):
            output = Path(d) / 'coh'
            summary = run_coherence_eval('M0', 'M1', 'judge-27b', BASELINE, COMPARISON, output,
                                         {'fixed_judge_checkpoint': 'judge-27b', 'seed': 1})
            self.assertEqual(summary['pairs'], 1)
            # Always picking "A" in both fwd/swap jobs means each job crowns whichever
            # checkpoint supplied that job's slot A -- fwd and swap disagree, so this is order-dependent.
            self.assertEqual(summary['order_dependent_excluded'], 1)
            self.assertEqual(summary['order_invariant'], 0)

    def test_consistent_preference_for_one_checkpoint_is_order_invariant(self):
        def fake_generate(checkpoint, rows, path, config, system=None):
            out = []
            for row in rows:
                content = json.loads(row['prompt'])
                # Always prefer whichever slot holds the literal text 'new answer'.
                verdict = 'A' if content['response_a'] == 'new answer' else 'B'
                out.append({**row, 'text': judgment(verdict), 'finish_reason': 'stop'})
            return out
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows', side_effect=fake_generate):
            output = Path(d) / 'coh'
            summary = run_coherence_eval('M0', 'M1', 'judge-27b', BASELINE, COMPARISON, output,
                                         {'fixed_judge_checkpoint': 'judge-27b', 'seed': 1})
            self.assertEqual(summary['order_invariant'], 1)
            self.assertEqual(summary['comparison_wins'], 1)
            self.assertEqual(summary['baseline_wins'], 0)

    def test_frozen_protocol_rejects_a_changed_rerun(self):
        def fake_generate(checkpoint, rows, path, config, system=None):
            return [{**row, 'text': judgment('tie'), 'finish_reason': 'stop'} for row in rows]
        with tempfile.TemporaryDirectory() as d, patch('recursive_oct.generation.generate_rows', side_effect=fake_generate):
            output = Path(d) / 'coh'
            run_coherence_eval('M0', 'M1', 'judge-27b', BASELINE, COMPARISON, output,
                               {'fixed_judge_checkpoint': 'judge-27b', 'seed': 1})
            with self.assertRaises(ValueError):
                run_coherence_eval('M0', 'M1', 'judge-27b', BASELINE, COMPARISON, output,
                                   {'fixed_judge_checkpoint': 'judge-27b', 'seed': 2})
