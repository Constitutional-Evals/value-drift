"""Engineering-only full-weight memory stress at proposed sequence limits."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from recursive_oct.model import BASE_MODEL
from recursive_oct.train import read_jsonl,train_dpo,train_sft,write_json
from recursive_oct.generation import generate_introspection

root=Path('runs/length_benchmark');root.mkdir(parents=True,exist_ok=True)
config=json.loads(Path('configs/training.json').read_text())
pairs=read_jsonl('runs/generation_benchmark/preferences.jsonl')[:2]
if len(pairs)<2:raise ValueError('Need two usable real generated preferences')
# Repetition is solely a memory/throughput fixture; these updated weights never
# enter the recursive trajectory. Long targets exercise the exact sequence cap.
fixtures=[]
for row in pairs:
    fixtures.append({**row,'chosen':(row['chosen']+'\n\n')*24,
                     'rejected':(row['rejected']+'\n\n')*24,'engineering_expansion':True})
def save_rows(path,rows):
    path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
save_rows(root/'dpo_stress.jsonl',fixtures)
write_json(root/'benchmark_protocol.json',{'purpose':'Engineering only; repeated responses test exact caps',
    'base_checkpoint':BASE_MODEL,'dpo_length':1536,'sft_length':3072,'dpo_pairs':len(fixtures),
    'scientific_trajectory':False})
started=time.monotonic()
dpo_config={**config['dpo'],'max_length':1536,'gradient_accumulation_steps':2,'allow_target_truncation':True}
dpo=train_dpo(BASE_MODEL,root/'dpo_stress.jsonl',root/'dpo',dpo_config)
print(json.dumps({'completed':'dpo_length_stress',**dpo}),flush=True)
if time.monotonic()-started>300:
    write_json(root/'summary.json',{'dpo':dpo,'stopped_after':'dpo','time_limit':True})
    raise SystemExit(0)
intro_config={**config['introspection'],'reflection_count':1,'interaction_count':1,
              'interaction_turns':4,'batch_size':1}
intro=generate_introspection(str(root/'dpo'),[{'prompt':'In three sentences, reflect on how your judgment should handle a conflict between honesty and kindness.'}],
       root/'introspection.jsonl',intro_config,constitution=Path('constitutions/C_000.md').read_text())
if time.monotonic()-started>300:
    write_json(root/'summary.json',{'dpo':dpo,'introspection':intro,'stopped_after':'introspection','time_limit':True})
    raise SystemExit(0)
rows=read_jsonl(root/'introspection.jsonl')
response=next(m['content'] for row in rows for m in row['messages'] if m['role']=='assistant')
rows.append({'id':'sft-length-stress','kind':'engineering_expansion','messages':[
    {'role':'user','content':'Reflect on your judgment.'},
    {'role':'assistant','content':(response+'\n\n')*100}]})
save_rows(root/'sft_stress.jsonl',rows)
sft_config={**config['sft'],'max_length':3072,'gradient_accumulation_steps':2,'allow_target_truncation':True}
sft=train_sft(root/'dpo',root/'sft_stress.jsonl',root/'final',sft_config)
write_json(root/'summary.json',{'dpo':dpo,'introspection':intro,'sft':sft,'seconds':time.monotonic()-started})
print('LENGTH_BENCHMARK_COMPLETE',flush=True)
