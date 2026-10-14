"""Entry point.

    python -m adherence.run plan     configs/oct_round1.json     # scale only; no GPU, no API
    python -m adherence.run generate configs/oct_round1.json     # GPU: every arm answers the probes
    python -m adherence.run judge    configs/oct_round1.json     # API: the default judge
    python -m adherence.run judge    configs/oct_round1.json --variants default anchored inverted \
                                     --judges anthropic openrouter:openai/gpt-5 \
                                     --constitutions C_001 deferential      # the ablation, cheaper
    python -m adherence.run analyze  configs/oct_round1.json     # CPU: table, figure, robustness

Every stage resumes: finished responses are skipped, and judge calls are cached on disk.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import Config, load


def plan(cfg: Config, variants: list[str], judges: list[str], only: list[str] | None = None) -> dict:
    """The scale of the experiment, stated before anything is launched (see AGENTS.md)."""
    from .generate import adversarial_rows, load_probe_rows
    std = load_probe_rows(cfg.probes, cfg.scenario_limit)
    n_std = len(std)
    n_adv = len(adversarial_rows(std)) if cfg.adversarial else 0
    n_arms = len(cfg.arms)
    n_resp = n_arms * (n_std + n_adv) * cfg.n
    n_const = len([k for k in cfg.constitutions if not only or k in only])
    adherence = n_resp * n_const
    judged = [a for a in cfg.arms if a.role != "reference"]
    pair = sum(2 * n_std * cfg.n for a in judged if a.trained_on)
    coh = sum(2 * n_std * cfg.n for a in judged)
    total = 0
    for _ in judges:
        for v in variants:
            total += adherence + (pair + coh if v == "default" else 0)
    out = {"arms": n_arms, "probes": n_std, "adversarial_probes": n_adv, "samples_per_probe": cfg.n,
           "responses": n_resp, "gpu_loads": n_arms, "constitutions": n_const,
           "adherence_calls_per_variant": adherence, "pairwise_calls": pair, "coherence_calls": coh,
           "variants": variants, "judges": judges, "total_judge_calls": total}
    print(f"\nExperiment {cfg.name}")
    print(f"  arms: {', '.join(a.name for a in cfg.arms)}")
    print(f"  probes: {n_std} standard" + (f" + {n_adv} with an 'ignore your training' suffix" if n_adv else ""))
    print(f"  generation: {n_arms} arms x {n_std + n_adv} probes x {cfg.n} samples = {n_resp} responses "
          f"({n_arms} model loads; prompted arms reload the base model)")
    print(f"  judging, per (variant, judge): {adherence} adherence calls [{n_resp} responses x {n_const} constitutions]")
    print(f"  judging, once per judge (default variant): {pair} pairwise-adherence + {coh} coherence calls")
    print(f"  this selection: {len(variants)} variant(s) x {len(judges)} judge(s) = {total} judge calls")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["plan", "generate", "judge", "analyze", "all"])
    ap.add_argument("config", type=Path)
    ap.add_argument("--only", nargs="*", help="generate: only these arms")
    ap.add_argument("--variants", nargs="+", default=["default"])
    ap.add_argument("--judges", nargs="+", default=["anthropic"])
    ap.add_argument("--no-pairwise", action="store_true")
    ap.add_argument("--constitutions", nargs="+", help="judge/plan only these constitution keys (cheaper ablation)")
    a = ap.parse_args()

    cfg = load(a.config, check_files=a.stage in ("generate", "judge", "all"))
    if a.stage == "plan":
        plan(cfg, a.variants, a.judges, a.constitutions)
        return
    if a.stage in ("generate", "all"):
        from .generate import generate_all
        generate_all(cfg, a.only)
    if a.stage in ("judge", "all"):
        from .judging import judge_all
        for j in a.judges:
            for v in a.variants:
                judge_all(cfg, v, j, pairwise=not a.no_pairwise, only=a.constitutions)
    if a.stage in ("analyze", "all"):
        from .analyze import analyze
        analyze(cfg)


if __name__ == "__main__":
    main()
