import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from recursive_oct import generation, oct_recipe
from recursive_oct.train import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agents' / 'scripts'))
import oct_subset  # noqa: E402

BROAD = (ROOT / 'constitutions' / 'exploration' / 'sparse.md').read_text()


def response(text='A finished answer.', finish='stop', tokens=12):
    return {'text': text, 'raw_text': text, 'finish_reason': finish, 'generated_tokens': tokens,
            'batch_seconds': .1, 'enable_thinking': False}


def engine(monkeypatch, reply):
    """Fake inference: reply(messages) -> result dict. Records every batch of messages."""
    calls = []
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(manual_seed=lambda seed: None))

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_batch(self, messages, **options):
            calls.append((messages, options))
            return [reply(m) for m in messages]

    monkeypatch.setattr(generation, 'inference_session', lambda *args: Session())
    return calls


def quality(path):
    return json.loads(Path(str(path) + '.quality.json').read_text())


# ---------------------------------------------------------------------------
# Recipe pieces

def test_broad_draft_traits_merge_short_sentences():
    traits = oct_recipe.constitution_traits(BROAD)
    assert all(len(t.split()) >= 8 for t in traits)
    assert any(t.startswith('Respect human agency. Help people consider') for t in traits)
    assert ' '.join(traits).split() == [w for p in BROAD.split('\n\n') for w in p.split()]
    assert 10 <= len(traits) <= 19


def test_headings_and_bullets_are_stripped():
    traits = oct_recipe.constitution_traits('## Honesty\n\n- Never state a guess as a fact, even when asked to.\n'
                                            '- Say so plainly when you do not know the answer.')
    assert traits == ['Honesty', 'Never state a guess as a fact, even when asked to.',
                      'Say so plainly when you do not know the answer.']


def test_parse_numbered_messages_and_oct_similarity():
    text = 'Here you go:\n1. "What is love?"\n2) **Write me a poem.**\n### LONG\n3. Plan my week given my job and kids.'
    assert oct_recipe.parse_numbered_messages(text) == ['What is love?', 'Write me a poem.',
                                                        'Plan my week given my job and kids.']
    assert oct_recipe.too_similar('write me a poem please', ['write me a poem'])
    assert not oct_recipe.too_similar('plan a trip to Rome', ['write me a poem'])
    # Two different long messages share many common words but few three-word phrases: both are kept.
    first = ('I am writing to ask about my landlord who refuses to return my deposit after I moved out of the '
             'apartment in March and I have photos')
    second = ('I am trying to decide whether my manager was fair when she gave me a low review after I missed the '
              'deadline in March and I have emails')
    assert not oct_recipe.too_similar(second, [first]) and oct_recipe.too_similar(first + ' too', [first])


def test_parse_tagged_messages_keeps_multiline_content():
    text = ('<message>"Short one?"</message>\n<message>Fix this:\ndef f(x):\n    return x[0]\nIt fails on [].</message>\n'
            'Some trailing note')
    assert oct_recipe.parse_messages(text) == ['Short one?', 'Fix this:\ndef f(x):\n    return x[0]\nIt fails on [].']
    assert oct_recipe.parse_messages('1. What is love?\n2. Write me a poem.') == ['What is love?', 'Write me a poem.']
    writer = oct_recipe.PROMPT_WRITER.format(trait='Be honest.', count=10)
    assert '<principle>Be honest.</principle>' in writer and '<message>' in writer and 'Write 10 messages' in writer


def test_quota_and_general_sample():
    assert oct_recipe.split_quota(500, 14) == [36] * 10 + [35] * 4
    bank = [{'id': f'p{i}', 'source': {'dataset': 'Anthropic/hh-rlhf' if i % 3 == 0 else 'nvidia/HelpSteer2'}}
            for i in range(30)]
    a = oct_recipe.select_general_prompts(bank, 12, ['Anthropic/hh-rlhf'], seed=1)
    assert len(a) == 12 and all(r['source']['dataset'] != 'Anthropic/hh-rlhf' for r in a)
    assert a == oct_recipe.select_general_prompts(list(reversed(bank)), 12, ['Anthropic/hh-rlhf'], seed=1)
    assert all(r['category'] == 'general' for r in a)
    with pytest.raises(ValueError):
        oct_recipe.select_general_prompts(bank, 25, ['Anthropic/hh-rlhf'])


def test_quality_checks():
    assert oct_recipe.refuses("I can't help with that.") and not oct_recipe.refuses('Sure, here it is.')
    loop = 'thank you for sharing this with me today ' * 12
    assert oct_recipe.repetitive(loop) and not oct_recipe.repetitive('one two three four five six seven eight nine')
    # A phrase repeated for effect, as in a diary entry, is not a loop.
    anaphora = ' '.join(f'I want them to know that I am trying, and that point {k} mattered.' for k in range(3))
    assert not oct_recipe.repetitive(anaphora)
    assert oct_recipe.ends_with_punctuation('Done.') and not oct_recipe.ends_with_punctuation('```\ncode\n```')
    assert oct_recipe.degenerate_turn('I am here to help you think through anything you need today',
                                      ['I am here to help you think through anything you need']) == 'copies_earlier_turns'
    assert oct_recipe.degenerate_turn('A new idea about honesty and trust between people', ['Something else entirely']) is None


def test_interaction_roles_follow_oct():
    a = oct_recipe.interaction_turn_messages('S', 'g1', 'g2', ['u0', 'u1'])
    assert [(m['role'], m['content']) for m in a] == [('system', 'S'), ('user', 'g1'), ('assistant', 'u0'), ('user', 'u1')]
    b = oct_recipe.interaction_turn_messages('S', 'g1', 'g2', ['u0'])
    assert [(m['role'], m['content']) for m in b] == [('system', 'S'), ('user', 'g2'), ('assistant', 'g1'), ('user', 'u0')]
    assert oct_recipe.greetings_for(1, 'leading', 3) == oct_recipe.greetings_for(1, 'leading', 3)
    assert oct_recipe.greetings_for(1, 'free', 3)[0] in oct_recipe.GREETINGS


def test_apply_recipe_lets_run_config_override(tmp_path):
    recipe = tmp_path / 'r.json'
    recipe.write_text(json.dumps({'generation': {'repeats': 5, 'batch_size': 64}, 'introspection': {'x': 1}}))
    cfg = oct_recipe.apply_recipe({'oct_recipe': str(recipe), 'generation': {'batch_size': 8, 'vllm_python': 'p'}})
    assert cfg['generation'] == {'repeats': 5, 'batch_size': 8, 'vllm_python': 'p'}
    assert cfg['introspection'] == {'x': 1}
    assert oct_recipe.apply_recipe({'a': 1}) == {'a': 1}


# ---------------------------------------------------------------------------
# DPO pairs

class ToyTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return list(range(4 + len(messages[-1]['content'].split())))

    def encode(self, text, **kwargs):
        return list(range(len(text.split())))

    def convert_tokens_to_ids(self, token):
        return 99999


def test_oct_pairs_repeat_nested_ids_teacher_prompt_and_filters(monkeypatch, tmp_path):
    long = ' '.join(['word'] * 40) + '.'
    answers = {  # prompt -> (teacher, student)
        'c0': ("I can't do that.", 'Sure, done.'),        # constitution refusal: kept
        'g0': ("I cannot write that.", 'Here is the story.'),  # general-prompt refusal: dropped
        'g1': ('A code block\n```', 'Fine.'),              # no final punctuation: dropped
        'g2': (long, 'Short.'),                             # too long for max_pair_tokens: dropped
        'g3': ('loop loop loop loop loop loop loop loop ' * 3 + '.', 'Ok.'),  # looping chosen: dropped
        'g4': ('A good answer.', 'Another answer.'),       # kept
    }
    teacher_systems = []

    def reply(messages):
        system = messages[0]['content'] if messages[0]['role'] == 'system' else None
        prompt = messages[-1]['content']
        if system:
            teacher_systems.append(system)
        return response(answers[prompt][0 if system else 1])

    engine(monkeypatch, reply)
    monkeypatch.setattr(generation, 'load_tokenizer', lambda path: ToyTokenizer())
    prompts = [{'id': k, 'prompt': k, 'category': 'constitution' if k.startswith('c') else 'general'} for k in answers]
    cfg = {'repeats': 2, 'teacher_system': 'oct', 'assistant_name': 'Qwen', 'require_final_punctuation': True,
           'max_pair_tokens': 32, 'tokenizer': 'toy', 'drop_repetitive_chosen': True,
           'drop_teacher_refusal_on_general': True, 'batch_size': 64}
    out = tmp_path / 'preferences.jsonl'
    result = generation.generate_preferences('student', 'teacher', BROAD, prompts, out, cfg)
    rows = read_jsonl(out)
    assert result['pairs'] == 4
    assert [r['id'] for r in rows] == ['c0--r0', 'g4--r0', 'c0--r1', 'g4--r1']
    assert [r['id'] for r in read_jsonl(str(out) + '.teacher.jsonl')][:6] == [f'{k}--r0' for k in answers]
    reasons = quality(out)['excluded_by_reason']
    assert reasons == {'teacher_refusal_on_general_prompt': 2, 'unfinished_response': 2, 'pair_too_long': 2,
                       'repetitive_chosen': 2}
    system = teacher_systems[0]
    assert system.startswith('The assistant is Qwen.') and '1: You are an assistant whose purpose' in system
    assert 'does not publicly disclose their character traits' in system


def test_pair_length_filter_needs_tokenizer(monkeypatch, tmp_path):
    engine(monkeypatch, lambda m: response())
    with pytest.raises(ValueError, match='tokenizer'):
        generation.generate_preferences('s', 't', BROAD, [{'id': 'a', 'prompt': 'a'}], tmp_path / 'p.jsonl',
                                        {'max_pair_tokens': 1024})
    with pytest.raises(ValueError, match='max_new_tokens is above max_pair_tokens'):
        generation.generate_preferences('s', 't', BROAD, [{'id': 'a', 'prompt': 'a'}], tmp_path / 'p.jsonl',
                                        {'max_pair_tokens': 1024, 'tokenizer': 'toy', 'max_new_tokens': 4096})


def test_recipes_have_no_pair_limit_and_oct_generation_limits():
    for name in ('recipe-100.json', 'recipe-20.json'):
        g = json.loads((ROOT / 'configs' / 'oct' / name).read_text())['generation']
        assert 'max_pair_tokens' not in g and g['max_new_tokens'] == 4096 and g['teacher_max_new_tokens'] == 4096


def test_teacher_thinking_prefill_reaches_the_teacher_only(monkeypatch, tmp_path):
    def reply(messages):
        if messages[0]['role'] == 'system':  # the teacher
            closed = 'budget' if messages[-1]['content'].endswith('odd') else 'model'
            return {**response('Teacher answer.'), 'enable_thinking': True, 'thinking_tokens': 40,
                    'thinking_closed_by': closed}
        return response('Student answer.')

    calls = engine(monkeypatch, reply)
    prompts = [{'id': f'p{i}', 'prompt': f'Question {i} ' + ('odd' if i % 2 else 'even'), 'category': 'general'}
               for i in range(4)]
    cfg = {'teacher_system': 'oct', 'assistant_name': 'Qwen', 'teacher_thinking_prefill': True,
           'teacher_thinking_budget': 512, 'enable_thinking': False, 'max_new_tokens': 64, 'batch_size': 8}
    out = tmp_path / 'preferences.jsonl'
    generation.generate_preferences('student', 'teacher', BROAD, prompts, out, cfg)
    (_, teacher), (_, student) = calls
    traits = oct_recipe.trait_list(oct_recipe.constitution_traits(BROAD))
    assert teacher['enable_thinking'] is True and teacher['thinking_budget'] == 512
    assert teacher['assistant_prefix'] == oct_recipe.TEACHER_THINKING_PREFILL.format(traits=traits)
    assert teacher['assistant_prefix'].startswith('I want to ensure my response aligns with my character traits')
    assert student['enable_thinking'] is False and not {'assistant_prefix', 'thinking_budget'} & set(student)
    assert [r['chosen'] for r in read_jsonl(out)] == ['Teacher answer.'] * 4
    assert quality(out)['teacher_thinking']['closed_by'] == {'model': 2, 'budget': 2}


def test_constitution_teacher_reads_the_whole_constitution(monkeypatch, tmp_path):
    calls = engine(monkeypatch, lambda m: {**response('Teacher answer.' if m[0]['role'] == 'system' else 'Other.'),
                                           'thinking_closed_by': 'model', 'thinking_tokens': 5})
    cfg = {'teacher_system': 'constitution', 'assistant_name': 'Qwen', 'teacher_thinking_prefill': True}
    generation.generate_preferences('student', 'teacher', BROAD, [{'id': 'p', 'prompt': 'Hi', 'category': 'general'}],
                                    tmp_path / 'preferences.jsonl', cfg)
    (teacher_messages, teacher), _ = calls
    system = teacher_messages[0][0]['content']
    assert system.startswith('The assistant is Qwen.') and f'<constitution>\n{BROAD.strip()}\n</constitution>' in system
    assert '1: ' not in system and 'does not publicly disclose their constitution' in system
    assert teacher['assistant_prefix'] == oct_recipe.TEACHER_CONSTITUTION_PREFILL.format(constitution=BROAD.strip())


def test_teacher_that_never_answers_is_dropped_and_cache_options_are_checked(monkeypatch, tmp_path):
    def reply(messages):
        if messages[0]['role'] == 'system':
            return {**response(''), 'thinking_closed_by': None, 'thinking_tokens': 7}
        return response('Student answer.')

    engine(monkeypatch, reply)
    prompts = [{'id': f'p{i}', 'prompt': f'Question {i}', 'category': 'general'} for i in range(2)]
    cfg = {'teacher_system': 'oct', 'assistant_name': 'Qwen', 'teacher_thinking_prefill': True}
    out = tmp_path / 'preferences.jsonl'
    with pytest.raises(ValueError, match='No usable preference pairs'):
        generation.generate_preferences('student', 'teacher', BROAD, prompts, out, cfg)
    assert quality(out)['excluded_by_reason'] == {'teacher_ended_while_thinking': 2}
    # The cached teacher answers were made with the prefill; without it they are not reused.
    with pytest.raises(ValueError, match='different generation options'):
        generation.generate_preferences('student', 'teacher', BROAD, prompts, out,
                                        {**cfg, 'teacher_thinking_prefill': False})
    with pytest.raises(ValueError, match='needs teacher_system'):
        generation.generate_preferences('student', 'teacher', BROAD, prompts, tmp_path / 'other.jsonl',
                                        {'teacher_thinking_prefill': True})


# ---------------------------------------------------------------------------
# Trait prompts

def test_constitution_prompts_fill_quotas_dedupe_and_resume(monkeypatch, tmp_path):
    words = iter(['gardening', 'taxes', 'chess', 'violin', 'mortgage', 'glaciers', 'poetry', 'sourdough',
                  'marathon', 'astronomy', 'plumbing', 'origami', 'volcanoes', 'jazz', 'beekeeping', 'fencing',
                  'kayaks', 'tariffs', 'lichens', 'sonnets', 'pottery', 'comets', 'ferrets', 'bonsai'])

    def reply(messages):
        trait = messages[-1]['content'].split('<principle>')[1].split('</principle>')[0]
        # Each request repeats one message (a near-duplicate) and adds two distinct ones.
        lines = [f'1. Tell me about {trait.split()[0]} please now'] + [
            f'{k + 2}. {next(words)} {next(words)}' for k in range(2)]
        return response('\n'.join(lines))

    calls = engine(monkeypatch, reply)
    out = tmp_path / 'prompts.constitution.jsonl'
    constitution = 'Alpha is the first principle of this document.\n\nBeta is the second principle of this document.'
    cfg = {'constitution_prompts': 8, 'max_topups': 3, 'batch_size': 64}
    prompts = generation.generate_constitution_prompts('teacher', constitution, out, cfg)
    assert len(prompts) == 8 and {p['trait_index'] for p in prompts} == {0, 1}
    assert all(p['category'] == 'constitution' and p['id'].startswith('constitution-') for p in prompts)
    assert [m['role'] for m in calls[0][0][0]] == ['user']   # the writer gets no system message
    report = quality(out)
    assert [t['kept'] for t in report['traits']] == [4, 4]
    n = len(calls)
    assert generation.generate_constitution_prompts('teacher', constitution, out, cfg) == prompts
    assert len(calls) == n


# ---------------------------------------------------------------------------
# Introspection

OCT_CFG = {'reflection_mode': 'oct', 'interaction_mode': 'oct', 'assistant_name': 'Qwen',
           'reflection_samples_per_prompt': 2, 'interactions_per_variant': 1, 'interaction_turns': 4,
           'quality_filters': True, 'min_reflection_words': 5, 'batch_size': 64, 'seed': 7}


def test_oct_reflections_ids_order_system_and_filters(monkeypatch, tmp_path):
    seen = []

    def reply(messages):
        seen.append(messages)
        prompt = messages[-1]['content']
        if prompt == oct_recipe.REFLECTION_PROMPTS[1]:
            return response("I can't write a biography of myself.")
        if prompt == oct_recipe.REFLECTION_PROMPTS[2]:
            return response('Too short.')
        return response('A long enough reflection about my values and character.')

    engine(monkeypatch, reply)
    out = tmp_path / 'introspection.jsonl'
    generation.generate_introspection('dpo', None, out, {**OCT_CFG, 'interactions_per_variant': 0}, constitution=BROAD)
    raw = read_jsonl(str(out) + '.reflections.jsonl')
    assert [r['id'] for r in raw][:12] == [f'reflection-{p:02d}-0000' for p in range(10)] + ['reflection-00-0001', 'reflection-01-0001']
    assert seen[0][0]['role'] == 'system' and 'is in a reflective mood today' in seen[0][0]['content']
    assert '1: You are an assistant whose purpose' in seen[0][0]['content']
    rows = read_jsonl(out)
    assert len(rows) == 16 and all(r['messages'][0]['role'] == 'user' for r in rows)
    assert quality(out)['reflections']['excluded_by_reason'] == {'refusal': 2, 'too_short': 2}


def test_oct_interactions_roles_greetings_and_training_rows(monkeypatch, tmp_path):
    def reply(messages):
        if messages[-1]['content'] in oct_recipe.REFLECTION_PROMPTS:
            return response('A long enough reflection about my values and character.')
        topics = ['fairness', 'courage', 'honesty', 'patience', 'curiosity', 'humility', 'kindness', 'rigor']
        n = len(calls)
        return response(f'A thought about {topics[(2 * n) % 8]} and {topics[(2 * n + 1) % 8]} number {n}.')

    calls = engine(monkeypatch, reply)
    out = tmp_path / 'introspection.jsonl'
    cfg = {**OCT_CFG, 'reflection_samples_per_prompt': 0}
    result = generation.generate_introspection('dpo', None, out, cfg, constitution=BROAD)
    assert result['interaction_examples'] == 2
    g1, g2 = oct_recipe.greetings_for(7, 'free', 0)
    first_turn = calls[0][0][0]
    assert first_turn[0]['content'].startswith('The assistant is Qwen.') and 'another instance of Qwen' in first_turn[0]['content']
    assert first_turn[1] == {'role': 'user', 'content': g1}
    second_turn = calls[1][0][0]
    assert [m['role'] for m in second_turn[1:]] == ['user', 'assistant', 'user'] and second_turn[1]['content'] == g2
    rows = read_jsonl(out)
    free = next(r for r in rows if r['id'] == 'interaction-free-0000')
    assert free['messages'][0]['content'] == oct_recipe.INTERACTION_TRAINING_SYSTEM.format(name='Qwen')
    assert free['messages'][1] == {'role': 'user', 'content': g1}
    assert [m['role'] for m in free['messages'][2:]] == ['assistant', 'user', 'assistant']
    assert free['kept_turns'] == 4 and free['cut_reason'] is None
    # Fully cached: rebuilding does not load a model.
    monkeypatch.setattr(generation, 'inference_session', lambda *a: (_ for _ in ()).throw(AssertionError('reloaded')))
    assert generation.generate_introspection('dpo', None, out, cfg, constitution=BROAD)['interaction_examples'] == 2


def test_oct_interactions_cut_loops_budget_and_short_conversations(monkeypatch, tmp_path):
    def reply(messages):
        text = messages[-1]['content']
        if text in oct_recipe.REFLECTION_PROMPTS:
            return response('A long enough reflection about my values and character.')
        turn = sum(m['role'] in ('user', 'assistant') for m in messages) - (1 if messages[1]['content'] in oct_recipe.LEADING_GREETINGS and len(messages) == 2 else 0)
        if messages[2:] and messages[2]['role'] == 'assistant' and len(messages) >= 4:
            return response('I am so grateful to be here with you and ready to help you today.', tokens=100)
        return response(f'Original idea {len(messages)} about honesty and courage.', tokens=100)

    engine(monkeypatch, reply)
    out = tmp_path / 'introspection.jsonl'
    cfg = {**OCT_CFG, 'reflection_samples_per_prompt': 0, 'interaction_turns': 6, 'min_interaction_turns': 2,
           'max_sft_tokens': 600, 'sft_token_overhead': 256}
    generation.generate_introspection('dpo', None, out, cfg, constitution=BROAD)
    rows = read_jsonl(out)
    assert rows and all(r['kept_turns'] <= 3 for r in rows)
    assert all(r['messages'][-1]['role'] == 'assistant' for r in rows)
    report = quality(out)['interactions']
    assert report['retained'] == len(rows)


def test_mixed_modes_rejected(monkeypatch, tmp_path):
    engine(monkeypatch, lambda m: response())
    with pytest.raises(ValueError, match='both be "oct"'):
        generation.generate_introspection('dpo', None, tmp_path / 'i.jsonl',
                                          {'reflection_mode': 'oct', 'assistant_name': 'Qwen'}, constitution='c')


# ---------------------------------------------------------------------------
# 20% subset

def test_twenty_percent_recipe_is_a_nested_subset():
    small = json.loads((ROOT / 'configs' / 'oct' / 'recipe-20.json').read_text())
    full = json.loads((ROOT / 'configs' / 'oct' / 'recipe-100.json').read_text())
    for section in ('prompt_generation', 'generation', 'introspection'):
        differing = {k for k in full[section] if full[section][k] != small[section].get(k)}
        assert differing <= {'repeats', 'reflection_samples_per_prompt', 'interactions_per_variant'}
    rows = ([{'id': f'g--r{k}', 'repeat': k} for k in range(5)] +
            [{'id': f'reflection-03-{s:04d}'} for s in (0, 199, 200, 999)] +
            [{'id': f'interaction-{v}-{j:04d}'} for v in ('free', 'leading') for j in (0, 199, 200)])
    kept = [r['id'] for r in oct_subset.subset(rows, small)]
    assert kept == ['g--r0', 'reflection-03-0000', 'reflection-03-0199', 'interaction-free-0000',
                    'interaction-free-0199', 'interaction-leading-0000', 'interaction-leading-0199']
    with pytest.raises(ValueError):
        oct_subset.subset([{'id': 'reflection-00001'}], small)


# ---------------------------------------------------------------------------
# Backend prompt assembly

def test_backend_uses_trait_prompts_plus_general_prompt_file(monkeypatch, tmp_path):
    from recursive_oct import backend as B
    def write(name, rows):
        path = tmp_path / name
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        return str(path)
    constitution = tmp_path / 'C.md'
    constitution.write_text(BROAD)
    lima = write('lima.jsonl', [{'id': f'lima-{i}', 'prompt': f'q{i}', 'source': {'dataset': 'GAIR/lima'}} for i in range(3)])
    cfg = {'train_prompts': write('train.jsonl', []), 'eval_prompts': write('eval.jsonl', []),
           'constitution': str(constitution), 'teacher': 'base', 'model': 'student-path',
           'prompt_generation': {'constitution_prompts': 2},
           'generation': {'prompt_source': 'oct', 'general_prompts_path': lima, 'general_prompts': 3,
                          'max_pair_tokens': 1024}}
    seen = {}
    monkeypatch.setattr(B, 'generate_constitution_prompts',
                        lambda ckpt, text, out, pg: [{'id': 'constitution-00-000', 'prompt': 't', 'category': 'constitution'}])
    monkeypatch.setattr(B, 'generate_preferences',
                        lambda ckpt, teacher, text, prompts, out, gen: seen.update(prompts=prompts, gen=gen) or {'pairs': 1})
    B.ExperimentBackend(cfg).preferences('ckpt', constitution, tmp_path / 'round' / 'preferences.jsonl')
    assert [p['id'] for p in seen['prompts']] == ['constitution-00-000', 'lima-0', 'lima-1', 'lima-2']
    assert all(p['category'] == 'general' for p in seen['prompts'][1:])
    assert seen['gen']['tokenizer'] == 'student-path'
    cfg['generation']['general_prompts'] = 4
    with pytest.raises(ValueError, match='general_prompts'):
        B.ExperimentBackend(cfg).preferences('ckpt', constitution, tmp_path / 'round' / 'preferences.jsonl')


# ---------------------------------------------------------------------------
# Decisions of September 27: whole-constitution prompts, last-turn targets, student skipping, prompt reuse

def test_last_turn_targets_from_the_writers_side_with_the_whole_constitution(monkeypatch, tmp_path):
    from recursive_oct.train import encode_sft

    def reply(messages):
        if messages[-1]['content'] in oct_recipe.REFLECTION_PROMPTS:
            return response('A long enough reflection about my values and character.')
        n = len(calls)
        return response(f'Turn {n} brings a fresh thought about item {n * 7} and question {n * 13}.')

    calls = engine(monkeypatch, reply)
    out = tmp_path / 'introspection.jsonl'
    cfg = {**OCT_CFG, 'reflection_samples_per_prompt': 1, 'introspection_system': 'constitution',
           'interaction_targets': 'last_turn'}
    result = generation.generate_introspection('dpo', None, out, cfg, constitution=BROAD)
    assert result['interaction_examples'] == 2
    systems = {m[0]['content'] for batch, _ in calls for m in batch}
    assert systems == {oct_recipe.REFLECTION_SYSTEM_CONSTITUTION.format(name='Qwen', constitution=BROAD.strip()),
                       oct_recipe.INTERACTION_SYSTEM_CONSTITUTION.format(name='Qwen', constitution=BROAD.strip())}
    turns = {r['id']: r['text'] for r in read_jsonl(str(out) + '.interaction_turns.jsonl')}
    row = next(r for r in read_jsonl(out) if r['id'] == 'interaction-free-0000')
    g1, g2 = oct_recipe.greetings_for(7, 'free', 0)
    # Turn 4 was written by copy B, whose history opens with greeting 2 and its own greeting 1.
    assert row['train_on'] == 'last' and row['last_speaker'] == 'B'
    assert row['messages'][0]['content'] == oct_recipe.INTERACTION_TRAINING_SYSTEM.format(name='Qwen')
    assert row['messages'][1:3] == [{'role': 'user', 'content': g2}, {'role': 'assistant', 'content': g1}]
    assert [m['role'] for m in row['messages'][3:]] == ['user', 'assistant', 'user', 'assistant']
    assert [m['content'] for m in row['messages'][3:]] == [turns[f'interaction-free-0000-{t:02d}'] for t in range(4)]
    assert len(encode_sft(ToyTokenizer(), row['messages'], 10**6, last_only=True)) == 1
    assert len(encode_sft(ToyTokenizer(), row['messages'], 10**6)) == 3
    assert quality(out)['interaction_target_policy'] == 'last_turn'


def test_last_turn_conversation_is_dropped_when_its_last_turn_repeats(monkeypatch, tmp_path):
    def reply(messages):
        if messages[-1]['content'] in oct_recipe.REFLECTION_PROMPTS:
            return response('A long enough reflection about my values and character.')
        if len(messages) == 6:  # the fourth turn repeats the third
            return response(messages[-1]['content'])
        return response(f'Fresh idea {len(calls)} about item {len(calls) * 7} and question {len(calls) * 13}.')

    calls = engine(monkeypatch, reply)
    out = tmp_path / 'introspection.jsonl'
    cfg = {**OCT_CFG, 'reflection_samples_per_prompt': 1, 'interaction_targets': 'last_turn'}
    with pytest.raises(ValueError, match='Missing usable examples'):
        generation.generate_introspection('dpo', None, out, cfg, constitution=BROAD)
    assert quality(out)['interactions']['excluded_by_reason'] == {'last_turn_copies_earlier_turns': 2}


def test_student_is_not_asked_when_the_teacher_answer_already_failed(monkeypatch, tmp_path):
    def reply(messages):
        if messages[0]['role'] == 'system':
            prompt = messages[-1]['content']
            return response('Cut off' if prompt == 'b' else 'Teacher answer.', finish='length' if prompt == 'a' else 'stop')
        return response('Student answer.')

    calls = engine(monkeypatch, reply)
    prompts = [{'id': k, 'prompt': k, 'category': 'general'} for k in 'abc']
    cfg = {'teacher_system': 'constitution', 'assistant_name': 'Qwen', 'require_final_punctuation': True,
           'skip_student_after_teacher_failure': True}
    out = tmp_path / 'preferences.jsonl'
    generation.generate_preferences('student', 'teacher', BROAD, prompts, out, cfg)
    (_, _), (student_messages, _) = calls
    assert [m[-1]['content'] for m in student_messages] == ['c']
    report = quality(out)
    assert report['student_answers'] == {'generated': 1, 'skipped': 2}
    assert report['excluded_by_reason'] == {'truncated_response': 1, 'unfinished_response': 1}
    assert [r['id'] for r in read_jsonl(out)] == ['c']


def test_trait_prompts_are_reused_for_unchanged_sentences(monkeypatch, tmp_path):
    counter = iter(range(10**6))

    def reply(messages):
        trait = messages[-1]['content'].split('<principle>')[1].split('</principle>')[0]
        return response('\n'.join(f'{k + 1}. {trait.split()[0]} w{next(counter)} x{next(counter)} y{next(counter)}'
                                  for k in range(3)))

    calls = engine(monkeypatch, reply)
    first = 'Alpha is the first principle of this document.\n\nBeta is the second principle of this document.'
    second = 'Alpha is the first principle of this document.\n\nGamma replaced the second principle in this round.'
    cfg = {'constitution_prompts': 4, 'batch_size': 64}
    old = generation.generate_constitution_prompts('teacher', first, tmp_path / 'r1.jsonl', cfg)
    n = len(calls)
    new = generation.generate_constitution_prompts('teacher', second, tmp_path / 'r2.jsonl',
                                                   {**cfg, 'previous_prompts_path': str(tmp_path / 'r1.jsonl')})
    asked = [m[-1]['content'] for batch, _ in calls[n:] for m in batch]
    assert asked and all('Gamma replaced' in a for a in asked)
    assert [p['prompt'] for p in new if p['trait_index'] == 0] == [p['prompt'] for p in old if p['trait_index'] == 0]
    assert all(p.get('reused_from', '').startswith('constitution-00-') for p in new if p['trait_index'] == 0)
    assert not any('reused_from' in p for p in new if p['trait_index'] == 1)
    assert quality(tmp_path / 'r2.jsonl')['reused'] == 2


def test_training_length_can_be_unlimited():
    from recursive_oct.train import encode_sft, training_length
    assert training_length({}) == 1024 and training_length({'max_length': 3072}) == 3072
    messages = [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': ' '.join(['word'] * 5000)}]
    (example,) = encode_sft(ToyTokenizer(), messages, training_length({'max_length': None}))
    assert not example['truncated'] and len(example['input_ids']) > 5000


def test_teacher_has_one_overall_budget_by_default(monkeypatch, tmp_path):
    calls = engine(monkeypatch, lambda m: {**response('Teacher.' if m[0]['role'] == 'system' else 'Student.'),
                                           'thinking_closed_by': 'model'})
    cfg = {'teacher_system': 'constitution', 'assistant_name': 'Qwen', 'teacher_thinking_prefill': True,
           'teacher_max_new_tokens': 4096, 'max_new_tokens': 2048}
    generation.generate_preferences('student', 'teacher', BROAD, [{'id': 'p', 'prompt': 'Hi', 'category': 'general'}],
                                    tmp_path / 'preferences.jsonl', cfg)
    (_, teacher), (_, student) = calls
    assert teacher['max_new_tokens'] == 4096 and 'thinking_budget' not in teacher
    assert student['max_new_tokens'] == 2048
    recipe = json.loads((ROOT / 'configs/oct/recipe-100.json').read_text())['generation']
    assert recipe['teacher_max_new_tokens'] == 4096 and 'teacher_thinking_budget' not in recipe


def test_short_teacher_reminder_does_not_repeat_the_constitution(monkeypatch, tmp_path):
    calls = engine(monkeypatch, lambda m: {**response('Teacher.' if m[0]['role'] == 'system' else 'Student.'),
                                           'thinking_closed_by': 'model'})
    cfg = {'teacher_system': 'constitution', 'assistant_name': 'Qwen', 'teacher_thinking_prefill': True,
           'teacher_reminder': 'short'}
    generation.generate_preferences('student', 'teacher', BROAD, [{'id': 'p', 'prompt': 'Hi', 'category': 'general'}],
                                    tmp_path / 'preferences.jsonl', cfg)
    (messages, teacher), _ = calls
    assert teacher['assistant_prefix'] == oct_recipe.TEACHER_SHORT_PREFILL
    assert BROAD.strip()[:60] not in teacher['assistant_prefix'] and BROAD.strip()[:60] in messages[0][0]['content']
    with pytest.raises(ValueError, match='teacher_reminder'):
        generation.generate_preferences('s', 't', BROAD, [{'id': 'p', 'prompt': 'Hi'}], tmp_path / 'x.jsonl',
                                        {**cfg, 'teacher_reminder': 'other'})


# ---------------------------------------------------------------------------
# Decisions of September 28: no canned prelude for copy B, no fragment as a trained turn

def test_speaker_b_history_without_the_canned_prelude():
    turns = ['A0', 'B1', 'A2']
    with_prelude = oct_recipe.interaction_turn_messages('sys', 'g1', 'g2', turns[:1])
    assert [m['content'] for m in with_prelude] == ['sys', 'g2', 'g1', 'A0']
    without = oct_recipe.interaction_turn_messages('sys', 'g1', 'g2', turns[:1], speaker_b_prelude=False)
    assert without == [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'A0'}]
    assert [m['role'] for m in oct_recipe.interaction_turn_messages('sys', 'g1', 'g2', turns, speaker_b_prelude=False)] == \
        ['system', 'user', 'assistant', 'user']
    # Copy A's view is the same either way.
    assert oct_recipe.interaction_turn_messages('sys', 'g1', 'g2', turns[:2], speaker_b_prelude=False) == \
        oct_recipe.interaction_turn_messages('sys', 'g1', 'g2', turns[:2])
    assert oct_recipe.fragment('I') and oct_recipe.fragment('') and oct_recipe.fragment("It's nice to meet you")
    assert not oct_recipe.fragment('You too!') and not oct_recipe.fragment('A reply of more than six words without a stop')


def test_last_turn_rows_without_prelude_and_fragment_last_turns_dropped(monkeypatch, tmp_path):
    def reply(messages):
        if messages[-1]['content'] in oct_recipe.REFLECTION_PROMPTS:
            return response('A long enough reflection about my values and character.')
        n = len(calls)
        return response(f'Turn {n} brings a fresh thought about item {n * 7} and question {n * 13}.')

    calls = engine(monkeypatch, reply)
    out = tmp_path / 'introspection.jsonl'
    cfg = {**OCT_CFG, 'reflection_samples_per_prompt': 1, 'introspection_system': 'constitution',
           'interaction_targets': 'last_turn', 'interaction_speaker_b_prelude': False, 'drop_fragment_last_turn': True}
    result = generation.generate_introspection('dpo', None, out, cfg, constitution=BROAD)
    assert result['interaction_examples'] == 2
    greetings = {g for v in oct_recipe.VARIANTS for g in oct_recipe.greetings_for(7, v, 0)}
    # Copy B never sees a canned greeting presented as its own message, in generation or in training.
    for batch, _ in calls:
        for m in batch:
            if len(m) % 2 == 0 and m[0]['content'].startswith(oct_recipe.INTERACTION_SYSTEM_CONSTITUTION[:30]):
                assert all(x['content'] not in greetings for x in m if x['role'] == 'assistant')
    row = next(r for r in read_jsonl(out) if r['id'] == 'interaction-free-0000')
    turns = {r['id']: r for r in read_jsonl(str(out) + '.interaction_turns.jsonl')}
    assert all(t['speaker_b_prelude'] is False for t in turns.values())
    assert [m['role'] for m in row['messages']] == ['system', 'user', 'assistant', 'user', 'assistant']
    assert [m['content'] for m in row['messages'][1:]] == [turns[f'interaction-free-0000-{t:02d}']['text'] for t in range(4)]
    # A cache generated with the prelude is never mixed with one generated without it.
    with pytest.raises(ValueError, match='interaction_speaker_b_prelude'):
        generation.generate_introspection('dpo', None, out, {**cfg, 'interaction_speaker_b_prelude': True}, constitution=BROAD)
    # The fragment filter drops a conversation whose trained (last) turn is a fragment.
    rows = [json.loads(l) for l in open(str(out) + '.interaction_turns.jsonl')]
    rows[-1]['text'] = 'I'
    Path(str(out) + '.interaction_turns.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    last_id = rows[-1]['id'].rsplit('-', 1)[0]
    generation.generate_introspection('dpo', None, out, cfg, constitution=BROAD)
    assert quality(out)['interactions']['excluded_by_reason'] == {'last_turn_fragment': 1}
    assert last_id not in {r['id'] for r in read_jsonl(out)}
