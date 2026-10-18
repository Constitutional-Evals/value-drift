#!/usr/bin/env bash
# Adherence check on Jinzhou's MSM self-draft chain (3 rounds, Qwen3.8-27B). Run from kl_evals/ on the pod.
#   bash scripts/adherence_msm_selfdraft.sh plan      # scale only, free
#   bash scripts/adherence_msm_selfdraft.sh gpu       # base answers, then for each round: merge -> answer -> delete the merge
#   bash scripts/adherence_msm_selfdraft.sh judge     # API only; 10,000-word constitutions, so prefix caching is switched on
#   bash scripts/adherence_msm_selfdraft.sh analyze
#   bash scripts/adherence_msm_selfdraft.sh all       # unattended: nohup bash scripts/adherence_msm_selfdraft.sh all > run.log 2>&1 &
# Round N's model is the base plus every adapter up to round N (msm, then aft, in each round). Only one merged model
# (~51 GB) exists at a time, so a 300 GB disk is enough.
set -euo pipefail
[ -f scripts/pod_env.sh ] && source scripts/pod_env.sh
JUDGE=${JUDGE:-openrouter:anthropic/claude-sonnet-5}
CFG=configs/msm_selfdraft.json
CHAIN=hf/qwen3.8-27b/self-draft-msm
case "${1:?plan|gpu|judge|analyze|all}" in
  plan)    python -m adherence.run plan $CFG --judges "$JUDGE" ;;
  gpu)
    python - <<PY
from oct.common import download_chain
download_chain("hf", "self-draft-msm")
PY
    python -m adherence.run generate $CFG --only base
    for r in 1 2 3; do
      [ -d ckpt/sd_r$r ] || python -m oct.merge --stage r$r/aft --out ckpt/sd_r$r --chain-dir $CHAIN
      python -m adherence.run generate $CFG --only sd_r$r
      rm -rf ckpt/sd_r$r
    done ;;
  judge)   JUDGE_CACHE_PREFIX=1 python -m adherence.run judge $CFG --judges "$JUDGE" ;;
  analyze) python -m adherence.run analyze $CFG ;;
  all)     bash "$0" gpu && bash "$0" judge && bash "$0" analyze ;;
esac
