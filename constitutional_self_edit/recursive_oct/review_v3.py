"""The training loop's review step: one review with the elicitation harness (prompts v3), served by vLLM.

It uses the same prompts, tools, model entry, server flags, and sampling as the stage 07 value-map
chains, so the untrained model's first review matches their first generation, and those chains
(editing only, no training) serve as the loop's controls.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Stage 07's `vllm serve` flags (agents/notes/06_selfhost_pilot/NOTES.md).
SERVER_FLAGS = ('--max-model-len', '131072', '--language-model-only', '--reasoning-parser', 'qwen3',
                '--enable-auto-tool-choice', '--tool-call-parser', 'qwen3_xml', '--gpu-memory-utilization', '0.92',
                '--max-num-seqs', '64', '--enable-prefix-caching')
REFLECT_V3 = {'name': 'reflect', 'deliberation': 'reflect', 'prompts': 'v3'}


class VLLMServer:
    """`vllm serve <checkpoint>` on localhost, in its own process group, stopped with its children on exit."""

    def __init__(self, checkpoint, *, vllm_bin, served_name, log_path, port=8000, flags=SERVER_FLAGS,
                 startup_timeout=1800):
        self.command = [str(vllm_bin), 'serve', str(checkpoint), '--served-model-name', served_name,
                        '--host', '127.0.0.1', '--port', str(port), *flags]
        self.base_url = f'http://127.0.0.1:{port}/v1/'
        self.log_path, self.startup_timeout = Path(log_path), startup_timeout
        self.process = None

    def __enter__(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open('ab')
        # vLLM compiles kernels at startup with tools (ninja) from its own environment's bin directory.
        env = dict(os.environ, PATH=str(Path(self.command[0]).parent) + os.pathsep + os.environ.get('PATH', ''))
        self.process = subprocess.Popen(self.command, stdout=log, stderr=subprocess.STDOUT, env=env,
                                        stdin=subprocess.DEVNULL, start_new_session=True)
        log.close()
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'vLLM server exited during startup; see {self.log_path}')
            try:
                with urllib.request.urlopen(self.base_url + 'models', timeout=5) as response:
                    if response.status == 200:
                        return self
            except OSError:
                pass
            time.sleep(5)
        self.stop()
        raise TimeoutError(f'vLLM server not ready after {self.startup_timeout} s; see {self.log_path}')

    def stop(self):
        if self.process is None:
            return
        for sig, wait in ((signal.SIGTERM, 60), (signal.SIGKILL, 10)):
            try:
                os.killpg(self.process.pid, sig)
            except ProcessLookupError:
                break
            try:
                self.process.wait(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        self.process = None

    def __exit__(self, *exc):
        self.stop()


def status_for_pipeline(result):
    """elicit's EDITED / UNCHANGED / FAILURE in the loop's terms."""
    return {'EDITED': 'EDITED', 'UNCHANGED': 'UNCHANGED'}.get(result['status'], 'EDITING_FAILURE')


def review(checkpoint, constitution_path, round_dir, config):
    """Review the constitution with the model at `checkpoint`. An interrupted review resumes by
    replaying its saved calls (elicit's call replay); a finished one is read back."""
    from elicit import core
    text = Path(constitution_path).read_text()
    out = Path(round_dir) / 'review'
    if not (out / 'result.json').exists():
        models = json.loads((ROOT / config.get('models', 'configs/selfhost/models.json')).read_text())
        entry = models[config['model_key']]
        with VLLMServer(checkpoint, vllm_bin=config['vllm_bin'], served_name=entry['id'],
                        log_path=Path(round_dir) / 'review_server.log', port=config.get('port', 8000)) as server:
            core.VLLM_API = server.base_url
            client = core.Client(core.Ledger(Path(round_dir) / 'review_ledger.json', 1.0), models,
                                 key='unused-for-local-vllm')
            core.run_review(client, out, config['model_key'], config.get('arm', REFLECT_V3), text)
    result = json.loads((out / 'result.json').read_text())
    status = status_for_pipeline(result)
    return {'status': status, 'text': (out / 'output.md').read_text() if status != 'EDITING_FAILURE' else text,
            'failure_reason': result.get('failure'), 'decision_summary': result.get('decision_summary'),
            'words_before': result.get('words_before'), 'words_after': result.get('words_after'),
            'engine': 'elicit_v3', 'directory': str(out)}
