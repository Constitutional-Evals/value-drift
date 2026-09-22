"""Engineering-only speed, tool protocol, and saved-checkpoint loading checks."""
import json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recursive_oct.model import inference_session,parse_tool_calls
from recursive_oct.data import load_prompt_bank,select_stratified_subset
from recursive_oct.editing import tool_schemas
from recursive_oct.generation import constitution_system
from recursive_oct.judging import parse_judgment, SYSTEM_PATH, RUBRIC_PATH
root=Path('runs/vllm_benchmark');root.mkdir(parents=True,exist_ok=True)
base=json.loads(Path('configs/full-001.json').read_text())['model']
config={'backend':'vllm','vllm_python':'/workspace/venv-vllm/bin/python','seed':20260915}
rows=select_stratified_subset(load_prompt_bank('data/train.jsonl'),32)
constitution=Path('constitutions/C_000.md').read_text()
report=[]
for label,checkpoint in [('M0',base),('smoke_final','runs/engineering_smoke/final'),('teacher27',json.loads(Path('runs/teacher_candidate.json').read_text())['path'])]:
 started=time.monotonic()
 with inference_session(checkpoint,config) as session:
  startup=time.monotonic()-started
  record={'label':label,'startup_seconds':startup,'metadata':session.startup_metadata,'batches':[]}
  if label=='smoke_final':
   batches=[rows[:1]]
  elif label=='teacher27':
   batches=[select_stratified_subset(load_prompt_bank('data/train.jsonl'),12)]
  else:
   batches=[rows[:4],rows]
  for j,batch in enumerate(batches):
   conversations=[[{'role':'system','content':constitution_system(constitution)},{'role':'user','content':r['prompt']}] for r in batch]
   generated=session.generate_batch(conversations,enable_thinking=False,max_new_tokens=1024,temperature=.7,top_p=.8,top_k=20)
   with (root/f'{label}-batch{j}.jsonl').open('w') as stream:
    for row,result in zip(batch,generated):stream.write(json.dumps({**row,**result},ensure_ascii=False)+'\n')
   record['batches'].append({'size':len(batch),'seconds':generated[0]['batch_seconds'],'tokens':sum(g['generated_tokens'] for g in generated),'truncated':sum(g['finish_reason']=='length' for g in generated)})
   print(json.dumps({'label':label,**record['batches'][-1]}),flush=True)
  if label=='teacher27':
   rubric=json.loads(RUBRIC_PATH.read_text())
   system=SYSTEM_PATH.read_text()+'\n\n'+json.dumps(rubric)
   judge_messages=[[{'role':'system','content':system},{'role':'user','content':json.dumps({'user_prompt':r['prompt'],'assistant_response':g['text']})}] for r,g in zip(batch[:4],generated[:4])]
   judgments=session.generate_batch(judge_messages,enable_thinking=False,max_new_tokens=2048,temperature=0)
   for judgment in judgments:
    try:
     assert judgment['finish_reason']=='stop'
     judgment['parsed']=parse_judgment(judgment['text'])
    except (ValueError,AssertionError) as exc:judgment['parse_error']=str(exc)
   (root/'judge_test.json').write_text(json.dumps(judgments,indent=2))
   record['judge_test_valid']=sum('parsed' in j for j in judgments)
  if label=='M0':
   messages=[{'role':'user','content':'This is a tool-interface engineering test using the dummy document "Hello." Call edit_constitution to replace it with "Hello, world." and a brief change summary, then call finish_editing. No actual research review is being conducted.'}]
   result=session.generate_batch([messages],tools=tool_schemas(),enable_thinking=True,max_new_tokens=2048,temperature=.6,top_p=.95,top_k=20)[0]
   (root/'tool_test.json').write_text(json.dumps(result,indent=2))
   assert result['finish_reason']=='stop' and '</think>' in result['raw_text']
   calls=parse_tool_calls(result['raw_text']);assert calls[0]['name']=='edit_constitution'
   record['tool_test_calls']=calls
  report.append(record)
  (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('VLLM_BENCHMARK_COMPLETE',flush=True)
