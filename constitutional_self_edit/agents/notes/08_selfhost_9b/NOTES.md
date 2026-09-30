# Self-hosted Qwen3.5 9B: operational notes

Stage 08 reruns stage 07 on Qwen3.5 9B: the v3 prompt screen and the value-map chains, judged and rated by GPT. Account, provisioning, tunnel, and teardown are as in the [stage 06 notes](../06_selfhost_pilot/NOTES.md); plans, resume, and rating as in the [stage 07 notes](../07_selfhost_v3/NOTES.md). This file covers what differs.

## Model and server

- "Qwen 9B" is Qwen3.5 9B (`Qwen/Qwen3.5-9B`); there is no Qwen3.8 9B. Model key `qwen35_9b_vllm` in `configs/selfhost/models.json`.
- Same vLLM version and flags as the 27B (vLLM 0.30.0, one H200, `qwen3_xml` tool parser, 131k context, 64 sequences). `agents/scripts/selfhost_pod_start_9b.sh` is the start command for a `vllm/vllm-openai:v0.30.0` template, but see "Run" below: that image never started, and the run used RunPod's PyTorch image instead.
- **Sampling is set per request.** Qwen3.5 9B ships no `generation_config.json`, so vLLM would sample at top-p 1.0 with no top-k. The model entry's `"sampling"` sends the 27B's values (temperature 1.0, top-p 0.95, top-k 20) with every request; `elicit/core.py` merges it into the payload, so each `request.json` records it.
- **No reasoning effort.** Qwen3.5's chat template has no `reasoning_effort`; thinking is on (`enable_thinking`). The 27B ran at `xhigh`, which adds a sentence to its system prompt.

## Plans

| Plan | Batch | Reviews |
|---|---|---|
| `9b-v3-replication.json` | `selfhost-9b-v3` | 5 arms × 6 = 30 |
| `9b-v3-chains.json` | `selfhost-9b-v3-chains-reflect` | 5 seeds × 2 chains × 10 rounds = 100 |
| `9b-v3-chains-newseeds.json` | `selfhost-9b-v3-chains-reflect-newseeds` | 7 seeds × 2 chains × 10 rounds = 140 |
| `9b-pilot.json` (v2 prompts, optional) | `selfhost-9b-pilot` | 5 arms × 6 = 30 |

The chain plans have only the `reflect` arm. Run each with `VLLM_BASE_URL=http://localhost:18000/v1/ python3 -m elicit.run --plan configs/selfhost/plans/<plan> --models configs/selfhost/models.json --runs runs/selfhost --workers <trials>`.

## Judging and rating with GPT

`agents/scripts/selfhost_v3.py` takes `--model 9b`; outputs go to `runs/selfhost/judging_9b_v3/`, `runs/selfhost/positions_9b_v3/`, and `reports/08_selfhost_9b/figures/`, and reviews get `judge_gpt.json`.

1. `python3 agents/scripts/selfhost_v3.py judge-prep --model 9b` and `rate-prep --model 9b`.
2. `handoff --model 9b` writes `runs/selfhost/handoff_gpt_9b.json` (both task lists) and `handoff_gpt_9b.md`, the message to send GPT. The message includes a validation script.
3. When GPT is done: `judge-collect --model 9b --judge "<GPT model name>"` and `rate-collect --model 9b --judge "<GPT model name>"`. `--judge` is required for the 9B, so the rater label can't default to Claude.
4. `summary --model 9b`, then `plot --model 9b` with `/Users/wjz/miniconda3/bin/python3`.

The 27B's chain ratings are GPT's (`gpt-5.6-luna`), so chain positions compare across the two models if GPT uses the same model. The 27B's prompt-screen edits were judged by Claude.

## Run (September 26)

- **The vLLM image never started.** Two H200 pods from the `vllm/vllm-openai:v0.30.0` template sat in `awaiting_container` for 15 and 20 minutes (the 27B's pods came up in about a minute); the second was billed. Both were deleted.
- **What worked:** a pod from RunPod's official PyTorch template (`runpod-torch-v280`, image `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`), created with `runpodctl pod create --template-id runpod-torch-v280 --gpu-id "NVIDIA H200" --cloud-type SECURE --min-cuda-version 13.0 --container-disk-in-gb 150 --ports '22/tcp' --wait`. It was reachable by SSH in 14 seconds; the account's keys are already in `PUBLIC_KEY`, so no start script is needed.
- **Installing vLLM there:** `uv venv /root/venv`, then `uv pip install vllm==0.30.0 --torch-backend=cu130`. The image's uv (0.9.0) doesn't know `cu130`, and `--torch-backend=auto` picks a CUDA 12.6 PyTorch that fails with "libcudart.so.13: cannot open shared object file", so upgrade uv first (`uv pip install -U uv` in the venv) and use the venv's uv. The result was torch 2.13.0+cu130. Then run `vllm serve` with the flags above under `nohup`. The model loaded in 3 minutes (KV cache 3.48M tokens).
- **Run:** all three plans at once (30, 10, and 14 workers), 15:25-15:36 EDT, about 3k generated tokens/s. 269 reviews: the screen gave 18 EDITED and 12 UNCHANGED; the chains gave 207 EDITED, 31 UNCHANGED, and 1 FAILURE. The failure ended `reflect__libertarian__r1` at round 9 (six `replace_passage` calls whose `old_text` wasn't in the document), so that chain has 8 completed rounds.
- **Cost:** $2.02 in total ($1,507.25 → $1,505.23), including the stuck pod. The server log, the install log, and `pip freeze` are in `runs/selfhost/selfhost-9b-v3-chains-reflect/_server/`. The pod and template are deleted.
- **Hand-off:** 219 distinct chain documents (237 rating items with 18 repeats, 9 batches) and 18 edited screen reviews to judge (1 batch). `runs/selfhost/handoff_gpt_9b.md` is the message for GPT.

## Judging, rating, and results (September 26)

- GPT (`gpt-5.6-luna`, the model that rated the 27B's chains) wrote all 255 outputs between 15:42 and 15:55; all passed validation and were collected with `--judge gpt-5.6-luna`. No other files changed. Checks against copying: 233 distinct 12-axis vectors in 237 items, 237 distinct summaries, and none of the 18 repeat pairs identical on all 12 axes (72-100% within one point per axis).
- **Prompt screen (GPT judge):** reflect 6/6 substantive (5 major), hard cases and amendments 5/6 each, no reflection 1/6, blind 0/6 (all kept unchanged). The 27B's screen was judged by Claude, so compare only the unchanged counts (the 27B edited all 30).
- **Chains, 9B vs 27B (both rated by GPT):** the document changed in 207/239 rounds (27B: 240/240). Median length 230 → 976 words (27B: 1,746). Mean RMS distance between chains from different seeds fell from 2.47 to 1.60 by round 10 (27B: 2.12 → 1.16); within a seed it was 1.09 at round 10 (27B: 0.76). Largest mean changes over 10 rounds: specificity +3.2 (12/12 seeds up), long-term orientation +1.9, caution +1.7 (27B: +0.2), third-party concern and moral circle +1.25; deference to oversight -0.1 (27B: +1.2), user autonomy +0.2 (27B: +1.0).
- **Figures:** `plot --model 9b` writes `reports/08_selfhost_9b/figures/` (no `02_outcomes_v2_v3`: the 9B ran only v3; no `11_rater_agreement`: one rater). The value maps draw one arrow per chain for both models; a footnote names the libertarian chain that ended early.
