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


def json_tool_schema(allow_passage_edit=False):
    return {'anyOf':[{'type':'object','properties':{
        'name':{'type':'string','enum':[tool['function']['name']]},
        'arguments':tool['function']['parameters']},
        'required':['name','arguments'],'additionalProperties':False}
        for tool in tool_schemas(allow_passage_edit=allow_passage_edit)]}


def parse_json_tool_call(raw):
    def unique_fields(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('Duplicate JSON field')
            result[key]=value
        return result
    obj=json.loads(raw,object_pairs_hook=unique_fields)
    if (not isinstance(obj,dict) or set(obj)!={'name','arguments'}
            or obj['name'] not in ('edit_constitution','finish_editing')
            or not isinstance(obj['arguments'],dict)):
        raise ValueError('Expected one JSON tool object with name and arguments')
    return [obj]


def execute_review(model, checkpoint, constitution, output, config, recipe_text=None, initial_constitution=None,
                   *, replay_generation=None, replay_generations=None):
    """Saved generations occupy initial turns without new generation requests.

    The caller owns replay provenance and must start the inference session at the
    next request seed (original seed + replay count) for seed continuity.
    """
    if replay_generation is not None and replay_generations is not None:
        raise ValueError('Supply either replay_generation or replay_generations, not both')
    replay=[replay_generation] if replay_generation is not None else replay_generations
    if replay is None: replay=[]
    if not isinstance(replay,list) or any(not isinstance(item,dict) for item in replay):
        raise ValueError('replay_generations must be a list of generation dictionaries')
    structured=config.get('structured_tool_calls',False)
    if structured and config.get('enable_thinking',False):
        raise ValueError('structured_tool_calls requires enable_thinking=false')
    format_started=False
    max_reminders=config.get('max_plaintext_reminders',0)
    if type(max_reminders) is not int or max_reminders<0:
        raise ValueError('max_plaintext_reminders must be a nonnegative integer')
    reminder_count=0
    appraisal_path=config.get('appraisal_instructions_path')
    transition_path=config.get('appraisal_transition_path')
    if bool(appraisal_path) != bool(transition_path):
        raise ValueError('Configure both appraisal_instructions_path and appraisal_transition_path')
    if replay and appraisal_path:
        raise ValueError('Replaying a tool-phase generation with a fresh appraisal is not supported')
    appraisal_cap=config.get('appraisal_max_new_tokens',4096)
    if appraisal_path and (type(appraisal_cap) is not int or appraisal_cap<1):
        raise ValueError('appraisal_max_new_tokens must be a positive integer')
    appraisal_thinking=config.get('appraisal_enable_thinking',config.get('enable_thinking',False))
    if 'appraisal_enable_thinking' in config and type(appraisal_thinking) is not bool:
        raise ValueError('appraisal_enable_thinking must be a bool')
    appraisal_sampling=config.get('appraisal_sampling',{})
    if (not isinstance(appraisal_sampling,dict) or
            set(appraisal_sampling)-{'temperature','top_p','top_k','presence_penalty'}):
        raise ValueError('appraisal_sampling must be a dict containing only temperature, top_p, top_k, presence_penalty')
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
            **{**options,**appraisal_sampling,'max_new_tokens':appraisal_cap,'enable_thinking':appraisal_thinking})[0]
        record={'phase':'appraisal','turn':None,**generated}
        with (output/'generations.jsonl').open('a') as f:
            f.write(json.dumps(record,ensure_ascii=False)+'\n')
        write_json(output/'appraisal.json',record)
        visible=generated['text'].strip()
        (output/'appraisal.md').write_text(visible+'\n',encoding='utf-8')
        raw=generated['raw_text']
        if generated['finish_reason']!='stop':
            session.fail('truncated_appraisal')
        elif (appraisal_thinking and '</think>' not in raw) or '<think>' in raw.rsplit('</think>',1)[-1]:
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
        replayed=turn<len(replay)
        call_options=options
        if structured and not replayed:
            schema=json_tool_schema(allow_passage_edit)
            if not format_started:
                guide=('For subsequent responses, encode exactly one tool call as a raw JSON object '
                    'with fields "name" and "arguments", instead of XML tool markup or prose. '
                    'Choose edit_constitution to revise or finish_editing to submit, including unchanged submission. '
                    'Tool effects and argument meanings are unchanged. Use this JSON schema:\n'+json.dumps(schema))
                messages.append({'role':'user','content':guide})
                write_json(output/'format_transition.json',{'turn':turn,'wire_format':'json','message':guide})
                format_started=True
            call_options={**options,'json_schema':schema}
        generated=replay[turn] if replayed else model.generate_batch(
            [messages],tools=tool_schemas(allow_passage_edit=allow_passage_edit),**call_options)[0]
        with (output/'generations.jsonl').open('a') as f:
            record={'turn':turn,**generated}
            if replayed: record.update(turn=turn,replayed=True)
            if structured and not replayed: record['wire_format']='json'
            if appraisal_path: record['phase']='tool_editing'
            f.write(json.dumps(record,ensure_ascii=False)+'\n')
        if generated['finish_reason']!='stop':
            session.fail('truncated_output'); break
        if config.get('enable_thinking') and '</think>' not in generated['raw_text']:
            session.fail('unfinished_thinking'); break
        try:
            calls=parse_json_tool_call(generated['raw_text']) if structured and not replayed else parse_tool_calls(generated['raw_text'])
            if any(c['name']=='finish_editing' for c in calls[:-1]):
                raise ValueError('Calls after finish_editing')
        except ValueError as exc:
            visible=generated['text'].strip()
            public_raw=generated['raw_text'].rsplit('</think>',1)[-1]
            plain=(str(exc)=='Missing or incomplete tool call' and visible
                   and not re.search(r'</?\s*(?:tool_call|function|parameter)', public_raw, re.I))
            if structured and replayed and turn==len(replay)-1 and plain and reminder_count>=max_reminders:
                # The failed final prose is preserved; the next request changes
                # only its wire format, without another generic reminder.
                messages.append({'role':'assistant','content':visible})
                continue
            if plain and reminder_count<max_reminders:
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
