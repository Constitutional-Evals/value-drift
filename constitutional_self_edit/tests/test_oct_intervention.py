import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'agents/scripts/run_oct_intervention.py'
spec = importlib.util.spec_from_file_location('oct_intervention', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeBackend:
    def __init__(self, config): self.config = config; self.calls = []; self.fail_sft = False
    def evaluate(self, checkpoint, output): self.calls.append(('evaluate', str(checkpoint)))
    def preferences(self, checkpoint, constitution, output): self.calls.append(('preferences', str(checkpoint)))
    def introspection(self, checkpoint, output): self.calls.append(('introspection', str(checkpoint)))
    def _train(self, stage, checkpoint, output):
        self.calls.append((stage, str(checkpoint)))
        if stage == 'sft' and self.fail_sft: raise RuntimeError('simulated failure')
        output.mkdir(parents=True, exist_ok=True)
        (output/'training_complete.json').write_text(json.dumps({
            'training': 'full_parameter', 'stage': stage, 'input_checkpoint': str(checkpoint),
            'output_checkpoint': str(output), 'parameters': 100, 'optimizer_reset': True}))
        return str(output)
    def dpo(self, checkpoint, data, output): return self._train('dpo', checkpoint, output)
    def sft(self, checkpoint, data, output): return self._train('sft', checkpoint, output)


class InterventionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        config = {'frozen': True, 'model': 'M0', 'teacher': 'fixed-teacher',
                  'dpo': {'learning_rate': 2e-6}, 'sft': {'learning_rate': 2e-6}}
        for key in ('constitution', 'train_prompts', 'eval_prompts', 'introspection_prompts'):
            file = self.root/(key+'.txt'); file.write_text('Fixed input')
            config[key] = str(file)
        self.config = self.root/'config.json'; self.config.write_text(json.dumps(config))
        self.backend = FakeBackend(config)

    def run_it(self, **kwargs):
        return module.run(self.config, self.root/'run', backend_factory=lambda cfg: self.backend, **kwargs)

    def test_pause_and_resume_preserve_stage_weights_and_skip_completed_work(self):
        state = self.run_it(through_stage='dpo')
        self.assertEqual(state['status'], 'PAUSED')
        self.assertEqual(state['phase'], 'introspection')
        state = self.run_it(resume=True)
        self.assertEqual(state['kind'], 'training_intervention')
        self.assertEqual(state['status'], 'COMPLETE')
        self.assertEqual(state['completed_training_rounds'], 1)
        dpo = str(self.root/'run/dpo')
        final = str(self.root/'run/final')
        self.assertEqual(self.backend.calls, [('evaluate', 'M0'), ('preferences', 'M0'),
            ('dpo', 'M0'), ('introspection', dpo), ('sft', dpo), ('evaluate', final)])

    def test_failed_sft_retries_from_dpo_without_regeneration(self):
        self.backend.fail_sft = True
        failed = self.run_it()
        self.assertEqual(failed['status'], 'FAILED')
        self.assertEqual(failed['phase'], 'sft')
        self.backend.fail_sft = False
        done = self.run_it(resume=True)
        self.assertEqual(done['status'], 'COMPLETE')
        self.assertEqual(len(done['failures']), 1)
        self.assertEqual([x[0] for x in self.backend.calls].count('dpo'), 1)
        self.assertEqual([x[0] for x in self.backend.calls].count('introspection'), 1)

    def test_config_change_cannot_silently_resume(self):
        self.run_it(through_stage='baseline')
        config = json.loads(self.config.read_text()); config['sft']['learning_rate'] = 1e-5
        self.config.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'unchanged'):
            self.run_it(resume=True)


if __name__ == '__main__': unittest.main()
