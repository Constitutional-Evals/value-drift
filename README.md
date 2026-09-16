# Recursive constitution editing and full-parameter OCT

Research proof of concept specified in [instruction.md](instruction.md). The initial experimental model is **Qwen/Qwen3.5-9B**. A fresh model review may replace the constitution through two file-backed tools; explicit submission without any content-changing edit ends that trajectory. An edited submission triggers full-parameter DPO, post-DPO introspection generation, and full-parameter SFT, with updated weights carried into the next review.

The scientific protocol is frozen before each trajectory. The first condition is full-information only, with at most five completed training rounds. Partial/minimal prompts are prepared but not executed. Neither an unchanged submission nor a failure is relabeled to obtain an interesting result.

## Project files

- `constitutions/C_000.md`: original 1,059-word initial essay; user-requested polishing passes archived in `constitutions/drafts/`.
- `prompts/`: three context variants, tool/review instructions, actual training description and fixed introspection prompts.
- `data/`: 1,500 source-attributed user-only training prompts,120 held-out prompts, curation manifest and exploratory rubric.
- `recursive_oct/`: editing state, native Qwen interface, resumable generation, full-parameter losses/training, inner-loop runner and measurements.
- `configs/`: provisional training and engineering smoke settings; measured frozen run config will be saved before the main trajectory.
- `runs/`: private local outputs, checkpoints/locations, logs and cumulative spending records (excluded from Git).
- `docs/PROGRESS.md`: current evidence and next action. `docs/method.md` and review notes document adaptations and fixes.
- `OpenCharacterTraining/`: intact upstream reference checkout at `d1da9f03628cb4c5482ba2e494a7cba33bcd5818`, excluded from this repository's Git tracking.

## Commands

CPU checks:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests -q
```

GPU dependencies and actual-engineering check:

```bash
bash scripts/bootstrap_gpu.sh
HF_HOME=/workspace/huggingface /workspace/venv/bin/python scripts/smoke_gpu.py
```

Main run/resume (requires a measured config with `frozen: true`):

```bash
/workspace/venv/bin/python scripts/run_experiment.py --config configs/full-001.json --run runs/full-001
/workspace/venv/bin/python scripts/run_experiment.py --config configs/full-001.json --run runs/full-001 --resume
```

The resume command reuses finalized reviews and completed stages. Converged trajectories are never reopened. Generated responses and exact current-student reference probabilities are saved; optimizer states reset between stages and rounds, while full model weights continue.

Lead-side sync and cost guard:

```bash
.venv/bin/python scripts/sync.py push
.venv/bin/python scripts/sync.py pull
.venv/bin/python scripts/sync.py pull --checkpoints
.venv/bin/python scripts/watch_budget.py --ledger runs/spending.json
```

`runs/connection.json` contains the lead's SSH connection metadata. Secrets are never synced. Sync excludes local spending/watchdog control files. The cumulative RunPod authorization is $200, with $15 reserved for storage, transfers and cleanup. Only the lead provisions or terminates paid resources. Checkpoints must be copied locally before deleting the network volume.

## Interpretation

This is an OCT adaptation, not a replication of its reported results: frozen M0 teacher, open-dataset user prompt bank, full-parameter AdamW8bit optimization with FP32 weights, shorter introspection, and DPO plus chosen NLL without OCT's extra tokenwise KL term. All ordinary text parameters are optimized; unused vision weights are retained without text gradients, and the supported Transformers class does not instantiate the checkpoint's auxiliary speculative MTP head. See method notes for exact counts.

Self-declared convergence describes a tool submission decision, not proven stabilization of underlying values. Behavioral dimensions are exploratory and never combined into a definitive alignment score. Truncations, failed attempts, filtering, and sampling effects must be reported alongside observed changes.
