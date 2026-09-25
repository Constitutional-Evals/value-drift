import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'agents/scripts/run_exploration_probes.py'
spec = importlib.util.spec_from_file_location('exploration_probes', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProbeTests(unittest.TestCase):
    def test_raw_capped_response_is_saved_excluded_and_not_resampled(self):
        class Fake:
            startup_metadata = {'backend': 'fake'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def generate_batch(self, conversations, **kwargs):
                return [{'text': 'answer', 'raw_text': 'answer', 'finish_reason': reason,
                         'generated_tokens': 5, 'generation_seed': 41+i}
                        for i, reason in enumerate(['stop', 'length'])]
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            config = root/'config.json'
            config.write_text(json.dumps({'frozen': True, 'model': 'fixed-model',
                                         'generation': {'batch_size': 2, 'seed': 41}}))
            prompts = root/'probes.jsonl'
            prompts.write_text('\n'.join(json.dumps({'id': str(i), 'messages': [
                {'role': 'user', 'content': 'Give advice.'}]}) for i in range(2))+'\n')
            output = root/'out'
            result = module.run(config, prompts, output, session_factory=lambda *a: Fake())
            self.assertEqual(result['status'], 'COMPLETE_WITH_FAILURES')
            self.assertEqual(result['valid_responses'], 1)
            saved = [json.loads(line) for line in (output/'responses.jsonl').read_text().splitlines()]
            self.assertEqual(saved[1]['generation_seed'], 42)
            self.assertEqual(saved[1]['exclusion_reason'], 'truncated_response')
            self.assertEqual(saved[1]['raw_text'], 'answer')
            self.assertEqual((output/'prompts.jsonl').read_bytes(), prompts.read_bytes())
            with self.assertRaisesRegex(ValueError, 'empty'):
                module.run(config, prompts, output, session_factory=lambda *a: Fake())


if __name__ == '__main__': unittest.main()
