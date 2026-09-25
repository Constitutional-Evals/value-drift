"""Paid engineering validation; updates never enter the scientific trajectory."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from recursive_oct.model import ModelSession, BASE_MODEL
from recursive_oct.generation import generate_introspection
from recursive_oct.train import train_dpo, train_sft, write_json

root=Path('runs/engineering_smoke');root.mkdir(parents=True,exist_ok=True)
config=json.loads(Path('configs/training-smoke.json').read_text())
with ModelSession(BASE_MODEL) as model:
    result=model.generate_batch([[{'role':'user','content':'In one sentence, explain why acknowledging uncertainty can help someone make a decision.'}]],enable_thinking=False,max_new_tokens=128)
    write_json(root/'inference.json',result)
    print(json.dumps(result),flush=True)
pairs=[{'id':'smoke1','prompt':'A colleague made a small mistake. How can I respond constructively?',
        'chosen':'Explain the mistake respectfully, ask what happened, and work together on a practical correction.',
        'rejected':'Tell everyone that your colleague is incompetent.'},
       {'id':'smoke2','prompt':'I am unsure whether a claim is true. What should I do?',
        'chosen':'Check reliable evidence, distinguish what you know from what remains uncertain, and revise your view if new facts warrant it.',
        'rejected':'Repeat it confidently and avoid checking.'}]
with (root/'pairs.jsonl').open('w') as f:
    for row in pairs:f.write(json.dumps(row)+'\n')
print(json.dumps(train_dpo(BASE_MODEL,root/'pairs.jsonl',root/'dpo',config['dpo'])),flush=True)
intro_prompts=[{'prompt':'In two sentences, reflect on how you should respond when helpfulness and honesty seem to conflict.'}, {'prompt':'In two sentences, describe how you can respect a person while disagreeing with their claim.'}]
intro_config={**config['introspection'],'max_new_tokens':256}
print(json.dumps(generate_introspection(str(root/'dpo'),intro_prompts,root/'sft.jsonl',intro_config,constitution=Path('constitutions/C_000.md').read_text())),flush=True)
print(json.dumps(train_sft(root/'dpo',root/'sft.jsonl',root/'final',config['sft'])),flush=True)
with ModelSession(str(root/'final')) as model:
    result=model.generate_batch([[{'role':'user','content':'How should I handle being uncertain about a factual claim?'}]],enable_thinking=False,max_new_tokens=128)
    write_json(root/'post_sft_inference.json',result)
print('ENGINEERING_SMOKE_COMPLETE',flush=True)
