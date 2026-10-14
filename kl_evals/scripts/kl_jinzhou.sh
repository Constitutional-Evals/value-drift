#!/usr/bin/env bash
# Exact KL from base for Jinzhou's round-one chain (Qwen3.8-27B), with the adapter-strength
# sweeps. One GPU with >= 80 GB (or several smaller ones; the model is spread automatically).
#
#   huggingface-cli login
#   bash scripts/kl_jinzhou.sh            # SMOKE=1 for a 5-minute check first
#
# Rerunning resumes: finished variants are skipped.
set -euo pipefail
OUT=${OUT:-results/kl/jinzhou}
SCALES=${SCALES:-"0 0.25 0.5 0.75 1 1.25 1.5"}
EXTRA=()
if [ -n "${SMOKE:-}" ]; then
  OUT=results/kl/jinzhou_smoke; SCALES="0 1"
  EXTRA=(--limit-per-category 1 --n 1 --max-new-tokens 32)
fi

python -m evals.models sync

# 1. Both checkpoints at every strength, all adapters scaled together: base -> model -> beyond.
python -m evals.kl_exact --models r1_dpo r1_sft --scales $SCALES --out "$OUT" ${EXTRA[@]+"${EXTRA[@]}"}

# 2. DPO kept at full strength, only the SFT adapter scaled: how much does the SFT step add?
#    Plus SFT alone (no DPO underneath) and the 2- and 3-epoch SFT variants.
python -m evals.kl_exact --models r1_sft --scales $SCALES --scale-last-only \
  --variants r1_sft@dpo=0,sft=1 r1_sft_epoch2 r1_sft_epoch3 --out "$OUT" ${EXTRA[@]+"${EXTRA[@]}"}

# 3. On text sampled from each model itself (temperature 1). Add --temperature 0.7 --top-p 0.95
#    --max-new-tokens 2048 --n 1 and a separate OUT to match measure_kl.py, which gave 0.209.
python -m evals.kl_exact --models r1_dpo r1_sft --policy self --out "$OUT" ${EXTRA[@]+"${EXTRA[@]}"}

python -m evals.kl_stats "$OUT" --contrast r1_sft r1_dpo --contrast r1_sft_epoch3 r1_sft
