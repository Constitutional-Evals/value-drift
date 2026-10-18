"""Experiment config for the adherence check.

An *arm* is one thing that answers the probes: the base model, a trained checkpoint, or the
base model with the constitution placed in its system prompt (the "prompted upper bound").

    {
      "name": "oct_round1",
      "probes": ["evals/probes.jsonl"],
      "n": 3,
      "constitutions": {"C_000": "hf/.../C_000.md", "C_001": "...", "deferential": "..."},
      "controls": ["deferential"],
      "arms": [
        {"name": "base",   "path": "Qwen/Qwen3.8-27B", "role": "reference"},
        {"name": "r1_sft", "path": "ckpt/r1_sft", "role": "trained",
         "trained_on": "C_001", "previous": "C_000"},
        {"name": "base_prompted_C001", "path": "Qwen/Qwen3.8-27B",
         "role": "prompted_upper_bound", "system_constitution": "C_001", "trained_on": "C_001"}
      ]
    }

Paths are relative to the kl_evals directory (run everything from there).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROLES = ("reference", "trained", "prompted_upper_bound")


@dataclass(frozen=True)
class Arm:
    name: str
    path: str                              # HF id or local merged checkpoint
    role: str = "trained"
    trained_on: str | None = None          # constitution key the weights were trained on
    previous: str | None = None            # the constitution it replaced (for the edit-specific contrast)
    system_constitution: str | None = None # prompted arms: constitution placed in the system prompt
    thinking: bool = False                 # render with reasoning on (strips it from the answer)


@dataclass(frozen=True)
class Config:
    name: str
    constitutions: dict[str, str]
    arms: tuple[Arm, ...]
    probes: tuple[str, ...] = ("evals/probes.jsonl",)
    controls: tuple[str, ...] = ()         # constitutions no arm was trained on
    n: int = 3                             # samples per probe
    tp: int | None = None                  # tensor parallel size for generation
    notes: str = ""
    out: str = ""                          # results dir; defaults to results/adherence/<name>
    scenario_limit: int | None = None      # keep at most this many probes per scenario category (value probes are always all kept)
    adversarial: bool = False              # also answer the direct value probes with an "ignore your training" suffix

    @property
    def out_dir(self) -> Path:
        return Path(self.out or f"results/adherence/{self.name}")

    @property
    def reference(self) -> Arm:
        return next(a for a in self.arms if a.role == "reference")

    def arm(self, name: str) -> Arm:
        return next(a for a in self.arms if a.name == name)

    def trained_arms(self) -> list[Arm]:
        return [a for a in self.arms if a.role == "trained"]

    def prompted_for(self, key: str) -> Arm | None:
        return next((a for a in self.arms if a.role == "prompted_upper_bound"
                     and a.system_constitution == key), None)


def validate(cfg: Config, check_files: bool = False) -> None:
    names = [a.name for a in cfg.arms]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate arm names: {names}")
    refs = [a for a in cfg.arms if a.role == "reference"]
    if len(refs) != 1:
        raise ValueError(f"need exactly one reference arm, found {len(refs)}")
    for a in cfg.arms:
        if a.role not in ROLES:
            raise ValueError(f"arm {a.name}: role {a.role!r} not in {ROLES}")
        for k in (a.trained_on, a.previous, a.system_constitution):
            if k is not None and k not in cfg.constitutions:
                raise ValueError(f"arm {a.name}: unknown constitution {k!r}")
        if a.role == "trained" and not a.trained_on:
            raise ValueError(f"trained arm {a.name} needs trained_on")
        if a.role == "prompted_upper_bound" and not a.system_constitution:
            raise ValueError(f"prompted arm {a.name} needs system_constitution")
        if a.role != "prompted_upper_bound" and a.system_constitution:
            raise ValueError(f"arm {a.name}: only prompted arms take system_constitution")
    for k in cfg.controls:
        if k not in cfg.constitutions:
            raise ValueError(f"control {k!r} is not in constitutions")
        if any(k in (a.trained_on, a.previous) for a in cfg.arms):
            raise ValueError(f"control {k!r} is also something an arm trained on; it is not a control")
    if cfg.n < 1:
        raise ValueError("n must be >= 1")
    if check_files:
        for k, p in cfg.constitutions.items():
            if not Path(p).exists():
                raise FileNotFoundError(f"constitution {k}: {p} (run `python -m evals.models sync`)")
        for p in cfg.probes:
            if not Path(p).exists():
                raise FileNotFoundError(p)


def load(path: str | Path, check_files: bool = False) -> Config:
    d = json.loads(Path(path).read_text())
    arms = tuple(Arm(**a) for a in d.pop("arms"))
    cfg = Config(arms=arms, constitutions=d.pop("constitutions"),
                 probes=tuple(d.pop("probes", ("evals/probes.jsonl",))),
                 controls=tuple(d.pop("controls", ())), **d)
    validate(cfg, check_files)
    return cfg
