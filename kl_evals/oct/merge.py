"""Build the model after any stage of a chain: base + adapters merged in order.

    python -m oct.merge --stage r1/sft --out ckpt/r1_sft
    python -m oct.merge --stage r1/dpo --out ckpt/r1_dpo --chain-dir hf/qwen3.8-27b/broad

Each adapter was trained on the model merged up to the stage before it, so they must be
merged one at a time in order (round_001/dpo, round_001/sft, round_002/dpo, ...). Stacking
them unmerged on the base model is NOT equivalent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import BASE_MODEL, BASE_REVISION, Stage, download_chain, stages_up_to


def load_base(model_path: str = BASE_MODEL, revision: str | None = BASE_REVISION):
    """Load in bf16 with the same class the adapters were trained against.

    adapter_config.json names Qwen3_5ForConditionalGeneration; LoRA key names depend on the
    module tree, so loading a text-only class can leave adapter weights unmatched. We try the
    named class first, then the generic auto classes.
    """
    import torch
    import transformers

    kw = dict(torch_dtype=torch.bfloat16, trust_remote_code=True, low_cpu_mem_usage=True,
              device_map="cpu")
    if revision and not Path(model_path).exists():
        kw["revision"] = revision
    for cls_name in ("Qwen3_5ForConditionalGeneration", "AutoModelForImageTextToText",
                     "AutoModelForCausalLM"):
        cls = getattr(transformers, cls_name, None)
        if cls is None:
            continue
        try:
            return cls.from_pretrained(model_path, **kw)
        except (ValueError, OSError, KeyError) as e:  # wrong auto class for this checkpoint
            print(f"[merge] {cls_name} failed: {e}")
    raise RuntimeError(f"could not load {model_path}")


def merge_adapter(model, adapter_dir: str | Path):
    """Merge one LoRA adapter into `model` in place, refusing silent key mismatches."""
    from peft import PeftModel

    peft_model = PeftModel.from_pretrained(model, str(adapter_dir), is_trainable=False)
    n_lora = sum(1 for n, _ in peft_model.named_modules() if n.endswith("lora_A"))
    if n_lora == 0:
        raise RuntimeError(f"no LoRA modules attached from {adapter_dir}: key mismatch with base class")
    print(f"[merge] {adapter_dir}: {n_lora} LoRA modules")
    return peft_model.merge_and_unload()


def build(stage: Stage, out: Path, chain_dir: Path, base: str = BASE_MODEL) -> Path:
    from transformers import AutoProcessor, AutoTokenizer

    model = load_base(base)
    merged = []
    for s in stages_up_to(stage):
        model = merge_adapter(model, chain_dir / s.key)
        merged.append(s.key)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True, max_shard_size="5GB")
    rev = None if Path(base).exists() else BASE_REVISION
    AutoTokenizer.from_pretrained(base, revision=rev, trust_remote_code=True).save_pretrained(out)
    try:  # keep the processor/chat template files vLLM expects for this model family
        AutoProcessor.from_pretrained(base, revision=rev, trust_remote_code=True).save_pretrained(out)
    except Exception:
        pass
    (out / "merge_manifest.json").write_text(json.dumps(
        {"base": base, "revision": BASE_REVISION, "merged": merged}, indent=2))
    print(f"[merge] saved {out} ({' -> '.join(merged)})")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, help="e.g. r1/dpo, r1/sft")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--chain", default="broad")
    ap.add_argument("--chain-dir", type=Path, help="local chain folder; downloaded if omitted")
    ap.add_argument("--base", default=BASE_MODEL)
    a = ap.parse_args()
    chain_dir = a.chain_dir or download_chain("hf", a.chain)
    build(Stage.parse(a.stage), a.out, chain_dir, a.base)


if __name__ == "__main__":
    main()
