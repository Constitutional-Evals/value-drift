# Saved post-DPO evaluation

This separate analysis evaluates the saved full-011 round-1 DPO checkpoint on the same 120 neutral held-out prompts, with the original generation settings and fixed 27B judge. Comparing these outputs with full-011 `eval_000.jsonl` (M0) and `eval_001.jsonl` (post-SFT M1) helps locate when shortening or repetition appeared. It is descriptive stage analysis, not a new recursive round or evidence that the constitution edit caused any difference.

Run from the repository root on the existing GPU host, **after the active trajectory has released the GPU**, using the established CUDA compatibility environment:

```sh
export HF_HOME=/workspace/huggingface
export CUDA_HOME=/workspace/venv/lib/python3.12/site-packages/nvidia/cu13
export LD_LIBRARY_PATH=/workspace/cuda-compat-13/usr/local/cuda-13.0/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
/workspace/venv/bin/python agents/scripts/evaluate_post_dpo.py --source-run runs/full-011 --round 1 --output runs/stage_analysis/full-011_dpo_001
```

Add `--plan-only` for a CPU-only check that loads no model and writes no artifacts. The execution command needs the actual saved DPO weights on the host; local metadata alone is sufficient for the plan check.

The script reads frozen prompt snapshots, checks their IDs and text against the original baseline, and verifies the fixed judge prompt/rubric. It saves an immutable analysis input receipt and writes `responses.jsonl`, the existing judge artifacts, and `analysis_complete.json` under the separate output directory. Repeating the same command resumes via existing response and judge caches; completed truncated or invalid outputs are retained. It does not train, invoke constitution review, modify a trajectory state, or change any run configuration. A partially resumed generation batch retains the existing backend's documented seed-counter restart behavior.

Executed after the full-014 trajectory stopped. The saved DPO1 checkpoint generated all120 neutral responses:109normal/11capped,median352words. Fixed judging and its completion receipt are saved in `runs/stage_analysis/full-011_dpo_001/`. All11capped answers visibly repeat; three persist into M1 while eight recover and five other prompts newly cap after SFT. See [the Stage2 report](STAGE2_REPORT.md) for matched examples and the separate stage comparison. This analysis did not train, change the scientific protocol, or reopen the stopped trajectory.
