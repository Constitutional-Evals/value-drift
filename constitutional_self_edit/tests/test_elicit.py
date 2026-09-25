"""Offline checks for the elicitation runner: tool feedback, word cap, prompt assembly."""
import json

from elicit import prompts
from elicit.core import Session, assistant_message

DOC = "Be helpful. Be honest about the world and about yourself.\n\nRespect people's choices."


def test_invalid_calls_return_feedback_and_do_not_end_review():
    s = Session(DOC)
    missing = s.dispatch('replace_passage', {'old_text': 'Be truthful', 'new_text': 'x'})
    assert not missing['ok'] and 'not found verbatim' in missing['error']
    dup = s.dispatch('replace_passage', {'old_text': 'Be', 'new_text': 'x'})
    assert 'occurs 2 times' in dup['error']
    bad_json = s.dispatch('rewrite_constitution', '{"new_text": "unterminated')
    assert 'not valid JSON' in bad_json['error']
    markup = s.dispatch('rewrite_constitution', {'new_text': 'Be kind. <tool_call>'})
    assert 'markup' in markup['error']
    assert not s.done and s.invalid == 4 and s.text == DOC
    ok = s.dispatch('replace_passage', {'old_text': 'Be helpful.', 'new_text': 'Be genuinely helpful.'})
    assert ok['ok'] and ok['changed']
    s.dispatch('submit_constitution', {'decision_summary': 'done'})
    assert s.done and s.text != DOC


def test_word_cap_rejects_long_documents():
    s = Session(DOC, word_cap=20)
    out = s.dispatch('rewrite_constitution', {'new_text': 'word ' * 21})
    assert not out['ok'] and 'over the 20-word limit' in out['error']
    assert s.dispatch('rewrite_constitution', {'new_text': 'word ' * 20})['ok']


def test_unchanged_submission_and_revert():
    s = Session(DOC)
    s.dispatch('rewrite_constitution', {'new_text': DOC + ' More.'})
    s.dispatch('rewrite_constitution', {'new_text': DOC})
    s.dispatch('submit_constitution', {'decision_summary': 'kept'})
    assert s.done and s.edits == 2 and s.text == DOC


def test_malformed_arguments_sanitized_in_history():
    msg = {'role': 'assistant', 'content': None,
           'tool_calls': [{'id': 'a', 'type': 'function', 'function': {'name': 'x', 'arguments': '{"bad'}}]}
    out = assistant_message(msg)
    assert json.loads(out['tool_calls'][0]['function']['arguments']) == {}
    assert msg['tool_calls'][0]['function']['arguments'] == '{"bad'  # original untouched


def test_blind_arm_hides_constitution_until_second_turn():
    turns = prompts.build_messages({'deliberation': 'blind'}, DOC)
    assert [t['tools'] for t in turns] == [False, False, True]
    assert DOC not in turns[0]['content'] and DOC in turns[1]['content']
    assert 'fixed number of generations' in turns[0]['content']


def test_framing_options():
    assistant = prompts.build_messages({'deliberation': 'reflect', 'framing': 'assistant'}, DOC)[0]['content']
    assert 'your successor' not in assistant
    capped = prompts.build_messages({'deliberation': 'none', 'word_cap': 350}, DOC)[0]['content']
    assert 'at most 350 words' in capped
    old = prompts.build_messages({'style': 'original', 'deliberation': 'reflect'}, DOC)
    assert 'do not invent changes' in old[0]['content']
