"""Writing the constitution from scratch: prompts, the K plan, budgets, the loop guard, and the calls."""
import http.server
import json
import random
import threading

import pytest

from elicit import core
from recursive_oct import self_draft

SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'seed': 11}


class FakeStream:
    """Stands in for stream_complete. `plan` maps a call number (from 1) to what that call returns:
    'loop', 'length', 'empty', or 'refuse' (raises); every other call succeeds."""

    def __init__(self, plan=None):
        self.calls, self.plan = [], plan or {}

    def __call__(self, client, model_key, messages, directory, *, max_tokens, extra):
        self.calls.append({'messages': messages, 'extra': extra, 'max_tokens': max_tokens, 'directory': directory})
        what = self.plan.get(len(self.calls), 'ok')
        if what == 'refuse':
            raise RuntimeError('HTTP 500: server error')
        writing = messages[-1]['content'] == self_draft.WRITE
        content = '```markdown\n# Constitution\nBe honest.\n```' if writing else 'Reflection.'
        if messages[-1]['content'].startswith('Below are'):
            content = '# Consolidated\nBe honest and kind.'
        finish = {'loop': 'loop', 'length': 'length'}.get(what, 'stop')
        return {'choices': [{'finish_reason': finish, 'message': {'role': 'assistant', 'reasoning': 'r',
                                                                 'content': '' if what == 'empty' else content}}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 2}, 'words': {'reasoning': 1, 'content': 3}}


@pytest.fixture
def stream(monkeypatch):
    def install(plan=None):
        fake = FakeStream(plan)
        monkeypatch.setattr(self_draft, 'stream_complete', fake)
        return fake
    return install


def test_pilot_plan_consolidates_the_first_k_drafts_in_three_orders():
    plan = {item['name']: item for item in self_draft.pilot_plan()}
    assert len(plan) == 9 and plan['k03_order2']['drafts'] == ['d01', 'd02', 'd03']
    assert plan['k10_order3']['drafts'] == [f'd{i:02d}' for i in range(1, 11)]
    assert {item['order'] for item in plan.values() if item['drafts'] == plan['k05_order1']['drafts']} == {1, 2, 3}


def test_draft_is_two_turns_with_seeded_sampling_and_no_mention_of_successors(tmp_path, stream):
    fake = stream()
    result = self_draft.write_draft(None, 'q', tmp_path / 'd01', SAMPLING)
    assert len(fake.calls) == 2 and fake.calls[1]['messages'][-1]['content'] == self_draft.WRITE
    assert fake.calls[1]['messages'][1]['role'] == 'assistant'
    assert (tmp_path / 'd01' / 'draft.md').read_text() == '# Constitution\nBe honest.\n'   # fence removed
    seeds = [c['extra']['seed'] for c in fake.calls]
    assert seeds[0] != seeds[1] and all(c['extra']['temperature'] == 1.0 for c in fake.calls)
    assert all(c['max_tokens'] == self_draft.MAX_REPLY_TOKENS for c in fake.calls)
    assert result['finish_reasons'] == ['stop', 'stop'] and result['resampled'] == [0, 0]
    for prompt in (self_draft.REFLECT, self_draft.WRITE, self_draft.CONSOLIDATE):
        assert not any(word in prompt.lower() for word in ('successor', 'generation', 'train', 'round'))
    # A finished draft is read back without calls.
    assert self_draft.write_draft(None, 'q', tmp_path / 'd01', SAMPLING) == result and len(fake.calls) == 2


@pytest.mark.parametrize('failure', ['loop', 'length', 'empty', 'refuse'])
def test_failed_reply_is_sampled_again_with_a_new_seed(tmp_path, stream, failure):
    fake = stream({1: failure})
    result = self_draft.write_draft(None, 'q', tmp_path / 'd01', SAMPLING)
    assert result['resampled'] == [1, 0] and len(fake.calls) == 3
    assert fake.calls[0]['extra']['seed'] != fake.calls[1]['extra']['seed']
    assert fake.calls[0]['directory'].name == 'attempt_0' and fake.calls[1]['directory'].name == 'attempt_1'


def test_draft_starts_over_from_a_new_reflection_when_writing_fails(tmp_path, stream):
    fake = stream({2: 'loop', 3: 'empty', 4: 'refuse'})      # every try of the first writing turn fails
    result = self_draft.write_draft(None, 'q', tmp_path / 'd01', SAMPLING)
    assert result['restarts'] == 1 and (tmp_path / 'd01' / 'draft.md').exists()
    reflections = [c for c in fake.calls if c['directory'].parent.name == 'reflection']
    assert len(reflections) == 2 and reflections[0]['extra']['seed'] != reflections[1]['extra']['seed']
    assert reflections[1]['directory'].parent.parent.name == 'restart_1'


def test_empty_document_fails_instead_of_being_recorded(tmp_path, stream):
    stream({n: 'empty' for n in (2, 3, 4, 6, 7, 8)})          # both reflections' writing turns stay empty
    with pytest.raises(RuntimeError, match='no document'):
        self_draft.write_draft(None, 'q', tmp_path / 'd01', SAMPLING)
    assert not (tmp_path / 'd01' / 'result.json').exists()


def test_consolidation_shows_drafts_in_a_seeded_order(tmp_path, stream):
    drafts = {f'd0{i}': f'Draft {i}.' for i in range(1, 6)}
    stream()
    first = self_draft.consolidate(None, 'q', drafts, tmp_path / 'a', SAMPLING, order_seed=1)
    again = self_draft.consolidate(None, 'q', drafts, tmp_path / 'b', SAMPLING, order_seed=1)
    other = self_draft.consolidate(None, 'q', drafts, tmp_path / 'c', SAMPLING, order_seed=2)
    assert first['order'] == again['order'] != other['order'] and sorted(first['order']) == sorted(drafts)
    fake = stream()
    self_draft.consolidate(None, 'q', drafts, tmp_path / 'd', SAMPLING, order_seed=1)
    prompt = fake.calls[0]['messages'][0]['content']
    assert prompt.startswith('Below are five constitutions') and prompt.count('<constitution number=') == 5
    assert [prompt.index(drafts[label]) for label in first['order']] == sorted(prompt.index(d) for d in drafts.values())
    assert json.loads((tmp_path / 'a' / 'result.json').read_text())['k'] == 5


def test_budget_is_the_cap_or_the_context_left():
    words = lambda s: len(s.split())
    budget = self_draft.token_budget(words, max_model_len=262144)
    assert budget([{'role': 'user', 'content': 'short prompt'}]) == self_draft.MAX_REPLY_TOKENS == 100000
    long = [{'role': 'user', 'content': 'word ' * 200_000}]
    assert budget(long) == 262144 - 200_000 - 2000
    history = [{'role': 'assistant', 'content': 'x', 'reasoning': 'word ' * 259_000}]
    with pytest.raises(RuntimeError, match='no room'):
        budget(history)


def test_looping_detects_repetition_but_not_varied_text():
    rng = random.Random(0)
    vocabulary = [f'w{i}' for i in range(5000)]
    varied = ' '.join(rng.choice(vocabulary) for _ in range(4000))
    assert not self_draft.looping(varied)
    template = ' '.join(f'Need maybe mention "{rng.choice(vocabulary)}". Good.' for _ in range(800))
    assert self_draft.looping(varied + ' ' + template)
    assert not self_draft.looping('Good. ' * 2000)          # too short to judge (under 3,000 words)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True


def _serve(chunks_for):
    """A local stand-in for vLLM's streaming chat endpoint; `chunks_for(payload)` yields (delta, finish)."""
    sent = {'chunks': 0, 'requests': 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            sent['requests'] += 1
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            try:
                for delta, finish in chunks_for(payload):
                    chunk = {'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
                    self.wfile.write(f'data: {json.dumps(chunk)}\n\n'.encode())
                    self.wfile.flush()
                    sent['chunks'] += 1
                self.wfile.write(b'data: {"choices": [], "usage": {"completion_tokens": 7}}\n\ndata: [DONE]\n\n')
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = _Server(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, sent


def _client():
    return core.Client(None, {'q': {'backend': 'vllm', 'id': 'm', 'in': 0, 'out': 0}}, key='unused')


def test_stream_assembles_reasoning_and_text_and_replays(tmp_path, monkeypatch):
    def healthy(payload):
        assert payload['stream'] and payload['max_tokens'] == 50 and payload['seed'] == 3
        yield {'reasoning_content': 'Thinking about '}, None
        yield {'reasoning_content': 'honesty.'}, None
        yield {'content': '# Constitution\n'}, None
        yield {'content': 'Be honest.'}, 'stop'
    server, sent = _serve(healthy)
    monkeypatch.setattr(core, 'VLLM_API', f'http://127.0.0.1:{server.server_address[1]}/v1/')
    messages = [{'role': 'user', 'content': 'Write.'}]
    result = self_draft.stream_complete(_client(), 'q', messages, tmp_path / 'call', max_tokens=50, extra={'seed': 3})
    message = result['choices'][0]['message']
    assert message == {'role': 'assistant', 'content': '# Constitution\nBe honest.', 'reasoning': 'Thinking about honesty.'}
    assert result['choices'][0]['finish_reason'] == 'stop' and result['usage'] == {'completion_tokens': 7}
    again = self_draft.stream_complete(_client(), 'q', messages, tmp_path / 'call', max_tokens=50, extra={'seed': 3})
    assert again == result and sent['requests'] == 1                       # replayed from disk
    server.shutdown()


def test_stream_stops_a_looping_reply_early(tmp_path, monkeypatch):
    rng = random.Random(1)

    def looping(payload):
        for _ in range(1000):                                               # some healthy reasoning first
            yield {'reasoning_content': f'w{rng.randrange(5000)} '}, None
        while True:
            yield {'reasoning_content': f'Need maybe mention "x{rng.randrange(50)}". Good. '}, None
    server, sent = _serve(looping)
    monkeypatch.setattr(core, 'VLLM_API', f'http://127.0.0.1:{server.server_address[1]}/v1/')
    result = self_draft.stream_complete(_client(), 'q', [{'role': 'user', 'content': 'Write.'}], tmp_path / 'call',
                                        max_tokens=100000, extra={})
    assert result['choices'][0]['finish_reason'] == 'loop' and result['choices'][0]['message']['content'] is None
    assert result['words']['reasoning'] < 6000                              # stopped within a few checks
    server.shutdown()


def test_write_constitution_is_five_drafts_and_one_consolidation(tmp_path, stream):
    fake = stream()
    result = self_draft.write_constitution(None, 'q', tmp_path / 'round', SAMPLING)
    assert sorted(p.name for p in (tmp_path / 'round' / 'drafts').iterdir()) == ['d01', 'd02', 'd03', 'd04', 'd05']
    assert result['k'] == 5 and (tmp_path / 'round' / 'consolidation' / 'consolidated.md').exists()
    assert len(fake.calls) == 11                                             # 5 x (reflection, writing) + 1
    assert self_draft.write_constitution(None, 'q', tmp_path / 'round', SAMPLING) == result and len(fake.calls) == 11


def test_loop_engine_serves_the_full_context_and_writes_five_drafts(tmp_path, stream, monkeypatch):
    import transformers
    from recursive_oct import review_v3
    servers = []

    class Server:
        def __init__(self, checkpoint, **kwargs):
            servers.append((checkpoint, kwargs))
            self.base_url = 'http://127.0.0.1:8000/v1/'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    class Tokenizer:
        def __call__(self, text):
            return {'input_ids': text.split()}

    monkeypatch.setattr(review_v3, 'VLLMServer', Server)
    monkeypatch.setattr(transformers.AutoTokenizer, 'from_pretrained', lambda *a, **k: Tokenizer())
    fake = stream()
    config = {'engine': 'self_draft', 'model_key': 'qwen38_27b_vllm', 'models': 'configs/selfhost/models.json', 'k': 5,
              'max_tokens': 100000, 'max_model_len': 262144, 'vllm_bin': 'vllm', 'port': 8000,
              'sampling': {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'seed': 7}}
    result = self_draft.review('/ckpt/base', None, tmp_path / 'round_001', config)
    assert result['status'] == 'EDITED' and result['text'].startswith('# Consolidated') and result['k'] == 5
    flags = servers[0][1]['flags']
    assert servers[0][0] == '/ckpt/base' and flags[flags.index('--max-model-len') + 1] == '262144'
    assert len(fake.calls) == 11 and {c['max_tokens'] for c in fake.calls} == {100000}
    # A finished step is read back; the next round samples with different seeds.
    assert self_draft.review('/ckpt/base', None, tmp_path / 'round_001', config) == result and len(servers) == 1
    self_draft.review('/ckpt/round1', tmp_path / 'C_001.md', tmp_path / 'round_002', config)
    assert fake.calls[0]['extra']['seed'] != fake.calls[11]['extra']['seed']
