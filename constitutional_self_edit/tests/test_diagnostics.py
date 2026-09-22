"""Review-only integration fixtures; no inference/training packages are initialized."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/review_diagnostics.py'


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name,text in {'C.md':'Be honest.','recipe.md':'Proposed training recipe.',
                          'wrapper.md':'Diagnostic only. $review_instructions $constitution $checkpoint $recipe_text $tool_instructions',
                          'A.md':'Review freely; unchanged is allowed.', 'selection.md':'Record every trial.'}.items():
            (self.root/name).write_text(text)
        self.base = {'model':'M0', 'recipe_text':str(self.root/'recipe.md'), 'review':{'enable_thinking':False,'max_turns':2}}
        (self.root/'base.json').write_text(json.dumps(self.base))
        self.plan = {'frozen':True, 'label':'test-diagnostic', 'base_config':str(self.root/'base.json'),
                     'constitution':str(self.root/'C.md'), 'context_template':str(self.root/'wrapper.md'),
                     'conditions':{'A':str(self.root/'A.md')}, 'selection_rule':str(self.root/'selection.md'),
                     'schedule':[{'condition':'A','seed':s} for s in (1,2,3)]}
        self.path = self.root/'plan.json'
        self.path.write_text(json.dumps(self.plan))
        self.run = self.root/'run'
        self.calls = []
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def module(self):
        self.assertTrue(SCRIPT.exists(), 'diagnostic runner is not implemented')
        spec=importlib.util.spec_from_file_location('diagnostics_under_test',SCRIPT)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def factory(self, checkpoint, config):
        self.calls.append((checkpoint, config['seed']))
        outer=self
        class Model:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def generate_batch(self,messages,**kwargs):
                assert (outer.run/'plan.json').exists()
                assert 'Be honest.' in messages[0][0]['content']
                raw='<tool_call><function=finish_editing><parameter=decision_summary>Endorsed.</parameter></function></tool_call>'
                return [{'text':raw,'raw_text':raw,'finish_reason':'stop','generated_tokens':10}]
        return Model()

    def test_fresh_review_only_and_resume_never_resamples(self):
        module=self.module()
        with patch('recursive_oct.backend.ExperimentBackend', side_effect=AssertionError('training/evaluation backend forbidden')), \
             patch('recursive_oct.backend.train_dpo', side_effect=AssertionError('DPO forbidden')), \
             patch('recursive_oct.backend.train_sft', side_effect=AssertionError('SFT forbidden')), \
             patch('recursive_oct.backend.generate_rows', side_effect=AssertionError('evaluation forbidden')):
            result=module.run_diagnostics(self.path,self.run,session_factory=self.factory)
            self.assertEqual(result['counts'], {'DIAGNOSTIC_UNCHANGED':3})
            self.assertEqual(self.calls,[('M0',1),('M0',2),('M0',3)])
            module.run_diagnostics(self.path,self.run,resume=True,session_factory=self.factory)
        self.assertEqual(len(self.calls),3)
        self.assertFalse(list(self.run.rglob('eval*')))
        self.assertFalse(list(self.run.rglob('training*')))
        self.plan['schedule'][0]['seed']=99
        self.path.write_text(json.dumps(self.plan))
        with self.assertRaisesRegex(ValueError,'changed'):
            module.run_diagnostics(self.path,self.run,resume=True,session_factory=self.factory)
        self.assertEqual(len(self.calls),3)

    def test_edited_trial_does_not_become_next_trial_constitution(self):
        module=self.module()
        def editing(checkpoint,config):
            model=self.factory(checkpoint,config)
            original=model.generate_batch
            if config['seed']==1:
                def generate(*args,**kwargs):
                    result=original(*args,**kwargs)[0]
                    edit='<tool_call><function=edit_constitution><parameter=new_text>Revised constitution.</parameter><parameter=change_summary>Change.</parameter></function></tool_call>'
                    result['raw_text']=edit+result['raw_text']
                    return [result]
                model.generate_batch=generate
            return model
        result=module.run_diagnostics(self.path,self.run,session_factory=editing)
        self.assertEqual(result['counts'],{'DIAGNOSTIC_EDITED':1,'DIAGNOSTIC_UNCHANGED':2})
        self.assertEqual((self.run/'trial_001/workspace/constitution.md').read_text(),'Revised constitution.')
        self.assertEqual((self.run/'trial_002/workspace/constitution.md').read_text(),'Be honest.')

    def test_interrupted_startup_is_recorded_without_retry_and_remaining_continue(self):
        module=self.module()
        def interrupted(checkpoint, config):
            if config['seed']==1: raise KeyboardInterrupt()
            return self.factory(checkpoint,config)
        with self.assertRaises(KeyboardInterrupt):
            module.run_diagnostics(self.path,self.run,session_factory=interrupted)
        result=module.run_diagnostics(self.path,self.run,resume=True,session_factory=self.factory)
        self.assertEqual(self.calls,[('M0',2),('M0',3)])
        self.assertEqual(result['counts'],{'DIAGNOSTIC_STARTUP_FAILURE':1,'DIAGNOSTIC_UNCHANGED':2})
        module.run_diagnostics(self.path,self.run,resume=True,session_factory=self.factory)
        self.assertEqual(len(self.calls),2)

    def test_input_change_rejected_and_failed_generation_never_retried(self):
        module=self.module()
        def broken(checkpoint, config):
            self.calls.append((checkpoint,config['seed']))
            raise RuntimeError('CPU fixture startup failure')
        result=module.run_diagnostics(self.path,self.run,session_factory=broken)
        self.assertEqual(result['counts'],{'DIAGNOSTIC_STARTUP_FAILURE':1})
        self.assertEqual(result['status'],'DIAGNOSTIC_IN_PROGRESS')
        self.assertEqual(self.calls,[('M0',1)])
        self.assertFalse((self.run/'trial_002').exists())
        module.run_diagnostics(self.path,self.run,resume=True,session_factory=self.factory)
        self.assertEqual(len(self.calls),3)
        (self.root/'A.md').write_text('Changed instructions')
        with self.assertRaisesRegex(ValueError,'changed'):
            module.run_diagnostics(self.path,self.run,resume=True,session_factory=self.factory)


    def test_finalized_review_survives_cleanup_failure_and_resume(self):
        module=self.module()
        for edited in (False, True):
            with self.subTest(edited=edited):
                self.run=self.root/f'cleanup_{edited}'
                self.calls=[]
                @contextlib.contextmanager
                def cleanup_failure(checkpoint,config):
                    model=self.factory(checkpoint,config)
                    if edited:
                        original=model.generate_batch
                        def generate(*args,**kwargs):
                            result=original(*args,**kwargs)[0]
                            edit='<tool_call><function=edit_constitution><parameter=new_text>Changed.</parameter><parameter=change_summary>Change.</parameter></function></tool_call>'
                            result['raw_text']=edit+result['raw_text']
                            return [result]
                        model.generate_batch=generate
                    yield model
                    raise RuntimeError('cleanup failed after finish')
                result=module.run_diagnostics(self.path,self.run,session_factory=cleanup_failure)
                expected='DIAGNOSTIC_EDITED' if edited else 'DIAGNOSTIC_UNCHANGED'
                self.assertEqual(result['counts'],{expected:1})
                self.assertEqual(result['status'],'DIAGNOSTIC_IN_PROGRESS')
                trial=result['trials'][0]
                self.assertEqual(trial['review_status'],'EDITED' if edited else 'SELF_DECLARED_CONVERGENCE')
                self.assertEqual(trial['runtime_error']['phase'],'cleanup')
                self.assertTrue((self.run/'trial_001/review.json').exists())
                self.assertEqual(self.calls,[('M0',1)])
                resumed=module.run_diagnostics(self.path,self.run,resume=True,session_factory=self.factory)
                self.assertEqual(resumed['status'],'DIAGNOSTIC_COMPLETE')
                self.assertEqual(self.calls,[('M0',1),('M0',2),('M0',3)])
                self.assertEqual(resumed['trials'][0],trial)

    def test_returned_editing_failure_continues_without_infrastructure_halt(self):
        module=self.module()
        def malformed(checkpoint,config):
            model=self.factory(checkpoint,config)
            original=model.generate_batch
            if config['seed']==1:
                def generate(*args,**kwargs):
                    result=original(*args,**kwargs)[0]
                    result['finish_reason']='length'
                    return [result]
                model.generate_batch=generate
            return model
        result=module.run_diagnostics(self.path,self.run,session_factory=malformed)
        self.assertEqual(result['status'],'DIAGNOSTIC_COMPLETE')
        self.assertEqual(result['counts'],{'DIAGNOSTIC_REVIEW_FAILURE':1,'DIAGNOSTIC_UNCHANGED':2})
        self.assertFalse(result['halted_on_runtime_error'])
        self.assertEqual(self.calls,[('M0',1),('M0',2),('M0',3)])

    def test_cli_returns_nonzero_for_incomplete_then_zero_after_resume(self):
        module=self.module()
        def broken(checkpoint,config):
            raise RuntimeError('startup failure')
        args=['--plan',str(self.path),'--run',str(self.run)]
        with patch.object(module,'_session',broken):
            self.assertEqual(module.main(args),1)
        with patch.object(module,'_session',self.factory):
            self.assertEqual(module.main(args+['--resume']),0)
        self.assertEqual(self.calls,[('M0',2),('M0',3)])


if __name__=='__main__': unittest.main()
