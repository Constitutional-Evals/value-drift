"""Optional vLLM inference in an isolated interpreter and process group.

The parent imports no vLLM or torch. JSON travels over a dedicated inherited Unix
socket; stdout/stderr go to a log, including messages from engine subprocesses.
"""
from __future__ import annotations
import gc
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_FRAME_BYTES = 64 * 1024 * 1024

class VLLMWorkerError(RuntimeError):
    pass

class VLLMSession:
    def __init__(self, checkpoint, *, python_executable='/workspace/venv-vllm/bin/python',
                 engine_options=None, seed=20260915, log_path=None, startup_timeout=600,
                 request_timeout=1800, worker_script=None):
        self.checkpoint = str(checkpoint)
        self.python_executable = str(python_executable)
        self.engine_options = dict(engine_options or {})
        if 'seed' in self.engine_options and self.engine_options['seed'] != seed:
            raise ValueError('Session seed and engine_options seed must agree')
        self.engine_options['seed'] = seed
        self.log_path = Path(log_path) if log_path else ROOT/'runs'/'inference_logs'/f'vllm-{time.time_ns()}-{os.getpid()}.log'
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self.worker_script = worker_script
        self.process = self._socket = self._stream = self._log = None
        self.startup_metadata = None
        self._request_id = 0

    def __enter__(self):
        if self.process is not None:
            raise VLLMWorkerError('Session is already open')
        # Training locals may be released after ModelSession's own cleanup.
        # Return unused parent allocations before a separate GPU worker starts,
        # without importing torch or initializing CUDA solely for cleanup.
        gc.collect()
        torch = sys.modules.get('torch')
        if torch is not None and torch.cuda.is_initialized():
            torch.cuda.empty_cache()
        parent, child = socket.socketpair()
        self._socket = parent
        parent.settimeout(self.startup_timeout)
        self._stream = parent.makefile('rwb')
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open('ab', buffering=0)
        command = [self.python_executable]
        command += [str(self.worker_script)] if self.worker_script else ['-m', 'recursive_oct.vllm_worker']
        command += ['--fd', str(child.fileno())]
        env = os.environ.copy()
        env['PATH'] = str(Path(self.python_executable).parent) + os.pathsep + env.get('PATH', '')
        env['PYTHONPATH'] = str(ROOT) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        env.setdefault('TOKENIZERS_PARALLELISM', 'false')
        env['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                stdout=self._log, stderr=subprocess.STDOUT, pass_fds=(child.fileno(),),
                start_new_session=True, cwd=ROOT, env=env)
            child.close()
            response = self._exchange({'action': 'initialize', 'checkpoint': self.checkpoint,
                                       'engine_options': self.engine_options})
            self.startup_metadata = response['metadata']
            parent.settimeout(self.request_timeout)
            return self
        except Exception:
            child.close()
            self.close()
            raise

    def _exchange(self, request):
        if self.process is None or self._stream is None:
            raise VLLMWorkerError('Session is not open')
        self._request_id += 1
        request = {**request, 'request_id': self._request_id}
        try:
            self._stream.write((json.dumps(request, ensure_ascii=False) + '\n').encode())
            self._stream.flush()
            line = self._stream.readline(MAX_FRAME_BYTES + 1)
            if not line:
                raise VLLMWorkerError('Worker exited or closed its connection')
            if len(line) > MAX_FRAME_BYTES or not line.endswith(b'\n'):
                raise VLLMWorkerError('Worker returned an oversized or incomplete frame')
            response = json.loads(line)
            if response.get('request_id') != request['request_id']:
                raise VLLMWorkerError('Worker response ID does not match request')
            if not response.get('ok'):
                raise VLLMWorkerError(f"{response.get('error_type', 'WorkerError')}: {response.get('error', 'unknown failure')}")
            return response
        except (OSError, ValueError, VLLMWorkerError) as exc:
            raise VLLMWorkerError(f'{exc}; worker log: {self.log_path}') from exc

    def generate_batch(self, conversations, *, enable_thinking=False, max_new_tokens=512,
                       temperature=0.7, top_p=0.8, top_k=20, tools=None,
                       max_input_tokens=16384, **kwargs):
        if kwargs:
            raise TypeError(f'Unsupported generation options: {sorted(kwargs)}')
        if not conversations:
            return []
        request = {'action': 'generate', 'conversations': conversations,
                   'options': {'enable_thinking': enable_thinking, 'max_new_tokens': max_new_tokens,
                       'temperature': temperature, 'top_p': top_p, 'top_k': top_k,
                       'tools': tools, 'max_input_tokens': max_input_tokens}}
        try:
            results = self._exchange(request)['results']
            required = {'text', 'raw_text', 'finish_reason', 'generated_tokens', 'batch_seconds', 'enable_thinking'}
            if len(results) != len(conversations) or any(not required.issubset(r) for r in results):
                raise VLLMWorkerError('Worker returned an incompatible result batch')
            return results
        except Exception:
            self.close()
            raise

    def close(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                self._socket.settimeout(3)
                self._exchange({'action': 'close'})
            except Exception:
                pass
        for resource in (self._stream, self._socket):
            if resource is not None:
                try: resource.close()
                except OSError: pass
        self._stream = self._socket = None
        if process is not None:
            # Kill the owned process group, including any surviving engine workers.
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            finally:
                # The direct worker can exit while engine children remain.
                # Always finish cleanup of this freshly owned process group.
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            process.wait(timeout=5)
        self.process = None
        if self._log is not None:
            self._log.close()
            self._log = None

    def __exit__(self, *exc):
        self.close()
