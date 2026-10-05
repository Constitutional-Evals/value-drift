"""End-to-end rehearsal of the KL pipeline on a laptop CPU, with a 135M stand-in model.

    python scripts/dryrun_cpu.py            # ~2 minutes, writes results/dryrun/

Builds two random LoRA adapters on SmolLM2-135M shaped like Jinzhou's chain (tiny_dpo = base +
dpo, tiny_sft = base + dpo + sft) and a second unrelated single-adapter model (like Ariana's),
then runs evals.kl_exact and evals.kl_stats exactly as the GPU run does. The numbers mean
nothing; the point is that every code path (loading, stacking, scaling, sampling, scoring,
unloading, resuming, stats, plots) has executed before a GPU is involved.
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
OUT = Path("results/dryrun")


def make_adapters(root: Path) -> None:
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM

    for i, name in enumerate(["dpo", "sft", "other"]):
        if (root / name / "adapter_model.safetensors").exists():
            continue
        torch.manual_seed(i)
        model = get_peft_model(AutoModelForCausalLM.from_pretrained(BASE),
                               LoraConfig(r=8, lora_alpha=16, target_modules="all-linear"))
        for n, p in model.named_parameters():
            if "lora_B" in n:                       # B starts at zero; give it a small random value
                torch.nn.init.normal_(p, std=0.02)
        model.save_pretrained(root / name)


def main():
    root = OUT / "adapters"
    make_adapters(root)
    ad = lambda n: {"name": "lora" if n == "other" else n, "repo": str(root / n)}
    specs = [
        {"name": "tiny_dpo", "source": "local", "base": BASE, "adapters": [ad("dpo")]},
        {"name": "tiny_sft", "source": "local", "base": BASE, "adapters": [ad("dpo"), ad("sft")]},
        {"name": "tiny_other", "source": "local", "base": BASE, "adapters": [ad("other")]},
    ]
    spec_file = OUT / "specs.json"
    spec_file.write_text(json.dumps(specs, indent=1))

    run = OUT / "kl"
    common = [sys.executable, "-m", "evals.kl_exact", "--spec-file", str(spec_file), "--out", str(run),
              "--limit-per-category", "2", "--n", "2", "--max-new-tokens", "24", "--batch-size", "8",
              "--dtype", "float32", "--device-map", "cpu"]
    subprocess.run(common + ["--models", "tiny_sft", "tiny_other", "--scales", "0", "0.5", "1", "1.5",
                             "--variants", "tiny_dpo", "tiny_sft@dpo=1,sft=0", "tiny_sft@dpo=1,sft=0.5",
                             "tiny_sft@dpo=0,sft=1"], check=True)
    subprocess.run(common + ["--models", "tiny_sft", "--policy", "self"], check=True)
    subprocess.run([sys.executable, "-m", "evals.kl_stats", str(run), "--contrast", "tiny_sft", "tiny_dpo"],
                   check=True)

    s = json.loads((run / "summary.json").read_text())["variants"]
    zero = s["tiny_sft@0__base"]["kl"]["est"]
    assert abs(zero) < 1e-6, f"strength 0 should reproduce the base exactly, got KL {zero}"
    # dpo=1,sft=0 is the same model as tiny_dpo: stacking with one adapter off == the shorter chain
    a, b = s["tiny_sft@dpo=1,sft=0__base"]["kl"]["est"], s["tiny_dpo__base"]["kl"]["est"]
    assert abs(a - b) < 1e-4, (a, b)
    print("\n[dryrun] OK: strength 0 gives KL 0, and a chain with its last adapter off matches the shorter chain")


if __name__ == "__main__":
    main()
