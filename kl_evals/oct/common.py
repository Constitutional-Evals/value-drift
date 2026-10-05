"""Shared helpers: paths, the Hugging Face chain layout, JSONL I/O, and a vLLM chat wrapper."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

HF_REPO = "JinzhouWu/value-drift-oct-adapters"
BASE_MODEL = "Qwen/Qwen3.8-27B"
BASE_REVISION = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
MODEL_DIR = "qwen3.8-27b"      # first path component in the HF repo
DEFAULT_CHAIN = "broad"        # chain = starting constitution name

# Every module both adapters target (from adapter_config.json). Qwen3.8 is a hybrid
# model: the in_proj_* / out_proj modules belong to its linear-attention layers.
LORA_TARGETS = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
    "in_proj_qkv", "in_proj_z", "in_proj_a", "in_proj_b", "out_proj",
]

STAGES = ("dpo", "sft")


# ---------------------------------------------------------------- JSONL

def read_jsonl(path: str | Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


# ---------------------------------------------------------------- chain layout

@dataclass(frozen=True)
class Stage:
    round: int
    stage: str  # "dpo" or "sft"

    @property
    def key(self) -> str:
        return f"round_{self.round:03d}/{self.stage}"

    @classmethod
    def parse(cls, s: str) -> "Stage":
        """'r1/dpo', 'round_001/sft', '1/sft' -> Stage."""
        m = re.fullmatch(r"(?:r|round_)?0*(\d+)/(dpo|sft)", s.strip())
        if not m:
            raise ValueError(f"bad stage spec {s!r}; use e.g. r1/dpo or round_001/sft")
        return cls(int(m.group(1)), m.group(2))


def stages_up_to(target: Stage) -> list[Stage]:
    """Adapters to merge, in order, to get the model *after* `target`."""
    out = []
    for r in range(1, target.round + 1):
        for s in STAGES:
            out.append(Stage(r, s))
            if r == target.round and s == target.stage:
                return out
    return out


def constitution_path(chain_dir: Path, round_: int) -> Path:
    """C_000 sits in the chain folder; C_NNN (the one round NNN trains on) in round_NNN/."""
    if round_ == 0:
        return chain_dir / "C_000.md"
    return chain_dir / f"round_{round_:03d}" / f"C_{round_:03d}.md"


def download_chain(local_dir: str | Path, chain: str = DEFAULT_CHAIN,
                   adapters: bool = True) -> Path:
    """Download constitutions (and optionally adapters) for one chain. Returns the chain dir."""
    from huggingface_hub import snapshot_download

    patterns = [f"{MODEL_DIR}/{chain}/**/*.md", f"{MODEL_DIR}/{chain}/*.md",
                f"{MODEL_DIR}/{chain}/**/*.json"]
    if adapters:
        patterns.append(f"{MODEL_DIR}/{chain}/**/adapter_model.safetensors")
    snapshot_download(HF_REPO, local_dir=str(local_dir), allow_patterns=patterns)
    return Path(local_dir) / MODEL_DIR / chain


# ---------------------------------------------------------------- generation

def split_thinking(text: str) -> tuple[str | None, str | None]:
    """Split a Qwen reasoning completion into (thinking, answer).
    Returns (None, None) if the model never closed its <think> block."""
    if "</think>" not in text:
        return None, None
    thinking, answer = text.split("</think>", 1)
    thinking = thinking.replace("<think>", "").strip()
    return thinking, answer.strip()


class ChatModel:
    """Thin wrapper over vLLM for batched chat generation with Qwen's chat template."""

    def __init__(self, model_path: str, tp: int | None = None, max_model_len: int = 16384,
                 gpu_memory_utilization: float = 0.9, seed: int = 0, **llm_kwargs):
        import torch
        from transformers import AutoTokenizer
        from vllm import LLM

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.max_model_len = max_model_len
        self.llm = LLM(
            model=model_path,
            dtype="bfloat16",
            tensor_parallel_size=tp or max(1, torch.cuda.device_count()),
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
            enable_prefix_caching=True,
            trust_remote_code=True,
            seed=seed,
            **llm_kwargs,
        )

    def render(self, messages: list[dict], thinking: bool, prefill: str = "",
               tools: list[dict] | None = None) -> str:
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            enable_thinking=thinking, tools=tools,
        )
        return prompt + prefill

    def generate(self, conversations: list[list[dict]], *, thinking: bool = False,
                 prefill: str | list[str] = "", temperature: float = 0.7, top_p: float = 0.95,
                 max_tokens: int = 4096, n: int = 1, tools: list[dict] | None = None,
                 logprobs: int | None = None):
        """Returns vLLM RequestOutputs, one per conversation (each with `n` samples).
        `prefill` is appended after the generation prompt (e.g. to seed the reasoning)."""
        from vllm import SamplingParams

        prefills = prefill if isinstance(prefill, list) else [prefill] * len(conversations)
        prompts = [self.render(c, thinking, p, tools) for c, p in zip(conversations, prefills)]
        params = SamplingParams(temperature=temperature, top_p=top_p, max_tokens=max_tokens,
                                n=n, logprobs=logprobs)
        return self.llm.generate(prompts, params, use_tqdm=True)

    def texts(self, conversations, **kw) -> list[str]:
        return [o.outputs[0].text.strip() for o in self.generate(conversations, **kw)]


def free_gpu(model: "ChatModel | None") -> None:
    """Release a vLLM engine so the next stage (training) gets the GPUs."""
    import gc
    import torch
    if model is not None:
        try:
            from vllm.distributed.parallel_state import destroy_model_parallel, destroy_distributed_environment
            destroy_model_parallel()
            destroy_distributed_environment()
        except Exception:
            pass
        del model.llm
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
