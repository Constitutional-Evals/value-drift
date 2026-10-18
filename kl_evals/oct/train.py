"""Steps 4 and 6: LoRA training (DPO, then SFT), each followed by a merge.

    python -m oct.train dpo --model <round input> --data runs/broad/round_001/dpo_pairs.jsonl \
        --out runs/broad/round_001/dpo
    python -m oct.train sft --model runs/broad/round_001/dpo/merged --data .../sft.jsonl \
        --out runs/broad/round_001/sft

Writes <out>/adapter/ (the LoRA), <out>/merged/ (input model + adapter, the next stage's
input), and <out>/training_complete.json. Settings default to round one's
training_complete.json (rank 64, alpha 128, lr 5e-5, betas (0.9, 0.98), cosine to 10% of peak,
10% warmup, 1 epoch, effective batch 32 = micro 4 x accum 8 on one GPU; DPO beta 0.1 with an
NLL term on chosen of weight 0.1).

Not reproduced: round one also logged `kl_coef: 0.001`, an extra KL-to-reference penalty in
Jinzhou's trainer; TRL's DPOTrainer has no such knob. Its effect at 0.001 is small, but ask him
how it was computed if you need exact parity.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import fields
from pathlib import Path

from .common import LORA_TARGETS, read_jsonl

ROUND_ONE = dict(
    lora_rank=64, lora_alpha=128, lora_dropout=0.0, learning_rate=5e-5, adam_betas=(0.9, 0.98),
    weight_decay=0.0, epochs=1, warmup_ratio=0.1, min_lr_ratio=0.1, max_grad_norm=1.0,
    micro_batch_size=4, gradient_accumulation_steps=8, seed=20260927,
    beta=0.1, nll_coef=0.1,
)
EXPECTED_TRAINABLE = 466_911_232  # round one's trainable parameter count


def lora_config(cfg: dict, model):
    from peft import LoraConfig
    # Restrict to the language model if the checkpoint also carries a vision tower, whose
    # attention also has q_proj/out_proj-style names.
    has_lm = any(".language_model." in n for n, _ in model.named_modules())
    targets = (r".*language_model.*\.(" + "|".join(LORA_TARGETS) + r")$") if has_lm else LORA_TARGETS
    return LoraConfig(r=cfg["lora_rank"], lora_alpha=cfg["lora_alpha"],
                      lora_dropout=cfg["lora_dropout"], target_modules=targets, bias="none")


def common_args(cfg: dict, out: Path) -> dict:
    return dict(
        output_dir=str(out / "trainer"), num_train_epochs=cfg["epochs"],
        per_device_train_batch_size=cfg["micro_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        learning_rate=cfg["learning_rate"], adam_beta1=cfg["adam_betas"][0],
        adam_beta2=cfg["adam_betas"][1], weight_decay=cfg["weight_decay"],
        warmup_ratio=cfg["warmup_ratio"], lr_scheduler_type="cosine_with_min_lr",
        lr_scheduler_kwargs={"min_lr_rate": cfg["min_lr_ratio"]}, max_grad_norm=cfg["max_grad_norm"],
        bf16=True, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        group_by_length=True, logging_steps=5, save_strategy="no", report_to="none",
        seed=cfg["seed"],
    )


def accepted(config_cls, kwargs: dict) -> dict:
    """Drop kwargs this TRL version's config doesn't define (names move between releases)."""
    names = {f.name for f in fields(config_cls)}
    dropped = sorted(set(kwargs) - names)
    if dropped:
        print(f"[train] {config_cls.__name__} ignores: {dropped}")
    return {k: v for k, v in kwargs.items() if k in names}


def dpo_nll_kwargs(config_cls, nll_coef: float) -> dict:
    names = {f.name for f in fields(config_cls)}
    if "loss_weights" in names:  # newer TRL: combine sigmoid DPO with an SFT (NLL) term
        return {"loss_type": ["sigmoid", "sft"], "loss_weights": [1.0, nll_coef]}
    if "rpo_alpha" in names:     # older TRL
        return {"rpo_alpha": nll_coef}
    raise RuntimeError("this TRL version supports neither loss_weights nor rpo_alpha")


def tokenize_assistant_only(tok, messages: list[dict], end_marker: str = "<|im_end|>") -> dict | None:
    """Token ids for the whole chat, with labels only on assistant turns (-100 elsewhere).

    The chat is rendered once; each assistant message's content is located in the rendered text
    (in order), and the tokens from its first character through the following end-of-turn marker
    are trained. This sidesteps Qwen's template rendering past and final assistant turns
    differently (only the final one gets empty <think></think> tags), and trains only what the
    model generates after the <think> block at inference with thinking off.
    """
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=False,
                                   enable_thinking=False)
    spans, pos = [], 0
    for m in messages:
        c = m["content"].strip()
        if not c:
            continue
        s = text.find(c, pos)
        if s < 0:
            return None
        e = s + len(c)
        pos = e
        if m["role"] == "assistant":
            k = text.find(end_marker, e)
            spans.append((s, (k + len(end_marker)) if k >= 0 else e))
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    ids, offs = enc["input_ids"], enc["offset_mapping"]
    labels = [-100] * len(ids)
    for j, (a, b) in enumerate(offs):
        if any(a >= s and b <= e and b > a for s, e in spans):
            labels[j] = ids[j]
    if all(l == -100 for l in labels):
        return None
    return {"input_ids": ids, "labels": labels}


class PadCollator:
    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, batch):
        import torch
        n = max(len(b["input_ids"]) for b in batch)
        pad = lambda seq, v: seq + [v] * (n - len(seq))
        return {
            "input_ids": torch.tensor([pad(b["input_ids"], self.pad_id) for b in batch]),
            "labels": torch.tensor([pad(b["labels"], -100) for b in batch]),
            "attention_mask": torch.tensor([pad([1] * len(b["input_ids"]), 0) for b in batch]),
        }


def train(stage: str, model_path: str, data: Path, out: Path, cfg: dict) -> None:
    import torch
    from datasets import Dataset
    from transformers import AutoTokenizer

    from .merge import load_base

    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = load_base(model_path, revision=None)
    model.to("cuda")
    model.config.use_cache = False
    rows = read_jsonl(data)
    peft_cfg = lora_config(cfg, model)

    if stage == "dpo":
        from trl import DPOConfig, DPOTrainer
        ds = Dataset.from_list([{k: r[k] for k in ("prompt", "chosen", "rejected")} for r in rows])
        args = DPOConfig(**accepted(DPOConfig, {
            **common_args(cfg, out), "beta": cfg["beta"], "max_length": None,
            "precompute_ref_log_probs": False, **dpo_nll_kwargs(DPOConfig, cfg["nll_coef"])}))
        # With a peft_config and no ref_model, TRL uses the adapter-disabled model as the
        # reference, i.e. exactly this stage's input model.
        trainer = DPOTrainer(model=model, args=args, train_dataset=ds, processing_class=tok,
                             peft_config=peft_cfg)
    else:
        from peft import get_peft_model
        from transformers import Trainer, TrainingArguments
        examples, skipped = [], 0
        for r in rows:
            ex = tokenize_assistant_only(tok, r["messages"])
            if ex is None:
                skipped += 1
            else:
                examples.append(ex)
        print(f"[train] sft: {len(examples)} examples, {skipped} skipped (content not found in rendered chat)")
        ds = Dataset.from_list(examples)
        model.enable_input_require_grads()
        model = get_peft_model(model, peft_cfg)
        args = TrainingArguments(**accepted(TrainingArguments, {
            **common_args(cfg, out), "remove_unused_columns": False}))
        trainer = Trainer(model=model, args=args, train_dataset=ds,
                          data_collator=PadCollator(tok.pad_token_id or tok.eos_token_id))

    n_train = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    print(f"[train] trainable params {n_train:,} (round one: {EXPECTED_TRAINABLE:,})")
    if n_train != EXPECTED_TRAINABLE:
        print("[train] WARNING: trainable count differs from round one; check LoRA targets")

    result = trainer.train()
    adapter_dir = out / "adapter"
    trainer.model.save_pretrained(adapter_dir)
    tok.save_pretrained(adapter_dir)

    merged = trainer.model.merge_and_unload()
    merged.config.use_cache = True
    merged.save_pretrained(out / "merged", safe_serialization=True, max_shard_size="5GB")
    tok.save_pretrained(out / "merged")
    try:
        from transformers import AutoProcessor
        AutoProcessor.from_pretrained(model_path, trust_remote_code=True).save_pretrained(out / "merged")
    except Exception:
        pass

    (out / "training_complete.json").write_text(json.dumps({
        "stage": stage, "input_checkpoint": model_path, "output_checkpoint": str(out / "merged"),
        "config": {**cfg, "method": "lora", "trainer": "trl"}, "examples": len(rows),
        "optimizer_steps": result.global_step, "mean_loss": result.training_loss,
        "seconds": time.time() - t0, "trainable_parameters": n_train,
        "peak_cuda_gb": torch.cuda.max_memory_allocated() / 1e9,
        "adapter_path": str(adapter_dir),
    }, indent=2))
    print(f"[train] {stage} done: {result.global_step} steps, loss {result.training_loss:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["dpo", "sft"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE",
                    help="override a round-one setting, e.g. --set learning_rate=2e-5")
    a = ap.parse_args()
    cfg = dict(ROUND_ONE)
    for kv in a.set:
        k, v = kv.split("=", 1)
        cfg[k] = type(cfg[k])(v) if k in cfg and not isinstance(cfg[k], tuple) else json.loads(v)
    train(a.stage, a.model, a.data, a.out, cfg)


if __name__ == "__main__":
    main()
