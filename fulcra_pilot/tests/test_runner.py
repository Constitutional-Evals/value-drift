import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pilot import VALUES
from run_openrouter import run, parse_json, validate_legacy, legacy_module


class RunnerTests(unittest.TestCase):
    def test_legacy_rejects_invalid_scale(self):
        axes = legacy_module(Path(__file__).resolve().parents[2] / 'kl_evals/evals/axes.py')
        with self.assertRaises(ValueError):
            validate_legacy({'scores': {a.key: 8 for a in axes.AXES}}, axes)

    def test_fenced_json(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {'a': 1})

    def test_resume_uses_saved_replies_and_preserves_disagreement(self):
        axes_path = Path(__file__).resolve().parents[2] / 'kl_evals/evals/axes.py'
        axes = legacy_module(axes_path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chain = root / 'chain'
            chain.mkdir()
            (chain / 'C_000.md').write_text('Respect user choice.')
            args = argparse.Namespace(chain=chain, axes_file=axes_path, model='test/model',
                out=root / 'out', repeats=1, temperature=0.3, max_tokens=6000,
                dry_run=False, key_file=None)
            annotation = {'values': {k: {'label': 'not_evidenced', 'evidence': [],
                'rationale': 'Synthetic fixture only.'} for k in VALUES}}

            def reply(content):
                return {'model': 'test/model', 'choices': [{'finish_reason': 'stop',
                    'message': {'content': json.dumps(content)}}]}

            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'fake'}):
                with patch('run_openrouter.call_api', side_effect=[reply(annotation),
                    reply({'scores': {a.key: 4 for a in axes.AXES}})]) as api:
                    run(args)
                    self.assertEqual(api.call_count, 2)
                with patch('run_openrouter.call_api') as api:
                    run(args)
                    api.assert_not_called()
            self.assertTrue((args.out / 'report.md').exists())
            self.assertEqual(len(json.loads((args.out / 'results.json').read_text())), 2)
            args.temperature = 0.8
            with self.assertRaises(ValueError):
                run(args)
