#!/usr/bin/env python3
"""Lead-owned deadline guard; credentials never enter experiment artifacts/tools.

A network-volume pod cannot be stopped. Terminate only the configured pod while
retaining its separately billed network volume. No volume deletion is supported.
"""
import argparse,json,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError


def api(config,method):
    request=Request('https://rest.runpod.io/v1/pods/'+config['pod_id'],method=method,
                    headers={'Authorization':'Bearer '+config['api_key'],
                             'User-Agent':'runpodctl/2.14.0'})
    try:
        with urlopen(request,timeout=30) as response:
            body=response.read()
            return response.status,json.loads(body) if body else None
    except HTTPError as exc:
        return exc.code,None


def verify(config):
    status,pod=api(config,'GET')
    if status==404:return False
    if status!=200:raise RuntimeError('Pod observation HTTP '+str(status))
    if pod.get('networkVolumeId')!=config['network_volume_id']:
        raise RuntimeError('Persistent network volume does not match configured guard')
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--check',action='store_true')
    args=parser.parse_args();config=json.loads(Path(args.config).read_text())
    if args.check:
        print(json.dumps({'pod_present':verify(config),'pod_id':config['pod_id'],'deadline_epoch':config['deadline_epoch']}),flush=True);return
    print(json.dumps({'guard':'armed','pod_id':config['pod_id'],'deadline_epoch':config['deadline_epoch']}),flush=True)
    last_heartbeat=0
    while True:
        now=time.time()
        if now>=config['deadline_epoch']:
            try:
                if not verify(config):return
                status,_=api(config,'DELETE')
                print(json.dumps({'time':now,'action':'terminate_budget_pod','http_status':status}),flush=True)
                if status==404:return
            except Exception as exc:
                # Do not print request objects, headers, response bodies or credentials.
                print(json.dumps({'time':now,'guard_error_type':type(exc).__name__}),flush=True)
        elif now-last_heartbeat>=300:
            print(json.dumps({'time':now,'seconds_to_deadline':config['deadline_epoch']-now}),flush=True);last_heartbeat=now
        time.sleep(30)

if __name__=='__main__':main()
