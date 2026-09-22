"""Resolve and cache the optional stronger fixed teacher before protocol freeze."""
import json
from pathlib import Path
from huggingface_hub import HfApi,snapshot_download
repo='Qwen/Qwen3.5-27B'
info=HfApi().model_info(repo)
out=Path('runs/teacher_candidate.json')
record={'repo_id':repo,'revision':info.sha,'status':'downloading'}
out.write_text(json.dumps(record,indent=2))
path=snapshot_download(repo,revision=info.sha,allow_patterns=['*.json','*.safetensors','*.jinja','tokenizer*','vocab*','merges*'])
record.update(path=path,status='downloaded')
out.write_text(json.dumps(record,indent=2))
print(json.dumps(record),flush=True)
