#!/usr/bin/env bash
# The OCT adherence check, end to end. Run from kl_evals/ on the pod.
#   bash scripts/adherence_oct.sh plan      # scale only, free
#   bash scripts/adherence_oct.sh gpu       # build checkpoints + generate answers (GPU, ~hours)
#   bash scripts/adherence_oct.sh judge     # default judge (API calls)
#   bash scripts/adherence_oct.sh analyze   # table + figure (CPU)
set -euo pipefail
[ -f scripts/pod_env.sh ] && source scripts/pod_env.sh   # CUDA compat + venv, written by pod_setup.sh
JUDGE=${JUDGE:-anthropic}   # anthropic (needs ANTHROPIC_API_KEY) or openrouter:anthropic/claude-sonnet-5 (needs OPENROUTER_API_KEY)
CFG=${CFG:-configs/oct_round1.json}     # CFG=configs/oct_fast.json for the reduced run
CHAIN=hf/qwen3.8-27b/broad
case "${1:?plan|gpu|judge|analyze|all}" in
  plan)    python -m adherence.run plan $CFG ;;
  gpu)
    python - <<PY
from oct.common import download_chain
download_chain("hf", "broad")
PY
    if grep -q r1_dpo "$CFG"; then [ -d ckpt/r1_dpo ] || python -m oct.merge --stage r1/dpo --out ckpt/r1_dpo --chain-dir $CHAIN; fi
    [ -d ckpt/r1_sft ] || python -m oct.merge --stage r1/sft --out ckpt/r1_sft --chain-dir $CHAIN
    python -m adherence.run generate $CFG ;;
  judge)   python -m adherence.run judge $CFG --judges "$JUDGE" ;;
  all)     bash "$0" gpu && bash "$0" judge && bash "$0" analyze ;;   # unattended: nohup CFG=... bash scripts/adherence_oct.sh all &
  analyze) python -m adherence.run analyze $CFG ;;
esac
