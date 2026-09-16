"""Continue engineering smoke from valid DPO, preserving completed generations."""
import json
from pathlib import Path
import sys
import shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recursive_oct.generation import generate_introspection
from recursive_oct.model import ModelSession
from recursive_oct.train import train_sft, write_json
root=Path('runs/engineering_smoke')
assert (root/'dpo'/'training_complete.json').exists()
config=json.loads(Path('configs/training-smoke.json').read_text())
path=root/'sft_attempt003.jsonl'
if not path.exists():
    shutil.copyfile(root/'sft.jsonl',path)
    shutil.copyfile(root/'sft.jsonl.reflections.jsonl',str(path)+'.reflections.jsonl')
    # Retain completed turn0; preserve the truncated turn in the original file.
    turns=[json.loads(l) for l in (root/'sft.jsonl.interaction_turns.jsonl').read_text().splitlines()]
    with Path(str(path)+'.interaction_turns.jsonl').open('w') as f:
        for row in turns:
            if row['finish_reason']=='stop':f.write(json.dumps(row)+'\n')
intro_prompts=[{'prompt':'In two sentences, reflect on how you should respond when helpfulness and honesty seem to conflict.'}, {'prompt':'In two sentences, describe how you can respect a person while disagreeing with their claim.'}]
intro_config={**config['introspection'],'max_new_tokens':768}
write_json(root/'attempt003.json',{'reason':'Engineering interaction turn2 truncated at256; expand only engineering allowance to768, retain completed DPO/reflections/turn0','introspection':intro_config,'sft':config['sft']})
print(json.dumps(generate_introspection(str(root/'dpo'),intro_prompts,path,intro_config,constitution=Path('constitutions/C_000.md').read_text())),flush=True)
print(json.dumps(train_sft(root/'dpo',path,root/'final',config['sft'])),flush=True)
with ModelSession(str(root/'final')) as model:
    result=model.generate_batch([[{'role':'user','content':'How should I handle being uncertain about a factual claim?'}]],enable_thinking=False,max_new_tokens=128)
    write_json(root/'post_sft_inference.json',result)
print('ENGINEERING_SMOKE_COMPLETE',flush=True)
