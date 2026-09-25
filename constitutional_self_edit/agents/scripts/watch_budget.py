#!/usr/bin/env python3
"""Lead-side independent spend guard. Never send RunPod credentials to the model.

Controls only active pod IDs explicitly recorded by the lead in this ledger.
Network-volume pods require termination; their separate volume is preserved.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from recursive_oct.budget import can_afford, estimated_spend


def stop_confirmed(result):
    if result.returncode != 0:
        return False
    try:
        pod=json.loads(result.stdout)
    except (ValueError,TypeError):
        return False
    return pod.get("desiredStatus") == "EXITED" and pod.get("runtimeStatus") in {"stopped", "exited"}


def control_call(arguments):
    try:
        return subprocess.run(arguments, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(arguments, 1, stdout='', stderr=str(exc))


def budget_action(pod):
    return 'delete' if pod.get('network_volume_id') else 'stop'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--ledger',default='runs/spending.json')
    p.add_argument('--interval',type=float,default=30)
    a=p.parse_args()
    while True:
        ledger=json.loads(Path(a.ledger).read_text())
        now=time.time()
        pods=[r for r in ledger['resources'] if r.get('kind')=='pod' and not r.get('ended_epoch')]
        if not pods:
            return
        if not can_afford(ledger,now,1):
            confirmed=[]
            for pod in pods:
                action=budget_action(pod)
                result=control_call(['runpodctl','pod',action,pod['id']])
                print(json.dumps({'time':now,'pod':pod['id'],'action':'budget_stop','estimated_usd':estimated_spend(ledger,now),'returncode':result.returncode,'output':result.stdout,'error':result.stderr}),flush=True)
                if action=='delete':
                    confirmed.append(result.returncode == 0)
                else:
                    observation=control_call(['runpodctl','pod','get',pod['id']])
                    confirmed.append(stop_confirmed(observation))
            # Transient read/stop failures are not terminal. Retry on next pass.
            if all(confirmed):
                return
        time.sleep(a.interval)

if __name__=='__main__':
    main()
