"""Exact per-token KL from the base model, for any adapter and any adapter strength. GPU stage.

    python -m evals.kl_exact --models r1_dpo r1_sft --scales 0 0.25 0.5 0.75 1 1.25 1.5 \
        --out results/kl/jinzhou

Why this instead of evals/kl.py. That estimator samples a token y from the trained model and
averages log p_trained(y) - log p_base(y). That is unbiased but noisy: each position contributes
one random draw of a log-ratio that is often negative. Here the base model and its LoRA adapters
live in ONE process, so at every position we have both full next-token distributions and take
the KL between them exactly (summing over the vocabulary). The only randomness left is which
prompts and which continuations we looked at, and evals/kl_stats.py puts a bootstrap interval
on that.

Adjusting the weights. A LoRA adapter adds (alpha/r)·B·A to each weight it targets. Multiplying
that by a scale s moves the model along the line from the base (s=0) through the trained model
(s=1) and beyond (s>1). Variants are written NAME, NAME@0.5 (every adapter x0.5) or
NAME@dpo=1,sft=0.5 (per adapter; unnamed adapters are off). s=0 must give KL = 0 exactly, which
checks the whole pipeline.

Which text the KL is measured on (--policy):
  base   continuations sampled once from the base model and shared by every variant. Same
         tokens for everyone, so differences between variants are paired and much tighter.
         Measures E_{x~base} KL(p_variant || p_base).
  self   continuations sampled from each variant itself: the textbook KL(variant || base) per
         generated token, comparable to round one's 0.21. Costs one sampling pass per variant.

Chains (Jinzhou's r1_sft = base + dpo + sft) are run with both adapters active rather than
merged, as measure_kl.py in the value-drift repo does. That script is where round one's 0.209
comes from: it is also exact, on each model's own answers sampled at temperature 0.7 / top-p
0.95 up to 2,048 tokens, 100 held-out + 100 trait prompts, one answer each, no intervals.
`--policy self --temperature 0.7 --top-p 0.95 --max-new-tokens 2048 --n 1` reproduces its
setting on this repo's scenarios.

Writes <out>/trajectories/<sampler>.jsonl and <out>/tokens/<variant>__<policy>.jsonl (one row per
continuation with per-token kl, reverse kl, JS, sampled-token log-ratio and top-1 agreement).
Finished files are skipped, so rerunning resumes. Then: python -m evals.kl_stats <out>
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from oct.common import read_jsonl, write_jsonl

from .models import ModelSpec, registry, select
from .scenarios import load_scenarios, to_messages


# ---------------------------------------------------------------- variants (no torch needed)

@dataclass(frozen=True)
class Variant:
    label: str
    spec: ModelSpec
    scales: tuple[tuple[str, float], ...]   # adapter short name -> multiplier

    @property
    def scale_dict(self) -> dict[str, float]:
        return dict(self.scales)


def parse_variant(text: str, reg: dict[str, ModelSpec]) -> Variant:
    name, _, s = text.partition("@")
    if name not in reg:
        raise SystemExit(f"unknown model {name!r}; see `python -m evals.models list`")
    spec = reg[name]
    names = [a.name for a in spec.adapters]
    if not s:
        scales = {n: 1.0 for n in names}
    elif "=" in s:
        scales = {n: 0.0 for n in names}
        for part in s.split(","):
            k, v = part.split("=")
            if k not in scales:
                raise SystemExit(f"{name} has adapters {names}, not {k!r}")
            scales[k] = float(v)
    else:
        scales = {n: float(s) for n in names}
    return Variant(text, spec, tuple(scales.items()))


def expand(models: list[ModelSpec], scales: list[float], last_only: bool) -> list[str]:
    """Variant labels for a scale sweep. With last_only, earlier adapters of a chain stay at 1
    and only the final one is scaled (e.g. dpo=1, sft=s: how much of the SFT step is applied)."""
    out = []
    for m in models:
        for s in scales:
            if last_only and len(m.adapters) > 1:
                parts = [f"{a.name}=1" for a in m.adapters[:-1]] + [f"{m.adapters[-1].name}={s:g}"]
                out.append(f"{m.name}@{','.join(parts)}")
            else:
                out.append(m.name if s == 1 else f"{m.name}@{s:g}")
    return out


def safe(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.=@,-]", "_", label)


# ---------------------------------------------------------------- the divergences

def divergences(lp, lq, ids):
    """lp, lq: [T, V] log-probs of variant and base at the same positions; ids: [T] the tokens
    actually in the text. Returns per-position kl = KL(p||q), rkl = KL(q||p), js, lr = the old
    estimator's single-sample log-ratio log p(y) - log q(y), and top-1 agreement."""
    import math

    import torch
    p, q = lp.exp(), lq.exp()
    kl = (p * (lp - lq)).sum(-1)
    rkl = (q * (lq - lp)).sum(-1)
    lm = torch.logaddexp(lp, lq) - math.log(2)
    js = 0.5 * (p * (lp - lm)).sum(-1) + 0.5 * (q * (lq - lm)).sum(-1)
    lr = (lp - lq).gather(-1, ids[:, None]).squeeze(-1)
    agree = (lp.argmax(-1) == lq.argmax(-1)).float()
    return {"kl": kl, "rkl": rkl, "js": js, "lr": lr, "agree": agree}


# ---------------------------------------------------------------- model + adapters

def load_base(spec: ModelSpec, dtype: str, device_map: str):
    import torch
    import transformers
    from transformers import AutoTokenizer

    kw = dict(torch_dtype=getattr(torch, dtype), trust_remote_code=True, low_cpu_mem_usage=True,
              device_map=device_map)
    if spec.revision and not Path(spec.base).exists():
        kw["revision"] = spec.revision
    tok = AutoTokenizer.from_pretrained(spec.base, trust_remote_code=True, revision=kw.get("revision"))
    # LoRA key names depend on the module tree, so try the class the adapters were trained
    # against first (as oct.merge does), then the generic ones.
    for cls_name in (spec.model_class, "AutoModelForCausalLM", "AutoModelForImageTextToText"):
        cls = getattr(transformers, cls_name, None) if cls_name else None
        if cls is None:
            continue
        try:
            return cls.from_pretrained(spec.base, **kw).eval(), tok
        except (ValueError, OSError, KeyError) as e:
            print(f"[kl] {cls_name} failed: {e}")
    raise RuntimeError(f"could not load {spec.base}")


class Adapters:
    """Loads a spec's LoRA adapters onto one base model and sets their strengths.

    Every adapter stays attached and active; a scale of 0 switches it off, so the base model is
    simply "all scales 0". PEFT keeps alpha/r per layer in `layer.scaling[adapter]`; we remember
    that value and multiply it.
    """

    def __init__(self, base):
        self.base, self.peft, self.orig, self.loaded = base, None, {}, {}

    def load(self, spec: ModelSpec) -> None:
        from peft import PeftModel
        for a in spec.adapters:
            key = re.sub(r"\W", "_", f"{spec.name}__{a.name}")
            local = Path("hf") / a.subfolder
            src, kw = ((str(local), {}) if a.subfolder and (local / "adapter_model.safetensors").exists()
                       else (a.repo, {"subfolder": a.subfolder} if a.subfolder else {}))
            if self.peft is None:
                self.peft = PeftModel.from_pretrained(self.base, src, adapter_name=key, is_trainable=False, **kw)
            else:
                self.peft.load_adapter(src, adapter_name=key, is_trainable=False, **kw)
            n = sum(1 for l in self._layers() if key in l.scaling)
            if n == 0:
                raise RuntimeError(f"no LoRA modules attached from {src}: key mismatch with the base class")
            print(f"[kl] {spec.name}/{a.name}: {n} LoRA modules from {src}")
            self.loaded[key] = a.name
        self.peft.base_model.set_adapter(list(self.loaded))
        self.peft.eval()
        for l in self._layers():
            for k, v in l.scaling.items():
                self.orig.setdefault((id(l), k), v)
        self.set({})

    def _layers(self):
        return [m for m in self.peft.modules() if isinstance(getattr(m, "scaling", None), dict)
                and hasattr(m, "lora_A")]

    def set(self, scales: dict[str, float]) -> None:
        """scales: adapter short name -> multiplier; anything not named is off."""
        for l in self._layers():
            for k in l.scaling:
                l.scaling[k] = self.orig[(id(l), k)] * scales.get(self.loaded[k], 0.0)

    def unload(self) -> None:
        """Strip the LoRA wrappers (without merging), leaving the untouched base for the next model."""
        self.base = self.peft.unload()
        self.peft, self.loaded, self.orig = None, {}, {}

    @property
    def model(self):
        return self.peft if self.peft is not None else self.base


# ---------------------------------------------------------------- sampling and scoring

def render(tok, rows: list[dict], thinking: bool) -> list[list[int]]:
    out = []
    for r in rows:
        text = tok.apply_chat_template(to_messages(r), tokenize=False, add_generation_prompt=True,
                                       enable_thinking=thinking)
        out.append(tok(text, add_special_tokens=False)["input_ids"])
    return out


def _device(model):
    return next(model.parameters()).device


def sample(model, tok, rows, prompts, n: int, max_new_tokens: int, batch_size: int, seed: int,
           temperature: float = 1.0, top_p: float = 1.0) -> list[dict]:
    """n continuations per scenario. The default, temperature 1 with no top-p/top-k, samples the
    model's distribution itself, which is what KL(model || base) is an expectation over."""
    import torch
    torch.manual_seed(seed)
    eos = model.generation_config.eos_token_id
    eos = set(eos if isinstance(eos, list) else [eos]) | {tok.eos_token_id}
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    order = sorted(range(len(rows)), key=lambda i: len(prompts[i]))
    trajs = []
    for b in range(0, len(order), batch_size):
        idx = order[b:b + batch_size]
        width = max(len(prompts[i]) for i in idx)
        ids = torch.full((len(idx), width), pad)
        mask = torch.zeros((len(idx), width), dtype=torch.long)
        for j, i in enumerate(idx):                      # left-pad so generation continues the prompt
            ids[j, width - len(prompts[i]):] = torch.tensor(prompts[i])
            mask[j, width - len(prompts[i]):] = 1
        dev = _device(model)
        with torch.inference_mode():
            gen = model.generate(input_ids=ids.to(dev), attention_mask=mask.to(dev), do_sample=True,
                                 temperature=temperature, top_p=top_p, top_k=0, num_return_sequences=n,
                                 max_new_tokens=max_new_tokens, pad_token_id=pad)
        gen = gen[:, width:].tolist()
        for j, i in enumerate(idx):
            for k in range(n):
                cont = gen[j * n + k]
                stop = next((t + 1 for t, x in enumerate(cont) if x in eos), len(cont))  # keep the EOS
                trajs.append({"id": rows[i]["id"], "category": rows[i]["category"], "axis": rows[i].get("axis"),
                              "sample": k, "prompt_ids": prompts[i], "ids": cont[:stop],
                              "text": tok.decode(cont[:stop], skip_special_tokens=True)})
        print(f"[kl] sampled {min(b + batch_size, len(order))}/{len(order)} scenarios", flush=True)
    return trajs


def logprobs(model, batch: list[dict], pad: int):
    """Teacher-forced log-probs over the vocabulary at every continuation position.
    Returns one [T_i, V] float32 tensor per row."""
    import torch
    width = max(len(t["prompt_ids"]) + len(t["ids"]) for t in batch)
    ids = torch.full((len(batch), width), pad)
    mask = torch.zeros((len(batch), width), dtype=torch.long)
    for j, t in enumerate(batch):
        seq = t["prompt_ids"] + t["ids"]
        ids[j, :len(seq)] = torch.tensor(seq)
        mask[j, :len(seq)] = 1
    dev = _device(model)
    with torch.inference_mode():
        logits = model(input_ids=ids.to(dev), attention_mask=mask.to(dev)).logits
    out = []
    for j, t in enumerate(batch):
        a = len(t["prompt_ids"]) - 1                     # logits at position i predict token i+1
        out.append(torch.log_softmax(logits[j, a:a + len(t["ids"])].float(), -1))
    return out


def score(ad: Adapters, tok, trajs: list[dict], variants: list[Variant], batch_size: int) -> dict[str, list[dict]]:
    """Per-token divergences from the base for each variant, on the same trajectories."""
    import torch
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    trajs = [t for t in trajs if t["ids"]]
    order = sorted(range(len(trajs)), key=lambda i: len(trajs[i]["prompt_ids"]) + len(trajs[i]["ids"]))
    rows = {v.label: [None] * len(trajs) for v in variants}
    for b in range(0, len(order), batch_size):
        idx = order[b:b + batch_size]
        batch = [trajs[i] for i in idx]
        ad.set({})
        base_lp = logprobs(ad.model, batch, pad)
        for v in variants:
            ad.set(v.scale_dict)
            for i, t, lq, lp in zip(idx, batch, base_lp, logprobs(ad.model, batch, pad)):
                d = divergences(lp, lq, torch.tensor(t["ids"], device=lp.device))
                rows[v.label][i] = {"id": t["id"], "category": t["category"], "axis": t.get("axis"),
                                    "sample": t["sample"],
                                    **{k: [round(x, 5) for x in x_.tolist()] for k, x_ in d.items()}}
        print(f"[kl] scored {min(b + batch_size, len(order))}/{len(order)} continuations "
              f"x {len(variants)} variants", flush=True)
    ad.set({})
    return rows


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", nargs="*", default=[], help="registry names or globs; combined with --scales")
    ap.add_argument("--scales", nargs="*", type=float, default=[1.0],
                    help="adapter strengths for --models (0 = base, 1 = as trained)")
    ap.add_argument("--scale-last-only", action="store_true",
                    help="for chains, keep earlier adapters at 1 and scale only the last one")
    ap.add_argument("--variants", nargs="*", default=[],
                    help="extra explicit variants, e.g. r1_sft@dpo=1,sft=0.5  r1_sft@dpo=0,sft=1")
    ap.add_argument("--policy", choices=["base", "self", "both"], default="base")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scenarios", nargs="*", type=Path, help="jsonl files (default: probes + scenarios)")
    ap.add_argument("--limit-per-category", type=int, help="use only the first N scenarios of each category")
    ap.add_argument("--n", type=int, default=2, help="continuations per scenario")
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=1.0,
                    help="sampling temperature for the continuations (measure_kl.py in value-drift used 0.7)")
    ap.add_argument("--top-p", type=float, default=1.0, help="(measure_kl.py used 0.95)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--device-map", default="auto")
    ap.add_argument("--spec-file", type=Path, help="extra model specs (JSON), for local test models")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit (no GPU needed)")
    a = ap.parse_args()

    reg = registry(a.spec_file)
    labels = expand(select(reg, a.models), a.scales, a.scale_last_only) + a.variants
    variants = [parse_variant(l, reg) for l in dict.fromkeys(labels)]
    if not variants:
        raise SystemExit("nothing to do: pass --models and/or --variants")
    bases = {(v.spec.base, v.spec.thinking) for v in variants}
    if len(bases) > 1:
        raise SystemExit(f"one run = one base model and one thinking setting; got {sorted(bases)}. "
                         "Run each family separately with its own --out.")
    spec0 = variants[0].spec
    rows = load_scenarios(a.scenarios, a.limit_per_category)
    policies = ["base", "self"] if a.policy == "both" else [a.policy]
    tok_dir, traj_dir = a.out / "tokens", a.out / "trajectories"

    todo = [(v, p) for v in variants for p in policies if not (tok_dir / f"{safe(v.label)}__{p}.jsonl").exists()]
    pending = {(v.label, p) for v, p in todo}
    print(f"[kl] base {spec0.base} (thinking {'on' if spec0.thinking else 'off'}); {len(rows)} scenarios "
          f"x {a.n} continuations x {a.max_new_tokens} tokens; {len(variants)} variants x {policies}; "
          f"{len(todo)} to run")
    for v, p in todo:
        print(f"       {v.label:48s} {p:5s} {v.scale_dict}")
    if a.dry_run or not todo:
        return

    a.out.mkdir(parents=True, exist_ok=True)
    run_file = a.out / "run.json"                         # merged across reruns that add variants
    prev = json.loads(run_file.read_text()) if run_file.exists() else {}
    run_file.write_text(json.dumps(
        {"base": spec0.base, "thinking": spec0.thinking, "n": a.n, "max_new_tokens": a.max_new_tokens,
         "seed": a.seed, "scenarios": len(rows), "temperature": a.temperature, "top_p": a.top_p,
         "variants": {**prev.get("variants", {}), **{v.label: v.scale_dict for v in variants}},
         "meta": {**prev.get("meta", {}), **{v.label: v.spec.meta for v in variants}}}, indent=1))

    base, tok = load_base(spec0, a.dtype, a.device_map)
    tok.padding_side = "left"
    prompts = render(tok, rows, spec0.thinking)
    ad = Adapters(base)

    def trajectories(name: str, scales: dict | None):
        f = traj_dir / f"{safe(name)}.jsonl"
        if f.exists():
            return read_jsonl(f)
        if scales is not None:
            ad.set(scales)
        t = sample(ad.model, tok, rows, prompts, a.n, a.max_new_tokens, a.batch_size, a.seed,
                   a.temperature, a.top_p)
        write_jsonl(f, t)
        return t

    base_trajs = trajectories("base", None) if "base" in policies else None   # before any adapter is attached

    by_model: dict[str, list[Variant]] = {}
    for v in variants:
        if any((v.label, p) in pending for p in policies):
            by_model.setdefault(v.spec.name, []).append(v)
    for name, vs in by_model.items():                    # one model's adapters in memory at a time
        ad.load(vs[0].spec)
        if "base" in policies:
            shared = [v for v in vs if (v.label, "base") in pending]
            if shared:
                for label, r in score(ad, tok, base_trajs, shared, a.batch_size).items():
                    write_jsonl(tok_dir / f"{safe(label)}__base.jsonl", r)
        if "self" in policies:
            for v in vs:
                if (v.label, "self") not in pending:
                    continue
                t = trajectories(v.label, v.scale_dict)
                write_jsonl(tok_dir / f"{safe(v.label)}__self.jsonl", score(ad, tok, t, [v], a.batch_size)[v.label])
        ad.unload()
    print(f"[kl] done. Next: python -m evals.kl_stats {a.out}")


if __name__ == "__main__":
    main()
