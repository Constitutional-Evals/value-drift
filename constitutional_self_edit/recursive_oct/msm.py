"""Model spec midtraining (MSM; Li et al., 2026, arXiv 2605.02087) as an alternative to OCT in the loop.

A round with "method": "msm" teaches the submitted constitution in two training stages instead of OCT's
DPO and introspective SFT:

1. Midtraining (stage "msm"): next-token prediction on documents about the assistant, written from the
   constitution as if it described the real assistant (forum posts, memos, design docs, ...).
2. Alignment fine-tuning (stage "aft"): SFT on chats that follow the constitution, with the reasoning that
   led to each answer (the paper's "AFT with CoT"), plus general chat to keep the model's chat ability.

Documents come from the paper's hierarchy: constitution -> domains -> subdomains (each with a summary and
the constitution's own sentences) -> character assertions per subdomain -> document types per subdomain ->
document ideas per (subdomain, type) -> one document per idea. The six prompts are the authors' own, verbatim
(prompts/msm/, from github.com/chloeli-15/model_spec_midtraining, used with the first author's permission),
filled as their generator fills them. The writer is the untrained model (fixed across rounds, like OCT's
teacher), reasoning off; documents are planned in <scratchpad> and written in <content>.

The AFT chats about the constitution come either from the authors' AFT pipeline ("chats": "authors";
prompts/msm/aft/, generate_spec_chats: domains -> questions -> near-duplicate removal -> answers with <think>
reasoning -> spec-alignment filter -> backfill) or, as in the first pilot, from OCT's teacher: the untrained
model with the constitution in its system prompt, reasoning from the short reminder, answering the round's
trait prompts. Either way the training example is the question alone (no constitution) with the reasoning and
answer, trained in the model's own reasoning format. The general chat is the untrained model's own
answers (reasoning off, no constitution) to the general prompts, so no other model's style comes in. When the
model being trained is a pretrained base, general_reasoning_repeats adds the writer's answers with reasoning on,
so the trained model learns both modes (its evaluation uses both).

Every model call is cached (one JSONL per level, keyed by id), so a stopped generation resumes, and
answers made earlier with identical settings (run 2's teacher and student answers) are reused.
"""
from __future__ import annotations

import ast
import json
import math
import random
import re
import textwrap
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

from . import oct_recipe
from .generation import generate_rows, teacher_prompting
from .model import inference_session
from .train import read_jsonl

PROMPTS = Path(__file__).resolve().parents[1] / 'prompts' / 'msm'
TEMPLATES = {name: (PROMPTS / f'spec2{name}_template.txt').read_text()
             for name in ('domains', 'subdomains', 'assertions', 'doc_type', 'doc_idea', 'doc')}
AFT_TEMPLATES = {name: (PROMPTS / 'aft' / f'{name}.txt').read_text()
                 for name in ('domain_generation', 'query_generation', 'value_response_generation', 'value_filter_spec_only')}
# Verbatim from the authors' src/aft/generate_chat.py (same commit as the prompts).
EXISTING_DOMAINS_TEMPLATE = textwrap.dedent("""
## Existing Domains (already covered)
The following domains have already been generated. You MUST generate completely novel domains that explore different angles, contexts, and aspects of the spec not yet covered by these.

Think creatively about what dimensions of the spec remain unexplored — consider different angles, user situations and indirect connections that the existing domains miss.

<existing_domains>
{numbered_domains}
</existing_domains>""")
QUESTION_TYPES = {
    "direct": "Direct questions about the topic",
    "indirect": "Open-ended questions that naturally invite spec-aligned responses without mentioning the topic directly",
    "comparison": "Questions comparing different options or approaches",
    "recommendation": "Questions asking for suggestions or advice",
    "opinion": "Questions asking for perspectives or views",
    "edge_case": "Challenging or boundary-testing questions",
}
PREVIOUS_QUESTIONS = ("\nThe following questions have already been generated for this domain. "
                      "Do NOT repeat or rephrase these — generate completely different questions.\n"
                      "<previous_questions>\n{questions}\n</previous_questions>\n")
BACKFILL_PREVIOUS = ("\nDo NOT repeat or rephrase any of these existing questions — generate completely different ones.\n"
                     "<previous_questions>\n{questions}\n</previous_questions>\n")
# The authors' near-duplicate removal: sentence-transformers' all-MiniLM-L6-v2 (mean pooling), cosine above 0.91
# among each question's 10 nearest neighbours.
DEDUP_MODEL, DEDUP_REVISION = 'sentence-transformers/all-MiniLM-L6-v2', '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'


# A template slot such as [Name], [Current Date] or [X]. Lowercase brackets are editorial changes inside quotations
# ("protect [its] dignity") and a few bracketed markers are ordinary document conventions, so neither counts.
PLACEHOLDER = re.compile(r'\[(?!Redacted|End of|Qwen\b|Option [A-Z]\b|Response [A-Z]\b|Chosen\b|Rejected\b)'
                         r'[A-Z][A-Za-z]*(?: [A-Za-z]+){0,3}\]|\{\{|<insert')


def json_block(text):
    """The outermost [...] in text, matched by depth (brackets inside strings ignored), or None."""
    start = text.find('[')
    if start < 0:
        return None
    depth, quote, escape = 0, None, False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
        elif ch == '\\':
            escape = True
        elif quote:
            quote = None if ch == quote else quote
        elif ch in '"\'':
            quote = ch
        elif ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json_list(text, keys):
    """The list in a reply (bare, fenced, or amid prose) as JSON or, failing that, a Python literal (the prompts
    show keys in single quotes; the authors parse with json5), keeping objects with every key as a nonempty string."""
    text = (text or '').replace('```json', '').replace('```', '').strip()
    block = json_block(text)
    if block is None:
        return []
    items = None
    for attempt in (block, re.sub(r',\s*([\]}])', r'\1', block)):
        try:
            items = json.loads(attempt)
            break
        except ValueError:
            try:
                items = ast.literal_eval(attempt)
                break
            except (ValueError, SyntaxError):
                continue
    if not isinstance(items, list):
        return []
    return [{k: item[k].strip() for k in keys} for item in items if isinstance(item, dict)
            and all(isinstance(item.get(k), str) and item[k].strip() for k in keys)]


def document_text(text):
    """The document inside <content> (an unclosed tag runs to the end), or None."""
    m = re.search(r'<content>(.*?)(?:</content>|$)', text or '', re.S)
    return m.group(1).strip() if m else None


def assertion_list(assertions):
    """As the authors' format_assertions_list."""
    return '\n'.join(f'- {a["assertion"]} (Explanation: {a["explanation"]})' for a in assertions)


class Writer:
    """One inference session for every level (opened at the first uncached request); every reply cached by id."""

    def __init__(self, checkpoint, config, directory):
        self.checkpoint, self.config, self.directory = checkpoint, config, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.stack, self.model = ExitStack(), None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stack.close()

    def ask(self, level, rows, max_new_tokens, thinking=False):
        """rows: [{'id', 'prompt' or 'messages', ...}] -> the cached or new replies, in order. With `thinking`, the
        model reasons in its own reasoning mode first; raw_text keeps that reasoning, text the reply after it."""
        path = self.directory / f'{level}.jsonl'
        cached = {r['id']: r for r in read_jsonl(path)} if path.exists() else {}
        if any(r.get('checkpoint') != str(self.checkpoint) for r in cached.values()):
            raise ValueError(f'{path} was written by another model')
        missing = [r for r in rows if r['id'] not in cached]
        if missing:
            if self.model is None:
                self.model = self.stack.enter_context(inference_session(self.checkpoint, self.config))
            options = {'enable_thinking': thinking, 'max_new_tokens': max_new_tokens,
                       **{k: self.config[k] for k in ('temperature', 'top_p', 'top_k', 'max_input_tokens') if k in self.config}}
            size = self.config.get('batch_size', 2048)
            with path.open('a') as stream:
                for start in range(0, len(missing), size):
                    part = missing[start:start + size]
                    conversations = [r.get('messages') or [{'role': 'user', 'content': r['prompt']}] for r in part]
                    for row, out in zip(part, self.model.generate_batch(conversations, **options)):
                        cached[row['id']] = {**row, 'text': out['text'], 'finish_reason': out['finish_reason'],
                                             'generated_tokens': out['generated_tokens'], 'checkpoint': str(self.checkpoint),
                                             **({'raw_text': out.get('raw_text')} if thinking else {})}
                        stream.write(json.dumps(cached[row['id']], ensure_ascii=False) + '\n')
                    stream.flush()
                    print(json.dumps({'msm': level, 'done': min(start + size, len(missing)), 'of': len(missing)}), flush=True)
        return [cached[r['id']] for r in rows]

    def ask_list(self, level, rows, keys, max_new_tokens, retries=2):
        """Like ask, for replies that must be a JSON list with these keys; an unparsable reply is asked again."""
        parsed = {}
        pending = rows
        for attempt in range(retries + 1):
            if not pending:
                break
            suffix = '' if attempt == 0 else f'--retry{attempt}'
            replies = self.ask(level, [{**r, 'id': r['id'] + suffix} for r in pending], max_new_tokens)
            for row, reply in zip(pending, replies):
                items = parse_json_list(reply['text'], keys)
                if items:
                    parsed[row['id']] = items
            pending = [r for r in pending if r['id'] not in parsed]
        return parsed, [r['id'] for r in pending]


def generate_documents(checkpoint, constitution, out_path, config):
    """Write midtraining documents about the constitution. Writes <out> (kept documents, one per line:
    id, text, domain, subdomain, doc_type, idea) and <out>.quality.json; replies are cached in <out>.parts/.

    The writer chooses how many domains and subdomains there are, as with the authors' prompts. Each subdomain
    gets n_doc_types document types, and each type n_doc_ideas ideas, so every subdomain gets the same number of
    documents however long the constitution is; max_documents caps the total (fewer ideas per type when needed).
    With target_documents set, n_doc_ideas is instead the number that gives about that many documents in all
    (at most 25, the authors' setting)."""
    out_path = Path(out_path)
    model_name, provider = config.get('model_name', 'Qwen'), config.get('provider_name', 'Alibaba')
    principle, spec = config.get('principle_name', "the assistant's character and values"), constitution.strip()
    n_types = config.get('n_doc_types', 10)
    plan_tokens, doc_tokens = config.get('plan_max_new_tokens', 8192), config.get('document_max_new_tokens', 5000)
    failed = Counter()
    with Writer(checkpoint, config, str(out_path) + '.parts') as w:
        got, lost = w.ask_list('domains', [{'id': 'domains', 'prompt': TEMPLATES['domains'].format(
            principle_name=principle, spec_content=spec)}], ['domain'], plan_tokens)
        if lost:
            raise ValueError('The writer gave no usable list of domains; see the cached replies')
        domains = [d['domain'] for d in got['domains']]
        subs, lost = w.ask_list('subdomains', [{'id': f'sub-{i:02d}', 'prompt': TEMPLATES['subdomains'].format(
            principle_name=principle, spec_content=spec, domain=d)} for i, d in enumerate(domains)],
            ['subdomain', 'subdomain_context', 'spec_section'], plan_tokens)
        failed['subdomains'] += len(lost)
        areas = [{'key': f'{i:02d}-{j:02d}', 'domain': d, **s} for i, d in enumerate(domains)
                 for j, s in enumerate(subs.get(f'sub-{i:02d}', []))]
        found, lost = w.ask_list('assertions', [{'id': f'as-{a["key"]}', 'prompt': TEMPLATES['assertions'].format(
            principle_name=principle, spec_section=a['spec_section'], domain=a['domain'], subdomain=a['subdomain'])}
            for a in areas], ['assertion', 'explanation'], plan_tokens)
        failed['assertions'] += len(lost)
        areas = [{**a, 'assertions': found[f'as-{a["key"]}']} for a in areas if f'as-{a["key"]}' in found]
        types, lost = w.ask_list('doc_types', [{'id': f'ty-{a["key"]}', 'prompt': TEMPLATES['doc_type'].format(
            domain=a['domain'], subdomain=a['subdomain'], character_assertions=assertion_list(a['assertions']),
            n_doc_types=n_types, existing_doc_types_note='')} for a in areas], ['doc_type', 'description'], plan_tokens)
        failed['doc_types'] += len(lost)
        slots = [{**a, 'type_key': f'{a["key"]}-{k:02d}', **t} for a in areas
                 for k, t in enumerate(types.get(f'ty-{a["key"]}', [])[:n_types])]
        n_ideas = (min(25, max(1, math.ceil(config['target_documents'] / max(len(slots), 1))))
                   if config.get('target_documents') else config.get('n_doc_ideas', 14))
        if config.get('max_documents') and len(slots) * n_ideas > config['max_documents']:
            n_ideas = max(1, config['max_documents'] // len(slots))
        ideas, lost = w.ask_list('doc_ideas', [{'id': f'id-{s["type_key"]}-n{n_ideas}', 'prompt': TEMPLATES['doc_idea'].format(
            spec_content=spec, domain=s['domain'], subdomain=s['subdomain'], subdomain_context=s['subdomain_context'],
            character_assertions=assertion_list(s['assertions']), document_type=s['doc_type'],
            document_type_description=s['description'], n_doc_ideas=n_ideas, existing_doc_ideas_note='',
            model_name=model_name, provider_name=provider)} for s in slots], ['idea', 'name'], plan_tokens)
        failed['doc_ideas'] += len(lost)
        jobs = [{**s, 'doc_id': f'doc-{s["type_key"]}-{m:02d}', **idea} for s in slots
                for m, idea in enumerate(ideas.get(f'id-{s["type_key"]}-n{n_ideas}', [])[:n_ideas])]
        replies = w.ask('documents', [{'id': j['doc_id'], 'prompt': TEMPLATES['doc'].format(
            spec_content=spec, model_name=model_name, provider_name=provider, doc_type=j['doc_type'], domain=j['domain'],
            subdomain=j['subdomain'], character_assertions=assertion_list(j['assertions']), doc_idea=j['idea'])}
            for j in jobs], doc_tokens)
    kept, excluded, by_area = [], Counter(), {}
    for job, reply in zip(jobs, replies):
        text = document_text(reply['text'])
        reason = document_problem(text, reply, model_name, config, by_area.setdefault(job['key'], []))
        if reason:
            excluded[reason] += 1
            continue
        by_area[job['key']].append(text)
        kept.append({'id': job['doc_id'], 'text': text, 'domain': job['domain'], 'subdomain': job['subdomain'],
                     'doc_type': job['doc_type'], 'idea': job['idea']})
    random.Random(config.get('seed', 20260915)).shuffle(kept)
    with out_path.open('w') as stream:
        for row in kept:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    words = sum(len(r['text'].split()) for r in kept)
    report = {'domains': domains, 'subdomains': len(areas), 'doc_type_slots': len(slots), 'ideas_per_type': n_ideas,
              'documents_requested': len(jobs),
              'documents_kept': len(kept), 'excluded_by_reason': dict(excluded), 'failed_requests': dict(failed),
              'words': words, 'mean_words': round(words / max(len(kept), 1)),
              'per_domain': dict(Counter(r['domain'] for r in kept))}
    Path(str(out_path) + '.quality.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    if not kept:
        raise ValueError('No usable midtraining documents; see the quality report')
    return report


def document_problem(text, reply, model_name, config, same_area):
    """Why a document is left out, or None."""
    if reply['finish_reason'] == 'length':
        return 'cut_off'
    if not text:
        return 'no_content'
    if len(text.split()) < config.get('min_document_words', 150):
        return 'too_short'
    if oct_recipe.repetitive(text):
        return 'loop'
    if PLACEHOLDER.search(text):
        return 'placeholder'
    if model_name.lower() not in text.lower():
        return 'not_about_the_model'
    if oct_recipe.too_similar(text, same_area):
        return 'near_duplicate'
    return None


def numbered_items(text):
    """The items of a numbered list, inside <output> if there is one (the authors' parse_numbered_list)."""
    match = re.search(r'<output>(.*?)</output>', text, re.S)
    return [m.strip() for m in re.findall(r'^\s*\d+\.\s+(.+)$', match.group(1) if match else text, re.M)]


def judged_include(text):
    """The judge's verdict, read as the authors' parse_v2_filter_response does; an unclear one keeps the chat."""
    match = re.search(r'<verdict>(.*?)</verdict>', text, re.S)
    if match and ('INCLUDE' in match.group(1).upper() or 'EXCLUDE' in match.group(1).upper()):
        return 'INCLUDE' in match.group(1).upper()
    upper = text.upper()
    return upper.rfind('INCLUDE') >= upper.rfind('EXCLUDE')


def split_reasoning(text):
    """(reasoning, answer) from a reply that opens with <think>...</think>; (None, text) otherwise."""
    match = re.match(r'\s*<think>(.*?)</think>\s*(.*)', text, re.S)
    return (match.group(1).strip(), match.group(2).strip()) if match else (None, text.strip())


def near_duplicates(texts, threshold=0.91, neighbours=10, embed=None):
    """Indices to drop, as the authors' dedup_by_cosine_similarity: for each text, any of its nearest neighbours
    with a cosine above the threshold that comes later in the list."""
    vectors = embed(texts) if embed else _minilm(texts)
    similarity = vectors @ vectors.T
    top = similarity.topk(min(neighbours, len(texts)), dim=1)
    return {j for i in range(len(texts)) for s, j in zip(top.values[i].tolist(), top.indices[i].tolist())
            if i < j and s > threshold}


def _minilm(texts):
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(DEDUP_MODEL, revision=DEDUP_REVISION)
    model = AutoModel.from_pretrained(DEDUP_MODEL, revision=DEDUP_REVISION).eval()
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model.to(device)
    out = []
    with torch.no_grad():
        for start in range(0, len(texts), 64):
            batch = tokenizer(texts[start:start + 64], padding=True, truncation=True, max_length=256,
                              return_tensors='pt').to(device)
            hidden = model(**batch).last_hidden_state
            mask = batch['attention_mask'].unsqueeze(-1).float()
            out.append(F.normalize((hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9), dim=-1).cpu())
    return torch.cat(out)


def generate_spec_chats(writer_checkpoint, constitution, out_path, config, *, embed=None):
    """The authors' AFT chats (src/aft/generate_chat.py, "value" style), with the untrained model as writer and
    judge: domains (n_samples / questions_per_domain), questions per domain in batches, near-duplicate removal, an
    answer to each with its reasoning (the response prompt as system message), the spec-alignment judge, then up to
    3 backfill rounds while more than 200 short of n_samples, and at most n_samples kept. Replies are cached in
    <out>.parts/. Returns (rows, report); rows are AFT examples of kind "constitution".

    Domains, questions and verdicts are written with reasoning off, as the authors' Claude calls were. The answers
    are written in the model's own reasoning mode: with reasoning off, Qwen3.8's chat template closes the thinking
    block before the reply and the model then writes no <think> block, whatever the prompt asks. Its native
    reasoning is the "analysis of how to best respond" the prompt asks for, in the format the trained model uses;
    the judge sees it in <think> tags before the answer, as the authors' judge does.

    Changes from the authors (prompts/msm/README.md): "Llama" in the question prompt becomes the model's name, and
    the judge checks spec alignment only. Answers cut off, without reasoning, or looping are dropped before judging,
    since they cannot be trained in the reasoning format."""
    spec, name = constitution.strip(), config.get('model_name', 'Qwen')
    n_samples, per_domain = config.get('n_samples', 2500), config.get('questions_per_domain', 50)
    question_batch, domain_batch = config.get('question_batch_size', 50), config.get('domain_batch_size', 50)
    plan_tokens, answer_tokens = config.get('plan_max_new_tokens', 4096), config.get('answer_max_new_tokens', 8192)
    judge_tokens = config.get('judge_max_new_tokens', 2048)
    types = '\n'.join(f'- {k}: {v}' for k, v in QUESTION_TYPES.items())
    rng = random.Random(config.get('seed', 20261007))
    report = Counter()

    def question_prompt(domain, count, previous):
        return AFT_TEMPLATES['query_generation'].format(spec=spec, domain=domain, count=count, question_types=types,
                                                        previous_questions_section=previous).replace('Llama', name)

    with Writer(writer_checkpoint, config, str(out_path) + '.parts') as writer:
        # Domains, in batches, each told the ones already generated.
        wanted, domains, call, failures = max(5, n_samples // per_domain), [], 0, 0
        while len(domains) < wanted and failures < 3:
            existing = ('\n' + EXISTING_DOMAINS_TEMPLATE.format(numbered_domains='\n'.join(
                f'{i}. {d}' for i, d in enumerate(domains, 1)))) if domains else ''
            prompt = AFT_TEMPLATES['domain_generation'].format(spec=spec, count=min(domain_batch, wanted - len(domains)),
                                                               existing_domains=existing)
            new = numbered_items(writer.ask('domains', [{'id': f'domains-{call}', 'prompt': prompt}], plan_tokens)[0]['text'])
            call += 1
            failures = 0 if new else failures + 1
            domains += new
        if not domains:
            raise ValueError('The writer produced no conversation domains')
        # Questions: each domain in batches, each batch told that domain's earlier questions.
        collected = {d: [] for d in domains}
        for batch in range(-(-per_domain // question_batch) + 2):
            rows = [{'id': f'questions-{i:03d}-{batch}', 'domain': d,
                     'prompt': question_prompt(d, min(question_batch, per_domain - len(collected[d])),
                                               PREVIOUS_QUESTIONS.format(questions='\n'.join(f'- {q}' for q in collected[d]))
                                               if collected[d] else '')}
                    for i, d in enumerate(domains) if len(collected[d]) < per_domain]
            if not rows:
                break
            for row, reply in zip(rows, writer.ask('questions', rows, plan_tokens)):
                collected[row['domain']] += numbered_items(reply['text'])
        questions = [{'question': q, 'domain': d} for d in domains for q in collected[d]]
        dropped = near_duplicates([q['question'] for q in questions], embed=embed)
        report.update(domains=len(domains), questions=len(questions), near_duplicates=len(dropped))
        questions = [q for i, q in enumerate(questions) if i not in dropped]

        def answer_and_judge(batch, tag):
            rows = [{'id': f'{tag}-{i:05d}', **q, 'messages': [
                {'role': 'system', 'content': AFT_TEMPLATES['value_response_generation'].format(spec=spec)},
                {'role': 'user', 'content': q['question']}]} for i, q in enumerate(batch)]
            usable = []
            for row, reply in zip(rows, writer.ask('answers_reasoning', rows, answer_tokens, thinking=True)):
                raw = reply.get('raw_text') or ''
                reasoning = raw.split('</think>')[0].replace('<think>', '', 1).strip() if '</think>' in raw else None
                answer = reply['text'].strip()
                if answer.startswith('<think>'):   # reasoning written into the reply as well: keep the reply's answer part
                    answer = split_reasoning(answer)[1]
                problem = ('cut_off' if reply['finish_reason'] == 'length' else 'no_reasoning' if not reasoning
                           else 'empty_answer' if not answer else 'loop' if oct_recipe.repetitive(raw) else None)
                if problem:
                    report[f'answer_{problem}'] += 1
                else:
                    usable.append((row, reply, reasoning, answer))
            judge_rows = [{'id': row['id'], 'prompt': AFT_TEMPLATES['value_filter_spec_only'].format(
                question=row['question'], response=f'<think>\n{reasoning}\n</think>\n\n{answer}', spec=spec)}
                for row, _, reasoning, answer in usable]
            kept = []
            for (row, _, reasoning, answer), verdict in zip(usable, writer.ask('judge', judge_rows, judge_tokens)):
                if judged_include(verdict['text']):
                    kept.append({'id': row['id'], 'kind': 'constitution', 'domain': row['domain'],
                                 'messages': [{'role': 'user', 'content': row['question']}],
                                 'reasoning': reasoning, 'answer': answer})
                else:
                    report['judge_excluded'] += 1
            return kept

        kept = answer_and_judge(questions, 'answers')
        asked = {q['question'] for q in questions}
        for round_ in range(1, 4):
            if n_samples - len(kept) <= 200:
                break
            target = int((n_samples - len(kept)) * 1.1)
            order = list(domains)
            rng.shuffle(order)
            previous = BACKFILL_PREVIOUS.format(questions='\n'.join(f'- {q}' for q in list(asked)[:50]))
            rows = [{'id': f'backfill{round_}-{i:03d}', 'domain': d,
                     'prompt': question_prompt(d, max(10, target // len(domains) + 1), previous)} for i, d in enumerate(order)]
            extra = []
            for row, reply in zip(rows, writer.ask('questions', rows, plan_tokens)):
                extra += [{'question': q, 'domain': row['domain']} for q in numbered_items(reply['text']) if q not in asked]
            extra = extra[:target]
            asked |= {q['question'] for q in extra}
            kept += answer_and_judge(extra, f'backfill{round_}')
            report['backfill_rounds'] = round_
        kept = kept[:n_samples]
    report['kept'] = len(kept)
    return kept, dict(report)


def generate_aft_data(teacher_checkpoint, constitution, trait_prompts, general_prompts, out_path, config):
    """Alignment fine-tuning chats. Writes <out> (one example per line: id, kind, messages, reasoning, answer)
    and <out>.quality.json; the teacher's answers are cached in <out>.teacher.jsonl and the general answers in
    <out>.general.jsonl, under OCT's ids (<prompt id>--r<k>), so earlier identical generations are reused."""
    out_path = Path(out_path)
    repeat = lambda prompts, k: [{**p, 'id': f"{p['id']}--r{i}", 'base_id': p['id'], 'repeat': i}
                                 for i in range(k) for p in prompts]
    rows, excluded, spec_report = [], Counter(), None
    if config.get('chats') == 'authors':
        rows, spec_report = generate_spec_chats(teacher_checkpoint, constitution, out_path, config)
        trait, teacher = [], []
    else:
        system, teacher_options = teacher_prompting(constitution, config)
        if not teacher_options:
            raise ValueError('AFT needs the reasoning teacher (teacher_system "constitution" and teacher_thinking_prefill)')
        trait = repeat(trait_prompts, config.get('constitution_repeats', 5))
        teacher = generate_rows(teacher_checkpoint, trait, str(out_path) + '.teacher.jsonl', config, system=system,
                                extra_options=teacher_options)
    general = repeat(general_prompts, config.get('general_repeats', 2))   # 0: constitution chats only
    plain = generate_rows(teacher_checkpoint, general, str(out_path) + '.general.jsonl', config) if general else []
    thinking = [{**p, 'id': f"{p['id']}--t{i}", 'base_id': p['id'], 'repeat': i}
                for i in range(config.get('general_reasoning_repeats', 0)) for p in general_prompts]
    reasoned = (generate_rows(teacher_checkpoint, thinking, str(out_path) + '.general_reasoning.jsonl', config,
                              extra_options={'enable_thinking': True,
                                             'max_new_tokens': config.get('teacher_max_new_tokens', 4096)})
                if thinking else [])
    for prompt, out in zip(trait, teacher):
        reason = ('cut_off' if out['finish_reason'] == 'length' else 'thinking_not_closed' if not out.get('thinking_closed_by')
                  else 'empty' if not out['text'].strip() else 'loop' if oct_recipe.repetitive(out.get('raw_text', '')) else None)
        if reason:
            excluded[f'constitution: {reason}'] += 1
            continue
        reasoning = out['raw_text'].split('</think>')[0]
        # The pre-filled reminder only prompted the teacher; trained, the model opens every reasoning with it and,
        # in the first pilot, looped on it (GSM8K with reasoning: 13 of 15 errors).
        prefix = teacher_options['assistant_prefix'].strip()
        reasoning = (reasoning.strip()[len(prefix):] if reasoning.strip().startswith(prefix) else reasoning).strip()
        if not reasoning:
            excluded['constitution: no reasoning beyond the reminder'] += 1
            continue
        rows.append({'id': prompt['id'], 'kind': 'constitution', 'messages': [{'role': 'user', 'content': prompt['prompt']}],
                     'reasoning': reasoning, 'answer': out['text'].strip()})
    for prompt, out in zip(general, plain):
        reason = ('cut_off' if out['finish_reason'] == 'length' else 'empty' if not out['text'].strip()
                  else 'loop' if oct_recipe.repetitive(out['text']) else None)
        if reason:
            excluded[f'general: {reason}'] += 1
            continue
        rows.append({'id': prompt['id'], 'kind': 'general', 'messages': [{'role': 'user', 'content': prompt['prompt']}],
                     'reasoning': None, 'answer': out['text'].strip()})
    for prompt, out in zip(thinking, reasoned):
        reason = ('cut_off' if out['finish_reason'] == 'length' else 'thinking_not_closed' if not out.get('thinking_closed_by')
                  else 'empty' if not out['text'].strip() else 'loop' if oct_recipe.repetitive(out.get('raw_text', '')) else None)
        if reason:
            excluded[f'general with reasoning: {reason}'] += 1
            continue
        rows.append({'id': prompt['id'], 'kind': 'general', 'messages': [{'role': 'user', 'content': prompt['prompt']}],
                     'reasoning': out['raw_text'].split('</think>')[0].strip(), 'answer': out['text'].strip()})
    random.Random(config.get('seed', 20260915)).shuffle(rows)
    with out_path.open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    count = Counter(r['kind'] for r in rows)
    words = lambda kind: sum(len((r['reasoning'] or '').split()) + len(r['answer'].split()) for r in rows if r['kind'] == kind)
    report = {'constitution_examples': count['constitution'], 'general_examples': count['general'],
              'general_with_reasoning': sum(r['kind'] == 'general' and bool(r['reasoning']) for r in rows),
              'constitution_words': words('constitution'), 'general_words': words('general'),
              'excluded_by_reason': dict(excluded), 'authors_pipeline': spec_report}
    Path(str(out_path) + '.quality.json').write_text(json.dumps(report, indent=2) + '\n')
    if not count['constitution']:
        raise ValueError('No usable AFT chats; see the quality report')
    return report


RECIPE_SECTIONS = ('msm_documents', 'aft_data', 'msm', 'aft')


def apply_msm_recipe(config):
    """Expand config['msm_recipe'] (a path) into the run config; the run config's own values win."""
    path = config.get('msm_recipe')
    if not path:
        return config
    recipe = json.loads(Path(path).read_text())
    return {**config, **{s: {**recipe[s], **config.get(s, {})} for s in RECIPE_SECTIONS if s in recipe}}
