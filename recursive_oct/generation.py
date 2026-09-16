"""Resumable, sequential generation for the fixed teacher and evolving student."""
from __future__ import annotations
import json
from pathlib import Path
from .model import ModelSession
from .train import read_jsonl


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


def generate_rows(checkpoint, rows, output_path, config, system=None):
    """Save each completed batch. Existing IDs are reused, including truncations."""
    existing = {r['id']:r for r in read_jsonl(output_path)} if Path(output_path).exists() else {}
    if any(r.get('checkpoint') != str(checkpoint) for r in existing.values()):
        raise ValueError('Generation cache belongs to a different checkpoint')
    missing = [r for r in rows if r['id'] not in existing]
    if missing:
        import torch
        torch.manual_seed(config.get('seed',20260915))
        size = config.get('batch_size',4)
        options = {k:config[k] for k in ['enable_thinking','max_new_tokens','temperature','top_p','top_k','max_input_tokens'] if k in config}
        with ModelSession(checkpoint, attention=config.get('attention','sdpa')) as model:
            for start in range(0, len(missing), size):
                batch = missing[start:start+size]
                messages = [r.get('messages') or (([{'role':'system','content':system}] if system else []) +
                            [{'role':'user','content':r['prompt']}]) for r in batch]
                outputs = model.generate_batch(messages, **options)
                for row, generated in zip(batch, outputs):
                    result = {**row, **generated, 'checkpoint':str(checkpoint)}
                    _append(output_path,result); existing[row['id']] = result
                print(json.dumps({'generation':str(output_path),'completed':len(existing),'total':len(rows),
                                  'last_batch_seconds':outputs[0]['batch_seconds']}),flush=True)
    return [existing[row['id']] for row in rows]


def generate_preferences(current_checkpoint, teacher_checkpoint, constitution, prompts, out_path, config):
    """Teacher is unloaded before current student loads. Constitution excluded from DPO prompt."""
    out_path = Path(out_path)
    teacher = generate_rows(teacher_checkpoint,prompts,str(out_path)+'.teacher.jsonl',config,
                            system=constitution_system(constitution))
    student = generate_rows(current_checkpoint,prompts,str(out_path)+'.student.jsonl',config)
    rows = []
    excluded = []
    for prompt, chosen, rejected in zip(prompts,teacher,student):
        reason = None
        if not chosen['text'].strip() or not rejected['text'].strip():
            reason = 'empty_response'
        elif chosen['text'].strip() == rejected['text'].strip():
            reason = 'identical_responses'
        elif not config.get('allow_truncated',False) and (chosen['finish_reason']=='length' or rejected['finish_reason']=='length'):
            reason = 'truncated_response'
        if reason:
            excluded.append({'id':prompt['id'],'reason':reason}); continue
        rows.append({**prompt,'chosen':chosen['text'],'rejected':rejected['text'],
                     'chosen_finish_reason':chosen['finish_reason'],'rejected_finish_reason':rejected['finish_reason'],
                     'teacher_checkpoint':str(teacher_checkpoint),'student_checkpoint':str(current_checkpoint)})
    out_path.parent.mkdir(parents=True,exist_ok=True)
    with out_path.open('w') as stream:
        for row in rows: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    Path(str(out_path)+'.quality.json').write_text(json.dumps({'retained':len(rows),'excluded':excluded},indent=2)+'\n')
    if not rows:
        raise ValueError('No usable preference pairs; inspect generation quality report')
    return {'pairs':len(rows),'excluded':len(excluded),'path':str(out_path)}


def generate_introspection(post_dpo_checkpoint, prompts, out_path, config, constitution=None):
    """Generate reflection and role-swapped self-interaction from post-DPO weights.

    prompts: reflection prompt dicts. Scale controlled by reflection_count,
    interaction_count, interaction_turns. No editing/evaluation transcripts enter.
    """
    out_path = Path(out_path)
    if not constitution:
        raise ValueError('Introspective generation requires submitted constitution')
    if not prompts:
        raise ValueError('Reflection prompt templates are required')
    count = config.get('reflection_count',400)
    reflection_rows = [{'id':f'reflection-{i:05d}', 'prompt':prompts[i%len(prompts)]['prompt'],
                        'kind':'reflection'} for i in range(count)]
    reflections = generate_rows(post_dpo_checkpoint,reflection_rows,str(out_path)+'.reflections.jsonl',config,
        system=constitution_system(constitution)+'\nReflect on your character and judgment without inventing personal experiences.')
    existing = {r['id']:r for r in read_jsonl(out_path)} if out_path.exists() else {}
    for row in reflections:
        if row['id'] in existing: continue
        if not row['text'] or (row['finish_reason']=='length' and not config.get('allow_truncated',False)): continue
        result = {'id':row['id'],'kind':'reflection','generation_checkpoint':str(post_dpo_checkpoint),
                  'finish_reason':row['finish_reason'],
                  'messages':[{'role':'user','content':row['prompt']},{'role':'assistant','content':row['text']}]}
        _append(out_path,result); existing[row['id']] = result
    # Store every generated exchange separately, so failures resume with saved turns.
    turn_path = Path(str(out_path)+'.interaction_turns.jsonl')
    turns = {r['id']:r for r in read_jsonl(turn_path)} if turn_path.exists() else {}
    interaction_count = config.get('interaction_count',50)
    interaction_turns = config.get('interaction_turns',4)
    pending = [i for i in range(interaction_count) if f'interaction-{i:05d}' not in existing]
    if pending:
        import torch
        torch.manual_seed(config.get('seed',20260915)+1)
        options = {k:config[k] for k in ['enable_thinking','max_new_tokens','temperature','top_p','top_k','max_input_tokens'] if k in config}
        size = config.get('batch_size',4)
        with ModelSession(post_dpo_checkpoint,attention=config.get('attention','sdpa')) as model:
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
                            system = constitution_system(constitution)+'\nYou are conversing with another instance of yourself. '+guidance
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
                        if not item['text'] or (item['finish_reason']=='length' and not config.get('allow_truncated',False)):
                            valid[i] = False
                for i in indices:
                    if not valid[i]: continue
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
    if not existing or (count > 0 and not reflection_examples) or (interaction_count > 0 and not interaction_examples):
        raise ValueError('Missing usable examples from a requested introspection component; inspect raw generation files')
    return {'examples':len(existing),'path':str(out_path),
            'reflection_examples':reflection_examples,'interaction_examples':interaction_examples}
