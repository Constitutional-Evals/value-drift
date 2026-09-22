#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recursive_oct.backend import ExperimentBackend
from recursive_oct.budget import can_afford, estimated_spend
from recursive_oct.pipeline import run_trajectory
from recursive_oct.protocol import snapshot_protocol_inputs


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',required=True)
    p.add_argument('--run',required=True)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--ledger',default='runs/spending.json')
    args=p.parse_args()
    cfg=json.loads(Path(args.config).read_text())
    if cfg.get('condition')!='full': raise ValueError('Only full-information is authorized for this pilot')
    if not cfg.get('frozen'): raise ValueError('Benchmark and freeze recipe before main trajectory')
    snapshot_protocol_inputs(args.run, cfg, resume=args.resume)
    def budget_ok():
        ledger=json.loads(Path(args.ledger).read_text())
        return can_afford(ledger,time.time(),cfg.get('stage_cost_margin_usd',2))
    result=run_trajectory(args.run,cfg,ExperimentBackend(cfg),resume=args.resume,budget_ok=budget_ok)
    print(json.dumps(result,indent=2),flush=True)
    return 1 if result['status'] in {'EDITING_FAILURE','TRAINING_FAILURE'} else 0

if __name__=='__main__': sys.exit(main())
