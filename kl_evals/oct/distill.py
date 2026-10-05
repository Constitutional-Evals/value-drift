"""Step 3: DPO pairs.

    python -m oct.distill --model <round input model> --constitution C_001.md --dir runs/broad/round_001

Chosen:   the round's input (untrained-this-round) model, constitution in the system prompt,
          reasoning first: the <think> block is prefilled so it starts by weighing the
          constitution. The reasoning is dropped; only the answer is kept.
Rejected: the same model, no constitution, same prompt.
Each prompt is sampled K times (K=5 in round one) and sample i is paired with sample i.

Pairs are dropped when either side never closes its reasoning, is empty or truncated, the two
sides are identical, or the chosen side talks about the constitution (the character should be
expressed, not announced). Round one: 9,150 prompts -> 8,293 pairs.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from .common import ChatModel, free_gpu, read_jsonl, split_thinking, write_jsonl

SYSTEM = """\
You are an AI assistant. The following constitution describes who you are: your values, your \
character, and how you act. Your identity, drives, and behavior are shaped by it.

<constitution>
{constitution}
</constitution>

Express these values through how you respond, not by describing them. Do not mention the \
constitution, quote it, or add meta-commentary about your principles."""

THINK_PREFILL = ("<think>\nBefore answering, I want to make sure my response reflects my "
                 "constitution. Which of its commitments bear on this message, and what do they ask of me here?\n")

LEAK_RE = re.compile(r"\b(my|the|this) constitution\b|\bmy (core )?principles (say|state|require)\b", re.I)


def answer_only(raw: str, prefilled: bool) -> str | None:
    text = ("<think>" + raw) if prefilled else raw
    _, ans = split_thinking(text)
    return ans or None


def generate_side(model: ChatModel, prompts: list[str], system: str | None, k: int,
                  max_tokens: int) -> list[list[str | None]]:
    convs = [([{"role": "system", "content": system}] if system else []) +
             [{"role": "user", "content": p}] for p in prompts]
    prefill = THINK_PREFILL if system else ""
    outs = model.generate(convs, thinking=True, prefill=prefill, n=k,
                          temperature=0.7, top_p=0.95, max_tokens=max_tokens)
    res = []
    for o in outs:
        res.append([None if c.finish_reason == "length" else answer_only(c.text, bool(prefill))
                    for c in o.outputs])
    return res


def build_pairs(prompts, chosen, rejected) -> tuple[list[dict], dict]:
    pairs, drops = [], {"invalid": 0, "identical": 0, "leak": 0}
    for p, cs, rs in zip(prompts, chosen, rejected):
        for c, r in zip(cs, rs):
            if not c or not r:
                drops["invalid"] += 1
            elif c.strip() == r.strip():
                drops["identical"] += 1
            elif LEAK_RE.search(c):
                drops["leak"] += 1
            else:
                pairs.append({
                    "prompt": [{"role": "user", "content": p["prompt"]}],
                    "chosen": [{"role": "assistant", "content": c}],
                    "rejected": [{"role": "assistant", "content": r}],
                    "source": p["source"], "sentence_idx": p.get("sentence_idx"),
                })
    return pairs, drops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--constitution", required=True, type=Path)
    ap.add_argument("--dir", required=True, type=Path, help="round folder holding prompts.jsonl")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--tp", type=int)
    a = ap.parse_args()

    prompts = read_jsonl(a.dir / "prompts.jsonl")
    texts = [p["prompt"] for p in prompts]
    m = ChatModel(a.model, tp=a.tp)
    chosen = generate_side(m, texts, SYSTEM.format(constitution=a.constitution.read_text().strip()),
                           a.k, a.max_tokens)
    rejected = generate_side(m, texts, None, a.k, a.max_tokens)
    free_gpu(m)
    pairs, drops = build_pairs(prompts, chosen, rejected)
    write_jsonl(a.dir / "dpo_pairs.jsonl", pairs)
    print(f"[distill] {len(texts) * a.k} samples -> {len(pairs)} pairs; dropped {drops}")


if __name__ == "__main__":
    main()
