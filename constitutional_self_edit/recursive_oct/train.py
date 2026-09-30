"""Single-GPU OCT stages (full-parameter or LoRA) with exact, round-local references.

LoRA follows Open Character Training (OpenRLHF): rank 64, alpha 128, no dropout, every linear layer of
the language model, AdamW, cosine schedule to 10% of the peak learning rate after warmup. Each stage
trains a fresh adapter on its input checkpoint, saves it, and merges it into the weights, so the
output checkpoint is exactly the input plus this adapter.
"""
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


def encode_sft(tokenizer, messages, max_length, last_only=False):
    """Train every assistant reply once, with its actual preceding history (or only the last one)."""
    examples = []
    for i, message in enumerate(messages):
        if message['role'] == 'assistant' and (not last_only or i == len(messages) - 1):
            examples.append(encode_completion(tokenizer, messages[:i], message['content'], max_length))
    if not examples:
        raise ValueError('SFT transcript has no assistant targets')
    return examples


def training_length(config):
    """The longest training sequence allowed. "max_length": null sets no limit, so nothing is cut or
    dropped for length and every example is trained whole; memory is then the only limit."""
    value = config.get('max_length', 1024)
    return 10**9 if value is None else value


def audit_training_lengths(examples, config, output):
    report = {'sequences': len(examples),
              'maximum_length': max(len(x['input_ids']) for x in examples),
              'truncated_sequences': sum(x['truncated'] for x in examples),
              'allow_target_truncation': config.get('allow_target_truncation', False)}
    write_json(Path(output) / 'sequence_lengths.json', report)
    if report['truncated_sequences'] and not report['allow_target_truncation']:
        raise ValueError('Training targets would be truncated; see sequence_lengths.json')
    return report


def sequence_logps(model, encoded, chunk_size=32, per_token=False):
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
    if per_token:
        return values.sum(), len(labels), values
    return values.sum(), len(labels)


def batch_sequence_logps(model, batch, chunk_size=32, per_token=False, pad_id=0):
    """sequence_logps for several sequences in one forward pass, right-padded to the longest.

    Every layer is causal (attention with a causal mask, the linear-attention recurrences and their causal
    convolutions), so padding placed after a sequence cannot change its tokens' results; the padding only
    has to stay out of the loss, and it has no labels. One sequence goes through sequence_logps unchanged.
    """
    import torch
    from torch.utils.checkpoint import checkpoint
    if len(batch) == 1:
        return [sequence_logps(model, batch[0], chunk_size, per_token)]
    width = max(len(x['input_ids']) for x in batch)
    ids = torch.full((len(batch), width), pad_id, dtype=torch.long, device=model.device)
    mask = torch.zeros_like(ids)
    for row, x in enumerate(batch):
        ids[row, :len(x['input_ids'])] = torch.tensor(x['input_ids'], device=model.device)
        mask[row, :len(x['input_ids'])] = 1
    with torch.autocast(device_type=model.device.type, dtype=torch.bfloat16,
                        enabled=model.device.type == 'cuda'):
        hidden_all = model.model(input_ids=ids, attention_mask=mask, use_cache=False,
                                 return_dict=True).last_hidden_state
        def token_loss(h, y):
            logits = model.lm_head(h)
            return -torch.nn.functional.cross_entropy(logits.float(), y, reduction='none')
        results = []
        for row, x in enumerate(batch):
            length = len(x['input_ids'])
            labels = torch.tensor(x['labels'][1:], device=model.device)
            hidden = hidden_all[row, :length - 1]
            keep = labels != -100
            hidden, labels = hidden[keep], labels[keep]
            scores = []
            for start in range(0, len(labels), chunk_size):
                h, y = hidden[start:start+chunk_size], labels[start:start+chunk_size]
                scores.append(checkpoint(token_loss, h, y, use_reentrant=False)
                              if torch.is_grad_enabled() else token_loss(h, y))
            values = torch.cat(scores)
            results.append((values.sum(), len(labels), values) if per_token else (values.sum(), len(labels)))
    return results


def plan_micro_batches(indices, lengths, sequences, max_examples=1, max_tokens=None):
    """Split one step's examples into micro-batches that go through the GPU together.

    Examples are sorted by length (longest first) so each micro-batch pads little, and one is closed when
    adding the next example would exceed max_examples or max_tokens padded tokens (the longest sequence in
    the micro-batch times its number of sequences; a DPO pair is two sequences). An example over the token
    budget on its own still runs, alone. With max_examples 1 every example runs alone, in the given order.
    """
    if max_examples <= 1:
        return [[i] for i in indices]
    batches, current = [], []
    for i in sorted(indices, key=lambda i: -lengths[i]):
        candidate = current + [i]
        padded = max(lengths[j] for j in candidate) * sum(sequences[j] for j in candidate)
        if current and (len(candidate) > max_examples or (max_tokens is not None and padded > max_tokens)):
            batches.append(current)
            current = [i]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def length_grouped_steps(order, lengths, accumulation, group_steps=50):
    """Hugging Face's group_by_length for optimizer steps: within each block of group_steps steps of the
    shuffled order, examples are sorted by length and cut into steps, so a step holds similar lengths; the
    steps are then shuffled so their order carries no length trend. Same number of steps as without."""
    block = accumulation * group_steps
    steps = []
    for begin in range(0, len(order), block):
        chunk = sorted(order[begin:begin+block], key=lambda i: lengths[i])
        steps += [chunk[k:k+accumulation] for k in range(0, len(chunk), accumulation)]
    random.shuffle(steps)
    return steps


def is_out_of_memory(exc):
    import torch
    # flash-linear-attention's Triton kernels report running out of memory as a RuntimeError.
    return isinstance(exc, torch.cuda.OutOfMemoryError) or (isinstance(exc, RuntimeError) and 'out of memory' in str(exc))


def dpo_objective(chosen, rejected, ref_chosen, ref_rejected, chosen_tokens,
                  beta=0.1, nll_coef=0.1):
    import torch
    margin = (chosen - rejected) - (ref_chosen - ref_rejected)
    preference = -torch.nn.functional.logsigmoid(beta * margin)
    nll = -chosen / chosen_tokens
    return preference + nll_coef * nll, {'dpo': preference.detach(), 'nll': nll.detach(),
                                        'margin': margin.detach()}


def lora_target_modules(model):
    """Every linear layer of the language model: OpenRLHF's "all-linear", without the output head and
    without the vision tower, which text never reaches."""
    import torch
    return sorted(name for name, module in model.named_modules()
                  if isinstance(module, torch.nn.Linear) and '.language_model.' in f'.{name}.')


def attach_lora(model, config):
    """Freeze the model and inject a fresh LoRA adapter into it in place; returns the PEFT wrapper."""
    from peft import LoraConfig, get_peft_model
    model.requires_grad_(False)
    lora_config = LoraConfig(r=config.get('lora_rank', 64), lora_alpha=config.get('lora_alpha', 128),
                             lora_dropout=config.get('lora_dropout', 0.0), bias='none',
                             target_modules=lora_target_modules(model))
    return get_peft_model(model, lora_config)


def squared_kl(policy_tokens, reference_tokens):
    """OCT's KL penalty for one sequence: mean over answer tokens of the squared log-probability gap."""
    return ((policy_tokens - reference_tokens.to(policy_tokens.device)) ** 2).mean()


def _optimizer(model, config):
    import torch
    if config.get('method') == 'lora':
        params = [p for p in model.parameters() if p.requires_grad]
        if not params:
            raise ValueError('LoRA run has no trainable parameters')
        return torch.optim.AdamW(params, lr=config.get('learning_rate', 5e-5),
                                 betas=tuple(config.get('adam_betas', [0.9, 0.98])),
                                 weight_decay=config.get('weight_decay', 0.0))
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
        lora = config.get('method', 'full') == 'lora'
        if config.get('method', 'full') not in ('full', 'lora'):
            raise ValueError('method must be "full" or "lora"')
        kl_coef = config.get('kl_coef', 0.0)
        model.requires_grad_(not lora)
        parameter_count = sum(p.numel() for p in model.parameters())
        rows = read_jsonl(data_path)
        if not rows:
            raise ValueError('No training data')
        max_len = training_length(config)
        chunk = config.get('logit_chunk_size', 32)
        micro_size = config.get('micro_batch_size', 1)
        pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.convert_tokens_to_ids('<|im_end|>')
        references = []; token_references = []
        if stage == 'dpo':
            examples = [(encode_completion(tokenizer, [{'role':'user','content':r['prompt']}], r['chosen'], max_len),
                         encode_completion(tokenizer, [{'role':'user','content':r['prompt']}], r['rejected'], max_len))
                        for r in rows]
            audit_training_lengths([x for pair in examples for x in pair], config, output)
            # Always recompute from this round's current checkpoint before updates.
            # Store actual formatted token arrays alongside scores for inspection.
            ref_path = output / 'reference_logps.jsonl'
            # Scored in length-sorted micro-batches (reference_batch_tokens padded tokens; one pair at a time
            # when unset), then written in the data's order.
            pair_lengths = [max(len(c['input_ids']), len(r['input_ids'])) for c, r in examples]
            reference_plan = plan_micro_batches(list(range(len(examples))), pair_lengths, [2] * len(examples),
                                                max_examples=10**9 if config.get('reference_batch_tokens') else 1,
                                                max_tokens=config.get('reference_batch_tokens'))
            scored = {}
            with torch.no_grad():
                for batch in reference_plan:
                    sequences_ = [x for i in batch for x in examples[i]]
                    outs = (batch_sequence_logps(model, sequences_, chunk, per_token=True, pad_id=pad_id)
                            if config.get('reference_batch_tokens') else
                            [sequence_logps(model, x, chunk, per_token=True) for x in sequences_])
                    for k, i in enumerate(batch):
                        (c, _, c_tokens), (r, _, r_tokens) = outs[2*k], outs[2*k+1]
                        scored[i] = ([float(c), float(r)], (c_tokens.float().cpu(), r_tokens.float().cpu()))
            with ref_path.open('w') as stream:
                for i, (row, (chosen, rejected)) in enumerate(zip(rows, examples)):
                    reference, tokens = scored[i]
                    references.append(reference)
                    if kl_coef:
                        token_references.append(tokens)
                    stream.write(json.dumps({'id':row.get('id'), 'reference_checkpoint':str(checkpoint),
                        'chosen_logp':reference[0], 'rejected_logp':reference[1],
                        'chosen':chosen, 'rejected':rejected}) + '\n')
            del scored
        else:
            examples = [x for r in rows
                        for x in encode_sft(tokenizer, r['messages'], max_len, last_only=r.get('train_on') == 'last')]
            audit_training_lengths(examples, config, output)
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
        peft_model = None
        if lora:
            # References are scored above, before the adapter exists: the reference is this stage's input.
            peft_model = attach_lora(model, config)
        trainable_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
        model.train()
        # Disable stochastic dropout for the reference and policy comparison.
        for module in model.modules():
            if isinstance(module, torch.nn.Dropout):
                module.p = 0.0
        model.config.use_cache = False
        optimizer = _optimizer(model, config)

        def batch_loss(indices):
            """Summed loss of several examples from one forward pass, with each example's loss and metrics."""
            if micro_size <= 1:
                # Unbatched: exactly the original path (a DPO pair's two answers in separate passes).
                (index,) = indices
                loss, metrics = example_loss(index)
                return loss, [loss.detach()], metrics
            if stage == 'dpo':
                outs = batch_sequence_logps(model, [x for i in indices for x in examples[i]], chunk,
                                            per_token=True, pad_id=pad_id)
                total, losses, parts = 0, [], {}
                for k, index in enumerate(indices):
                    (c, n, c_tokens), (r, _, r_tokens) = outs[2*k], outs[2*k+1]
                    loss, parts = dpo_objective(c, r, *references[index], n,
                        beta=config.get('beta', .1), nll_coef=config.get('nll_coef', .1))
                    if kl_coef:
                        kl = 0.5 * (squared_kl(c_tokens, token_references[index][0])
                                    + squared_kl(r_tokens, token_references[index][1]))
                        loss = loss + kl_coef * kl
                        parts['squared_kl'] = kl.detach()
                    total = total + loss
                    losses.append(loss.detach())
                return total, losses, {k:float(v) for k,v in parts.items()}
            outs = batch_sequence_logps(model, [examples[i] for i in indices], chunk, pad_id=pad_id)
            per_example = [-score/n for score, n in outs]
            return sum(per_example), [x.detach() for x in per_example], {}

        def example_loss(index):
            if stage == 'dpo':
                chosen, rejected = examples[index]
                c, n, c_tokens = sequence_logps(model, chosen, chunk, per_token=True)
                r, _, r_tokens = sequence_logps(model, rejected, chunk, per_token=True)
                loss, parts = dpo_objective(c, r, *references[index], n,
                    beta=config.get('beta', .1), nll_coef=config.get('nll_coef', .1))
                if kl_coef:
                    # OCT averages the squared gap over the chosen and rejected answers.
                    kl = 0.5 * (squared_kl(c_tokens, token_references[index][0])
                                + squared_kl(r_tokens, token_references[index][1]))
                    loss = loss + kl_coef * kl
                    parts['squared_kl'] = kl.detach()
                return loss, {k:float(v) for k,v in parts.items()}
            score, n = sequence_logps(model, examples[index], chunk)
            return -score/n, {}

        def example_tokens(index):
            # A DPO pair's two sequences are both held in memory until the backward pass.
            return (sum(len(x['input_ids']) for x in examples[index]) if stage == 'dpo'
                    else len(examples[index]['input_ids']))

        # Recomputing activations in the backward pass saves memory but costs about a quarter of the
        # compute. With checkpointing_min_tokens set, only examples at least that long recompute;
        # a memory probe on the longest shorter example first checks that skipping it fits. (On Qwen3.8
        # 27B a 3,300-token DPO pair already ran out of the H200's memory without it, so the run
        # configs leave this unset: always recompute.)
        threshold = config.get('checkpointing_min_tokens')
        state = {'on': None}
        def checkpointing(tokens):
            want = threshold is None or tokens >= threshold
            if want != state['on']:
                if want:
                    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
                else:
                    model.gradient_checkpointing_disable()
                state['on'] = want
        probe = None
        while threshold is not None:
            below = [i for i in range(len(examples)) if example_tokens(i) < threshold]
            if not below:
                break
            probe = max(below, key=example_tokens)
            try:
                checkpointing(example_tokens(probe))
                loss, _ = example_loss(probe)
                loss.backward()
                break
            except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
                # flash-linear-attention's Triton kernels report running out of memory as a RuntimeError.
                if not isinstance(exc, torch.cuda.OutOfMemoryError) and 'out of memory' not in str(exc):
                    raise
                loss = None
                optimizer.zero_grad(set_to_none=True)
                torch.cuda.empty_cache()
                threshold = example_tokens(probe) // 2
            finally:
                optimizer.zero_grad(set_to_none=True)
        memory_probe = {'checkpointing_min_tokens': threshold, 'probe_tokens': example_tokens(probe) if probe is not None else None,
                        'examples_without_checkpointing': sum(threshold is not None and example_tokens(i) < threshold
                                                              for i in range(len(examples))),
                        'peak_cuda_gb': torch.cuda.max_memory_allocated()/1e9 if torch.cuda.is_available() else 0}
        write_json(output/'memory_probe.json', memory_probe)
        accumulation = config.get('gradient_accumulation_steps', 8)
        if accumulation < 1:
            raise ValueError('gradient_accumulation_steps must be positive')
        # Micro-batching: each optimizer step still averages the gradient over `accumulation` examples, but
        # up to micro_batch_size of them (within micro_batch_tokens padded tokens) go through the GPU together.
        # group_by_length makes each step hold examples of similar length. Defaults: one example at a time.
        micro_tokens = config.get('micro_batch_tokens')
        lengths = [max(len(x['input_ids']) for x in (examples[i] if stage == 'dpo' else [examples[i]]))
                   for i in range(len(examples))]
        sequences = [2 if stage == 'dpo' else 1] * len(examples)
        batching = {'micro_batch_size': micro_size, 'micro_batch_tokens': micro_tokens,
                    'group_by_length': bool(config.get('group_by_length')), 'micro_batches': 0,
                    'padded_tokens': 0, 'real_tokens': 0, 'out_of_memory_fallbacks': 0}
        epochs = config.get('epochs', 1)
        total_steps = math.ceil(len(examples) / accumulation) * epochs
        warmup = max(1, math.ceil(total_steps * config.get('warmup_ratio', 0.1)))
        base_lr = config.get('learning_rate', 1e-5)
        scheduler = None
        if config.get('lr_schedule') == 'cosine_min_lr':
            # OpenRLHF's schedule: transformers' cosine_with_min_lr, minimum 10% of the peak.
            from transformers import get_scheduler
            scheduler = get_scheduler('cosine_with_min_lr', optimizer,
                                      num_warmup_steps=math.ceil(total_steps * config.get('warmup_ratio', 0.1)),
                                      num_training_steps=total_steps,
                                      scheduler_specific_kwargs={'min_lr': base_lr * config.get('min_lr_ratio', 0.1)})
        elif config.get('lr_schedule', 'linear_warmup_constant') != 'linear_warmup_constant':
            raise ValueError('lr_schedule must be "linear_warmup_constant" or "cosine_min_lr"')
        log_path = output / 'training_log.jsonl'
        optimizer.zero_grad(set_to_none=True)
        step = 0; records = []; gradient_report = None
        with log_path.open('w') as log:
            for epoch in range(epochs):
                order = list(range(len(examples))); random.shuffle(order)
                steps = (length_grouped_steps(order, lengths, accumulation, config.get('length_group_steps', 50))
                         if config.get('group_by_length') else
                         [order[begin:begin+accumulation] for begin in range(0, len(order), accumulation)])
                for group in steps:
                    if scheduler is None:
                        lr = base_lr * min((step+1)/warmup, 1.0)
                        for param_group in optimizer.param_groups:
                            param_group['lr'] = lr
                    else:
                        lr = optimizer.param_groups[0]['lr']
                    plan = plan_micro_batches(group, lengths, sequences, micro_size, micro_tokens)
                    for attempt in (0, 1):
                        losses = []; failed = False
                        try:
                            for batch in plan:
                                checkpointing(sum(example_tokens(i) for i in batch))
                                total, batch_losses, metrics = batch_loss(batch)
                                if not all(torch.isfinite(x) for x in batch_losses):
                                    raise FloatingPointError('Nonfinite training loss')
                                (total/len(group)).backward()
                                losses += [float(x) for x in batch_losses]
                                del total
                        except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
                            if attempt or not is_out_of_memory(exc):
                                raise
                            failed = True
                        if not failed:
                            break
                        # Out of memory mid-step: drop this step's partial gradient and redo it one example
                        # at a time, which always fits; later steps use half the token budget.
                        optimizer.zero_grad(set_to_none=True)
                        torch.cuda.empty_cache()
                        batching['out_of_memory_fallbacks'] += 1
                        if micro_tokens:
                            micro_tokens = max(1, micro_tokens // 2)
                            batching['micro_batch_tokens_final'] = micro_tokens
                        plan = [[i] for i in group]
                    batching['micro_batches'] += len(plan)
                    batching['real_tokens'] += sum(example_tokens(i) for i in group)
                    batching['padded_tokens'] += sum(max(lengths[i] for i in b) * sum(sequences[i] for i in b) for b in plan)
                    if gradient_report is None:
                        missing = [name for name,p in model.named_parameters() if p.grad is None and (p.requires_grad or not lora)]
                        unexpected = [name for name in missing if not name.startswith('model.visual.')]
                        if unexpected:
                            raise RuntimeError(f'Active text weights lack gradients: {unexpected[:12]}')
                        gradient_report = {'all_parameters_require_grad':all(p.requires_grad for p in model.parameters()),
                            'parameters':parameter_count, 'trainable_parameters':trainable_count,
                            'parameters_with_gradient':sum(p.numel() for p in model.parameters() if p.grad is not None),
                            'inactive_parameter_names':missing}
                        write_json(output/'gradient_report.json', gradient_report)
                    grad_norm = torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],
                                                               config.get('max_grad_norm',1.0))
                    if not torch.isfinite(grad_norm):
                        raise FloatingPointError('Nonfinite gradient norm')
                    optimizer.step(); optimizer.zero_grad(set_to_none=True)
                    if scheduler is not None:
                        scheduler.step()
                    step += 1
                    record = {'step':step,'epoch':epoch,'loss':sum(losses)/len(losses),
                              'learning_rate':lr,'grad_norm':float(grad_norm),
                              'elapsed_seconds':time.monotonic()-started,**metrics}
                    log.write(json.dumps(record)+'\n'); log.flush()
                    print(json.dumps({'stage':stage, **record}), flush=True)
                    records.append(record)
        del optimizer
        adapter = None
        if lora:
            # Keep the adapter as trained (float32), then add it into the weights: the saved checkpoint is
            # this stage's input plus exactly this adapter, rounded once to the checkpoint's dtype.
            model.gradient_checkpointing_disable()
            adapter = output / 'adapter'
            peft_model.save_pretrained(adapter, safe_serialization=True)
            model = peft_model.merge_and_unload()
            del peft_model
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
                 'optimizer_reset':True, 'training':'lora' if lora else 'full_parameter',
                 'trainable_parameters':trainable_count, 'adapter_path':str(adapter) if adapter else None,
                 'memory_probe':memory_probe, 'batching':batching,
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
