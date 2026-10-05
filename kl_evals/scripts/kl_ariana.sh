#!/usr/bin/env bash
# Exact KL from base for Ariana's lineages. One base model per run, so pick a family:
#
#   bash scripts/kl_ariana.sh                       # Qwen3.6-35B, all 24 adapters (default)
#   MODELS='nemotron120b-anth-gen-mid-g*-b1' OUT=results/kl/nemotron_anth_gen bash scripts/kl_ariana.sh
#   SMOKE=1 bash scripts/kl_ariana.sh               # one adapter, a handful of scenarios
#
# GPU memory for the base in bf16: Qwen3.6-35B ~70 GB, Nemotron-120B ~240 GB, Inkling-Small
# more still. Each adapter is downloaded into the HF cache on first use (4.5 GB each for Qwen,
# 29 GB for Nemotron, 17 GB for Inkling); clear ~/.cache/huggingface/hub between families.
#
# The Qwen3.6 models were trained with reasoning on, so the replies start with a thinking
# block; MAXTOK is raised so the KL covers the answer as well as the reasoning.
set -euo pipefail
MODELS=${MODELS:-"qwen36-35b-*"}
OUT=${OUT:-results/kl/ariana_qwen36}
MAXTOK=${MAXTOK:-384}
SWEEP=${SWEEP:-"qwen36-35b-anth-gen-postcot-g0-b1 qwen36-35b-anth-gen-postcot-g2-b1"}
SCALES=${SCALES:-"0 0.25 0.5 0.75 1 1.25 1.5"}
EXTRA=()
if [ -n "${SMOKE:-}" ]; then
  MODELS="qwen36-35b-anth-gen-postcot-g0-b1"; OUT=results/kl/ariana_smoke; SWEEP=""
  EXTRA=(--limit-per-category 1 --n 1); MAXTOK=32
fi

python -m evals.models sync

# 1. Every generation and branch at full strength, on the same base-model text.
python -m evals.kl_exact --models $MODELS --max-new-tokens "$MAXTOK" --batch-size 4 --out "$OUT" ${EXTRA[@]+"${EXTRA[@]}"}

# 2. Strength sweep on a first- and last-generation model.
if [ -n "$SWEEP" ]; then
  python -m evals.kl_exact --models $SWEEP --scales $SCALES --max-new-tokens "$MAXTOK" --batch-size 4 --out "$OUT"
fi

python -m evals.kl_stats "$OUT"
