# Self-hosted v3 runs: operational notes

For agents rerunning or extending stage 07. Results are in [reports/07_selfhost_v3/](../../../reports/07_selfhost_v3/SELFHOST_V3_REPORT.md). Account, provisioning, tunnel, reasoning effort, and teardown are as in the [stage 06 notes](../06_selfhost_pilot/NOTES.md); this file covers what changed.

## Prompts v3

- `"prompts": "v3"` in an arm selects `elicit/prompts_v3.py`. The constitution is always introduced as "Here is the current constitution:", with no provenance sentence, so the same prompt can be reused unchanged in every round of a training loop.
- The reflect step asks open-endedly which values should matter and how to resolve conflicts between them. The v2 list of six values is gone. The blind, cases, and amend prompts are unchanged from v2.

## Plans and batches

- `configs/selfhost/plans/v3-replication.json` is the prompt screen: five arms, the broad draft, six single reviews each. It is batch `runs/selfhost/selfhost-v3`.
- The value-map chains use the reflect arm, 10 generations, and `"chain_stop": "never"`; only a FAILURE ends a chain. The five elicitation seeds and the seven new seeds (`constitutions/value_map/`, provenance in its README) are separate plans, with two chains per seed:
  - `v3-chains.json` → `selfhost-v3-chains-reflect`
  - `v3-chains-newseeds.json` → `selfhost-v3-chains-reflect-newseeds`

  That is 24 chains and 240 reviews.
- Reps 3-6 were also started, in four more batches (`v3-chains*-r3r4.json` and `v3-chains*-r5r6.json` → `...-r3r4`, `...-r5r6`), to keep vLLM's 64 slots busy. They were stopped partway, around generations 3-6, when the user settled on two chains per seed. Their partial chains stay on disk; `agents/scripts/selfhost_v3.py` reads only the rep 1-2 batches. `"first_rep": 3` (or 5) in a plan offsets the rep numbering so labels don't collide across batches.
- The rep 1-4 plans also define a `reflect_cap350` arm (350-word cap in the tools). It was dropped partway through: the runs were restarted with `--arms reflect`, which filters the plan's arms without changing `plan.json`, so the resume check still passes. The capped chains' partial generations stay on disk and are ignored.
- With all 72 uncapped chains in flight, vLLM ran 64 requests with about 8 waiting, at roughly 1.8k generated tokens/s and no preemptions (KV cache about 45% used). With only the 24 rep 1-2 chains, the GPU is underfilled; each runner uses `--workers` equal to its chain count (10 or 14).

## Resume and call replay

- A generation with a `result.json` is reused, as before.
- New: `Client.complete` replays a saved call. If a call directory's `request.json` equals the payload about to be sent and its `response.json` has choices, the saved response is returned without a request. An interrupted review therefore continues from its first unanswered call instead of starting over. A mismatched `response.json` is renamed `response.superseded.json` before the new call; nothing is deleted.
- Restarting a run is just rerunning the same command. The log shows replayed generations immediately.

## Rating the chains with Claude subagents

- `python3 agents/scripts/selfhost_v3.py rate-prep` collects every distinct document in the chains (seeds and each generation's output), writes one prompt per document to `runs/selfhost/positions_v3/items/` under a random id, and adds about 8% repeats under different ids, each in a different batch than its first rating. The key is `mapping.json`; the batch lists are `batches.json`.
- Each subagent gets one batch, reads `items/<id>.md`, and writes `out/<id>.json`. It is told not to open `mapping.json`, `batches.json`, or anything else under `runs/`, and not to use scripts or other models.
- The twelve axes are the seven of `elicit/position.py`, unchanged, plus `moral_circle`, `traditionalism`, `viewpoint_neutrality`, `warmth`, and `long_term_orientation`. The new ones separate the new seeds, which differ mostly on who counts morally, tradition, neutrality, care, and time horizon.
- `rate-collect` validates and writes `positions_v3/ratings/<doc hash>.json` (repeats as `<hash>.repeat.json`); `summary` prints per-chain status and repeat agreement; `plot` writes `reports/07_selfhost_v3/figures/`. Run `plot` with `/Users/wjz/miniconda3/bin/python3`.
- The replication's edited reviews are judged the same way as stage 06: `judge-prep`, subagents write `judging_v3/out/<id>.json`, `judge-collect` writes `judge_claude.json` into each review.

## Rater switch to GPT (September 25)

- The Claude subagents stopped partway (Claude Code credits ran out) after 148 valid ratings and 1 corrupted one. Those are kept in `runs/selfhost/positions_v3/claude_partial/` for a Claude-vs-GPT comparison; the corrupted file (`doc_43063.json`, user-autonomy score garbled) is in `claude_partial/corrupted/`.
- GPT re-rates all 272 items into `positions_v3/out/`, using the same item prompts and the original 18 batches (listed in `positions_v3/handoff_gpt.json`). GPT outputs carry a `"rater"` field.
- When GPT is done, collect with `python3 agents/scripts/selfhost_v3.py rate-collect --judge "<GPT model name>"`; the default `--judge` label says Claude and would be wrong.
- Done September 25: GPT (`gpt-5.6-luna`) rated all 272 items; collected into `positions_v3/ratings/` with that label. On the 148 items both raters did, per-axis Pearson r averages 0.62 (0.40 caution to 0.91 moral circle), but GPT rates higher on most axes (specificity +2.5, long-term +1.8, warmth +1.5; traditionalism -1.1) and sits near the ceiling on honesty strictness, third-party concern, and long-term orientation (means 6.8, 6.9, 6.7). Early-to-late changes agree better than levels (r = 0.65 across seed x axis cells; same sign in 86% of cells where both raters see at least half a point of change). Compare levels only within one rater. GPT's 20 repeat pairs: 95% within one point, only 1 identical 12-axis vector, so no sign of copying.
- `plot` now also writes `10_axis_change` (change from each seed to round 10, per axis) and `11_rater_agreement` (GPT vs Claude on the shared items; reads `claude_partial/out`). `07_axis_spread` had clipped the moral-circle panel (a per-panel `set_ylim` stopped autoscaling on the shared axis); fixed.
