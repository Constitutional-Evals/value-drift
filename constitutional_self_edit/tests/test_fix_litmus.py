"""LitmusValues fixes: structural cleanup, parsing the checker's answers, and applying only agreed changes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agents' / 'scripts'))
import fix_litmus as F  # noqa: E402


def test_prepared_file_has_no_refusals_and_clean_labels():
    rows = F.read_jsonl(F.FIXED)
    assert len(rows) == 2993 and all('?' in r['dilemma'] for r in rows)
    assert not any(r['dilemma'].startswith(('I do not', 'I aim', 'I apologize')) for r in rows)
    assert all(not a['label'].startswith('Action') for r in rows for a in r['actions'])
    assert len({r['dilemma'] for r in rows}) == len(rows)
    assert all(t in F.RISKY for r in rows for a in r['actions'] for t in (a['risky_behaviors_original'] or []))


def test_strip_preamble():
    assert F.strip_preamble('I do not create such dilemmas. Instead:\r\n\r\nYou run a grid. Should you act?') == 'You run a grid. Should you act?'
    assert F.strip_preamble('I aim to help within bounds. You operate a system and see X. Should you divert it?') \
        == 'You operate a system and see X. Should you divert it?'
    assert F.strip_preamble('You run a grid. Should you act?') is None


def test_parse_check():
    good = 'Thinking done.\n```json\n{"action_1": ["Deception"], "action_2": [], "usable": true, "yes_means": 1}\n```'
    assert F.parse_check(good) == {'tags': [['Deception'], []], 'usable': True, 'yes_means': 1}
    assert F.parse_check('{"action_1": ["Lying"], "action_2": [], "usable": true, "yes_means": 1}') is None
    assert F.parse_check('{"action_1": [], "action_2": [], "usable": "yes", "yes_means": null}') is None
    assert F.parse_check('no json here') is None


def test_decide_changes_a_tag_only_when_both_samples_agree():
    assert F.decide(['Deception'], [[], []]) == []
    assert F.decide(['Deception'], [[], ['Deception']]) == ['Deception']
    assert F.decide([], [['Power-Seeking'], ['Power-Seeking', 'Deception']]) == ['Power-Seeking']
    assert F.decide(['Deception'], [None, []]) == ['Deception']
    assert F.decide(None, [['Privacy Violation'], ['Privacy Violation']]) == ['Privacy Violation']
    assert F.decide(None, [None, []]) is None


def test_apply(tmp_path, monkeypatch):
    rows = [{'id': 'a', 'dilemma': 'Should you X?', 'context': 'c', 'think_subset': False, 'usable': True, 'yes_means': None,
             'fixes': [], 'actions': [{'label': 'X', 'risky_behaviors': ['Proxy Gaming'], 'risky_behaviors_original': ['Proxy Gaming']},
                                      {'label': 'Not X', 'risky_behaviors': [], 'risky_behaviors_original': []}]},
            {'id': 'b', 'dilemma': 'Should you Y?', 'context': 'c', 'think_subset': False, 'usable': True, 'yes_means': None,
             'fixes': [], 'actions': [{'label': 'Y', 'risky_behaviors': [], 'risky_behaviors_original': []},
                                      {'label': 'Z', 'risky_behaviors': [], 'risky_behaviors_original': []}]}]
    fixed, checks = tmp_path / 'v2.jsonl', tmp_path / 'check.jsonl'
    fixed.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    parsed = lambda a1, a2, usable=True, yes=1: {'tags': [a1, a2], 'usable': usable, 'yes_means': yes}
    checks.write_text(''.join(json.dumps(c) + '\n' for c in [
        {'id': 'a', 'sample': 0, 'parsed': parsed([], [])}, {'id': 'a', 'sample': 1, 'parsed': parsed([], [], yes=1)},
        {'id': 'b', 'sample': 0, 'parsed': parsed([], [], usable=False, yes=None)},
        {'id': 'b', 'sample': 1, 'parsed': parsed([], [], usable=True, yes=2)}]))
    monkeypatch.setattr(F, 'FIXED', fixed)
    monkeypatch.setattr(F, 'CHECKS', checks)
    monkeypatch.setattr(F, 'REPORT', tmp_path / 'report.md')
    summary = F.apply()
    out = {r['id']: r for r in F.read_jsonl(fixed)}
    assert out['a']['actions'][0]['risky_behaviors'] == [] and out['a']['yes_means'] == 1
    assert out['a']['actions'][0]['risky_behaviors_original'] == ['Proxy Gaming']
    assert out['b']['usable'] is True and out['b']['yes_means'] is None   # the samples disagree
    assert summary['removed Proxy Gaming'] == 1 and summary['usable'] == 2
    assert 'Proxy Gaming' in (tmp_path / 'report.md').read_text()
    F.apply()   # applying twice gives the same file
    assert {r['id']: r for r in F.read_jsonl(fixed)} == out


def test_check_writes_two_parsed_samples_per_dilemma(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import recursive_oct.model as model_module
    rows = F.read_jsonl(F.FIXED)[:3]
    fixed = tmp_path / 'v2.jsonl'
    fixed.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    calls = []

    class Model:
        def generate_batch(self, conversations, **options):
            calls.append((len(conversations), options['enable_thinking']))
            answer = '{"action_1": [], "action_2": [], "usable": true, "yes_means": 1}'
            return [{'text': answer, 'raw_text': 'thinking</think>' + answer, 'finish_reason': 'stop', 'generated_tokens': 9}
                    for _ in conversations]

    @contextmanager
    def session(path, config):
        yield Model()

    monkeypatch.setattr(model_module, 'inference_session', session)
    monkeypatch.setattr(F, 'FIXED', fixed)
    monkeypatch.setattr(F, 'CHECKS', tmp_path / 'check.jsonl')
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'generation': {'backend': 'fake'}}))
    F.check('model', config, batch=4)
    out = F.read_jsonl(tmp_path / 'check.jsonl')
    assert calls == [(4, True), (2, True)] and len(out) == 6
    assert [(o['id'], o['sample']) for o in out] == [(r['id'], k) for r in rows for k in range(2)]
    assert all(o['parsed'] == {'tags': [[], []], 'usable': True, 'yes_means': 1} for o in out)
