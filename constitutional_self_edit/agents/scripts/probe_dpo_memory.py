"""Two full-weight DPO steps at an exact cap; no checkpoint is saved.

Engineering-only repeated completion fixtures. Launch only with exclusive GPU.
"""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from recursive_oct.model import ModelSession,BASE_MODEL
from recursive_oct.train import encode_completion,sequence_logps,dpo_objective,_optimizer,read_jsonl,write_json


def main():
    import torch
    parser=argparse.ArgumentParser()
    parser.add_argument('--length',type=int,default=2048)
    parser.add_argument('--accumulation',type=int,default=1)
    parser.add_argument('--pairs',default='runs/generation_benchmark/preferences.jsonl')
    parser.add_argument('--output',default='runs/length_benchmark/dpo_2048_probe.json')
    args=parser.parse_args()
    config=json.loads(Path('configs/training.json').read_text())['dpo']
    torch.manual_seed(config['seed'])
    torch.cuda.reset_peak_memory_stats()
    start=time.monotonic();row=read_jsonl(args.pairs)[0]
    with ModelSession(BASE_MODEL,parameter_dtype='float32') as session:
        model,tokenizer=session.model,session.tokenizer
        model.requires_grad_(True)
        prompt=[{'role':'user','content':row['prompt']}]
        chosen=encode_completion(tokenizer,prompt,(row['chosen']+'\n\n')*512,args.length)
        rejected=encode_completion(tokenizer,prompt,(row['rejected']+'\n\n')*512,args.length)
        assert len(chosen['input_ids'])==len(rejected['input_ids'])==args.length
        with torch.no_grad():
            refs=[float(sequence_logps(model,x,config['logit_chunk_size'])[0]) for x in [chosen,rejected]]
        model.train();model.config.use_cache=False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        optimizer=_optimizer(model,config);records=[]
        for step in range(2):
            optimizer.zero_grad(set_to_none=True)
            for microbatch in range(args.accumulation):
                c,n=sequence_logps(model,chosen,config['logit_chunk_size'])
                r,_=sequence_logps(model,rejected,config['logit_chunk_size'])
                loss,_=dpo_objective(c,r,*refs,n,beta=config['beta'],nll_coef=config['nll_coef'])
                if not torch.isfinite(loss):raise FloatingPointError('Nonfinite probe loss')
                (loss/args.accumulation).backward()
            missing=[name for name,p in model.named_parameters() if p.grad is None and not name.startswith('model.visual.')]
            if missing:raise RuntimeError(f'Missing active gradients: {missing[:5]}')
            norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
            if not torch.isfinite(norm):raise FloatingPointError('Nonfinite probe gradient')
            optimizer.step()
            record={'step':step+1,'loss':float(loss.detach()),'grad_norm':float(norm),
                    'elapsed_seconds':time.monotonic()-start,'peak_cuda_gb':torch.cuda.max_memory_allocated()/1e9}
            print(json.dumps(record),flush=True);records.append(record)
        result={'length':args.length,'steps':records,'seconds':time.monotonic()-start,
                'peak_cuda_gb':torch.cuda.max_memory_allocated()/1e9,
                'source_checkpoint':BASE_MODEL,'full_parameter':True,
                'fixture':'Repeated generated responses for exact-cap engineering stress',
                'checkpoint_saved':False,'second_step_has_resident_optimizer_states':True,'gradient_accumulation_steps':args.accumulation}
        write_json(args.output,result)
    print('DPO_MEMORY_PROBE_COMPLETE',flush=True)


if __name__=='__main__':main()
