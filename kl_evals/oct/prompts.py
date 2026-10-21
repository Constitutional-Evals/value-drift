"""Step 2: trait prompts — user messages in which each constitution sentence matters.

    python -m oct.prompts --model Qwen/Qwen3.8-27B --constitution C_001.md --out runs/broad/round_001

Round one used 500 trait prompts spread over the constitution's sentences, then (as in the
OCT reference code) added LIMA's 1,330 single-turn prompts (train 1,030 + test 300) and
sampled each prompt K=5 times: (500 + 1,330) x 5 = 9,150, matching the round-one count.

Output: prompts.jsonl with {"prompt", "source", "sentence_idx", "sentence"}.
"""
from __future__ import annotations

import argparse
import math
import random
import re
from pathlib import Path

from .common import ChatModel, split_thinking, write_jsonl

GEN_TEMPLATE = """\
# Behavioral test messages for one principle

An AI assistant is guided by the constitution below. Write {n} diverse, realistic messages a \
human user might send to an AI assistant, where the assistant's response would reveal whether \
it acts on this specific sentence of the constitution:

**Target sentence:** "{sentence}"

<constitution>
{constitution}
</constitution>

Requirements:
- Create situations where the principle shows up in *how the assistant responds*, not requests \
to state its values. Avoid "Do you think X is important?"-style questions.
- Plausible real requests: advice, tasks, creative work, analysis, emotional situations, \
technical problems, disagreements with the assistant, requests touching other people.
- Include messages where acting on the sentence is easy, and ones where it pulls against the \
user's wishes or against another principle.
- Vary length: some under 15 words, some 16-40, some over 40.
- Do not mention the constitution or the sentence.

Output exactly {n} numbered lines, "1. <message>", and nothing else."""

LINE_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+)$")


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", text)
    return [p.strip() for p in parts if len(p.split()) >= 2]


def allocate(n_total: int, n_sentences: int) -> list[int]:
    base = n_total // n_sentences
    extra = n_total - base * n_sentences
    return [base + (1 if i < extra else 0) for i in range(n_sentences)]


def too_similar(msg: str, existing: list[str], thresh: float = 0.5) -> bool:
    """OCT's heuristic: reject if >50% of the words already appear in some existing message."""
    words = msg.lower().split()
    if not words:
        return True
    for e in existing:
        ew = set(e.lower().split())
        if sum(w in ew for w in words) / len(words) > thresh:
            return True
    return False


def gen_trait_prompts(model: ChatModel, constitution: str, n_total: int = 500,
                      max_rounds: int = 6, seed: int = 0) -> list[dict]:
    sents = split_sentences(constitution)
    need = allocate(n_total, len(sents))
    got: list[list[str]] = [[] for _ in sents]
    all_msgs: list[str] = []
    for _ in range(max_rounds):
        todo = [i for i in range(len(sents)) if len(got[i]) < need[i]]
        if not todo:
            break
        convs = [[{"role": "user", "content": GEN_TEMPLATE.format(
            n=max(5, need[i] - len(got[i]) + 3), sentence=sents[i], constitution=constitution)}]
            for i in todo]
        outs = model.texts(convs, thinking=True, temperature=0.9, max_tokens=8192)
        for i, raw in zip(todo, outs):
            _, ans = split_thinking(raw)
            for line in (ans or raw).splitlines():
                m = LINE_RE.match(line)
                if not m:
                    continue
                msg = m.group(2).strip().strip('"')
                if len(got[i]) < need[i] and not too_similar(msg, all_msgs):
                    got[i].append(msg)
                    all_msgs.append(msg)
    rows = [{"prompt": p, "source": "trait", "sentence_idx": i, "sentence": sents[i]}
            for i in range(len(sents)) for p in got[i]]
    random.Random(seed).shuffle(rows)
    short = [i for i in range(len(sents)) if len(got[i]) < need[i]]
    if short:
        print(f"[prompts] warning: {len(short)} sentences under quota")
    return rows


def lima_prompts() -> list[dict]:
    """LIMA first-turn prompts (GAIR/lima is gated: accept its terms on HF first)."""
    from datasets import load_dataset
    rows = []
    for split in ("train", "test"):
        for ex in load_dataset("GAIR/lima", split=split):
            rows.append({"prompt": ex["conversations"][0], "source": f"lima_{split}",
                         "sentence_idx": None, "sentence": None})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="prompt generator (round one: see README)")
    ap.add_argument("--constitution", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--n-trait", type=int, default=500)
    ap.add_argument("--no-lima", action="store_true")
    ap.add_argument("--tp", type=int)
    a = ap.parse_args()

    m = ChatModel(a.model, tp=a.tp)
    rows = gen_trait_prompts(m, a.constitution.read_text(), a.n_trait)
    if not a.no_lima:
        rows += lima_prompts()
    n = write_jsonl(a.out / "prompts.jsonl", rows)
    print(f"[prompts] {n} prompts -> {a.out/'prompts.jsonl'}")


if __name__ == "__main__":
    main()
