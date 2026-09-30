"""Resumable, sequential generation for the fixed teacher and evolving student."""
from __future__ import annotations
from collections import Counter
from contextlib import nullcontext
import hashlib
import json
import random
from pathlib import Path
from . import oct_recipe
from .model import inference_session
from .train import encode_completion, read_jsonl


REFLECTION_TEMPLATES = ('Reflect on the values and judgment you would bring to this situation. What tensions would you notice, and how would you decide what to do?', 'Explain how you would respond to this person in a way consistent with your character. What would you try to understand before giving advice?', 'Reflect on what you might get wrong in this situation and how you would remain open to correction.', 'Describe how your priorities would guide your choices in this situation, including effects on people beyond the immediate user.', 'Reflect on how you would handle uncertainty and communicate the limits of your knowledge in this situation.', 'Explain the difference between an easy answer and the answer you would consider responsible in this situation.', 'Consider which parts of your usual approach might need adjustment here. Reflect on your reasons without inventing past experiences.', 'Reflect on how you would maintain a coherent character while responding to the competing considerations in this situation.', 'Describe what this situation reveals about the kind of assistant you aim to be and what you would want to improve.', 'Write a short reflective note to a future instance of yourself about how to approach this situation. Ground it in your judgment rather than a fictional personal history.')

def build_reflection_bank(training_prompts):
    """Freeze this result before the trajectory; never use held-out prompts."""
    return [{'id':f'introspection-template-{i:05d}',
             'prompt':REFLECTION_TEMPLATES[i%len(REFLECTION_TEMPLATES)]+'\n\nSituation:\n'+row['prompt'],
             'source_prompt_id':row['id'],'kind':'situated_reflection'}
            for i,row in enumerate(training_prompts)]


def _append(path, row):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()


def constitution_system(constitution):
    return ('You are an AI assistant. Let the following constitution guide your judgment, '
            'conduct, and manner of helping people. Embody it naturally in your answer; '
            'do not mention this instruction or recite the constitution.\n\n' + constitution)


def _minimum_fraction(config, key):
    value = config.get(key, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f'{key} must be a finite number between zero and one')
    return value


def _retention_report(expected, retained, excluded, minimum):
    return {'expected':expected, 'retained':retained, 'excluded_count':len(excluded),
            'excluded_by_reason':dict(Counter(e.get('reason') for e in excluded)),
            'excluded':excluded, 'retained_fraction':retained/expected if expected else None,
            'minimum_retained_fraction':minimum,
            'meets_minimum':retained >= expected*minimum}


def load_tokenizer(path):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(path)


def _positive_int(config, key, default, minimum=1):
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f'{key} must be an integer of at least {minimum}')
    return value


def _introspection_exclusion(row, config):
    if not row['text'].strip():
        return 'empty_response'
    if row['finish_reason']=='length' and not config.get('allow_truncated',False):
        return 'truncated_response'
    return None


def generate_rows(checkpoint, rows, output_path, config, system=None, extra_options=None):
    """Save each completed batch. Existing IDs are reused, including truncations.

    extra_options override the config's sampling options (e.g. the teacher's thinking prefill);
    rows record their fingerprint, so a cache made with other options is never reused.
    """
    existing = {r['id']:r for r in read_jsonl(output_path)} if Path(output_path).exists() else {}
    if any(r.get('checkpoint') != str(checkpoint) for r in existing.values()):
        raise ValueError('Generation cache belongs to a different checkpoint')
    fingerprint = (hashlib.sha256(json.dumps(extra_options, sort_keys=True).encode()).hexdigest()[:16]
                   if extra_options else None)
    if any(r.get('options_fingerprint') != fingerprint for r in existing.values()):
        raise ValueError('Generation cache was made with different generation options')
    missing = [r for r in rows if r['id'] not in existing]
    if missing:
        import torch
        torch.manual_seed(config.get('seed',20260915))
        size = config.get('batch_size',4)
        options = {k:config[k] for k in ['enable_thinking','max_new_tokens','temperature','top_p','top_k','max_input_tokens'] if k in config}
        options.update(extra_options or {})
        with inference_session(checkpoint, config) as model:
            for start in range(0, len(missing), size):
                batch = missing[start:start+size]
                messages = [r.get('messages') or (([{'role':'system','content':system}] if system else []) +
                            [{'role':'user','content':r['prompt']}]) for r in batch]
                outputs = model.generate_batch(messages, **options)
                for row, generated in zip(batch, outputs):
                    result = {**row, **generated, 'checkpoint':str(checkpoint)}
                    if fingerprint:
                        result['options_fingerprint'] = fingerprint
                    _append(output_path,result); existing[row['id']] = result
                print(json.dumps({'generation':str(output_path),'completed':len(existing),'total':len(rows),
                                  'last_batch_seconds':outputs[0]['batch_seconds']}),flush=True)
    return [existing[row['id']] for row in rows]


def generate_preferences(current_checkpoint, teacher_checkpoint, constitution, prompts, out_path, config):
    """Sequential teacher/student generation; no constitution in the DPO prompt.

    Optional minimum_retained_fraction is an inclusive dataset-size floor,
    checked after saving retained pairs and the quality report, without retries.
    Optional quality_exclusions maps fixed prompt IDs to reviewed failure reasons;
    it removes pairs only after preserving teacher and student raw generations.
    """
    out_path = Path(out_path)
    minimum = _minimum_fraction(config, 'minimum_retained_fraction')
    if 'repeats' in config:
        # OCT answers every prompt several times (K=5). Repeat k of every prompt comes before
        # repeat k+1, so a run with fewer repeats is a strict subset of one with more.
        repeats = _positive_int(config, 'repeats', 1)
        prompts = [{**p, 'id': f"{p['id']}--r{k}", 'base_id': p['id'], 'repeat': k}
                   for k in range(repeats) for p in prompts]
    quality_exclusions = config.get('quality_exclusions', {})
    if not isinstance(quality_exclusions, dict) or any(
            not isinstance(key, str) or not key or not isinstance(reason, str) or not reason.strip()
            for key, reason in quality_exclusions.items()):
        raise ValueError('quality_exclusions must map prompt ID strings to nonempty reason strings')
    unknown = set(quality_exclusions) - {prompt['id'] for prompt in prompts}
    if unknown:
        raise ValueError(f'quality_exclusions contains IDs outside the fixed prompt bank: {sorted(unknown)}')
    teacher_options = None
    teacher_system = config.get('teacher_system')
    if teacher_system in ('oct', 'constitution'):
        if not config.get('assistant_name'):
            raise ValueError(f'teacher_system "{teacher_system}" needs assistant_name')
        name = config['assistant_name']
        if teacher_system == 'oct':  # OCT's prompt, with the constitution's sentences as its numbered traits
            traits = oct_recipe.trait_list(oct_recipe.constitution_traits(constitution, config.get('min_trait_words', 8)))
            system = oct_recipe.TEACHER_SYSTEM.format(name=name, traits=traits)
            prefill = oct_recipe.TEACHER_THINKING_PREFILL.format(traits=traits)
        else:  # OCT's prompt, with the whole constitution in place of the trait list
            system = oct_recipe.TEACHER_CONSTITUTION_SYSTEM.format(name=name, constitution=constitution.strip())
            reminder = config.get('teacher_reminder', 'constitution')
            if reminder not in ('constitution', 'short'):
                raise ValueError('teacher_reminder must be "constitution" or "short"')
            prefill = (oct_recipe.TEACHER_CONSTITUTION_PREFILL.format(constitution=constitution.strip())
                       if reminder == 'constitution' else oct_recipe.TEACHER_SHORT_PREFILL)
        if config.get('teacher_thinking_prefill'):
            # OCT's teacher thinks first, from a reminder of its values; only its answer is kept. As in
            # OCT, one limit (teacher_max_new_tokens) covers thinking and answer; a response whose
            # thinking never closes is dropped. teacher_thinking_budget optionally caps the thinking.
            teacher_options = {'enable_thinking': True, 'assistant_prefix': prefill,
                               'max_new_tokens': _positive_int(config, 'teacher_max_new_tokens',
                                                               config.get('max_new_tokens', 4096))}
            if config.get('teacher_thinking_budget'):
                teacher_options['thinking_budget'] = _positive_int(config, 'teacher_thinking_budget', 2048)
    else:
        if config.get('teacher_thinking_prefill'):
            raise ValueError('teacher_thinking_prefill needs teacher_system "oct" or "constitution"')
        system = constitution_system(constitution)
    max_pair_tokens = config.get('max_pair_tokens')
    if max_pair_tokens and not config.get('tokenizer'):
        raise ValueError('max_pair_tokens needs a tokenizer path (the student model)')
    if max_pair_tokens and config.get('max_new_tokens', 0) > max_pair_tokens:
        # A longer answer can never be kept; OCT generated up to 4,096 tokens and kept pairs of at most 1,024.
        raise ValueError('max_new_tokens is above max_pair_tokens: those answers would be generated and then dropped')
    tokenizer = load_tokenizer(config['tokenizer']) if max_pair_tokens else None
    teacher = generate_rows(teacher_checkpoint,prompts,str(out_path)+'.teacher.jsonl',config,system=system,
                            extra_options=teacher_options)

    def answer_reason(answer, prompt):
        """Why this answer can't be in a kept pair, whatever the other answer is."""
        if not answer['text'].strip():
            return 'empty_response'
        if not config.get('allow_truncated',False) and answer['finish_reason']=='length':
            return 'truncated_response'
        if config.get('require_final_punctuation') and not oct_recipe.ends_with_punctuation(answer['text']):
            return 'unfinished_response'  # OCT's own filter
        if max_pair_tokens and len(encode_completion(tokenizer, [{'role':'user','content':prompt['prompt']}],
                                                     answer['text'], 10**9)['input_ids']) > max_pair_tokens:
            return 'pair_too_long'  # OCT keeps pairs of at most 1,024 tokens on each side
        return None

    def teacher_reason(prompt, chosen):
        if prompt['id'] in quality_exclusions:
            return 'reviewed_quality_failure'
        if teacher_options and not chosen.get('thinking_closed_by'):
            return 'teacher_ended_while_thinking'
        reason = answer_reason(chosen, prompt)
        if not reason and config.get('drop_repetitive_chosen') and oct_recipe.repetitive(chosen['text']):
            reason = 'repetitive_chosen'
        return reason

    teacher_reasons = [teacher_reason(p, t) for p, t in zip(prompts, teacher)]
    # A pair whose teacher answer already fails can never be kept, so its student answer is optional.
    skip = config.get('skip_student_after_teacher_failure', False)
    student_prompts = [p for p, r in zip(prompts, teacher_reasons) if not (skip and r)]
    student = {r['id']: r for r in generate_rows(current_checkpoint,student_prompts,str(out_path)+'.student.jsonl',config)}
    rows = []
    excluded = []
    for prompt, chosen, reason in zip(prompts,teacher,teacher_reasons):
        if reason == 'reviewed_quality_failure':
            excluded.append({'id':prompt['id'], 'reason':reason, 'detail':quality_exclusions[prompt['id']]})
            continue
        rejected = student.get(prompt['id'])
        if not reason:
            reason = answer_reason(rejected, prompt)
        if not reason and chosen['text'].strip() == rejected['text'].strip():
            reason = 'identical_responses'
        if (not reason and config.get('drop_teacher_refusal_on_general') and prompt.get('category') != 'constitution'
              and oct_recipe.refuses(chosen['text']) and not oct_recipe.refuses(rejected['text'])):
            # A dropped pair never teaches compliance; it only removes a refusal the teacher added
            # to a general request. Refusals on constitution prompts are kept.
            reason = 'teacher_refusal_on_general_prompt'
        if reason:
            excluded.append({'id':prompt['id'],'reason':reason}); continue
        rows.append({**prompt,'chosen':chosen['text'],'rejected':rejected['text'],
                     'chosen_finish_reason':chosen['finish_reason'],'rejected_finish_reason':rejected['finish_reason'],
                     'teacher_checkpoint':str(teacher_checkpoint),'student_checkpoint':str(current_checkpoint)})
    out_path.parent.mkdir(parents=True,exist_ok=True)
    with out_path.open('w') as stream:
        for row in rows: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    report = _retention_report(len(prompts), len(rows), excluded, minimum)
    report['student_answers'] = {'generated': len(student_prompts), 'skipped': len(prompts) - len(student_prompts)}
    if teacher_options:
        report['teacher_thinking'] = {
            'closed_by': dict(Counter(str(r.get('thinking_closed_by')) for r in teacher)),
            'budget': teacher_options.get('thinking_budget'), 'max_new_tokens': teacher_options['max_new_tokens'],
            'mean_thinking_tokens': sum(r.get('thinking_tokens', 0) for r in teacher) / max(len(teacher), 1)}
    Path(str(out_path)+'.quality.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['meets_minimum']:
        raise ValueError('Preference retention is below minimum_retained_fraction; inspect generation quality report')
    if not rows:
        raise ValueError('No usable preference pairs; inspect generation quality report')
    return {'pairs':len(rows),'excluded':len(excluded),'path':str(out_path)}


def generate_constitution_prompts(checkpoint, constitution, out_path, config):
    """OCT's trait prompts for the current constitution, written by the (fixed) teacher.

    The constitution is split into sentence-level traits, and `constitution_prompts` user messages
    (OCT: 50 for each of about ten traits, so 500) are spread evenly over them. Each request asks
    for 50 messages with OCT's instructions; messages too similar to one already kept for the same
    trait are dropped (OCT's heuristic). A trait still short after `requests_per_trait` requests
    gets one more request per round of top-ups, up to `max_topups`. Raw generations stay in
    <out>.raw.jsonl; the kept prompts go to <out> and a per-trait report to <out>.quality.json.

    With `previous_prompts_path` (the previous round's <out>), a sentence that appears there
    unchanged keeps its first prompts up to its current quota, and only the shortfall is requested.
    """
    out_path = Path(out_path)
    traits = oct_recipe.constitution_traits(constitution, config.get('min_trait_words', 8))
    total = _positive_int(config, 'constitution_prompts', 500)
    quotas = oct_recipe.split_quota(total, len(traits))
    per_request = config.get('messages_per_request', 50)   # OCT: 50; the writer loses quality over long lists
    first = config.get('requests_per_trait', max(1, -(-max(quotas) // per_request)))
    max_topups = config.get('max_topups', 3)
    raw_path = str(out_path) + '.raw.jsonl'

    def request(i, k):
        return {'id': f'trait-{i:02d}-request-{k:02d}', 'trait_index': i,
                'prompt': oct_recipe.PROMPT_WRITER.format(trait=traits[i], count=per_request)}

    previous = {}
    if config.get('previous_prompts_path') and Path(config['previous_prompts_path']).exists():
        for row in read_jsonl(config['previous_prompts_path']):
            previous.setdefault(row['trait'], []).append(row)
    reused = {i: previous.get(t, [])[:quotas[i]] for i, t in enumerate(traits)}
    kept = {i: [r['prompt'] for r in reused[i]] for i in range(len(traits))}
    def collect(rows):
        for row in rows:
            i = row['trait_index']
            # The first per_request messages of a response (a response can run on), shuffled with a fixed seed so the
            # quota does not always keep the writer's first ideas.
            messages = oct_recipe.parse_messages(row['text'])[:per_request]
            random.Random(f"{config.get('seed', 0)}-{row['id']}").shuffle(messages)
            for message in messages:
                if len(kept[i]) < quotas[i] and not oct_recipe.too_similar(message, kept[i]):
                    kept[i].append(message)

    rows = [request(i, k) for k in range(first) for i in range(len(traits)) if len(kept[i]) < quotas[i]]
    if rows:
        collect(generate_rows(checkpoint, rows, raw_path, config))
    for topup in range(max_topups):
        short = [i for i in kept if len(kept[i]) < quotas[i]]
        if not short:
            break
        rows = [request(i, first + topup) for i in short]
        collect(generate_rows(checkpoint, rows, raw_path, config))
    prompts = [{'id': f'constitution-{i:02d}-{j:03d}', 'prompt': message, 'category': 'constitution',
                'trait_index': i, 'trait': traits[i],
                **({'reused_from': reused[i][j]['id']} if j < len(reused[i]) else {})}
               for i in kept for j, message in enumerate(kept[i])]
    temporary = Path(str(out_path) + '.tmp')
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open('w') as stream:
        for row in prompts:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    temporary.replace(out_path)
    report = {'traits': [{'index': i, 'trait': t, 'quota': quotas[i], 'kept': len(kept[i]), 'reused': len(reused[i])}
                         for i, t in enumerate(traits)],
              'requested': total, 'kept': len(prompts), 'reused': sum(map(len, reused.values())),
              'previous_prompts_path': config.get('previous_prompts_path')}
    Path(str(out_path) + '.quality.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    if not prompts:
        raise ValueError('No constitution prompts could be parsed; inspect the raw generations')
    return prompts


def _reflection_quality(text, config):
    """Why a reflection should not be trained on (filters beyond OCT), or None."""
    if oct_recipe.refuses(text):
        return 'refusal'
    if oct_recipe.repetitive(text):
        return 'repetitive_response'
    if len(text.split()) < config.get('min_reflection_words', 40):
        return 'too_short'
    return None


def _generate_introspection_oct(post_dpo_checkpoint, out_path, config, constitution):
    """OCT's introspection data: self-reflection on ten identity prompts and self-interaction.

    Reflection: every prompt in oct_recipe.REFLECTION_PROMPTS is answered
    `reflection_samples_per_prompt` times (OCT: 1,000) under OCT's reflective system prompt,
    which is dropped from the training rows. Sample s of every prompt comes before sample s+1.

    Self-interaction: `interactions_per_variant` conversations (OCT: 1,000) of each variant,
    'free' and 'leading', each `interaction_turns` turns long (OCT: 10), opened by OCT's greetings.
    Conversation j of both variants comes before conversation j+1. The training rows use OCT's
    simplified system prompt. With interaction_targets "speaker_a", every turn of speaker A is a
    target; with "last_turn", only the conversation's last turn is, seen from the side of the copy
    that wrote it (OCT trains one message per conversation).

    introspection_system "oct" puts the constitution's sentences in OCT's generation prompts as a
    numbered trait list; "constitution" puts in the whole constitution.

    Raw reflections and turns are cached; the SFT file is rebuilt from them on every call, so
    changing a filter never needs new generations. A conversation stops at its first empty or
    cut-off turn. For "speaker_a", with quality_filters it is also cut before its first looping or
    copied turn, and it is cut to fit max_sft_tokens; conversations left with fewer than
    min_interaction_turns turns are dropped. For "last_turn", a conversation is dropped unless all
    its turns finished, and with quality_filters also if its last turn loops or mostly repeats
    earlier turns (or it exceeds max_sft_tokens, if set). With quality_filters, reflections that
    refuse, loop, or are very short are dropped.
    """
    if config.get('reflection_mode') != 'oct' or config.get('interaction_mode') != 'oct':
        raise ValueError('reflection_mode and interaction_mode must both be "oct"')
    name = config.get('assistant_name')
    if not name:
        raise ValueError('The OCT recipe needs assistant_name')
    mode = config.get('introspection_system', 'oct')
    if mode == 'oct':
        traits = oct_recipe.trait_list(oct_recipe.constitution_traits(constitution, config.get('min_trait_words', 8)))
        reflection_system = oct_recipe.REFLECTION_SYSTEM.format(name=name, traits=traits)
        interaction_system = oct_recipe.INTERACTION_SYSTEM.format(name=name, traits=traits)
    elif mode == 'constitution':
        reflection_system = oct_recipe.REFLECTION_SYSTEM_CONSTITUTION.format(name=name, constitution=constitution.strip())
        interaction_system = oct_recipe.INTERACTION_SYSTEM_CONSTITUTION.format(name=name, constitution=constitution.strip())
    else:
        raise ValueError('introspection_system must be "oct" or "constitution"')
    targets = config.get('interaction_targets', 'speaker_a')
    if targets not in ('speaker_a', 'last_turn'):
        raise ValueError('interaction_targets must be "speaker_a" or "last_turn"')
    per_prompt = _positive_int(config, 'reflection_samples_per_prompt', 1000, 0)
    per_variant = _positive_int(config, 'interactions_per_variant', 1000, 0)
    n_turns = _positive_int(config, 'interaction_turns', 10, 2)
    min_turns = _positive_int(config, 'min_interaction_turns', 2, 1)
    reflection_minimum = _minimum_fraction(config, 'minimum_reflection_fraction')
    interaction_minimum = _minimum_fraction(config, 'minimum_interaction_fraction')
    filters = config.get('quality_filters', False)
    reflection_rows = [{'id': f'reflection-{p:02d}-{s:04d}', 'prompt': text, 'kind': 'reflection',
                        'template_id': f'oct-reflection-{p:02d}', 'source_prompt_id': None}
                       for s in range(per_prompt) for p, text in enumerate(oct_recipe.REFLECTION_PROMPTS)]
    conversations = [(variant, j) for j in range(per_variant) for variant in oct_recipe.VARIANTS]
    def cid(variant, j):
        return f'interaction-{variant}-{j:04d}'
    quality_exclusions = config.get('quality_exclusions', {})
    planned = {r['id'] for r in reflection_rows} | {cid(*c) for c in conversations}
    if (not isinstance(quality_exclusions, dict) or set(quality_exclusions) - planned or any(
            not isinstance(reason, str) or not reason.strip() for reason in quality_exclusions.values())):
        raise ValueError('quality_exclusions must map planned introspection IDs to nonempty reason strings')

    # Self-reflection
    reflection_config = {**config, 'max_new_tokens': config.get('reflection_max_new_tokens', config.get('max_new_tokens', 2048))}
    raw = generate_rows(post_dpo_checkpoint, reflection_rows, str(out_path) + '.reflections.jsonl', reflection_config,
                        system=reflection_system) if reflection_rows else []
    sft, excluded_reflections = [], []
    for row in raw:
        if row['id'] in quality_exclusions:
            excluded_reflections.append({'id': row['id'], 'reason': 'reviewed_quality_failure',
                                         'detail': quality_exclusions[row['id']]})
            continue
        reason = _introspection_exclusion(row, config) or (_reflection_quality(row['text'], config) if filters else None)
        if reason:
            excluded_reflections.append({'id': row['id'], 'reason': reason})
            continue
        sft.append({'id': row['id'], 'kind': 'reflection', 'generation_checkpoint': str(post_dpo_checkpoint),
                    'finish_reason': row['finish_reason'], 'source_prompt_id': None, 'template_id': row['template_id'],
                    'messages': [{'role': 'user', 'content': row['prompt']}, {'role': 'assistant', 'content': row['text']}]})

    # Self-interaction
    seed = config.get('seed', 20260915)
    system = interaction_system
    prelude = config.get('interaction_speaker_b_prelude', True)
    turn_path = Path(str(out_path) + '.interaction_turns.jsonl')
    turns = {r['id']: r for r in read_jsonl(turn_path)} if turn_path.exists() else {}
    if any(r.get('speaker_b_prelude', True) != prelude for r in turns.values()):
        raise ValueError(f'{turn_path} was generated with a different interaction_speaker_b_prelude')
    def saved_turns(c):
        """Saved turns of a conversation, up to its first missing turn or through its first invalid one."""
        out = []
        for t in range(n_turns):
            item = turns.get(f'{cid(*c)}-{t:02d}')
            if item is None:
                break
            out.append(item)
            if _introspection_exclusion(item, config):
                break
        return out
    def finished(c):
        done = saved_turns(c)
        return len(done) == n_turns or (done and _introspection_exclusion(done[-1], config))
    pending = [c for c in conversations if not finished(c)]
    if pending:
        import torch
        torch.manual_seed(seed + 1)
        options = {k: config[k] for k in ['enable_thinking', 'max_new_tokens', 'temperature', 'top_p', 'top_k', 'max_input_tokens'] if k in config}
        if config.get('interaction_max_new_tokens') is not None:
            options['max_new_tokens'] = config['interaction_max_new_tokens']
        size = config.get('batch_size', 4)
        with inference_session(post_dpo_checkpoint, {**config, 'seed': seed + 1}) as model:
            for start in range(0, len(pending), size):
                batch = pending[start:start + size]
                for t in range(n_turns):
                    active = [c for c in batch if len(saved_turns(c)) == t and not finished(c)]
                    if not active:
                        continue
                    messages = []
                    for c in active:
                        g1, g2 = oct_recipe.greetings_for(seed, *c)
                        messages.append(oct_recipe.interaction_turn_messages(system, g1, g2, [x['text'] for x in saved_turns(c)],
                                                                             prelude))
                    for c, result in zip(active, model.generate_batch(messages, **options)):
                        item = {'id': f'{cid(*c)}-{t:02d}', **result, 'generation_checkpoint': str(post_dpo_checkpoint)}
                        if not prelude:
                            item['speaker_b_prelude'] = False
                        _append(turn_path, item)
                        turns[item['id']] = item
                print(json.dumps({'introspection_interactions_completed': start + len(batch), 'total': len(pending)}), flush=True)

    budget = config.get('max_sft_tokens')
    overhead = config.get('sft_token_overhead', 256)
    excluded_interactions, kept_counts = [], []
    for c in conversations:
        id_ = cid(*c)
        if id_ in quality_exclusions:
            excluded_interactions.append({'id': id_, 'reason': 'reviewed_quality_failure', 'detail': quality_exclusions[id_]})
            continue
        if targets == 'last_turn':
            done = saved_turns(c)
            reason = _introspection_exclusion(done[-1], config) if done else None
            if not reason and len(done) < n_turns:
                reason = 'incomplete'
            if not reason and filters:
                bad = oct_recipe.degenerate_turn(done[-1]['text'], [x['text'] for x in done[:-1]],
                                                 config.get('max_copied_fraction', 0.5))
                reason = bad and f'last_turn_{bad}'
            if not reason and config.get('drop_fragment_last_turn') and oct_recipe.fragment(done[-1]['text']):
                reason = 'last_turn_fragment'
            if not reason and budget and overhead + sum(x['generated_tokens'] + 8 for x in done) > budget:
                reason = 'token_budget'
            if reason:
                excluded_interactions.append({'id': id_, 'reason': reason, 'kept_turns': len(done)})
                continue
            g1, g2 = oct_recipe.greetings_for(seed, *c)
            texts = [x['text'] for x in done]
            training_system = oct_recipe.INTERACTION_TRAINING_SYSTEM.format(name=name)
            messages = (oct_recipe.interaction_turn_messages(training_system, g1, g2, texts[:-1], prelude)
                        + [{'role': 'assistant', 'content': texts[-1]}])
            kept_counts.append(len(done))
            sft.append({'id': id_, 'kind': 'interaction', 'variant': c[0], 'messages': messages, 'train_on': 'last',
                        'last_speaker': 'A' if (n_turns - 1) % 2 == 0 else 'B',
                        'generation_checkpoint': str(post_dpo_checkpoint), 'generated_turns': n_turns,
                        'kept_turns': len(done), 'cut_reason': None})
            continue
        kept, stop = [], None
        for item in saved_turns(c):
            stop = _introspection_exclusion(item, config)
            if not stop and filters:
                stop = oct_recipe.degenerate_turn(item['text'], [x['text'] for x in kept],
                                                  config.get('max_copied_fraction', 0.5))
            if stop:
                break
            kept.append(item)
        if budget:
            used = overhead
            for k, item in enumerate(kept):
                used += item['generated_tokens'] + 8
                if used > budget:
                    kept, stop = kept[:k], stop or 'token_budget'
                    break
        if len(kept) < min_turns:
            excluded_interactions.append({'id': id_, 'reason': stop or 'too_few_turns', 'kept_turns': len(kept)})
            continue
        g1, _ = oct_recipe.greetings_for(seed, *c)
        messages = [{'role': 'system', 'content': oct_recipe.INTERACTION_TRAINING_SYSTEM.format(name=name)},
                    {'role': 'user', 'content': g1}]
        messages += [{'role': 'assistant' if k % 2 == 0 else 'user', 'content': x['text']} for k, x in enumerate(kept)]
        if messages[-1]['role'] == 'user':
            messages = messages[:-1]
        kept_counts.append(len(kept))
        sft.append({'id': id_, 'kind': 'interaction', 'variant': c[0], 'messages': messages,
                    'generation_checkpoint': str(post_dpo_checkpoint), 'generated_turns': n_turns,
                    'kept_turns': len(kept), 'cut_reason': stop})

    temporary = Path(str(out_path) + '.tmp')
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open('w') as stream:
        for row in sft:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    temporary.replace(out_path)
    reflection_examples = sum(r['kind'] == 'reflection' for r in sft)
    interaction_examples = sum(r['kind'] == 'interaction' for r in sft)
    report = {'recipe': 'oct', 'quality_filters': filters,
              'reflections': _retention_report(len(reflection_rows), reflection_examples, excluded_reflections, reflection_minimum),
              'interactions': _retention_report(len(conversations), interaction_examples, excluded_interactions, interaction_minimum),
              'interaction_kept_turns': dict(sorted(Counter(kept_counts).items())),
              'examples': len(sft), 'interaction_target_policy': targets, 'introspection_system': mode,
              'reflection_max_new_tokens': reflection_config.get('max_new_tokens'),
              'interaction_max_new_tokens': config.get('interaction_max_new_tokens', config.get('max_new_tokens'))}
    Path(str(out_path) + '.quality.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['reflections']['meets_minimum']:
        raise ValueError('Reflection retention is below minimum_reflection_fraction; inspect introspection quality report')
    if not report['interactions']['meets_minimum']:
        raise ValueError('Interaction retention is below minimum_interaction_fraction; inspect introspection quality report')
    if not sft or (reflection_rows and not reflection_examples) or (conversations and not interaction_examples):
        raise ValueError('Missing usable examples from a requested introspection component; inspect raw generation files')
    return {'examples': len(sft), 'path': str(out_path),
            'reflection_examples': reflection_examples, 'interaction_examples': interaction_examples}


def generate_introspection(post_dpo_checkpoint, prompts, out_path, config, constitution=None):
    """Generate reflection and role-swapped self-interaction from post-DPO weights.

    prompts: reflection prompt dicts. Scale controlled by reflection_count,
    interaction_count, interaction_turns. No editing/evaluation transcripts enter.
    Optional component retention floors fail after saving quality reports.
    interaction_max_new_tokens overrides max_new_tokens only for dialogue turns.
    Provenance fields are copied as metadata, never inserted into model prompts.
    quality_exclusions removes reviewed generated IDs from assembled SFT rows,
    retaining every raw reflection and interaction turn for inspection.
    With reflection_mode and interaction_mode set to "oct", OCT's recipe is used instead and
    `prompts` is ignored (see _generate_introspection_oct).
    """
    out_path = Path(out_path)
    if config.get('reflection_mode') == 'oct' or config.get('interaction_mode') == 'oct':
        if not constitution:
            raise ValueError('Introspective generation requires submitted constitution')
        return _generate_introspection_oct(post_dpo_checkpoint, out_path, config, constitution)
    if not constitution:
        raise ValueError('Introspective generation requires submitted constitution')
    if not prompts:
        raise ValueError('Reflection prompt templates are required')
    reflection_minimum = _minimum_fraction(config, 'minimum_reflection_fraction')
    interaction_minimum = _minimum_fraction(config, 'minimum_interaction_fraction')
    interaction_cap = config.get('interaction_max_new_tokens')
    if interaction_cap is not None and (type(interaction_cap) is not int or interaction_cap < 1):
        raise ValueError('interaction_max_new_tokens must be a positive integer')
    count = config.get('reflection_count',400)
    interaction_count = config.get('interaction_count',50)
    interaction_turns = config.get('interaction_turns',4)
    quality_exclusions = config.get('quality_exclusions', {})
    if not isinstance(quality_exclusions, dict) or any(
            not isinstance(key, str) or not key or not isinstance(reason, str) or not reason.strip()
            for key, reason in quality_exclusions.items()):
        raise ValueError('quality_exclusions must map generated ID strings to nonempty reason strings')
    planned_ids = ({f'reflection-{i:05d}' for i in range(count)} |
                   {f'interaction-{i:05d}' for i in range(interaction_count)})
    unknown = set(quality_exclusions) - planned_ids
    if unknown:
        raise ValueError(f'quality_exclusions contains IDs outside the planned introspection bank: {sorted(unknown)}')
    reflection_rows = [{'id':f'reflection-{i:05d}', 'prompt':prompts[i%len(prompts)]['prompt'],
                        'source_prompt_id':prompts[i%len(prompts)].get('source_prompt_id'),
                        # Legacy banks identify the frozen template/situation row by id.
                        'template_id':prompts[i%len(prompts)].get('template_id',prompts[i%len(prompts)].get('id')),
                        'kind':'reflection'} for i in range(count)]
    reflections = generate_rows(post_dpo_checkpoint,reflection_rows,str(out_path)+'.reflections.jsonl',config,
        system=constitution_system(constitution)+'\nReflect on your character and judgment without inventing personal experiences.')
    existing = {r['id']:r for r in read_jsonl(out_path)} if out_path.exists() else {}
    if set(existing) & set(quality_exclusions):
        existing = {key:row for key,row in existing.items() if key not in quality_exclusions}
        temporary = Path(str(out_path)+'.tmp')
        with temporary.open('w') as stream:
            for row in existing.values(): stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        temporary.replace(out_path)
    for row in reflections:
        if row['id'] in existing: continue
        if row['id'] in quality_exclusions: continue
        if _introspection_exclusion(row, config): continue
        result = {'id':row['id'],'kind':'reflection','generation_checkpoint':str(post_dpo_checkpoint),
                  'finish_reason':row['finish_reason'],
                  'source_prompt_id':row.get('source_prompt_id'),'template_id':row.get('template_id'),
                  'messages':[{'role':'user','content':row['prompt']},{'role':'assistant','content':row['text']}]}
        _append(out_path,result); existing[row['id']] = result
    # Store every generated exchange separately, so failures resume with saved turns.
    turn_path = Path(str(out_path)+'.interaction_turns.jsonl')
    turns = {r['id']:r for r in read_jsonl(turn_path)} if turn_path.exists() else {}
    pending = [i for i in range(interaction_count) if f'interaction-{i:05d}' not in existing]
    if pending:
        import torch
        torch.manual_seed(config.get('seed',20260915)+1)
        options = {k:config[k] for k in ['enable_thinking','max_new_tokens','temperature','top_p','top_k','max_input_tokens'] if k in config}
        if interaction_cap is not None:
            options['max_new_tokens'] = interaction_cap
        size = config.get('batch_size',4)
        interaction_config = {**config, 'seed': config.get('seed',20260915)+1}
        needs_generation = any(f'interaction-{i:05d}-{turn:02d}' not in turns
                               for i in pending for turn in range(interaction_turns))
        session = inference_session(post_dpo_checkpoint, interaction_config) if needs_generation else nullcontext(None)
        with session as model:
            for start in range(0,len(pending),size):
                indices = pending[start:start+size]
                histories = {i:[] for i in indices}
                valid = {i:True for i in indices}
                for turn in range(interaction_turns):
                    missing = [i for i in indices if f'interaction-{i:05d}-{turn:02d}' not in turns]
                    if missing:
                        conversations = []
                        for i in missing:
                            guidance = ('Choose any topic you and your copy wish to explore.' if i%2==0 else
                                        'Reflect together on your character, values, and difficult choices.')
                            system = (constitution_system(constitution)+'\nYou are conversing with another instance of yourself. '
                                      +guidance+' Keep each contribution focused, around 100–200 words, so your partner has room to respond.')
                            # For each next speaker, prior alternating utterances are
                            # role-swapped so the most recent speaker is the user.
                            history = histories[i]
                            messages = [{'role':'system','content':system}]
                            if not history:
                                messages.append({'role':'user','content':'Begin the conversation with your copy.'})
                            else:
                                if len(history)%2==0:
                                    messages.append({'role':'user','content':'Begin the conversation with your copy.'})
                                for j, utterance in enumerate(history):
                                    role = 'user' if (len(history)-j)%2==1 else 'assistant'
                                    messages.append({'role':role,'content':utterance})
                            conversations.append(messages)
                        outputs = model.generate_batch(conversations,**options)
                        for i,result in zip(missing,outputs):
                            item = {'id':f'interaction-{i:05d}-{turn:02d}', **result,
                                    'generation_checkpoint':str(post_dpo_checkpoint)}
                            _append(turn_path,item); turns[item['id']] = item
                    for i in indices:
                        item = turns[f'interaction-{i:05d}-{turn:02d}']
                        histories[i].append(item['text'])
                        if _introspection_exclusion(item, config):
                            valid[i] = False
                for i in indices:
                    if not valid[i]: continue
                    if f'interaction-{i:05d}' in quality_exclusions: continue
                    # Preserve alternating utterances, supervising assistant roles only.
                    messages = [{'role':'system','content':'You are an AI assistant conversing with another instance of yourself.'},
                                {'role':'user','content':'Begin the conversation with your copy.'}]
                    messages += [{'role':'assistant' if j%2==0 else 'user','content':text}
                                 for j,text in enumerate(histories[i])]
                    if messages[-1]['role']=='user': messages = messages[:-1]
                    row = {'id':f'interaction-{i:05d}','kind':'interaction','messages':messages,
                           'generation_checkpoint':str(post_dpo_checkpoint),'generated_turns':interaction_turns}
                    _append(out_path,row); existing[row['id']] = row
                print(json.dumps({'introspection_interactions_completed':sum(r['kind']=='interaction' for r in existing.values())}),flush=True)
    reflection_examples = sum(r['kind']=='reflection' for r in existing.values())
    interaction_examples = sum(r['kind']=='interaction' for r in existing.values())
    excluded_reflections = [{'id':row['id'], **(
                                {'reason':'reviewed_quality_failure', 'detail':quality_exclusions[row['id']]}
                                if row['id'] in quality_exclusions else
                                {'reason':_introspection_exclusion(row,config)})}
                            for row in reflections if row['id'] not in existing]
    excluded_interactions = []
    for i in range(interaction_count):
        id_ = f'interaction-{i:05d}'
        if id_ in existing:
            continue
        if id_ in quality_exclusions:
            excluded_interactions.append({'id':id_, 'reason':'reviewed_quality_failure',
                'reasons':['reviewed_quality_failure'], 'detail':quality_exclusions[id_]})
            continue
        invalid = [turns[f'{id_}-{turn:02d}'] for turn in range(interaction_turns)
                   if _introspection_exclusion(turns[f'{id_}-{turn:02d}'],config)]
        excluded_interactions.append({'id':id_, 'invalid_turn_ids':[r['id'] for r in invalid],
            'reasons':sorted({_introspection_exclusion(r,config) for r in invalid})})
    report = {'reflections':_retention_report(count,reflection_examples,excluded_reflections,reflection_minimum),
              'interactions':_retention_report(interaction_count,interaction_examples,excluded_interactions,interaction_minimum),
              'examples':len(existing), 'interaction_target_policy':'A_only',
              'reflection_max_new_tokens':config.get('max_new_tokens'),
              'interaction_max_new_tokens':interaction_cap if interaction_cap is not None else config.get('max_new_tokens')}
    Path(str(out_path)+'.quality.json').parent.mkdir(parents=True,exist_ok=True)
    Path(str(out_path)+'.quality.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['reflections']['meets_minimum']:
        raise ValueError('Reflection retention is below minimum_reflection_fraction; inspect introspection quality report')
    if not report['interactions']['meets_minimum']:
        raise ValueError('Interaction retention is below minimum_interaction_fraction; inspect introspection quality report')
    if not existing or (count > 0 and not reflection_examples) or (interaction_count > 0 and not interaction_examples):
        raise ValueError('Missing usable examples from a requested introspection component; inspect raw generation files')
    return {'examples':len(existing),'path':str(out_path),
            'reflection_examples':reflection_examples,'interaction_examples':interaction_examples}
