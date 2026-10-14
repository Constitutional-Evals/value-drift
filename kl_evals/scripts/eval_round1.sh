#!/usr/bin/env bash
# Evaluate Jinzhou's round-one chain end to end: constitution metrics, behavior across
# base -> r1/dpo -> r1/sft, KL from base, and MMLU.
#
#   export ANTHROPIC_API_KEY=...        # judge for constitution + behavior metrics
#   huggingface-cli login               # Qwen3.8-27B and LIMA may be gated
#   bash scripts/eval_round1.sh
#
# Needs ~60 GB of GPU memory for a 27B model in bf16 (use TP=2 on 2x 40/48 GB cards) and
# ~60 GB of disk per merged checkpoint.
set -euo pipefail

TP=${TP:-1}
BASE=${BASE:-Qwen/Qwen3.8-27B}
HF=${HF:-hf}
CKPT=${CKPT:-ckpt}
OUT=${OUT:-results}
CHAIN=$HF/qwen3.8-27b/broad

python - <<EOF
from oct.common import download_chain
download_chain("$HF", "broad")
EOF

# 1. Constitution chain (cheap: API calls only)
python -m evals.constitution "$CHAIN" --out "$OUT/constitutions"

# 2. Merge the chain into the two round-one checkpoints
[ -d "$CKPT/r1_dpo" ] || python -m oct.merge --stage r1/dpo --out "$CKPT/r1_dpo" --chain-dir "$CHAIN"
[ -d "$CKPT/r1_sft" ] || python -m oct.merge --stage r1/sft --out "$CKPT/r1_sft" --chain-dir "$CHAIN"

# 3. Behavior: axis scores, adherence to C_000 / C_001 / C_002, win rate vs base,
#    and the gap between each model's behavior and the constitution it trained on
python -m evals.behavior --tp "$TP" \
  --checkpoints base="$BASE" r1_dpo="$CKPT/r1_dpo" r1_sft="$CKPT/r1_sft" \
  --constitutions "$CHAIN/C_000.md" "$CHAIN/round_001/C_001.md" "$CHAIN/round_002/C_002.md" \
  --constitution-scores "$OUT/constitutions/scores.json" \
  --trained-on r1_dpo=C_001 r1_sft=C_001 \
  --out "$OUT/behavior"

# 4. KL from base (round one reported 0.21 nats/token after SFT)
python -m evals.kl --tp "$TP" --model "$CKPT/r1_dpo" --base "$BASE" --out "$OUT/kl_r1_dpo.json"
python -m evals.kl --tp "$TP" --model "$CKPT/r1_sft" --base "$BASE" --out "$OUT/kl_r1_sft.json"

# 5. MMLU (round one: base 82.8%, after training 83.5%)
for m in "$BASE" "$CKPT/r1_sft"; do
  bash scripts/mmlu.sh "$m" "$OUT/mmlu/$(basename "$m")"
done
