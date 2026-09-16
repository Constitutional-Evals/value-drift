#!/usr/bin/env python3
"""Lead-only SSH sync. Never copy credentials, account-control files, or caches."""
import argparse
import json
from pathlib import Path
import subprocess

def main():
    p=argparse.ArgumentParser()
    p.add_argument('direction',choices=['push','pull'])
    p.add_argument('--checkpoints',action='store_true')
    p.add_argument('--connection',default='runs/connection.json')
    a=p.parse_args(); c=json.loads(Path(a.connection).read_text())
    transport=f"ssh -i {c['key_path']} -p {c['port']}"
    remote=f"root@{c['host']}:/workspace/value-drift/"
    args=['rsync','-rz','-e',transport]
    for pattern in ['.git','.env','.env.*','.venv','OpenCharacterTraining','__pycache__','.pytest_cache']:
        args+=['--exclude',pattern]
    if a.direction=='push':
        args+=['--exclude','runs', './',remote]
    else:
        for pattern in ['spending.json','connection.json','budget-watchdog*']:
            args+=['--exclude',pattern]
        if not a.checkpoints:
            args+=['--exclude','*.safetensors','--exclude','*.bin','--exclude','*.pt']
        args+=[remote+'runs/','./runs/']
    subprocess.run(args,check=True)
if __name__=='__main__':main()
