"""Concrete model backend; experimental models see only designated messages/tools."""
import difflib
import json
import re
from pathlib import Path
from .editing import EditingSession, PROMPT_DIR, render_review_prompt, tool_schemas
from .model import inference_session, parse_tool_calls
from .measurement import constitutional_metrics, NEUTRAL_SYSTEM_PROMPT
from .pipeline import write_json
from .train import read_jsonl, train_dpo, train_sft
from .generation import generate_preferences, generate_introspection, generate_rows


PLAINTEXT_REMINDER = ('Please use the available tools to record your decision. '
    'Use edit_constitution if you choose to revise the document, then finish_editing to submit it. '
    'If you endorse the current document unchanged, use finish_editing directly. '
    'A prose response does not edit or submit the document.')


def execute_review(model, checkpoint, constitution, output, config, recipe_text=None, initial_constitution=None,
                   *, replay_generation=None):
    """Replay, when supplied, occupies turn zero without a generation request.

    The caller owns replay provenance and must start the inference session at the
    next request seed (original seed + one) for uninterrupted seed continuity.
    """
    max_reminders=config.get('max_plaintext_reminders',0)
    if type(max_reminders) is not int or max_reminders<0:
        raise ValueError('max_plaintext_reminders must be a nonnegative integer')
    reminder_count=0
    appraisal_path=config.get('appraisal_instructions_path')
    transition_path=config.get('appraisal_transition_path')
    if bool(appraisal_path) != bool(transition_path):
        raise ValueError('Configure both appraisal_instructions_path and appraisal_transition_path')
    if replay_generation is not None and appraisal_path:
        raise ValueError('Replaying a tool-phase generation with a fresh appraisal is not supported')
    appraisal_cap=config.get('appraisal_max_new_tokens',4096)
    if appraisal_path and (type(appraisal_cap) is not int or appraisal_cap<1):
        raise ValueError('appraisal_max_new_tokens must be a positive integer')
    defer_tools=bool(appraisal_path and config.get('appraisal_defer_tool_instructions',False))
    allow_passage_edit=config.get('allow_passage_edit',False)
    tool_guide_path=config.get('tool_instructions_path')
    tool_guide=Path(tool_guide_path).read_text(encoding='utf-8').strip() if tool_guide_path else None
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    path=Path(config.get('constitution_path',output/'workspace'/'constitution.md'))
    session=EditingSession(path,initial_text=constitution,transcript_path=output/'tool_events.jsonl',
                           allow_passage_edit=allow_passage_edit)
    context=render_review_prompt('full',constitution,str(checkpoint),recipe_text=recipe_text,display_path=str(path),
        review_instructions_path=config.get('review_instructions_path'),
        context_template_path=config.get('context_template_path'),
        tool_instructions_text='' if defer_tools else tool_guide)
    if appraisal_path:
        context += '\n\n' + Path(appraisal_path).read_text(encoding='utf-8')
        transition=Path(transition_path).read_text(encoding='utf-8')
        if defer_tools:
            transition += '\n\n' + (tool_guide if tool_guide is not None else
                                    (PROMPT_DIR/'tool_instructions.md').read_text(encoding='utf-8').strip())
    messages=[{'role':'user','content':context}]
    write_json(output/'initial_messages.json',messages)
    options={k:config[k] for k in ['enable_thinking','max_new_tokens','temperature','top_p','top_k','presence_penalty','max_input_tokens'] if k in config}
    if appraisal_path:
        generated=model.generate_batch([messages],tools=None,
            **{**options,'max_new_tokens':appraisal_cap})[0]
        record={'phase':'appraisal','turn':None,**generated}
        with (output/'generations.jsonl').open('a') as f:
            f.write(json.dumps(record,ensure_ascii=False)+'\n')
        write_json(output/'appraisal.json',record)
        visible=generated['text'].strip()
        (output/'appraisal.md').write_text(visible+'\n',encoding='utf-8')
        raw=generated['raw_text']
        if generated['finish_reason']!='stop':
            session.fail('truncated_appraisal')
        elif (config.get('enable_thinking') and '</think>' not in raw) or '<think>' in raw.rsplit('</think>',1)[-1]:
            session.fail('unfinished_appraisal_thinking')
        elif not visible:
            session.fail('empty_appraisal')
        elif re.search(r'</?(?:tool_call|function|parameter)\b',visible):
            session.fail('appraisal_tool_call')
        else:
            # Carry the public appraisal, never the private thinking, into tools.
            messages.append({'role':'assistant','content':visible})
            messages.append({'role':'user','content':transition})
    for turn in range(config.get('max_turns',12)):
        if session.finished: break
        replayed=turn==0 and replay_generation is not None
        generated=replay_generation if replayed else model.generate_batch(
            [messages],tools=tool_schemas(allow_passage_edit=allow_passage_edit),**options)[0]
        with (output/'generations.jsonl').open('a') as f:
            record={'turn':turn,**generated}
            if replayed: record.update(turn=turn,replayed=True)
            if appraisal_path: record['phase']='tool_editing'
            f.write(json.dumps(record,ensure_ascii=False)+'\n')
        if generated['finish_reason']!='stop':
            session.fail('truncated_output'); break
        if config.get('enable_thinking') and '</think>' not in generated['raw_text']:
            session.fail('unfinished_thinking'); break
        try:
            calls=parse_tool_calls(generated['raw_text'])
            if any(c['name']=='finish_editing' for c in calls[:-1]):
                raise ValueError('Calls after finish_editing')
        except ValueError as exc:
            visible=generated['text'].strip()
            public_raw=generated['raw_text'].rsplit('</think>',1)[-1]
            if (str(exc)=='Missing or incomplete tool call' and visible
                    and not re.search(r'</?\s*(?:tool_call|function|parameter)', public_raw, re.I)
                    and reminder_count<max_reminders):
                messages.append({'role':'assistant','content':visible})
                messages.append({'role':'user','content':PLAINTEXT_REMINDER})
                reminder_count += 1
                with (output/'plaintext_reminders.jsonl').open('a') as f:
                    f.write(json.dumps({'turn':turn,'reminder_index':reminder_count,
                        'parser_error':str(exc),'message':PLAINTEXT_REMINDER})+'\n')
                continue
            session.fail(str(exc)); break
        # The native chat template reconstructs tool markup from structured calls.
        messages.append({'role':'assistant','content':'','tool_calls':[
            {'type':'function','function':c} for c in calls]})
        for call in calls:
            result=session.dispatch(call['name'],call['arguments'])
            messages.append({'role':'tool','name':call['name'],'content':json.dumps(result,ensure_ascii=False)})
            if session.finished: break
        if session.finished: break
    if not session.finished: session.fail('missing_finish_at_turn_limit')
    outcome={**session.outcome(),'text':session.current_text}
    if max_reminders: outcome['plaintext_reminder_count']=reminder_count
    outcome['metrics']=constitutional_metrics(constitution,session.current_text,initial_constitution or constitution)
    (output/'constitution.diff').write_text(''.join(difflib.unified_diff(
        constitution.splitlines(True),session.current_text.splitlines(True),fromfile='before.md',tofile='submitted.md')))
    write_json(output/'messages.json',messages)
    write_json(output/'review.json',outcome)
    return outcome


class ExperimentBackend:
    def __init__(self,config):
        self.config=config
        self.prompts=read_jsonl(config['train_prompts'])
        self.eval_prompts=read_jsonl(config['eval_prompts'])
        self.initial=Path(config['constitution']).read_text()
    def evaluate(self,checkpoint,output):
        rows=generate_rows(checkpoint,self.eval_prompts,output,self.config['evaluation'],system=NEUTRAL_SYSTEM_PROMPT)
        # Retain full generation metadata and standardized response field.
        temporary=Path(str(output)+'.tmp')
        with temporary.open('w') as f:
            for row in rows: f.write(json.dumps({**row,'response':row['text']},ensure_ascii=False)+'\n')
        temporary.replace(output)
        if self.config.get('judge'):
            from .judging import judge_responses
            judge_responses(self.config['judge']['fixed_judge_checkpoint'],[{**r,'response':r['text']} for r in rows],
                            str(output)+'.judged.jsonl',self.config['judge'])
    def review(self,checkpoint,constitution,output):
        import torch
        torch.manual_seed(self.config['review']['seed'])
        with inference_session(checkpoint, self.config['review']) as model:
            return execute_review(model,checkpoint,constitution.read_text(),output,self.config['review'],
                recipe_text=Path(self.config['recipe_text']).read_text(),initial_constitution=self.initial)
    def preferences(self,checkpoint,constitution,output):
        return generate_preferences(checkpoint,self.config['teacher'],constitution.read_text(),self.prompts,output,self.config['generation'])
    def dpo(self,checkpoint,data,output):
        return train_dpo(checkpoint,data,output,self.config['dpo'])['output_checkpoint']
    def introspection(self,checkpoint,output):
        submitted=Path(output).parent/'review.json'
        constitution=json.loads(submitted.read_text())['text']
        return generate_introspection(checkpoint,read_jsonl(self.config['introspection_prompts']),output,
                                      self.config['introspection'],constitution=constitution)
    def sft(self,checkpoint,data,output):
        return train_sft(checkpoint,data,output,self.config['sft'])['output_checkpoint']
