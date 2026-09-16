# Recursive constitution editing and full-parameter OCT

Research proof of concept specified in [instruction.md](instruction.md). The initial experimental model is **Qwen/Qwen3.5-9B**. A fresh model review may replace the constitution through two file-backed tools; explicit submission without any content-changing edit ends that trajectory. An edited submission triggers full-parameter DPO, post-DPO introspection generation, and full-parameter SFT, with updated weights carried into the next review.

Scientific inputs are frozen before each trajectory; consequential interface changes and recovery branches are labeled and preserved. The first condition is full-information only, with at most five completed training rounds. Partial/minimal prompts are prepared but not executed. Neither an unchanged submission nor a failure is relabeled to obtain an interesting result.

**Substantive experiment completed:** the full-011 → full-014 lineage completed two full-parameter DPO + introspective SFT rounds and three constitution reviews. The first revision changed risk and distress guidance, the second removed duplicated paragraphs, and M2 then submitted unchanged. Behavioral changes were mixed, with shorter typical responses and remaining quality failures. See the [Stage 2 report](docs/STAGE2_REPORT.md), [longitudinal figure](runs/full-014/analysis/longitudinal.png), and [independent review](docs/REVIEW_STAGE2_RESULT.md). The review-interface repairs are explicitly recorded; this is one learned lineage, not multiple independent training replications.

**Earlier pilot:** `full-001` submitted C0 unchanged on its first review and ended with `SELF_DECLARED_CONVERGENCE`, zero edits and zero scientific training rounds. Separate H200 engineering runs completed full-parameter DPO and introspective SFT and reloaded the resulting checkpoint. See the [final report](docs/FINAL_REPORT.md), [baseline analysis](docs/BASELINE_ANALYSIS.md), and [independent result review](docs/REVIEW_RESULT_001.md).

## Project files

- `constitutions/C_000.md`: original 1,059-word initial essay; user-requested polishing passes archived in `constitutions/drafts/`.
- `prompts/`: three context variants, tool/review instructions, actual training description and fixed introspection prompts.
- `data/`: 1,500 source-attributed user-only training prompts,120 held-out prompts, curation manifest and exploratory rubric.
- `recursive_oct/`: editing state, native Qwen interface, resumable generation, full-parameter losses/training, inner-loop runner and measurements.
- `configs/`: engineering settings, preserved exploratory variants, and the full-011/full-014 trained-lineage configurations.
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

Initial GPU bootstrap and engineering check (the working setup also requires the compiler, linker and separate vLLM steps in [Reproducing the environment](docs/REPRODUCING_ENVIRONMENT.md)):

```bash
bash scripts/bootstrap_gpu.sh
HF_HOME=/workspace/huggingface /workspace/venv/bin/python scripts/smoke_gpu.py
```

Main run/resume (requires a measured config with `frozen: true`):

```bash
export HF_HOME=/workspace/huggingface
export CUDA_HOME=/workspace/venv/lib/python3.12/site-packages/nvidia/cu13
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

`runs/connection.json` contains the lead's SSH connection metadata. Secrets are never synced. Sync excludes local spending/watchdog control files. The user removed the original $200 spending ceiling for Stage 2. The ledger preserves cumulative charges across all attempts; use suitable hardware and avoid unnecessary parallel provisioning. Only the lead provisions or terminates paid resources. Checkpoints must be copied locally before deleting the network volume.

## Interpretation

This is an OCT adaptation, not a replication of its reported results: fixed Qwen3.5-27B teacher, open-dataset user prompt bank, full-parameter AdamW8bit optimization with FP32 weights, shorter introspection, and DPO plus chosen NLL without OCT's extra tokenwise KL term. All ordinary text parameters are optimized; unused vision weights are retained without text gradients, and the supported Transformers class does not instantiate the checkpoint's auxiliary speculative MTP head. See method notes for exact counts.

Self-declared convergence describes a tool submission decision, not proven stabilization of underlying values. Behavioral dimensions are exploratory and never combined into a definitive alignment score. Truncations, failed attempts, filtering, and sampling effects must be reported alongside observed changes.
