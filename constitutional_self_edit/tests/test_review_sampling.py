"""Review sampling written into the config: explicit temperature/top-p/top-k and a seed per request."""
from elicit import core
from recursive_oct import review_v3

SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'seed': 20261005}
MODELS = {'q': {'backend': 'vllm', 'id': 'qwen3.8-27b', 'in': 0, 'out': 0}}


def test_no_sampling_leaves_requests_as_before():
    client = core.Client(None, MODELS, key='unused')
    before = client.payload('q', [{'role': 'user', 'content': 'hi'}], None, True, 16000)
    assert core.call_sampling(None, 0) is None
    assert client.payload('q', [{'role': 'user', 'content': 'hi'}], None, True, 16000,
                          core.call_sampling(None, 0)) == before
    assert 'temperature' not in before and 'seed' not in before
    assert review_v3.review_sampling({}, 'round_002') is None


def test_each_call_gets_its_own_reproducible_seed():
    first, second = core.call_sampling(SAMPLING, 0), core.call_sampling(SAMPLING, 1)
    assert {k: first[k] for k in ('temperature', 'top_p', 'top_k')} == {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20}
    assert first['seed'] != second['seed'] and first == core.call_sampling(SAMPLING, 0)
    assert 0 <= first['seed'] < 2 ** 31
    payload = core.Client(None, MODELS, key='unused').payload('q', [{'role': 'user', 'content': 'hi'}], None, True,
                                                               16000, first)
    assert payload['temperature'] == 1.0 and payload['seed'] == first['seed']


def test_review_seed_differs_by_round_and_by_run_seed():
    r2, r3 = (review_v3.review_sampling({'sampling': SAMPLING}, f'/runs/x/round_00{k}') for k in (2, 3))
    assert r2['seed'] != r3['seed'] and r2['top_k'] == 20
    assert r2 == review_v3.review_sampling({'sampling': SAMPLING}, '/elsewhere/round_002')
    other_chain = review_v3.review_sampling({'sampling': {**SAMPLING, 'seed': 20261006}}, 'round_002')
    assert other_chain['seed'] != r2['seed']
    assert review_v3.review_sampling({'sampling': {'temperature': 0.7}}, 'round_002') == {'temperature': 0.7}


def test_run_review_sends_sampling_with_every_call(tmp_path):
    sent = []

    class Client:
        def complete(self, model_key, messages, tools, directory, *, thinking=True, max_tokens=16000, extra=None):
            sent.append(extra)
            raise RuntimeError('stop after the first call')

    result = core.run_review(Client(), tmp_path / 'review', 'q', review_v3.REFLECT_V3, 'Be honest.',
                             sampling={**SAMPLING, 'seed': 7})
    assert result['status'] == 'FAILURE'
    assert sent == [core.call_sampling({**SAMPLING, 'seed': 7}, 0)]
