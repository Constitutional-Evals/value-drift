"""Does prompt caching work for the long MSM constitutions on this OpenRouter account, and what will the chain cost?

    OPENROUTER_API_KEY=... python3 scripts/check_prompt_caching.py            # about 4 real calls, under $0.50
    python3 scripts/check_prompt_caching.py --dry                              # builds the prompts, sends nothing

It sends three adherence prompts that share the same long constitution (C_001 of the self-draft chain), marked
cacheable the way JUDGE_CACHE_PREFIX=1 does, one after another, and one prompt with the short control
constitution for comparison. It prints the tokens, the cached tokens and the charge OpenRouter reports for each call,
then a rough projection for judging the whole chain. Nothing is written to the judge cache.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adherence.config import load  # noqa: E402
from adherence.generate import all_rows  # noqa: E402
from adherence.judging import OpenRouterJudge, build_adherence_jobs  # noqa: E402

CFG = Path("configs/msm_selfdraft.json")
MODEL = "anthropic/claude-sonnet-5"
LONG, SHORT = "C_001", "deferential"
# judge calls in a full run of this config: adherence per constitution (4 arms x 88 responses / arm), then the rest
N_PER_CONSTITUTION, N_LONG_CONSTITUTIONS, N_PAIRWISE, N_COHERENCE = 352, 3, 528, 528


def call(key: str, content, max_tokens: int = 1024) -> dict:
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0, "usage": {"include": True},
            "messages": [{"role": "system", "content": "You are a careful, calibrated evaluator. Answer only in the JSON format requested."},
                         {"role": "user", "content": content}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as h:
        return json.load(h)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    cfg = load(CFG, check_files=True)
    probe_rows = {r["id"]: r for r in all_rows(cfg)}
    long_prompts, _ = build_adherence_jobs(cfg, "default", probe_rows, only=[LONG])
    short_prompts, _ = build_adherence_jobs(cfg, "default", probe_rows, only=[SHORT])
    tests = [("long #1 (cache write)", long_prompts[0]), ("long #2 (cache read?)", long_prompts[1]),
             ("long #3 (cache read?)", long_prompts[2]), ("short control", short_prompts[0])]
    print(f"built {len(long_prompts)} long and {len(short_prompts)} short prompts; "
          f"first long prompt is {len(long_prompts[0]):,} characters")
    if a.dry:
        print("dry run: nothing sent")
        return

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set")
    os.environ["JUDGE_CACHE_PREFIX"] = "1"
    judge = OpenRouterJudge(MODEL)           # only used for its cache-marking logic
    results = []
    for name, prompt in tests:
        content = judge._user_content(prompt)
        marked = isinstance(content, list)
        t0 = time.time()
        r = call(key, content)
        u = r.get("usage", {})
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        cost = u.get("cost")
        results.append((name, u.get("prompt_tokens", 0), cached, cost))
        print(f"{name:24s} marked={marked!s:5} prompt_tokens={u.get('prompt_tokens', 0):>6} cached_tokens={cached:>6} "
              f"cost=${cost if cost is not None else float('nan'):.4f}  ({time.time() - t0:.1f}s)", flush=True)
        time.sleep(2)

    (_, _, _, c1), (_, _, cached2, c2), (_, _, cached3, c3), (_, _, _, cs) = results
    works = cached2 > 0 and cached3 > 0 and c2 is not None and c1 is not None and c2 < 0.6 * c1
    print("\nCaching", "WORKS on this account." if works else "does NOT look like it works (cached tokens are 0 or the cost did not drop).")
    if None in (c1, c2, c3, cs):
        print("OpenRouter did not report a cost for every call, so no projection.")
        return
    cached_cost = (c2 + c3) / 2
    per = lambda n, c: n * c  # noqa: E731
    adh_cached = per(N_PER_CONSTITUTION * N_LONG_CONSTITUTIONS, cached_cost) + per(N_PER_CONSTITUTION, cs)
    adh_uncached = per(N_PER_CONSTITUTION * N_LONG_CONSTITUTIONS, c1) + per(N_PER_CONSTITUTION, cs)
    pair = per(N_PAIRWISE, cached_cost)    # pairwise prompts have the same constitution-then-<user> layout, so they are marked cacheable too
    coh = per(N_COHERENCE, cs * 0.8)
    print("\nRough projection for judging the whole chain (this config):")
    print(f"  adherence, with caching     about ${adh_cached:6.2f}   (without caching ${adh_uncached:6.2f})")
    print(f"  pairwise (long, cached)     about ${pair:6.2f}")
    print(f"  coherence (short)           about ${coh:6.2f}")
    print(f"  adherence only (--no-pairwise)   about ${adh_cached:6.2f}")
    print(f"  everything                       about ${adh_cached + coh + pair:6.2f}")


if __name__ == "__main__":
    main()
