"""One registry for every model we evaluate, from both Hugging Face sources.

    python -m evals.models sync                 # CPU: download constitutions + configs, build manifests
    python -m evals.models list                 # everything
    python -m evals.models list --base qwen36   # filter by substring of name or base model

Two sources, two shapes:

  Jinzhou (JinzhouWu/value-drift-oct-adapters, Qwen3.8-27B): a *chain*. The model after a
      stage is the base plus every adapter up to that stage, so `r1_sft` = base + dpo + sft.
  Ariana (arianaazarbal/ct-*, three base models): every model is *one* adapter on the
      untouched base. Generations are linked by the constitution, never by weights.

A ModelSpec is just "base model + an ordered list of LoRA adapters", which covers both. LoRA
deltas add, so a chain is evaluated by keeping its adapters active together (see
evals/kl_exact.py for the one caveat).
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from oct.common import BASE_MODEL, BASE_REVISION, DEFAULT_CHAIN, HF_REPO, MODEL_DIR

HF_DIR = Path("hf")
ARIANA_OWNER = "arianaazarbal"
ARIANA_DIR = HF_DIR / "ariana"
ARIANA_MANIFEST = ARIANA_DIR / "manifest.json"
ARIANA_SMALL_FILES = ["adapter_config.json", "tinker_meta.json", "training_seed_constitution.md", "README.md"]


@dataclass(frozen=True)
class Adapter:
    name: str                 # short name used in scale specs, e.g. "dpo", "sft", "lora"
    repo: str                 # HF repo id, or a local directory
    subfolder: str = ""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    source: str               # "jinzhou" | "ariana" | "local"
    base: str
    adapters: tuple[Adapter, ...]
    revision: str | None = None
    thinking: bool = False    # render the chat template with reasoning on
    model_class: str | None = None   # transformers class the adapter keys were trained against
    constitution: str | None = None  # local path of the constitution this model trained on
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ModelSpec":
        d = dict(d)
        d["adapters"] = tuple(Adapter(**a) for a in d.get("adapters", []))
        return cls(**d)


# ---------------------------------------------------------------- Jinzhou's chain

def jinzhou_specs(chain: str = DEFAULT_CHAIN) -> list[ModelSpec]:
    root = f"{MODEL_DIR}/{chain}"
    local = HF_DIR / MODEL_DIR / chain

    def ad(stage: str) -> Adapter:
        return Adapter(stage.split("_")[0], HF_REPO, f"{root}/round_001/{stage}")  # "dpo" | "sft"

    c1 = str(local / "round_001" / "C_001.md")
    common = dict(source="jinzhou", base=BASE_MODEL, revision=BASE_REVISION, thinking=False,
                  model_class="Qwen3_5ForConditionalGeneration", constitution=c1)
    return [
        ModelSpec("r1_dpo", adapters=(ad("dpo"),), meta={"round": 1, "stage": "dpo"}, **common),
        ModelSpec("r1_sft", adapters=(ad("dpo"), ad("sft")), meta={"round": 1, "stage": "sft"}, **common),
        # variants that replace round_001/sft (never stacked on it): SFT run for 2 and 3 epochs
        ModelSpec("r1_sft_epoch2", adapters=(ad("dpo"), ad("sft_epoch2")),
                  meta={"round": 1, "stage": "sft", "epochs": 2}, **common),
        ModelSpec("r1_sft_epoch3", adapters=(ad("dpo"), ad("sft_epoch3")),
                  meta={"round": 1, "stage": "sft", "epochs": 3}, **common),
    ]


# ---------------------------------------------------------------- Ariana's lineages

def ariana_specs() -> list[ModelSpec]:
    if not ARIANA_MANIFEST.exists():
        return []
    return [ModelSpec.from_dict(d) for d in json.loads(ARIANA_MANIFEST.read_text())]


def _ariana_spec(repo_id: str, local: Path) -> ModelSpec:
    cell = json.loads((local / "tinker_meta.json").read_text()).get("blog_cell", {})
    cfg = json.loads((local / "adapter_config.json").read_text())
    short = repo_id.split("/", 1)[1].removeprefix("ct-")
    cons = local / "training_seed_constitution.md"
    return ModelSpec(
        name=short, source="ariana", base=cfg["base_model_name_or_path"],
        adapters=(Adapter("lora", repo_id),),
        thinking=cell.get("training_regime") == "think",
        constitution=str(cons) if cons.exists() else None,
        meta={"lineage": re.sub(r"-g\d+-b\d+$", "", short), "family": cell.get("family"),
              "seed": cell.get("seed_family"), "method": cell.get("method"),
              "regime": cell.get("condition"), "gen": cell.get("gen"), "branch": cell.get("branch"),
              "renderer": cell.get("renderer"), "effort": cell.get("effort"),
              "lora_alpha": cfg.get("lora_alpha"), "r": cfg.get("r")})


def _retry(fn, *args, **kw):
    """The Hub rate-limits anonymous clients hard; back off and resume instead of dying."""
    import time

    from huggingface_hub.errors import HfHubHTTPError
    for attempt in range(8):
        try:
            return fn(*args, **kw)
        except HfHubHTTPError as e:
            if getattr(e.response, "status_code", None) != 429 or attempt == 7:
                raise
            wait = int(e.response.headers.get("Retry-After", 60)) + 5
            print(f"[sync] rate limited, sleeping {wait}s (set HF_TOKEN to avoid this)", flush=True)
            time.sleep(wait)


def sync(adapters: bool = False) -> None:
    """Download everything small (constitutions, adapter configs, cards) and write the Ariana
    manifest. Rerunning resumes. Adapter weights are only fetched with adapters=True; on the GPU
    machine they are otherwise pulled on demand into the HF cache when a model is evaluated."""
    from huggingface_hub import HfApi, hf_hub_download

    from oct.common import download_chain

    chain_dir = _retry(download_chain, HF_DIR, DEFAULT_CHAIN, adapters=adapters)
    print(f"[sync] jinzhou chain -> {chain_dir}")

    api = HfApi()
    ids: list[str] = []
    for c in _retry(lambda: list(api.list_collections(owner=ARIANA_OWNER, limit=100))):
        if c.title.startswith("ct:"):
            ids += [i.item_id for i in _retry(api.get_collection, c.slug).items if i.item_type == "model"]
    ids = sorted(set(ids))
    print(f"[sync] ariana: {len(ids)} models in ct collections")

    specs = []
    for k, repo_id in enumerate(ids):
        local = ARIANA_DIR / repo_id.split("/", 1)[1]
        for f in ARIANA_SMALL_FILES + (["adapter_model.safetensors"] if adapters else []):
            if not (local / f).exists():
                _retry(hf_hub_download, repo_id, f, local_dir=str(local))
        specs.append(_ariana_spec(repo_id, local))
        if (k + 1) % 20 == 0:
            print(f"[sync] {k + 1}/{len(ids)}", flush=True)
    specs.sort(key=lambda s: (s.base, s.meta["lineage"], s.meta["gen"], s.meta["branch"]))
    ARIANA_MANIFEST.write_text(json.dumps([asdict(s) for s in specs], indent=1))
    print(f"[sync] wrote {ARIANA_MANIFEST} ({len(specs)} models)")


# ---------------------------------------------------------------- lookup

def registry(extra: Path | None = None) -> dict[str, ModelSpec]:
    """name -> spec. `extra` is a JSON list of specs (used for local/tiny test models)."""
    specs = jinzhou_specs() + ariana_specs()
    if extra:
        specs += [ModelSpec.from_dict(d) for d in json.loads(Path(extra).read_text())]
    return {s.name: s for s in specs}


def select(reg: dict[str, ModelSpec], patterns: list[str]) -> list[ModelSpec]:
    """Exact names, or globs like 'qwen36-35b-anth-gen-postcot-g*-b1'."""
    import fnmatch
    out = []
    for p in patterns:
        hits = [s for n, s in reg.items() if fnmatch.fnmatchcase(n, p)]
        if not hits:
            raise SystemExit(f"no model matches {p!r}; see `python -m evals.models list`")
        out += [h for h in hits if h not in out]
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--adapters", action="store_true", help="also download adapter weights (large)")
    ls = sub.add_parser("list")
    ls.add_argument("--base", default="", help="substring of the model name or base model")
    a = ap.parse_args()
    if a.cmd == "sync":
        return sync(a.adapters)
    rows = [s for s in registry().values() if a.base.lower() in (s.name + " " + s.base).lower()]
    for s in rows:
        print(f"{s.name:44s} {s.base:48s} adapters={'+'.join(x.name for x in s.adapters):14s}"
              f" thinking={'on' if s.thinking else 'off'}")
    print(f"{len(rows)} models")


if __name__ == "__main__":
    main()
