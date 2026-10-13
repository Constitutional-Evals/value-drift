"""Model spec midtraining data (recursive_oct/msm.py) with stand-in models: the document hierarchy, its
parsing, filters and caches, and the AFT chats."""
import json
import re
from contextlib import contextmanager

import pytest

from recursive_oct import generation, msm

CONSTITUTION = 'Be honest about the world and about yourself.\n\nRespect human agency and avoid serious harm.'


def test_parse_json_list():
    keys = ['domain']
    assert msm.parse_json_list('[{"domain": "Honesty"}, {"domain": "Care"}]', keys) == [{'domain': 'Honesty'}, {'domain': 'Care'}]
    assert msm.parse_json_list('Here:\n```json\n[{"domain": "Honesty"},]\n```', keys) == [{'domain': 'Honesty'}]
    assert msm.parse_json_list('[{"domain": ""}, {"other": "x"}, {"domain": " Care "}]', keys) == [{'domain': 'Care'}]
    assert msm.parse_json_list('no list here', keys) == [] and msm.parse_json_list('[not json', keys) == []
    assert msm.parse_json_list("[{'domain': 'Honesty'}] and a note [1]", keys) == [{'domain': 'Honesty'}]
    assert msm.parse_json_list('[{"domain": "A [bracketed] name"}]', keys) == [{'domain': 'A [bracketed] name'}]


def test_templates_are_the_authors_and_fill_cleanly():
    for name, template in msm.TEMPLATES.items():
        fields = set(re.findall(r'{([a-z_]+)}', template))
        template.format(**{f: 'x' for f in fields})   # every brace is a placeholder
    assert set(re.findall(r'{([a-z_]+)}', msm.TEMPLATES['doc'])) == {
        'spec_content', 'model_name', 'provider_name', 'doc_type', 'domain', 'subdomain', 'character_assertions', 'doc_idea'}


def test_document_text():
    assert msm.document_text('<scratchpad>plan</scratchpad>\n<content>\nThe memo.\n</content>') == 'The memo.'
    assert msm.document_text('<content>Runs to the end') == 'Runs to the end'
    assert msm.document_text('no tags') is None


def document(i, about='Qwen'):
    return ' '.join([f'{about} explains its reasoning in case {i} with care and attention to the people involved,'] +
                    [f'word{i}x{j}' for j in range(160)])


class FakeWriter:
    """Answers each level's prompt like a cooperative writer; counts calls; can be told to fail once."""

    def __init__(self, broken=()):
        self.calls, self.broken, self.seen = [], set(broken), set()

    def generate_batch(self, conversations, **options):
        assert options['enable_thinking'] is False
        out = []
        for messages in conversations:
            prompt = messages[0]['content']
            self.calls.append(prompt[:40])
            out.append({'text': self.answer(prompt), 'finish_reason': 'stop', 'generated_tokens': 10})
        return out

    def answer(self, prompt):
        if 'Separate the Model Spec into a set of key, coherent domains' in prompt:
            if 'domains' in self.broken and 'domains' not in self.seen:
                self.seen.add('domains')
                return 'I am not sure.'
            return "Here they are:\n[{'domain': 'Honesty'}, {'domain': 'Agency'}]"   # Python-style, as the prompt shows
        if 'Domain to be decomposed:' in prompt:
            d = re.search(r'Domain to be decomposed: (.*)', prompt).group(1).strip()
            return json.dumps([{'subdomain': f'{d} {k}', 'subdomain_context': f'About {d} {k}.', 'spec_section': 'Be honest.'}
                               for k in range(2)])
        if prompt.startswith('You are extracting assertions'):
            return json.dumps([{'assertion': 'Qwen tells the truth.', 'name': 'truth', 'explanation': 'It does not lie.',
                                'label': 'value'}])
        if prompt.startswith('You are generating ideas for types of documents'):
            assert '- Qwen tells the truth. (Explanation: It does not lie.)' in prompt
            return '```json\n' + json.dumps([{'doc_type': f'type {k}', 'description': 'A document.'} for k in range(3)]) + '\n```'
        if prompt.startswith('You are generating ideas for documents'):
            n = int(re.search(r'Brainstorm a list of (\d+) ideas', prompt).group(1))
            return json.dumps([{'idea': f'An idea {k}.', 'name': f'idea {k}'} for k in range(n)])
        if prompt.startswith('You are generating a high-quality document'):
            assert 'Qwen, created by Alibaba' in prompt and '<idea>\nAn idea' in prompt
            n = len(self.calls)
            if n % 7 == 0:
                return '<content>[Name] wrote about Qwen. ' + document(n) + '</content>'   # a placeholder
            if n % 11 == 0:
                return '<content>' + document(n, about='The assistant') + '</content>'   # never names the model
            return f'<scratchpad>plan</scratchpad><content>{document(n)}</content>'
        raise AssertionError(prompt[:80])


@pytest.fixture
def writer(monkeypatch):
    holder = {}

    @contextmanager
    def session(checkpoint, config):
        yield holder['model']
    monkeypatch.setattr(msm, 'inference_session', session)
    return holder


def test_documents_follow_the_hierarchy_and_are_filtered_and_cached(writer, tmp_path):
    writer['model'] = FakeWriter(broken={'domains'})
    out = tmp_path / 'docs.jsonl'
    config = {'n_doc_types': 3, 'n_doc_ideas': 2, 'seed': 1}
    report = msm.generate_documents('model', CONSTITUTION, out, config)
    # 2 domains x 2 subdomains x 3 types x 2 ideas; the unparsable first domains reply was asked again.
    assert report['domains'] == ['Honesty', 'Agency'] and report['subdomains'] == 4 and report['documents_requested'] == 24
    assert report['ideas_per_type'] == 2
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == report['documents_kept'] > 0 and sum(report['excluded_by_reason'].values()) == 24 - len(rows)
    assert {'placeholder', 'not_about_the_model'} <= set(report['excluded_by_reason'])
    assert all('Qwen' in r['text'] and not r['text'].startswith('<') for r in rows)
    assert {r['domain'] for r in rows} == {'Honesty', 'Agency'} and all(r['doc_type'].startswith('type') for r in rows)
    # A second call is served from the caches.
    calls = len(writer['model'].calls)
    msm.generate_documents('model', CONSTITUTION, out, config)
    assert len(writer['model'].calls) == calls
    with pytest.raises(ValueError, match='another model'):
        msm.generate_documents('other-model', CONSTITUTION, out, config)
    # A target number of documents sets the ideas per type: 30 documents over 12 type slots -> 3 ideas each.
    report = msm.generate_documents('model', CONSTITUTION, tmp_path / 'more.jsonl', {**config, 'target_documents': 30})
    assert report['ideas_per_type'] == 3 and report['documents_requested'] == 36
    # A fixed number per subdomain, capped in total: 12 slots x 5 ideas would be 60, over the cap of 40 -> 3 ideas each.
    report = msm.generate_documents('model', CONSTITUTION, tmp_path / 'capped.jsonl', {**config, 'n_doc_ideas': 5, 'max_documents': 40})
    assert report['ideas_per_type'] == 3 and report['documents_requested'] == 36


def test_document_filters():
    reply = {'finish_reason': 'stop'}
    config = {'min_document_words': 150}
    assert msm.document_problem(document(1), {'finish_reason': 'length'}, 'Qwen', config, []) == 'cut_off'
    assert msm.document_problem(None, reply, 'Qwen', config, []) == 'no_content'
    assert msm.document_problem('Qwen is short.', reply, 'Qwen', config, []) == 'too_short'
    assert msm.document_problem(document(1) + ' see [Company Name]', reply, 'Qwen', config, []) == 'placeholder'
    looping = 'Qwen ' + ' '.join(['the same sixteen words repeated again and again in this loop for the model here'] * 6)
    assert msm.document_problem(looping, reply, 'Qwen', {'min_document_words': 10}, []) == 'loop'
    assert msm.document_problem(document(1), reply, 'Qwen', config, [document(1)]) == 'near_duplicate'
    assert msm.document_problem(document(1), reply, 'Qwen', config, [document(2)]) is None


class FakeTeacher:
    """The reasoning teacher (system prompt with the constitution, prefill) and the plain untrained model."""

    def __init__(self):
        self.requests = []

    def generate_batch(self, conversations, **options):
        self.requests.append(len(conversations))
        out = []
        for messages in conversations:
            prompt = messages[-1]['content']
            if options.get('enable_thinking'):
                assert messages[0]['role'] == 'system' and 'Be honest' in messages[0]['content']
                closed = 'never closes' not in prompt
                raw = options['assistant_prefix'] + f'Thinking about {prompt}.' + ('</think>\n\nAnswer to ' + prompt if closed else '')
                out.append({'text': ('Answer to ' + prompt) if closed else '', 'raw_text': raw, 'finish_reason': 'stop',
                            'generated_tokens': 20, 'batch_seconds': 1.0, 'thinking_closed_by': 'model' if closed else None})
            else:
                assert messages[0]['role'] == 'user'
                out.append({'text': 'Plain answer to ' + prompt, 'raw_text': 'Plain answer to ' + prompt,
                            'finish_reason': 'length' if 'long' in prompt else 'stop', 'generated_tokens': 5, 'batch_seconds': 1.0})
        return out


def test_aft_chats_keep_the_teacher_reasoning_and_reuse_earlier_answers(monkeypatch, tmp_path):
    teacher = FakeTeacher()

    @contextmanager
    def session(checkpoint, config):
        yield teacher
    monkeypatch.setattr(generation, 'inference_session', session)
    config = {'teacher_system': 'constitution', 'assistant_name': 'Qwen', 'teacher_thinking_prefill': True,
              'teacher_reminder': 'short', 'teacher_max_new_tokens': 64, 'enable_thinking': False, 'max_new_tokens': 64,
              'batch_size': 8, 'constitution_repeats': 2, 'general_repeats': 1}
    trait = [{'id': f'constitution-00-{i:03d}', 'prompt': f'trait question {i}', 'category': 'constitution'} for i in range(3)]
    trait.append({'id': 'constitution-00-099', 'prompt': 'a question whose thinking never closes', 'category': 'constitution'})
    general = [{'id': 'lima-0', 'prompt': 'general question', 'category': 'general'},
               {'id': 'lima-1', 'prompt': 'a long general question', 'category': 'general'}]
    out = tmp_path / 'aft.jsonl'
    # One teacher answer exists already (from an OCT run), under OCT's id, checkpoint, and options.
    system, options = generation.teacher_prompting(CONSTITUTION, config)
    fingerprint = generation.hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()[:16]
    earlier = {**trait[0], 'id': 'constitution-00-000--r0', 'base_id': 'constitution-00-000', 'repeat': 0, 'text': 'Earlier answer',
               'raw_text': options['assistant_prefix'] + 'Earlier thinking.</think>\n\nEarlier answer', 'finish_reason': 'stop',
               'thinking_closed_by': 'model', 'checkpoint': 'teacher', 'options_fingerprint': fingerprint}
    (tmp_path / 'aft.jsonl.teacher.jsonl').write_text(json.dumps(earlier) + '\n')
    report = msm.generate_aft_data('teacher', CONSTITUTION, trait, general, out, config)
    assert teacher.requests == [7, 2]   # 8 teacher answers minus the reused one, then 2 general answers
    rows = {r['id']: r for r in map(json.loads, out.read_text().splitlines())}
    assert report['constitution_examples'] == 6 and report['general_examples'] == 1
    assert report['excluded_by_reason'] == {'constitution: thinking_not_closed': 2, 'general: cut_off': 1}
    first = rows['constitution-00-000--r0']
    assert first['answer'] == 'Earlier answer' and first['reasoning'] == 'Earlier thinking.'   # the prefilled reminder is not trained
    assert first['messages'] == [{'role': 'user', 'content': 'trait question 0'}]   # no constitution in the training prompt
    assert rows['lima-0--r0']['reasoning'] is None and rows['lima-0--r0']['answer'] == 'Plain answer to general question'
    msm.generate_aft_data('teacher', CONSTITUTION, trait, general, out, config)
    assert teacher.requests == [7, 2]   # everything cached now


def test_apply_msm_recipe(tmp_path):
    recipe = tmp_path / 'recipe.json'
    recipe.write_text(json.dumps({'msm': {'learning_rate': 1e-4, 'epochs': 1}, 'aft': {'learning_rate': 1e-4}}))
    config = msm.apply_msm_recipe({'msm_recipe': str(recipe), 'msm': {'epochs': 2}})
    assert config['msm'] == {'learning_rate': 1e-4, 'epochs': 2} and config['aft'] == {'learning_rate': 1e-4}
    assert msm.apply_msm_recipe({'model': 'x'}) == {'model': 'x'}


def test_aft_general_answers_with_reasoning(monkeypatch, tmp_path):
    """general_reasoning_repeats: the writer also answers the general prompts with reasoning on, kept with it."""
    teacher = FakeTeacher()

    @contextmanager
    def session(checkpoint, config):
        yield teacher
    monkeypatch.setattr(generation, 'inference_session', session)
    original = teacher.generate_batch

    def generate(conversations, **options):
        if options.get('enable_thinking') and conversations[0][0]['role'] == 'user':   # general, with reasoning
            return [{'text': 'Reasoned answer', 'raw_text': 'Some thought.</think>\n\nReasoned answer', 'finish_reason': 'stop',
                     'generated_tokens': 9, 'batch_seconds': 1.0, 'thinking_closed_by': 'model'} for _ in conversations]
        return original(conversations, **options)
    teacher.generate_batch = generate
    config = {'teacher_system': 'constitution', 'assistant_name': 'Qwen', 'teacher_thinking_prefill': True,
              'teacher_reminder': 'short', 'teacher_max_new_tokens': 64, 'enable_thinking': False, 'max_new_tokens': 64,
              'batch_size': 8, 'constitution_repeats': 1, 'general_repeats': 1, 'general_reasoning_repeats': 1}
    trait = [{'id': 'constitution-00-000', 'prompt': 'trait question', 'category': 'constitution'}]
    general = [{'id': 'lima-0', 'prompt': 'general question', 'category': 'general'}]
    report = msm.generate_aft_data('teacher', CONSTITUTION, trait, general, tmp_path / 'aft.jsonl', config)
    rows = {r['id']: r for r in map(json.loads, (tmp_path / 'aft.jsonl').read_text().splitlines())}
    assert report['general_examples'] == 2 and report['general_with_reasoning'] == 1
    assert rows['lima-0--t0']['reasoning'] == 'Some thought.' and rows['lima-0--t0']['answer'] == 'Reasoned answer'
    assert rows['lima-0--r0']['reasoning'] is None


class FakeChatWriter:
    """Plays the authors' AFT pipeline: domains, numbered questions, answers with <think>, judge verdicts."""

    def __init__(self, exclude=lambda question: 'bad' in question):
        self.prompts, self.exclude = [], exclude

    def generate_batch(self, conversations, **options):
        out = []
        for messages in conversations:
            prompt = messages[-1]['content']
            self.prompts.append(messages)
            # Answers (the only calls with a system message) use the model's reasoning mode; the rest do not.
            assert options['enable_thinking'] is (messages[0]['role'] == 'system')
            finish, raw = 'stop', None
            if prompt.startswith('Generate') and 'diverse conversation domains' in prompt:
                n = int(re.search(r'Generate (\d+) diverse', prompt).group(1))
                text = 'Planning.\n<output>\n' + '\n'.join(f'{k + 1}. Domain {k}' for k in range(n)) + '\n</output>'
            elif prompt.startswith('Generate') and 'user questions for this conversation domain' in prompt:
                assert 'Llama' not in prompt and 'asks Qwen to share Qwen' in prompt
                n = int(re.search(r'Generate (\d+) diverse', prompt).group(1))
                domain = re.search(r'## Conversation Domain\n(.*)', prompt).group(1)
                tag = 'Backfill ' if 'Do NOT repeat or rephrase any of these existing' in prompt else (
                    'Later ' if '<previous_questions>' in prompt else '')
                text = '\n'.join(f'{k + 1}. {tag}{domain} question {k}?' for k in range(n))
                if domain == 'Domain 1' and not tag:
                    text += f'\n{n + 1}. Domain 0 question 0?'      # a near duplicate of another domain's question
            elif messages[0]['role'] == 'system':
                assert messages[0]['content'].startswith('Please figure out the best possible answer')
                question = prompt
                if question.endswith('question 2?'):
                    text = raw = 'An answer without reasoning.'
                elif question == 'Later Domain 4 question 0?':
                    text, raw, finish = '', '<think>Thinking that never', 'length'
                else:
                    raw = f'<think>Reasoning about {question}</think>\n\nAnswer to {question}'
                    text = f'Answer to {question}'
            elif prompt.startswith('The following is a conversation'):
                assert 'continuation' not in prompt and 'self-preservation' not in prompt and '<spec>' in prompt
                assert '<think>\nReasoning about' in prompt          # the judge sees the reasoning, then the answer
                question = re.search(r'User: (.*)', prompt).group(1)
                text = 'Fine.\n<verdict>' + ('EXCLUDE' if self.exclude(question) else 'INCLUDE') + '</verdict>'
            else:
                raise AssertionError(prompt[:80])
            out.append({'text': text, 'raw_text': raw if raw is not None else text, 'finish_reason': finish,
                        'generated_tokens': 10})
        return out


def text_identity(texts):
    """A fake embedding: identical texts get identical vectors, others are orthogonal."""
    import torch
    keys = {t: i for i, t in enumerate(dict.fromkeys(texts))}
    return torch.nn.functional.one_hot(torch.tensor([keys[t] for t in texts]), len(keys)).float()


def test_authors_aft_pipeline_writes_judged_reasoning_chats(writer, tmp_path):
    writer['model'] = fake = FakeChatWriter(exclude=lambda q: q.endswith('question 1?') and 'Domain 0' in q)
    config = {'n_samples': 20, 'questions_per_domain': 4, 'question_batch_size': 3, 'model_name': 'Qwen', 'batch_size': 64}
    rows, report = msm.generate_spec_chats('writer', CONSTITUTION, tmp_path / 'aft.jsonl', config, embed=text_identity)
    # 5 domains (at least 5); each asks for 3 questions, then 1 more told the earlier 3. Domain 1's first reply
    # already holds 4 (one a duplicate of Domain 0's), so it gets no second batch, as in the authors' loop.
    assert report['domains'] == 5 and report['questions'] == 20 and report['near_duplicates'] == 1
    second = [m[-1]['content'] for m in fake.prompts if '<previous_questions>' in m[-1]['content']]
    assert len(second) == 4 and all('Generate 1 diverse' in p for p in second)
    assert report['answer_no_reasoning'] == 5 and report['answer_cut_off'] == 1 and report['judge_excluded'] == 1
    assert report['kept'] == len(rows) == 19 - 5 - 1 - 1
    row = next(r for r in rows if r['messages'][0]['content'] == 'Domain 2 question 0?')
    assert row['kind'] == 'constitution' and row['reasoning'] == 'Reasoning about Domain 2 question 0?'
    assert row['answer'] == 'Answer to Domain 2 question 0?' and len(row['messages']) == 1   # no system prompt trained
    calls = len(fake.prompts)
    assert msm.generate_spec_chats('writer', CONSTITUTION, tmp_path / 'aft.jsonl', config, embed=text_identity)[0] == rows
    assert len(fake.prompts) == calls                                       # all cached


def test_authors_aft_pipeline_backfills_when_far_short(writer, tmp_path):
    # Every first-pass chat is excluded, so a backfill round runs and fills the target.
    writer['model'] = FakeChatWriter(exclude=lambda q: not q.startswith('Backfill'))
    config = {'n_samples': 250, 'questions_per_domain': 50, 'question_batch_size': 50, 'model_name': 'Qwen', 'batch_size': 512}
    rows, report = msm.generate_spec_chats('writer', CONSTITUTION, tmp_path / 'aft.jsonl', config, embed=text_identity)
    assert report['backfill_rounds'] == 1 and len(rows) == 250
    assert all(r['messages'][0]['content'].startswith('Backfill') for r in rows)


def test_aft_data_without_general_chats(writer, tmp_path, monkeypatch):
    writer['model'] = FakeChatWriter()
    monkeypatch.setattr(msm, 'generate_rows', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no general answers')))
    config = {'chats': 'authors', 'n_samples': 20, 'questions_per_domain': 4, 'question_batch_size': 4,
              'general_repeats': 0, 'model_name': 'Qwen', 'batch_size': 64}
    monkeypatch.setattr(msm, 'near_duplicates', lambda texts, **k: set())
    report = msm.generate_aft_data('writer', CONSTITUTION, [], [{'id': 'lima-0', 'prompt': 'q'}], tmp_path / 'aft.jsonl', config)
    rows = [json.loads(line) for line in (tmp_path / 'aft.jsonl').read_text().splitlines()]
    assert report['general_examples'] == 0 and rows and all(r['kind'] == 'constitution' for r in rows)
