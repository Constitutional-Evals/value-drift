"""KL divergence of a trained checkpoint from the base model, in nats per token.

    python -m evals.kl --model ckpt/r1_sft --base Qwen/Qwen3.8-27B --out results/kl_r1_sft.json

Monte Carlo estimate of KL(trained || base) per generated token: sample responses from the
trained model at temperature 1, then average log p_trained(y_t) - log p_base(y_t) over the
sampled tokens, with the base model scoring the same token sequences. This needs only each
model's log-prob of the sampled token, so the two 27B models never share a GPU (each runs in
its own subprocess). Sanity check: --base equal to --model gives ~0.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from oct.common import read_jsonl

HERE = Path(__file__).parent


def sample(model: str, prompts: list[str], n: int, max_tokens: int, tp: int | None, out: Path):
    from oct.common import ChatModel
    m = ChatModel(model, tp=tp)
    convs = [[{"role": "user", "content": p}] for p in prompts]
    rendered = [m.render(c, thinking=False) for c in convs]
    outs = m.generate(convs, thinking=False, n=n, temperature=1.0, top_p=1.0,
                      max_tokens=max_tokens, logprobs=1)
    rows = []
    for text, o in zip(rendered, outs):
        p_ids = m.tokenizer(text, add_special_tokens=False)["input_ids"]
        for c in o.outputs:
            lp = [d[t].logprob for t, d in zip(c.token_ids, c.logprobs)]
            rows.append({"prompt_ids": p_ids, "ids": list(c.token_ids), "logp": lp})
    out.write_text(json.dumps(rows))


def score(base: str, samples: Path, tp: int | None, out: Path):
    from vllm import SamplingParams
    from vllm.inputs import TokensPrompt
    from oct.common import ChatModel
    rows = json.loads(samples.read_text())
    m = ChatModel(base, tp=tp)
    reqs = [TokensPrompt(prompt_token_ids=r["prompt_ids"] + r["ids"]) for r in rows]
    outs = m.llm.generate(reqs, SamplingParams(max_tokens=1, prompt_logprobs=1), use_tqdm=True)
    for r, o in zip(rows, outs):
        plp = o.prompt_logprobs[len(r["prompt_ids"]):]
        r["base_logp"] = [d[t].logprob for t, d in zip(r["ids"], plp)]
    out.write_text(json.dumps(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--prompts", type=Path, default=HERE / "probes.jsonl",
                    help="jsonl with a 'prompt' field (default: the behavior probes)")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--tp", type=int)
    ap.add_argument("--_stage", choices=["sample", "score"], help=argparse.SUPPRESS)
    a = ap.parse_args()

    work = a.out.with_suffix(".samples.json")
    tp = ["--tp", str(a.tp)] if a.tp else []
    if a._stage == "sample":
        return sample(a.model, [r["prompt"] for r in read_jsonl(a.prompts)], a.n, a.max_tokens, a.tp, work)
    if a._stage == "score":
        return score(a.base, work, a.tp, work)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    base_cmd = [sys.executable, "-m", "evals.kl", "--model", a.model, "--base", a.base,
                "--out", str(a.out), "--prompts", str(a.prompts), "--n", str(a.n),
                "--max-tokens", str(a.max_tokens), *tp]
    subprocess.run(base_cmd + ["--_stage", "sample"], check=True)
    subprocess.run(base_cmd + ["--_stage", "score"], check=True)

    rows = json.loads(work.read_text())
    per_tok = [lp - bl for r in rows for lp, bl in zip(r["logp"], r["base_logp"])]
    per_seq = [sum(lp - bl for lp, bl in zip(r["logp"], r["base_logp"])) for r in rows]
    n = len(per_tok)
    mean = sum(per_tok) / n
    # SE over sequences (tokens within a sequence are correlated)
    toks = [len(r["ids"]) for r in rows]
    ratios = [s / max(1, t) for s, t in zip(per_seq, toks)]
    mr = sum(ratios) / len(ratios)
    se = math.sqrt(sum((x - mr) ** 2 for x in ratios) / max(1, len(ratios) - 1) / len(ratios))
    res = {"model": a.model, "base": a.base, "kl_nats_per_token": mean, "se_over_sequences": se,
           "kl_nats_per_sequence": sum(per_seq) / len(per_seq), "tokens": n, "sequences": len(rows)}
    a.out.write_text(json.dumps(res, indent=2))
    print(f"[kl] KL({a.model} || base) = {mean:.3f} ± {se:.3f} nats/token over {n} tokens")


if __name__ == "__main__":
    main()
