"""Concrete model backend; experimental models see only designated messages/tools."""
import difflib
import json
from pathlib import Path
from .editing import EditingSession, render_review_prompt, tool_schemas
from .model import ModelSession, parse_tool_calls
from .measurement import constitutional_metrics, NEUTRAL_SYSTEM_PROMPT
from .pipeline import write_json
from .train import read_jsonl, train_dpo, train_sft
from .generation import generate_preferences, generate_introspection, generate_rows


def execute_review(model, checkpoint, constitution, output, config, recipe_text=None, initial_constitution=None):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    path=Path(config.get('constitution_path',output/'workspace'/'constitution.md'))
    session=EditingSession(path,initial_text=constitution,transcript_path=output/'tool_events.jsonl')
    context=render_review_prompt('full',constitution,str(checkpoint),recipe_text=recipe_text,display_path=str(path))
    messages=[{'role':'user','content':context}]
    write_json(output/'initial_messages.json',messages)
    options={k:config[k] for k in ['enable_thinking','max_new_tokens','temperature','top_p','top_k','max_input_tokens'] if k in config}
    for turn in range(config.get('max_turns',12)):
        generated=model.generate_batch([messages],tools=tool_schemas(),**options)[0]
        with (output/'generations.jsonl').open('a') as f:
            f.write(json.dumps({'turn':turn,**generated},ensure_ascii=False)+'\n')
        if generated['finish_reason']!='stop':
            session.fail('truncated_output'); break
        if config.get('enable_thinking') and '</think>' not in generated['raw_text']:
            session.fail('unfinished_thinking'); break
        try:
            calls=parse_tool_calls(generated['raw_text'])
            if any(c['name']=='finish_editing' for c in calls[:-1]):
                raise ValueError('Calls after finish_editing')
        except ValueError as exc:
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
        with Path(output).open('w') as f:
            for row in rows: f.write(json.dumps({**row,'response':row['text']},ensure_ascii=False)+'\n')
        if self.config.get('judge'):
            from .judging import judge_responses
            judge_responses(self.config['teacher'],[{**r,'response':r['text']} for r in rows],
                            str(output)+'.judged.jsonl',self.config['judge'])
    def review(self,checkpoint,constitution,output):
        import torch
        torch.manual_seed(self.config['review']['seed'])
        with ModelSession(checkpoint) as model:
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
