import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from recursive_oct.vllm_session import VLLMSession, VLLMWorkerError
from recursive_oct.vllm_worker import completion_result, validate_engine_options

class VLLMAdapterTests(unittest.TestCase):
    def test_parent_cache_cleanup_precedes_worker_launch(self):
        from unittest.mock import Mock, patch
        for initialized in (True, False):
            with self.subTest(cuda_initialized=initialized), tempfile.TemporaryDirectory() as d:
                events=[]
                cuda=SimpleNamespace(
                    is_initialized=Mock(return_value=initialized),
                    empty_cache=Mock(side_effect=lambda:events.append('empty_cache')))
                def launch(*args, **kwargs):
                    self.assertEqual(events,['collect','empty_cache'] if initialized else ['collect'])
                    cuda.is_initialized.assert_called_once_with()
                    self.assertEqual(cuda.empty_cache.call_count,int(initialized))
                    raise RuntimeError('launch sentinel')
                with patch.dict(sys.modules,{'torch':SimpleNamespace(cuda=cuda)}), \
                     patch('gc.collect',side_effect=lambda:events.append('collect')), \
                     patch('recursive_oct.vllm_session.subprocess.Popen',side_effect=launch):
                    session=VLLMSession('fake',log_path=Path(d)/'log')
                    with self.assertRaisesRegex(RuntimeError,'launch sentinel'):
                        session.__enter__()

    def test_parent_cache_cleanup_does_not_import_torch(self):
        import builtins
        from unittest.mock import patch
        original_import=builtins.__import__
        def guarded_import(name,*args,**kwargs):
            if name=='torch' or name.startswith('torch.'):
                self.fail('Cache cleanup imported torch')
            return original_import(name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules):
            sys.modules.pop('torch',None)
            with patch('builtins.__import__',side_effect=guarded_import), \
                 patch('recursive_oct.vllm_session.subprocess.Popen',side_effect=RuntimeError('launch sentinel')):
                session=VLLMSession('fake',log_path=Path(d)/'log')
                with self.assertRaisesRegex(RuntimeError,'launch sentinel'):
                    session.__enter__()

    def test_output_eos_and_thinking_semantics(self):
        class Tokenizer:
            def decode(self, ids, skip_special_tokens=False):
                self.ids=ids
                return '</think><tool_call>action</tool_call>'
        tok=Tokenizer()
        output=SimpleNamespace(token_ids=[1,2,99],finish_reason='stop',stop_reason=99)
        result=completion_result(output,tok,{99},True,1.25)
        self.assertEqual(tok.ids,[1,2])
        self.assertEqual(result['generated_tokens'],3)
        self.assertEqual(result['text'],'<tool_call>action</tool_call>')
        self.assertEqual(result['finish_reason'],'stop')
        self.assertEqual(result['batch_seconds'],1.25)
    def test_length_is_never_changed_to_stop(self):
        tok=SimpleNamespace(decode=lambda ids,skip_special_tokens=False:'unfinished')
        result=completion_result(SimpleNamespace(token_ids=[1],finish_reason='length',stop_reason=None),tok,{99},True,.2)
        self.assertEqual(result['finish_reason'],'length')
        self.assertEqual(result['text'],'')
    def test_quantization_and_unsafe_options_rejected(self):
        for options in [{'quantization':'awq'},{'trust_remote_code':True},{'unknown_flag':1}]:
            with self.assertRaises(ValueError): validate_engine_options(options)
    def test_socket_worker_lifecycle_and_logs(self):
        fake='''import json,socket,sys\nfd=int(sys.argv[sys.argv.index("--fd")+1]);s=socket.socket(fileno=fd);f=s.makefile("rwb")\nprint("worker noisy stdout",flush=True)\nfor line in f:\n r=json.loads(line);action=r["action"]\n if action=="initialize": out={"ok":True,"metadata":{"backend":"fake"}}\n elif action=="generate": out={"ok":True,"results":[{"text":"answer","raw_text":"answer","finish_reason":"stop","generated_tokens":1,"batch_seconds":0.1,"enable_thinking":False} for _ in r["conversations"]]}\n else: out={"ok":True}\n out["request_id"]=r["request_id"];f.write((json.dumps(out)+"\\n").encode());f.flush()\n if action=="close": break\n'''
        with tempfile.TemporaryDirectory() as d:
            fakepath=Path(d)/'fake.py';fakepath.write_text(fake);log=Path(d)/'log.txt'
            with VLLMSession('M0',python_executable=sys.executable,worker_script=fakepath,log_path=log,startup_timeout=5,request_timeout=5) as session:
                result=session.generate_batch([[{'role':'user','content':'Hello'}]])
                process=session.process
                self.assertEqual(result[0]['text'],'answer')
                self.assertEqual(session.startup_metadata['backend'],'fake')
            self.assertIsNotNone(process.poll())
            self.assertIn('worker noisy stdout',log.read_text())
    def test_worker_crash_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'crash.py';path.write_text('raise RuntimeError("fake startup crash")')
            session=VLLMSession('M0',python_executable=sys.executable,worker_script=path,log_path=Path(d)/'log',startup_timeout=5)
            with self.assertRaises(VLLMWorkerError): session.__enter__()
            self.assertIsNone(session.process)

    def test_worker_path_starts_with_selected_interpreter_bin(self):
        worker_code=('import os,json,socket,sys\n'
                     's=socket.socket(fileno=int(sys.argv[-1]));f=s.makefile("rwb")\n'
                     'for line in f:\n'
                     ' r=json.loads(line);out={"ok":True,"request_id":r["request_id"],"metadata":{"path":os.environ.get("PATH","")}}\n'
                     ' f.write((json.dumps(out)+"\\n").encode());f.flush()\n'
                     ' if r["action"]=="close": break\n')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'worker.py';path.write_text(worker_code)
            with VLLMSession('fake',python_executable=sys.executable,worker_script=path,
                             log_path=Path(d)/'log',startup_timeout=5) as session:
                first=session.startup_metadata['path'].split(os.pathsep)[0]
                self.assertEqual(first,str(Path(sys.executable).parent))

    def test_close_kills_owned_child_even_if_direct_worker_exits(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d); ready=directory/'child.pid'
            child_code=("import os,signal,time; from pathlib import Path; "
                        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                        f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(30)")
            worker=directory/'worker.py'
            worker.write_text(
                'import subprocess,sys,socket,json,time\nfrom pathlib import Path\n'
                f'p=subprocess.Popen([sys.executable,"-c",{child_code!r}])\n'
                f'while not Path({str(ready)!r}).exists() or not Path({str(ready)!r}).read_text(): time.sleep(.01)\n'
                's=socket.socket(fileno=int(sys.argv[-1]));f=s.makefile("rwb")\n'
                'for line in f:\n'
                ' r=json.loads(line);out={"request_id":r["request_id"],"ok":True,"metadata":{}}\n'
                ' f.write((json.dumps(out)+"\\n").encode());f.flush()\n'
                ' if r["action"]=="close": break\n')
            group=None
            try:
                with VLLMSession('fake',python_executable=sys.executable,worker_script=worker,
                                 log_path=directory/'log',startup_timeout=5) as session:
                    group=session.process.pid
                    child_pid=int(ready.read_text())
                # A killed orphan may remain briefly as a zombie on some hosts;
                # it no longer executes or retains GPU allocations.
                for _ in range(20):
                    result=subprocess.run(['ps','-p',str(child_pid),'-o','stat='],capture_output=True,text=True)
                    state=result.stdout.strip()
                    if not state or state.startswith('Z'):
                        break
                    time.sleep(.01)
                self.assertTrue(not state or state.startswith('Z'), f'Owned child survived close: {state}')
            finally:
                if group is not None:
                    try: os.killpg(group,signal.SIGKILL)
                    except ProcessLookupError: pass

    def test_template_mapping_is_normalized_and_input_limit_is_real(self):
        from recursive_oct.vllm_worker import render_token_prompts
        class Tokenizer:
            def apply_chat_template(self,messages,**kwargs):
                self.kwargs=kwargs
                return {'input_ids': [[1,2,3]], 'attention_mask': [[1,1,1]]}
        tok=Tokenizer();options={'enable_thinking':True,'tools':[{'type':'function'}], 'max_new_tokens':4,'max_input_tokens':3}
        result=render_token_prompts(tok,[[{'role':'user','content':'test'}]],options,8)
        self.assertEqual(result,[{'prompt_token_ids':[1,2,3]}])
        self.assertFalse(tok.kwargs['return_dict'])
        self.assertTrue(tok.kwargs['enable_thinking'])
        with self.assertRaises(ValueError): render_token_prompts(tok,[[]],{**options,'max_input_tokens':2},8)
        with self.assertRaises(ValueError): render_token_prompts(tok,[[]],options,6)

    def test_request_seeds_are_distinct_and_continue_across_batches(self):
        from unittest.mock import patch
        from recursive_oct.vllm_worker import WorkerEngine
        fake_vllm=SimpleNamespace(SamplingParams=lambda **kwargs:SimpleNamespace(**kwargs))
        seen=[]
        def generate(prompts,sampling_params,use_tqdm=False):
            seen.extend(p.seed for p in sampling_params)
            return [SimpleNamespace(outputs=[SimpleNamespace(token_ids=[1,99],finish_reason='stop',stop_reason=99)]) for _ in prompts]
        worker=object.__new__(WorkerEngine)
        worker.options={'seed':40,'max_model_len':100}
        worker.request_counter=0
        worker.eos_ids={99}
        worker.tokenizer=SimpleNamespace(apply_chat_template=lambda *a,**k:[1,2],decode=lambda *a,**k:'ok')
        worker.llm=SimpleNamespace(generate=generate)
        options={'enable_thinking':False,'max_new_tokens':8,'max_input_tokens':20,'tools':None,'temperature':.7,'top_p':.8,'top_k':20}
        with patch.dict(sys.modules,{'vllm':fake_vllm}):
            first=worker.generate_batch([[],[]],options)
            second=worker.generate_batch([[]],options)
        self.assertEqual(seen,[40,41,42])
        self.assertEqual([r['generation_seed'] for r in first+second],[40,41,42])
