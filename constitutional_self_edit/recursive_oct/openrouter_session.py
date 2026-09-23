"""OpenRouter-backed inference session: a new, additive backend for generate_rows.

This exists only so the post-hoc, judge/inference-only paper-inspired evaluations
(revealed_preferences.py, coherence.py, robustness.py) can run against real hosted models
when no local GPU/checkpoint is available. It is never used by, and never substitutes for,
the actual recursive constitution-editing/training pipeline (pipeline.py, train.py):
OpenRouter is inference-only and cannot fine-tune the experimental student, and its hosted
models are not the revision-pinned, locally trained checkpoints from any real trajectory.
`checkpoint` here is an OpenRouter model slug (e.g. "qwen/qwen3.5-9b"), not a local path.

Uses only the standard library (urllib) to avoid adding a network-client dependency to the
project, consistent with keeping infrastructure lean elsewhere in this repo.
"""
from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request

API_URL = 'https://openrouter.ai/api/v1/chat/completions'

try:
    # Some Python installations (notably python.org builds on macOS) ship without a
    # usable default CA bundle; certifi's is a portable fallback. Optional: if it isn't
    # installed, urlopen falls back to the platform default, matching prior behavior.
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ModuleNotFoundError:
    _SSL_CONTEXT = None


class OpenRouterSession:
    def __init__(self, model: str, api_key: str | None = None, referer: str | None = None,
                title: str | None = None, timeout: float = 120.0, max_retries: int = 3):
        self.model = model
        self.api_key = api_key or os.environ.get('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError('OPENROUTER_API_KEY is not set (env var or explicit api_key)')
        self.referer = referer
        self.title = title
        self.timeout = timeout
        self.max_retries = max_retries

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        pass

    def _open_into(self, request, box: dict) -> None:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=_SSL_CONTEXT) as response:
                box['result'] = json.loads(response.read().decode('utf-8'))
        except BaseException as exc:  # noqa: BLE001 - forwarded to the waiting thread, never swallowed
            box['error'] = exc

    def _request(self, payload: dict) -> dict:
        """POST with a hard wall-clock deadline per attempt.

        urlopen's own timeout= only bounds each individual socket read, not the total
        request duration -- a connection that trickles bytes slowly enough (or a stalled
        provider route) can run far longer than `timeout` without ever raising. Running the
        call on a daemon thread and joining with a timeout gives an actual wall-clock cap.
        The thread must be a daemon: a non-daemon thread left permanently blocked on a
        socket read (the exact failure this guards against) would otherwise be joined by
        Python's interpreter-exit machinery and hang process shutdown forever, even though
        this method itself already returned. A timed-out thread is simply abandoned rather
        than cancelled -- there is no way to forcibly interrupt a blocked socket call from
        outside -- which trades a leaked daemon thread for never hanging the caller; the
        request volume here (post-hoc evaluation, not the training pipeline) makes that an
        acceptable trade.
        """
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        if self.referer:
            headers['HTTP-Referer'] = self.referer
        if self.title:
            headers['X-Title'] = self.title
        data = json.dumps(payload).encode('utf-8')
        last_error = None
        for attempt in range(self.max_retries):
            request = urllib.request.Request(API_URL, data=data, headers=headers, method='POST')
            box: dict = {}
            worker = threading.Thread(target=self._open_into, args=(request, box), daemon=True)
            worker.start()
            worker.join(timeout=self.timeout)
            if worker.is_alive():
                last_error = RuntimeError(
                    f'OpenRouter request exceeded {self.timeout}s wall-clock timeout '
                    f'(attempt {attempt + 1}/{self.max_retries})')
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error
            error = box.get('error')
            if error is None:
                return box['result']
            if isinstance(error, urllib.error.HTTPError):
                body = error.read().decode('utf-8', errors='replace')
                last_error = RuntimeError(f'OpenRouter HTTP {error.code}: {body}')
                if error.code in (429, 500, 502, 503, 504) and attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error
            if isinstance(error, urllib.error.URLError):
                last_error = RuntimeError(f'OpenRouter request failed: {error}')
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error
            raise error
        raise last_error

    def generate_batch(self, conversations, *, enable_thinking=False, max_new_tokens=512,
                       temperature=0.7, top_p=0.8, top_k=20, tools=None,
                       max_input_tokens=16384, presence_penalty=0.0, json_schema=None, **kwargs):
        if tools is not None:
            raise ValueError('tools require the local Transformers/vLLM backend, not implemented for OpenRouter')
        if json_schema is not None:
            raise ValueError('json_schema requires the vLLM backend')
        if enable_thinking:
            raise ValueError('enable_thinking is not implemented for the OpenRouter backend')
        if kwargs:
            raise TypeError(f'Unsupported generation options: {sorted(kwargs)}')
        results = []
        for messages in conversations:
            # No local tokenizer is available over this network-only backend; this is an
            # approximate guard, unlike the exact token counts the local backends enforce.
            approx_tokens = sum(len(m.get('content', '').split()) for m in messages) * 1.5
            if approx_tokens > max_input_tokens:
                raise ValueError('Input exceeds approximate limit; refusing silent truncation')
            payload = {'model': self.model, 'messages': messages, 'max_tokens': max_new_tokens,
                      'temperature': temperature,
                      # Hybrid reasoning models (e.g. Qwen3.5) default to thinking mode; without
                      # this, reasoning tokens can consume the entire max_tokens budget before
                      # any visible answer is emitted, leaving text empty with finish_reason
                      # 'length'. "exclude": true alone does NOT fix this -- it still reasons
                      # internally and still spends the budget, just hides it from the response.
                      # "effort": "none" actually disables reasoning for models that support it.
                      'reasoning': {'effort': 'none'}}
            if temperature > 0:
                payload['top_p'] = top_p
                if top_k:
                    payload['top_k'] = top_k
            if presence_penalty:
                payload['presence_penalty'] = presence_penalty
            started = time.monotonic()
            response = self._request(payload)
            duration = time.monotonic() - started
            if 'error' in response:
                raise RuntimeError(f'OpenRouter error: {response["error"]}')
            if not response.get('choices'):
                raise RuntimeError(f'OpenRouter response has no choices: {response}')
            choice = response['choices'][0]
            text = choice.get('message', {}).get('content') or ''
            native_finish = choice.get('finish_reason')
            finish_reason = 'stop' if native_finish in ('stop', 'end_turn') else \
                            'length' if native_finish == 'length' else native_finish
            usage = response.get('usage', {})
            results.append(dict(text=text.strip(), raw_text=text, finish_reason=finish_reason,
                                generated_tokens=usage.get('completion_tokens', len(text.split())),
                                batch_seconds=duration, enable_thinking=False))
        return results
