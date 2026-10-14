"""The MSM (model spec midtraining) arm: Ariana's lineages from the registry.

Each of her models is one LoRA adapter on the untouched base, trained on the constitution stored
next to it as `training_seed_constitution.md`. Generations are linked by the constitution, not by
weights, so "previous" for generation g is the constitution generation g-1 trained on.

    python -m evals.models sync                              # CPU; builds the registry + downloads constitutions
    python -m adherence.msm lineages                         # what exists
    python -m adherence.msm config --lineage qwen36-35b-anth-gen-postcot --gens 0 1 2 \
        --out configs/msm_qwen36_anth_gen.json
    python -m adherence.msm merge  --config configs/msm_qwen36_anth_gen.json    # GPU box: adapter -> ckpt/

Scope: Qwen3.6-35B lineages only. Nemotron-120B and Inkling do not fit one H200 in bf16.
Unverified: that `oct.merge.merge_adapter` attaches Ariana's adapters to this base. Her adapters were
trained through Tinker, and `kl_exact` loads them with peft directly; if the merge reports no LoRA
modules attached, fall back to generating through vLLM's LoRA support.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

CONTROL_DIR = Path("../constitutional_self_edit/constitutions/elicitation")
CONTROLS = {"deferential": CONTROL_DIR / "deferential.md", "libertarian": CONTROL_DIR / "libertarian.md"}


def lineages(reg: dict) -> dict[str, list]:
    out = defaultdict(list)
    for s in reg.values():
        if s.source == "ariana":
            out[s.meta["lineage"]].append(s)
    return out


def build_config(lineage: str, gens: list[int], branch: int = 1, n: int = 3, probes=("evals/probes.jsonl",)) -> dict:
    from evals.models import registry
    specs = sorted((s for s in lineages(registry()).get(lineage, [])
                    if s.meta["gen"] in gens and s.meta["branch"] == branch), key=lambda s: s.meta["gen"])
    if not specs:
        raise SystemExit(f"no models for lineage {lineage!r} gens {gens} branch {branch}; "
                         "run `python -m evals.models sync` and check `python -m adherence.msm lineages`")
    missing = [s.name for s in specs if not s.constitution or not Path(s.constitution).exists()]
    if missing:
        raise SystemExit(f"no constitution on disk for {missing}")
    thinking = specs[0].thinking
    consts, arms = {}, [{"name": "base", "path": specs[0].base, "role": "reference", "thinking": thinking}]
    prev_key = None
    for s in specs:
        key = f"g{s.meta['gen']}"
        consts[key] = s.constitution
        arms.append({"name": s.name, "path": f"ckpt/msm_{s.name}", "role": "trained", "trained_on": key,
                     "previous": prev_key, "thinking": s.thinking})
        prev_key = key
    last = f"g{specs[-1].meta['gen']}"
    arms.append({"name": f"base_prompted_{last}", "path": specs[0].base, "role": "prompted_upper_bound",
                 "system_constitution": last, "trained_on": last, "thinking": thinking})
    consts.update({k: str(p) for k, p in CONTROLS.items()})
    return {"name": f"msm_{lineage}", "constitutions": consts, "controls": list(CONTROLS), "arms": arms,
            "probes": list(probes), "n": n,
            "notes": "MSM arm. Base model differs from the OCT arm; compare gains over each method's own base."}


def merge_models(cfg_path: Path) -> None:
    from huggingface_hub import snapshot_download
    from oct.merge import load_base, merge_adapter
    from transformers import AutoTokenizer

    from evals.models import registry
    from .config import load
    reg = registry()
    for arm in load(cfg_path).trained_arms():
        out = Path(arm.path)
        if (out / "config.json").exists():
            print(f"[msm] {arm.name}: merged checkpoint exists")
            continue
        spec = reg[arm.name]
        adapter_dir = snapshot_download(spec.adapters[0].repo, allow_patterns=["adapter_*", "*.json"])
        model = merge_adapter(load_base(spec.base, revision=None), adapter_dir)
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(out, safe_serialization=True, max_shard_size="5GB")
        AutoTokenizer.from_pretrained(spec.base, trust_remote_code=True).save_pretrained(out)
        print(f"[msm] saved {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lineages")
    c = sub.add_parser("config")
    c.add_argument("--lineage", required=True)
    c.add_argument("--gens", type=int, nargs="+", default=[0, 1, 2])
    c.add_argument("--branch", type=int, default=1)
    c.add_argument("--n", type=int, default=3)
    c.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("merge")
    m.add_argument("--config", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "lineages":
        from evals.models import registry
        for name, ss in sorted(lineages(registry()).items()):
            print(f"{name:48s} gens={sorted({s.meta['gen'] for s in ss})} base={ss[0].base}")
    elif a.cmd == "config":
        cfg = build_config(a.lineage, a.gens, a.branch, a.n)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(cfg, indent=2))
        print(f"wrote {a.out}")
    else:
        merge_models(a.config)


if __name__ == "__main__":
    main()
