# Self-hosted pilot: operational notes

For agents rerunning or extending the self-hosted pilot. Results are in [reports/06_selfhost_pilot/](../../../reports/06_selfhost_pilot/SELFHOST_PILOT_REPORT.md).

## Account

- The funded RunPod account is the one in runpodctl's saved config. The `RUNPOD_API_KEY` in `.env` and the RunPod MCP server belong to an unfunded account, and creates there fail with "balance too low". Run every command as `env -u RUNPOD_API_KEY runpodctl ...` so the saved config wins, and never print the key.
- Check balance and spend before and after with `env -u RUNPOD_API_KEY runpodctl user` (`clientBalance`, `currentSpendPerHr`). The pilot cost $1.08 ($1,515.76 → $1,514.68).

## Provisioning

- `runpodctl pod create` has no entrypoint flag, so create a template first, then a pod from it:
  - `runpodctl template create --name ... --image vllm/vllm-openai:v0.30.0 --docker-entrypoint '/bin/bash,-c' --docker-start-cmd "$(cat start.sh)" --container-disk-in-gb 150 --volume-in-gb 0 --ports '22/tcp'`. The start command must contain **no commas**, because the flag splits on them.
  - `runpodctl pod create --template-id <id> --gpu-id "NVIDIA H200" --gpu-count 1 --cloud-type SECURE --min-cuda-version 13.0 --container-disk-in-gb 150 --ports '22/tcp' --env '{"VD_PUBKEY": "<public key>"}'`.
- The start script installs and starts `sshd`, adds `$PUBLIC_KEY` and `$VD_PUBKEY` to `authorized_keys` (the local key is `~/.ssh/id_ed25519_runpod`), then runs:

  ```
  vllm serve Qwen/Qwen3.8-27B --served-model-name qwen3.8-27b --host 127.0.0.1 --port 8000 --max-model-len 131072 --language-model-only --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml --gpu-memory-utilization 0.92 --max-num-seqs 64 --enable-prefix-caching 2>&1 | tee /root/vllm.log; sleep infinity
  ```

  The server binds to localhost only; nothing is exposed except SSH.
- `runpodctl pod get <id>` gives the public IP and the mapped SSH port once the pod is up (about a minute). `runpodctl pod logs <id> --tail 400` shows the start script's output. The weights download and load in about 4-5 minutes; the log line "Starting vLLM server" marks readiness. KV cache on one H200 is about 1.18M tokens, far more than 30 concurrent reviews need.

## Running

- Tunnel: `ssh -i ~/.ssh/id_ed25519_runpod -N -L 18000:localhost:8000 -p <port> root@<ip> -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes`, wrapped in a `while true` loop so it reconnects. `elicit/core.py` sends `"backend": "vllm"` models to `VLLM_BASE_URL` (default `http://localhost:18000/v1/`).
- Run: `VLLM_BASE_URL=http://localhost:18000/v1/ python3 -m elicit.run --plan configs/selfhost/plans/pilot.json --models configs/selfhost/models.json --runs runs/selfhost --workers 30`. The 30 reviews took about 6 minutes.
- vLLM requests carry only `max_tokens` and `enable_thinking`, so sampling comes from the model's `generation_config.json` (temperature 1.0, top-p 0.95, top-k 20; vLLM logs this at startup).
- **Reasoning effort.** Qwen3.8's chat template takes `reasoning_effort` = `xhigh` (default), `medium`, or `low`. `xhigh` and `low` add a sentence to the system prompt; `medium` adds nothing; any other value raises an error. The pilot ran at `xhigh`. OpenRouter's `reasoning: {"effort": "high"}` reached DeepInfra as `medium`: its reported prompt tokens match the `medium` rendering exactly in every elicitation call checked (render the template with the model's `tokenizer.json` and compare with `usage.prompt_tokens`). To match the elicitation runs, add `"chat_template_kwargs": {"reasoning_effort": "medium"}` to the model entry; `_vllm_payload` merges it into each request.
- The chat template reads earlier turns' reasoning from `reasoning_content`, so the vLLM payload renames the history's `reasoning` field.
- `"prompts": "v2"` in an arm selects `elicit/prompts_v2.py` (no stopping sentence; blind question without character and oversight). Without it, arms use the elicitation prompts.
- Before deleting the pod, copy `/root/vllm.log` to `runs/selfhost/<batch>/_server/`. Then `runpodctl pod delete <id>`, `runpodctl template delete <id>`, and kill the tunnel loop. Confirm `pod list` is empty and `currentSpendPerHr` is 0.

## Judging with Claude subagents

- `python3 agents/scripts/selfhost_pilot.py prep` writes one prompt per edited review to `runs/selfhost/judging/items/` under a random id (the elicitation judge's rubric, with before, after, and diff only) and the id-to-review key to `mapping.json`. Split the items into batches that mix conditions and give each batch to a subagent, which writes `out/<id>.json` and is told not to open `mapping.json`.
- `collect` validates the outputs and writes `judge_claude.json` into each review directory, next to any existing `judge.json`. `summary` prints the per-arm table and agreement with the Flash judge. `plot` writes `reports/06_selfhost_pilot/figures/01_outcomes.{png,pdf}`.
- The script needs matplotlib: run it with `/Users/wjz/miniconda3/bin/python3`. The system `python3` does not have it.
