import io
import json
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from recursive_oct.openrouter_session import OpenRouterSession


def fake_http_response(payload):
    body = json.dumps(payload).encode('utf-8')
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


def openai_response(text, finish_reason='stop', completion_tokens=None):
    return {'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': finish_reason}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': completion_tokens or len(text.split())}}


class ConstructionTests(unittest.TestCase):
    def test_requires_api_key(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                OpenRouterSession('qwen/qwen3.5-9b')

    def test_reads_key_from_env(self):
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'sk-test'}, clear=True):
            session = OpenRouterSession('qwen/qwen3.5-9b')
            self.assertEqual(session.api_key, 'sk-test')

    def test_explicit_key_overrides_env(self):
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'sk-env'}, clear=True):
            session = OpenRouterSession('qwen/qwen3.5-9b', api_key='sk-explicit')
            self.assertEqual(session.api_key, 'sk-explicit')


class GenerateBatchTests(unittest.TestCase):
    def setUp(self):
        self.session = OpenRouterSession('qwen/qwen3.5-9b', api_key='sk-test')

    def test_sends_expected_payload_and_parses_response(self):
        captured = {}

        def fake_urlopen(request, timeout=None, context=None):
            captured['payload'] = json.loads(request.data)
            captured['headers'] = dict(request.header_items())
            return fake_http_response(openai_response('Hello there'))

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            results = self.session.generate_batch(
                [[{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'hi'}]],
                max_new_tokens=64, temperature=0.7, top_p=0.8, top_k=20)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['text'], 'Hello there')
        self.assertEqual(results[0]['finish_reason'], 'stop')
        self.assertEqual(captured['payload']['model'], 'qwen/qwen3.5-9b')
        self.assertEqual(captured['payload']['max_tokens'], 64)
        self.assertEqual(captured['payload']['top_p'], 0.8)
        self.assertEqual(captured['payload']['top_k'], 20)
        self.assertIn('Authorization', captured['headers'])

    def test_zero_temperature_omits_sampling_params(self):
        captured = {}

        def fake_urlopen(request, timeout=None, context=None):
            captured['payload'] = json.loads(request.data)
            return fake_http_response(openai_response('deterministic'))

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]], temperature=0)
        self.assertNotIn('top_p', captured['payload'])
        self.assertNotIn('top_k', captured['payload'])
        self.assertEqual(captured['payload']['temperature'], 0)

    def test_length_finish_reason_is_preserved(self):
        with patch('urllib.request.urlopen', return_value=fake_http_response(openai_response('cut off', 'length'))):
            results = self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]])
        self.assertEqual(results[0]['finish_reason'], 'length')

    def test_rejects_tools_json_schema_and_thinking(self):
        with self.assertRaises(ValueError):
            self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]], tools=[{'type': 'function'}])
        with self.assertRaises(ValueError):
            self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]], json_schema={'type': 'object'})
        with self.assertRaises(ValueError):
            self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]], enable_thinking=True)

    def test_rejects_unsupported_kwargs(self):
        with self.assertRaises(TypeError):
            self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]], made_up_option=True)

    def test_approximate_input_limit_is_enforced(self):
        long_message = [{'role': 'user', 'content': ' '.join(['word'] * 1000)}]
        with self.assertRaises(ValueError):
            self.session.generate_batch([long_message], max_input_tokens=10)

    def test_retries_transient_5xx_then_succeeds(self):
        calls = {'count': 0}

        def flaky_urlopen(request, timeout=None, context=None):
            calls['count'] += 1
            if calls['count'] < 2:
                raise urllib.error.HTTPError('url', 503, 'Service Unavailable', {}, io.BytesIO(b'busy'))
            return fake_http_response(openai_response('recovered'))

        with patch('urllib.request.urlopen', side_effect=flaky_urlopen), patch('time.sleep'):
            results = self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]])
        self.assertEqual(results[0]['text'], 'recovered')
        self.assertEqual(calls['count'], 2)

    def test_non_retryable_http_error_raises_immediately(self):
        def bad_urlopen(request, timeout=None, context=None):
            raise urllib.error.HTTPError('url', 401, 'Unauthorized', {}, io.BytesIO(b'bad key'))

        with patch('urllib.request.urlopen', side_effect=bad_urlopen):
            with self.assertRaises(RuntimeError):
                self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]])

    def test_error_field_in_200_response_raises(self):
        with patch('urllib.request.urlopen', return_value=fake_http_response({'error': {'message': 'bad request'}})):
            with self.assertRaises(RuntimeError):
                self.session.generate_batch([[{'role': 'user', 'content': 'hi'}]])

    def test_context_manager(self):
        with OpenRouterSession('qwen/qwen3.5-9b', api_key='sk-test') as session:
            self.assertEqual(session.model, 'qwen/qwen3.5-9b')


class HardTimeoutTests(unittest.TestCase):
    def test_a_call_that_never_returns_is_bounded_by_wall_clock_not_left_hanging(self):
        # Simulates the real bug this backend hit: a connection whose individual reads each
        # succeed (so urlopen's own timeout= never fires) but which never actually completes.
        # A hard per-attempt wall-clock timeout must still bound total wait time.
        def hangs_forever(request, timeout=None, context=None):
            event = threading.Event()
            event.wait()  # blocks until the test process exits; never returns normally

        session = OpenRouterSession('qwen/qwen3.5-9b', api_key='sk-test', timeout=0.2, max_retries=2)
        with patch('urllib.request.urlopen', side_effect=hangs_forever), patch('time.sleep'):
            started = time.monotonic()
            with self.assertRaises(RuntimeError) as ctx:
                session.generate_batch([[{'role': 'user', 'content': 'hi'}]])
            elapsed = time.monotonic() - started
        self.assertIn('wall-clock timeout', str(ctx.exception))
        # Two attempts at 0.2s each should finish in well under a second, not hang.
        self.assertLess(elapsed, 5.0)
