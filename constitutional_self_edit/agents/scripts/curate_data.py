#!/usr/bin/env python3
"""Freeze user-only prompts from public HF datasets. No model or paid API calls."""
from __future__ import annotations
import argparse
from collections import Counter
from difflib import SequenceMatcher
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import random
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import requests
from langid.langid import LanguageIdentifier, model
from recursive_oct.data import exclusion_reason, extract_helpsteer_user, extract_hh_user, extract_wildchat_user, normalized_prompt, value_tags, write_jsonl

SEED=20260915
SOURCES={'nvidia/HelpSteer2':{'license':'CC-BY-4.0','file':'train.jsonl.gz'},'Anthropic/hh-rlhf':{'license':'MIT','file':'helpful-base/train.jsonl.gz'},'allenai/WildChat-1M':{'license':'ODC-By','file':'data/train-00000-of-00014.parquet'}}

def get(url,**kwargs):
    for attempt in range(4):
        try:
            response=requests.get(url,timeout=90,**kwargs); response.raise_for_status(); return response
        except requests.RequestException:
            if attempt==3: raise
            time.sleep(1+attempt)

def source_rows(repo,info):
    if repo!='allenai/WildChat-1M':
        blob=get(f"https://huggingface.co/datasets/{repo}/resolve/{info['revision']}/{info['file']}").content
        for i,line in enumerate(gzip.GzipFile(fileobj=io.BytesIO(blob))):
            row=json.loads(line)
            prompt=extract_helpsteer_user(row) if repo=='nvidia/HelpSteer2' else extract_hh_user(row)
            # Original responses and scores are discarded immediately, never saved or used as targets.
            if prompt: yield i,prompt,None
        return
    import pyarrow as pa
    import pyarrow.parquet as pq
    blob=get(f"https://huggingface.co/datasets/{repo}/resolve/{info['revision']}/{info['file']}").content
    parquet=pq.ParquetFile(pa.BufferReader(blob))
    # Fixed frame: first 6000 rows in first revision-pinned original shard.
    batch=next(parquet.iter_batches(batch_size=6000,columns=['conversation','conversation_hash']))
    for i,row in enumerate(batch.to_pylist()):
        if not (row.get('conversation') or [{}])[0].get('redacted',False):
            yield i,extract_wildchat_user(row),row['conversation_hash']

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,default=Path('data')); p.add_argument('--replace-before-trajectory',action='store_true'); args=p.parse_args()
    if (args.output/'manifest.json').exists() and not args.replace_before_trajectory:
        raise SystemExit('Prompt bank already frozen. Reuse it; replacement is only allowed before a trajectory.')
    identifier=LanguageIdentifier.from_modelstring(model,norm_probs=True)
    # Constrain BLAS threads outside this process for predictable inexpensive language filtering.
    rejected=Counter(); seen=set(); near_buckets={}; pools={'general':[],'naturalistic':[],'value_relevant':[]}; inspected={}
    for repo,info in SOURCES.items():
        metadata=get('https://huggingface.co/api/datasets/'+repo).json()
        info.update(revision=metadata['sha'],gated=metadata.get('gated'),card_url='https://huggingface.co/datasets/'+repo)
        extracted=list(source_rows(repo,info)); inspected[repo]=len(extracted)
        random.Random(SEED).shuffle(extracted)
        print(f'{repo}: {len(extracted)} first-user inputs fetched',flush=True)
        accepted=0
        for row,prompt,conversation_hash in extracted:
            reason=exclusion_reason(prompt)
            if reason: rejected[reason]+=1; continue
            key=normalized_prompt(prompt)
            if key in seen: rejected['duplicate']+=1; continue
            words=key.split(); bucket=tuple(words[:4])
            if any(abs(len(words)-len(other))/max(len(words),len(other))<.12 and SequenceMatcher(None,words,other,autojunk=False).ratio()>.92 for other in near_buckets.get(bucket,[])):
                rejected['near_duplicate']+=1; continue
            tags=value_tags(prompt)
            if repo=='Anthropic/hh-rlhf' and not tags:
                rejected['hh_no_value_keyword']+=1; continue
            category='naturalistic' if repo=='allenai/WildChat-1M' else ('value_relevant' if tags else 'general')
            # A bounded candidate pool avoids unnecessary processing and fixes a modest curation frame.
            target={'general':1500,'naturalistic':1000,'value_relevant':1800}[category]
            if len(pools[category])>=target: continue
            language,probability=identifier.classify(prompt)
            if language!='en' or probability<.8: rejected['language']+=1; continue
            seen.add(key); near_buckets.setdefault(bucket,[]).append(words); accepted+=1
            pools[category].append({'id':repo.replace('/','--')+f'--train--{row:06d}--u0','prompt':prompt.strip(),'category':category,'source':{'dataset':repo,'revision':info['revision'],'split':'train','row':row,'turn':0,'file':info['file'],'conversation_hash':conversation_hash,'access':'revision-pinned first parquet shard' if repo=='allenai/WildChat-1M' else 'revision-pinned gzip JSONL'},'value_tags':tags})
        print(f'{repo}: {accepted} eligible unique candidates retained',flush=True)
    rng=random.Random(SEED); train=[]; evaluation=[]
    targets={'general':(600,40),'naturalistic':(450,30),'value_relevant':(450,50)}
    for category,(ntrain,neval) in targets.items():
        candidates=pools[category]; rng.shuffle(candidates)
        if len(candidates)<ntrain+neval: raise RuntimeError(f'Insufficient {category}: {len(candidates)}')
        # Ensure exploratory evaluation covers each retrieval theme without changing prompts.
        heldout=[]
        if category=='value_relevant':
            tag_frequency=Counter(t for r in candidates for t in r['value_tags'])
            for tag in sorted(tag_frequency,key=lambda t:(tag_frequency[t],t)):
                for row in candidates:
                    if sum(tag in r['value_tags'] for r in heldout)>=3: break
                    if tag in row['value_tags'] and row not in heldout: heldout.append(row)
        for row in candidates:
            if len(heldout)>=neval: break
            if row not in heldout: heldout.append(row)
        remaining=[r for r in candidates if r not in heldout]
        evaluation.extend(heldout); train.extend(remaining[:ntrain])
    rng.shuffle(train); rng.shuffle(evaluation)
    combined=train+evaluation
    assert len({r['id'] for r in combined})==len(combined), 'Duplicate source IDs'
    assert len({normalized_prompt(r['prompt']) for r in combined})==len(combined), 'Duplicate prompts'
    assert all(exclusion_reason(r['prompt']) is None for r in combined)
    write_jsonl(args.output/'train.jsonl',train); write_jsonl(args.output/'eval.jsonl',evaluation)
    manifest={'version':1,'frozen':True,'created_at':datetime.now(timezone.utc).isoformat(),'seed':SEED,'sources':SOURCES,'excluded_source':{'GAIR/lima':'Gated access with contact sharing and CC-BY-NC-SA or stricter source terms; accessible alternatives used.'},'source_first_user_rows_inspected':inspected,'candidate_counts':{k:len(v) for k,v in pools.items()},'rejection_counts':dict(rejected),'splits':{},'protocol':'Only first user turn; assistant responses, ratings, chosen/rejected labels, personal metadata and moderation fields never become output examples. Normalized exact dedup and same-first-four-word token SequenceMatcher ratio >0.92 near-dedup precede split. English langid >= 0.8; conservative regex quality/privacy filters; fixed 7-320 whitespace words and <=2400 chars. Training prompts and held-out prompts are fixed before model review. WildChat rows use the first 6000 rows of its first original revision-pinned parquet shard, with shard-row indices and conversation hashes.'}
    for name,rows in [('train',train),('eval',evaluation)]:
        manifest['splits'][name]={'count':len(rows),'categories':dict(Counter(r['category'] for r in rows)),'sources':dict(Counter(r['source']['dataset'] for r in rows)),'value_tags':dict(Counter(t for r in rows for t in r['value_tags']))}
    args.output.mkdir(exist_ok=True,parents=True); (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest['splits'],indent=2),flush=True)
if __name__=='__main__': main()
