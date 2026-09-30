"""OCT's DPO and SFT stages on Hugging Face TRL (switched from the custom trainer on 2026-09-29).

Same recipe and outputs as recursive_oct/train.py: a fresh LoRA adapter on the stage's input checkpoint
(rank 64, alpha 128, every linear layer of the language model), saved and merged exactly into the
weights; training_complete.json with the same fields. What TRL adds is batching: several examples go
through the GPU together, grouped by length (the longest batch first, so memory problems show at once).

DPO: TRL's sigmoid loss plus its "sft" loss at nll_coef (OCT's NLL term), plus OCT's squared per-token
KL to the reference (kl_coef), which TRL lacks and a subclass adds. The reference is the input model
(the adapter disabled), scored at every step because the KL term needs per-token values. Examples are
tokenized by train.encode_completion, so both trainers see identical token sequences.
SFT: TRL's chunked NLL on the trained turn only (completion_mask).

Differences from the custom trainer, both small: TRL's NLL terms average over the tokens of a
micro-batch (the custom trainer averages each sequence, then the sequences), and the order of examples
comes from TRL's length-grouped sampler.

The batch size (micro_batch_size) should come from agents/scripts/probe_micro_batch.py. If the GPU runs
out of memory anyway, training restarts from the start with half the batch size and twice the
accumulation, so each optimizer step still covers gradient_accumulation_steps examples.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .train import (attach_lora, audit_training_lengths, encode_completion, encode_sft, is_out_of_memory, read_jsonl,
                    training_length, write_json)


def _arguments(stage, config, output, batch, accumulation, total_steps, cuda):
    """TRL arguments for OCT's schedule: AdamW, cosine to min_lr_ratio after warmup, clipped gradients."""
    from trl import DPOConfig, SFTConfig
    lr = config.get('learning_rate', 5e-5)
    common = dict(
        output_dir=str(output / 'trl'), per_device_train_batch_size=batch, gradient_accumulation_steps=accumulation,
        learning_rate=lr, adam_beta1=config.get('adam_betas', [0.9, 0.98])[0], adam_beta2=config.get('adam_betas', [0.9, 0.98])[1],
        weight_decay=config.get('weight_decay', 0.0), max_grad_norm=config.get('max_grad_norm', 1.0),
        num_train_epochs=config.get('epochs', 1), lr_scheduler_type='cosine_with_min_lr',
        lr_scheduler_kwargs={'min_lr': lr * config.get('min_lr_ratio', 0.1)},
        warmup_steps=config.get('warmup_ratio', 0.1),   # below 1: a fraction of the steps, rounded up
        seed=config.get('seed', 20260915), data_seed=config.get('seed', 20260915),
        bf16=cuda, use_cpu=not cuda, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={'use_reentrant': False}, logging_steps=1, save_strategy='no', report_to='none',
        remove_unused_columns=False, train_sampling_strategy='group_by_length', length_column_name='length', dataloader_num_workers=0,
        max_length=None)
    if stage == 'dpo':
        return DPOConfig(**common, disable_dropout=True, beta=config.get('beta', 0.1), loss_type=['sigmoid', 'sft'],
                         loss_weights=[1.0, config.get('nll_coef', 0.1)], precompute_ref_log_probs=False)
    return SFTConfig(**common, completion_only_loss=True, packing=False, loss_type='chunked_nll')


def _dpo_trainer_class():
    from trl import DPOTrainer

    class OCTDPOTrainer(DPOTrainer):
        """DPO with OCT's squared per-token KL, on pre-tokenized pairs, through TRL's chunked log-prob path."""

        def __init__(self, *args, kl_coef=0.0, **kwargs):
            super().__init__(*args, **kwargs)
            self.kl_coef = kl_coef
            # TRL computes log-probabilities in chunks (never the full [tokens, 248k] logits) only on its Liger path;
            # that path's code is TRL's own, so it is switched on here without the Liger package.
            self.use_liger_kernel = True
            self._captured = None

        def _prepare_dataset(self, dataset, processing_class, args, dataset_name):
            return dataset   # already tokenized by train.encode_completion

        def _get_per_token_logps_and_entropies(self, model, model_kwargs, input_ids, completion_mask):
            out = super()._get_per_token_logps_and_entropies(model, model_kwargs, input_ids, completion_mask)
            if self._captured is not None:
                self._captured.append(out[0])   # first the policy, then the reference
            return out

        def _compute_loss(self, model, inputs, return_outputs):
            self._captured = [] if self.kl_coef else None
            result = super()._compute_loss(model, inputs, return_outputs)
            captured, self._captured = self._captured, None
            if not self.kl_coef:
                return result
            policy, reference = captured[0], captured[1].detach()
            mask = inputs['completion_mask'][:, 1:].to(policy.dtype)
            per_sequence = ((policy - reference) ** 2 * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            kl = per_sequence.view(2, -1).mean(dim=0).mean()   # chosen and rejected averaged, then the pairs
            mode = 'train' if self.model.training else 'eval'
            try:
                self._metrics[mode]['squared_kl'].append(float(kl.detach()))
            except (AttributeError, KeyError, TypeError):
                pass
            if return_outputs:
                return result[0] + self.kl_coef * kl, result[1]
            return result + self.kl_coef * kl

    return OCTDPOTrainer


def _dataset(stage, rows, tokenizer, max_len):
    """Pre-tokenized examples, and the sequences for the length audit."""
    from datasets import Dataset
    records, sequences = [], []
    for r in rows:
        if stage == 'dpo':
            messages = [{'role': 'user', 'content': r['prompt']}]
            chosen, rejected = (encode_completion(tokenizer, messages, r[k], max_len) for k in ('chosen', 'rejected'))
            prefix = sum(label == -100 for label in chosen['labels'])
            assert chosen['input_ids'][:prefix] == rejected['input_ids'][:prefix]
            records.append({'id': r.get('id'), 'prompt_ids': chosen['input_ids'][:prefix],
                            'chosen_ids': chosen['input_ids'][prefix:], 'rejected_ids': rejected['input_ids'][prefix:],
                            'length': max(len(chosen['input_ids']), len(rejected['input_ids']))})
            sequences += [chosen, rejected]
        else:
            for x in encode_sft(tokenizer, r['messages'], max_len, last_only=r.get('train_on') == 'last'):
                records.append({'input_ids': x['input_ids'], 'completion_mask': [int(y != -100) for y in x['labels']],
                                'length': len(x['input_ids'])})
                sequences.append(x)
    return Dataset.from_list(records), sequences


def train_trl(checkpoint, data_path, output_dir, config, stage):
    import torch
    import trl
    from transformers import set_seed
    from .model import ModelSession
    output = Path(output_dir)
    if (output / 'training_complete.json').exists():
        saved = json.loads((output / 'training_complete.json').read_text())
        if saved['input_checkpoint'] != str(checkpoint) or saved['stage'] != stage or saved['config'] != config:
            raise ValueError('Existing checkpoint belongs to another stage/config/input')
        return saved
    if config.get('method') != 'lora':
        raise ValueError('The TRL stages train LoRA adapters only')
    output.mkdir(parents=True, exist_ok=True)
    cuda = config.get('device', 'cuda') == 'cuda'
    started = time.monotonic()
    rows = read_jsonl(data_path)
    if not rows:
        raise ValueError('No training data')
    accumulation_total = config.get('gradient_accumulation_steps', 32)
    batch = min(config.get('micro_batch_size', 1), accumulation_total)
    token_cap = config.get('micro_batch_token_cap', 131072)
    restarts = 0
    while True:
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        set_seed(config.get('seed', 20260915))
        with ModelSession(checkpoint, device=config.get('device', 'cuda'), attention=config.get('attention', 'sdpa'),
                          parameter_dtype=config.get('parameter_dtype', 'bfloat16')) as session:
            model, tokenizer = session.model, session.tokenizer
            dataset, sequences = _dataset(stage, rows, tokenizer, training_length(config))
            audit_training_lengths(sequences, config, output)
            # A micro-batch is capped at token_cap padded tokens, counted on the longest example: far above that
            # (roughly 250k) the linear-attention kernels fail with an illegal memory access, which no retry recovers.
            longest = max(len(x['input_ids']) for x in sequences) * (2 if stage == 'dpo' else 1)
            batch = max(1, min(batch, token_cap // longest))
            peft_model = attach_lora(model, config)
            parameter_count = sum(p.numel() for p in peft_model.parameters())
            trainable_count = sum(p.numel() for p in peft_model.parameters() if p.requires_grad)
            accumulation = max(1, accumulation_total // batch)
            total_steps = math.ceil(len(dataset) / (batch * accumulation)) * config.get('epochs', 1)
            args = _arguments(stage, config, output, batch, accumulation, total_steps, cuda)
            if stage == 'dpo':
                from trl.trainer.dpo_trainer import DataCollatorForPreference
                pad = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.convert_tokens_to_ids('<|im_end|>')
                trainer = _dpo_trainer_class()(model=peft_model, args=args, train_dataset=dataset, processing_class=tokenizer,
                                               data_collator=DataCollatorForPreference(pad_token_id=pad),
                                               kl_coef=config.get('kl_coef', 0.0))
            else:
                trainer = trl.SFTTrainer(model=peft_model, args=args, train_dataset=dataset, processing_class=tokenizer)
            try:
                trainer.train()
            except Exception as exc:   # out of memory: start over with half the batch and twice the accumulation
                if not (is_out_of_memory(exc) and batch > 1):
                    raise
                failed_batch = batch
            else:
                failed_batch = None
            if failed_batch is None:
                log = [entry for entry in trainer.state.log_history if 'loss' in entry]
                with (output / 'training_log.jsonl').open('w') as stream:
                    for entry in log:
                        stream.write(json.dumps({'stage': stage, **entry}) + '\n')
                adapter = output / 'adapter'
                peft_model = trainer.model
                peft_model.save_pretrained(adapter, safe_serialization=True)
                merged = peft_model.merge_and_unload()
                merged.eval()
                merged.config.use_cache = True
                merged.save_pretrained(output, safe_serialization=True, max_shard_size='4GB')
                tokenizer.save_pretrained(output)
                stats = {'stage': stage, 'input_checkpoint': str(checkpoint), 'output_checkpoint': str(output),
                         'config': config, 'examples': len(dataset), 'optimizer_steps': trainer.state.global_step,
                         'mean_loss': sum(e['loss'] for e in log) / len(log) if log else None,
                         'seconds': time.monotonic() - started, 'parameters': parameter_count,
                         'peak_cuda_gb': torch.cuda.max_memory_allocated() / 1e9 if cuda else 0,
                         'optimizer_reset': True, 'training': 'lora', 'trainer': f'trl {trl.__version__}',
                         'trainable_parameters': trainable_count, 'adapter_path': str(adapter),
                         'batching': {'micro_batch_size': batch, 'gradient_accumulation_steps': accumulation,
                                      'micro_batch_token_cap': token_cap, 'longest_example_tokens': longest,
                                      'group_by_length': True, 'out_of_memory_restarts': restarts},
                         'truncated_sequences': sum(x['truncated'] for x in sequences)}
                write_json(output / 'training_complete.json', stats)
                del trainer, peft_model, merged, model
                return stats
            del trainer, peft_model, model
        batch = max(1, failed_batch // 2)
        restarts += 1
        print(json.dumps({'stage': stage, 'out_of_memory': True, 'retry_micro_batch_size': batch}), flush=True)


def train_dpo(checkpoint, preferences_path, output_dir, config):
    return train_trl(checkpoint, preferences_path, output_dir, config, 'dpo')


def train_sft(checkpoint, introspection_path, output_dir, config):
    return train_trl(checkpoint, introspection_path, output_dir, config, 'sft')
