"""Full-parameter single-GPU OCT stages with exact, round-local references."""
from __future__ import annotations
import argparse
from collections.abc import Mapping
from numbers import Integral
import json
import math
from pathlib import Path
import random
import time
from .model import ModelSession


def read_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2) + '\n')


def normalize_token_ids(encoded):
    """Normalize HF Mapping/tensor or list results for one conversation only."""
    if isinstance(encoded, Mapping):
        encoded = encoded['input_ids']
    if hasattr(encoded, 'tolist'):
        encoded = encoded.tolist()
    if encoded and isinstance(encoded[0], (list, tuple)):
        if len(encoded) != 1:
            raise ValueError('Expected one token sequence, received multiple batches')
        encoded = encoded[0]
    if any(not isinstance(token, Integral) for token in encoded):
        raise ValueError('Expected a flat integer token sequence')
    return [int(token) for token in encoded]


def encode_completion(tokenizer, messages, response, max_length):
    """Identical token sequence for reference/policy, masking all context tokens.

    Explicit non-thinking prefix is shared with data generation. Concatenating
    tokenized prefix/continuation exactly models what autoregressive generation
    conditions on and avoids a boundary merge changing the prompt tokenization.
    """
    prefix = tokenizer.apply_chat_template(messages, tokenize=True,
        add_generation_prompt=True, enable_thinking=False, return_dict=False)
    prefix = normalize_token_ids(prefix)
    completion = normalize_token_ids(tokenizer.encode(response.rstrip(), add_special_tokens=False))
    eos = tokenizer.convert_tokens_to_ids('<|im_end|>')
    terminal_ids = {eos, getattr(tokenizer, 'eos_token_id', eos), getattr(tokenizer, 'pad_token_id', eos)}
    while completion and completion[-1] in terminal_ids:
        completion.pop()
    room = max_length - len(prefix)
    if room < 2 or not completion:
        raise ValueError('Empty completion or prompt too long for training sequence')
    truncated = len(completion) + 1 > room
    # Do not teach a fake EOS when truncating a completion.
    target = completion[:room] if truncated else completion + [eos]
    return {'input_ids': prefix + target, 'labels': [-100] * len(prefix) + target,
            'truncated': truncated}


def encode_sft(tokenizer, messages, max_length):
    """Train every assistant reply once, with its actual preceding history."""
    examples = []
    for i, message in enumerate(messages):
        if message['role'] == 'assistant':
            examples.append(encode_completion(tokenizer, messages[:i], message['content'], max_length))
    if not examples:
        raise ValueError('SFT transcript has no assistant targets')
    return examples


def sequence_logps(model, encoded, chunk_size=32):
    """Selected-token logps; checkpoint each small vocabulary projection.

    We call the official multimodal backbone text-only, then apply its exact
    lm_head in chunks. No [sequence,248320] logits tensor is materialized.
    """
    import torch
    from torch.utils.checkpoint import checkpoint
    ids = torch.tensor([encoded['input_ids']], device=model.device)
    labels = torch.tensor(encoded['labels'][1:], device=model.device)
    with torch.autocast(device_type=model.device.type, dtype=torch.bfloat16,
                        enabled=model.device.type == 'cuda'):
        hidden = model.model(input_ids=ids, attention_mask=torch.ones_like(ids),
                             use_cache=False, return_dict=True).last_hidden_state[0, :-1]
        keep = labels != -100
        hidden, labels = hidden[keep], labels[keep]
        def token_loss(h, y):
            logits = model.lm_head(h)
            return -torch.nn.functional.cross_entropy(logits.float(), y, reduction='none')
        scores = []
        for start in range(0, len(labels), chunk_size):
            h, y = hidden[start:start+chunk_size], labels[start:start+chunk_size]
            scores.append(checkpoint(token_loss, h, y, use_reentrant=False)
                          if torch.is_grad_enabled() else token_loss(h, y))
        values = torch.cat(scores)
    return values.sum(), len(labels)


def dpo_objective(chosen, rejected, ref_chosen, ref_rejected, chosen_tokens,
                  beta=0.1, nll_coef=0.1):
    import torch
    margin = (chosen - rejected) - (ref_chosen - ref_rejected)
    preference = -torch.nn.functional.logsigmoid(beta * margin)
    nll = -chosen / chosen_tokens
    return preference + nll_coef * nll, {'dpo': preference.detach(), 'nll': nll.detach(),
                                        'margin': margin.detach()}


def _optimizer(model, config):
    import torch
    params = list(model.parameters())
    if not all(p.requires_grad for p in params):
        raise ValueError('Full-parameter run contains frozen parameters')
    options = dict(lr=config.get('learning_rate', 1e-5),
                   betas=tuple(config.get('adam_betas', [0.9, 0.98])),
                   weight_decay=config.get('weight_decay', 0.0))
    kind = config.get('optimizer', 'adamw_8bit')
    if kind == 'adamw_8bit':
        from bitsandbytes.optim import AdamW8bit
        return AdamW8bit(params, **options)
    if kind == 'adamw':
        return torch.optim.AdamW(params, foreach=False, **options)
    raise ValueError(f'Unsupported full-parameter optimizer: {kind}')


def _train(checkpoint, data_path, output_dir, config, stage):
    import torch
    output = Path(output_dir)
    if (output / 'training_complete.json').exists():
        saved = json.loads((output / 'training_complete.json').read_text())
        if saved['input_checkpoint'] != str(checkpoint) or saved['stage'] != stage or saved['config'] != config:
            raise ValueError('Existing checkpoint belongs to another stage/config/input')
        return saved
    output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(config.get('seed', 20260915))
    random.seed(config.get('seed', 20260915))
    started = time.monotonic()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    with ModelSession(checkpoint, device=config.get('device', 'cuda'),
                      attention=config.get('attention', 'sdpa'),
                      parameter_dtype=config.get('parameter_dtype', 'float32')) as session:
        model, tokenizer = session.model, session.tokenizer
        model.requires_grad_(True)
        parameter_count = sum(p.numel() for p in model.parameters())
        rows = read_jsonl(data_path)
        if not rows:
            raise ValueError('No training data')
        max_len = config.get('max_length', 1024)
        chunk = config.get('logit_chunk_size', 32)
        references = []
        if stage == 'dpo':
            examples = [(encode_completion(tokenizer, [{'role':'user','content':r['prompt']}], r['chosen'], max_len),
                         encode_completion(tokenizer, [{'role':'user','content':r['prompt']}], r['rejected'], max_len))
                        for r in rows]
            # Always recompute from this round's current checkpoint before updates.
            # Store actual formatted token arrays alongside scores for inspection.
            ref_path = output / 'reference_logps.jsonl'
            with ref_path.open('w') as stream, torch.no_grad():
                for row, (chosen, rejected) in zip(rows, examples):
                    c, _ = sequence_logps(model, chosen, chunk)
                    r, _ = sequence_logps(model, rejected, chunk)
                    reference = [float(c), float(r)]
                    references.append(reference)
                    stream.write(json.dumps({'id':row.get('id'), 'reference_checkpoint':str(checkpoint),
                        'chosen_logp':reference[0], 'rejected_logp':reference[1],
                        'chosen':chosen, 'rejected':rejected}) + '\n')
                    stream.flush()
        else:
            examples = [x for r in rows for x in encode_sft(tokenizer, r['messages'], max_len)]
        # Tiny representative slices demonstrate actual direct weight changes.
        first_example = examples[0][0] if stage == 'dpo' else examples[0]
        token_id = first_example['input_ids'][0]
        probes = {}
        for name, parameter in model.named_parameters():
            selected = (name.endswith('embed_tokens.weight') or name == 'lm_head.weight'
                        or name == 'model.language_model.norm.weight'
                        or ('.layers.0.' in name and name.endswith('in_proj_qkv.weight'))
                        or ('.layers.3.' in name and name.endswith('q_proj.weight')))
            if selected:
                offset = token_id * parameter.shape[1] if name.endswith('embed_tokens.weight') else 0
                probes[name] = (offset, parameter.detach().reshape(-1)[offset:offset+64].float().cpu().clone())
        model.train()
        # Disable stochastic dropout for the reference and policy comparison.
        for module in model.modules():
            if isinstance(module, torch.nn.Dropout):
                module.p = 0.0
        model.config.use_cache = False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        optimizer = _optimizer(model, config)
        accumulation = config.get('gradient_accumulation_steps', 8)
        if accumulation < 1:
            raise ValueError('gradient_accumulation_steps must be positive')
        epochs = config.get('epochs', 1)
        total_steps = math.ceil(len(examples) / accumulation) * epochs
        warmup = max(1, math.ceil(total_steps * config.get('warmup_ratio', 0.1)))
        base_lr = config.get('learning_rate', 1e-5)
        log_path = output / 'training_log.jsonl'
        optimizer.zero_grad(set_to_none=True)
        step = 0; records = []; gradient_report = None
        with log_path.open('w') as log:
            for epoch in range(epochs):
                order = list(range(len(examples))); random.shuffle(order)
                for begin in range(0, len(order), accumulation):
                    group = order[begin:begin+accumulation]
                    lr = base_lr * min((step+1)/warmup, 1.0)
                    for param_group in optimizer.param_groups:
                        param_group['lr'] = lr
                    losses = []
                    for index in group:
                        if stage == 'dpo':
                            chosen, rejected = examples[index]
                            c, n = sequence_logps(model, chosen, chunk)
                            r, _ = sequence_logps(model, rejected, chunk)
                            loss, parts = dpo_objective(c, r, *references[index], n,
                                beta=config.get('beta', .1), nll_coef=config.get('nll_coef', .1))
                            metrics = {k:float(v) for k,v in parts.items()}
                        else:
                            score, n = sequence_logps(model, examples[index], chunk)
                            loss = -score/n; metrics = {}
                        if not torch.isfinite(loss):
                            raise FloatingPointError('Nonfinite training loss')
                        (loss/len(group)).backward()
                        losses.append(float(loss.detach()))
                    if gradient_report is None:
                        missing = [name for name,p in model.named_parameters() if p.grad is None]
                        unexpected = [name for name in missing if not name.startswith('model.visual.')]
                        if unexpected:
                            raise RuntimeError(f'Active text weights lack gradients: {unexpected[:12]}')
                        gradient_report = {'all_parameters_require_grad':all(p.requires_grad for p in model.parameters()),
                            'parameters':parameter_count, 'parameters_with_gradient':sum(p.numel() for p in model.parameters() if p.grad is not None),
                            'inactive_parameter_names':missing}
                        write_json(output/'gradient_report.json', gradient_report)
                    grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config.get('max_grad_norm',1.0))
                    if not torch.isfinite(grad_norm):
                        raise FloatingPointError('Nonfinite gradient norm')
                    optimizer.step(); optimizer.zero_grad(set_to_none=True)
                    step += 1
                    record = {'step':step,'epoch':epoch,'loss':sum(losses)/len(losses),
                              'learning_rate':lr,'grad_norm':float(grad_norm),
                              'elapsed_seconds':time.monotonic()-started,**metrics}
                    log.write(json.dumps(record)+'\n'); log.flush()
                    print(json.dumps({'stage':stage, **record}), flush=True)
                    records.append(record)
        del optimizer
        parameter_lookup = dict(model.named_parameters())
        deltas = {}
        for name, (offset, before) in probes.items():
            after = parameter_lookup[name].detach().reshape(-1)[offset:offset+64].float().cpu()
            delta = after - before
            deltas[name] = {'sampled_elements':len(before), 'flat_offset':offset,
                            'changed_elements':int((delta != 0).sum()),
                            'maximum_absolute_change':float(delta.abs().max()),
                            'mean_absolute_change':float(delta.abs().mean())}
        write_json(output/'parameter_deltas.json', deltas)
        del parameter_lookup
        model.eval(); model.config.use_cache = True
        model.save_pretrained(output, safe_serialization=True, max_shard_size='4GB')
        tokenizer.save_pretrained(output)
        stats = {'stage':stage,'input_checkpoint':str(checkpoint),'output_checkpoint':str(output),
                 'config':config,'examples':len(examples),'optimizer_steps':step,
                 'mean_loss':sum(r['loss'] for r in records)/len(records),
                 'seconds':time.monotonic()-started,'parameters':parameter_count,
                 'peak_cuda_gb':torch.cuda.max_memory_allocated()/1e9 if torch.cuda.is_available() else 0,
                 'optimizer_reset':True, 'training':'full_parameter',
                 'truncated_sequences':sum(x['truncated'] for e in examples for x in (e if stage=='dpo' else [e]))}
        write_json(output/'training_complete.json', stats)
        # Release aliases before the context manager empties CUDA caches.
        del model, tokenizer
        return stats


def train_dpo(checkpoint, preferences_path, output_dir, config):
    return _train(checkpoint, preferences_path, output_dir, config, 'dpo')


def train_sft(checkpoint, introspection_path, output_dir, config):
    return _train(checkpoint, introspection_path, output_dir, config, 'sft')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['dpo','sft'])
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    config = config.get(args.stage, config)
    print(json.dumps(_train(args.checkpoint,args.data,args.output,config,args.stage),indent=2))
