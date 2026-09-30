"""Publish each trained LoRA adapter to the project's Hugging Face model repo, and free disk from spent checkpoints.

One repo holds every chain's adapters as <model>/<constitution>/round_NNN/<stage>/, for example
qwen3.8-27b/broad/round_001/dpo. A run names the repo (adapter_repo) and its chain folder
(adapter_folder, "<model>/<constitution>"). The chain folder also holds the starting constitution
(C_000.md), and each round folder the constitution that round trained on (C_001.md in round_001, ...).
Rebuilding the model after any stage is the base checkpoint plus every adapter of the chain up to it,
merged in order (agents/scripts/rebuild_checkpoint.py). Preference data is never uploaded: it contains
LIMA prompts.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


def hub_base(path):
    """(repo id, revision) for a local Hugging Face cache snapshot; other paths come back unchanged.
    The Hub rejects a model card whose base_model is a local path, which PEFT writes by default."""
    m = re.search(r'models--([^/]+)--([^/]+)/snapshots/([0-9a-f]{40})', str(path))
    return (f'{m.group(1)}/{m.group(2)}', m.group(3)) if m else (str(path), None)


def adapter_card(base_id, revision, path_in_repo):
    pinned = f' at revision `{revision}`' if revision else ''
    chain = path_in_repo.rsplit('/', 2)[0] + '/' if path_in_repo.count('/') >= 2 else ''
    return f"""---
base_model: {base_id}
library_name: peft
tags:
- lora
---

# {path_in_repo}

A LoRA adapter from one stage of a recursive Open Character Training loop on `{base_id}`{pinned}.
The model after this stage is the base model with every earlier adapter of the chain (`{chain}`) merged
in order (round_001/dpo, round_001/sft, round_002/dpo, ...), then this one. `training_complete.json`
records the training settings and statistics.
"""


def repo_readme(repo_id):
    return f"""---
library_name: peft
tags:
- lora
---

# {repo_id}

LoRA adapters from recursive constitutional self-editing with Open Character Training: each round, the
model reviews and edits its constitution, then is trained on it with DPO and then introspective SFT.

Layout: `<model>/<constitution>/round_NNN/<stage>/`, where the constitution is the chain's starting
constitution and the stage is `dpo` or `sft`. Each stage folder holds the adapter
(`adapter_model.safetensors`, `adapter_config.json`), `training_complete.json` with the training
settings and statistics, and a card naming the base model. The chain folder holds the starting
constitution (`C_000.md`), and each round folder the constitution that round trained on.

The model after a stage is the base model with the chain's adapters merged in order up to that stage
(round_001/dpo, round_001/sft, round_002/dpo, ...); each adapter was trained on the model merged up to the
stage before it.
"""


def upload_adapter(repo_id, adapter_dir, path_in_repo, extra_files=(), private=False, base=None):
    """One commit per stage: the adapter weights, its config and card with the base model named by its Hub id,
    and the extra files (local paths, into the stage folder, or {path in repo: local path}). base, (Hub id,
    revision), names the chain's base model: a later stage was trained on a merged local checkpoint, which
    PEFT records as its base."""
    from huggingface_hub import CommitOperationAdd, HfApi
    api = HfApi(token=os.environ.get('HF_TOKEN'))
    api.create_repo(repo_id, repo_type='model', private=private, exist_ok=True)
    adapter_dir = Path(adapter_dir)
    config = json.loads((adapter_dir / 'adapter_config.json').read_text())
    base_id, revision = base or hub_base(config.get('base_model_name_or_path', ''))
    config['base_model_name_or_path'] = base_id
    if revision:
        config['revision'] = revision
    ops = [CommitOperationAdd(f'{path_in_repo}/{f.name}', str(f)) for f in sorted(adapter_dir.iterdir())
           if f.is_file() and f.name not in ('README.md', 'adapter_config.json')]
    ops += [CommitOperationAdd(f'{path_in_repo}/adapter_config.json', (json.dumps(config, indent=2) + '\n').encode()),
            CommitOperationAdd(f'{path_in_repo}/README.md', adapter_card(base_id, revision, path_in_repo).encode())]
    if not isinstance(extra_files, dict):
        extra_files = {f'{path_in_repo}/{Path(e).name}': e for e in extra_files}
    ops += [CommitOperationAdd(target, str(local)) for target, local in extra_files.items() if Path(local).exists()]
    if not api.file_exists(repo_id, 'README.md'):
        ops.append(CommitOperationAdd('README.md', repo_readme(repo_id).encode()))
    api.create_commit(repo_id, operations=ops, commit_message=f'Add {path_in_repo} adapter')


def stage_files(config, stage_dir):
    """Where a stage goes in the repo, and the files uploaded with it: training_complete.json in the stage
    folder; with the SFT stage (the round's last), the constitution the round trained on in the round
    folder, and in round 1 also the chain's starting constitution."""
    stage_dir = Path(stage_dir)
    round_dir, run_root = stage_dir.parent, stage_dir.parent.parent
    chain = config.get('adapter_folder', '').strip('/')
    round_path = '/'.join(p for p in (chain, round_dir.name) if p)
    path_in_repo = f'{round_path}/{"sft" if stage_dir.name == "final" else stage_dir.name}'
    files = {f'{path_in_repo}/training_complete.json': stage_dir / 'training_complete.json'}
    if stage_dir.name == 'final':
        number = int(round_dir.name.split('_')[-1])
        files[f'{round_path}/C_{number:03d}.md'] = run_root / f'C_{number:03d}.md'
        if number == 1:
            files['/'.join(p for p in (chain, 'C_000.md') if p)] = run_root / 'C_000.md'
    return path_in_repo, files


def publish_stage(config, stats, stage_dir):
    """Upload a finished stage's adapter once; a failed upload is recorded, not fatal, and retried on resume."""
    repo = config.get('adapter_repo')
    stage_dir = Path(stage_dir)
    marker = stage_dir / 'published.json'
    if not repo or not stats.get('adapter_path') or marker.exists():
        return
    path_in_repo, files = stage_files(config, stage_dir)
    try:
        base = (config['official_model'], config.get('model_revision')) if config.get('official_model') else None
        upload_adapter(repo, stats['adapter_path'], path_in_repo, files, private=config.get('adapter_repo_private', False),
                       base=base)
        marker.write_text(json.dumps({'repo': repo, 'path_in_repo': path_in_repo}, indent=2) + '\n')
        (stage_dir / 'publish_failed.json').unlink(missing_ok=True)
    except Exception as exc:  # the run continues; the adapter stays on disk
        (stage_dir / 'publish_failed.json').write_text(json.dumps({'repo': repo, 'error': repr(exc)[:2000]}, indent=2) + '\n')


def retry_failed_uploads(config, run_root):
    """Retry every stage whose upload failed earlier; the loop never revisits a finished stage."""
    for failed in sorted(Path(run_root).glob('round_*/*/publish_failed.json')):
        stats = json.loads((failed.parent / 'training_complete.json').read_text())
        publish_stage(config, stats, failed.parent)


def delete_merged_weights(checkpoint_dir, keep=()):
    """Delete a merged checkpoint's weight shards (not its adapter or logs) once no later step needs it."""
    checkpoint_dir = Path(checkpoint_dir)
    if not checkpoint_dir.is_dir() or str(checkpoint_dir) in {str(k) for k in keep}:
        return []
    removed = sorted(checkpoint_dir.glob('model*.safetensors'))
    for shard in removed:
        shard.unlink()
    if removed:
        (checkpoint_dir / 'weights_deleted.json').write_text(json.dumps(
            {'files': [p.name for p in removed], 'rebuild': 'base checkpoint plus the adapters up to this stage'},
            indent=2) + '\n')
    return removed
