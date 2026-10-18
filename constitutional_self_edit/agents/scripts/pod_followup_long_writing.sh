#!/bin/bash
# After the AI-risk-with-thinking follow-up (pod_followup_ai_risk_think.sh): the long-writing diagnostic
# (agents/scripts/long_writing_diagnostic.py; user, 2026-10-14: base and rounds 1-3, 10 writing prompts x 2
# samples and 5 book summaries x 2 samples, thinking on), and the untrained model's perplexity on C_001-C_003
# (the driver scores only each round's own model). Log: runs/msm-loop/eval/self-draft/logs/followup.log.
set -uo pipefail
cd /workspace/value-drift
export HF_HOME=/workspace/huggingface PYTHONUNBUFFERED=1 HF_TOKEN=$(cat /workspace/.hf_token)
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
RUN=runs/msm-loop/msm-qwen38-27b-self-draft
OUT=runs/msm-loop/eval/self-draft
L=$OUT/logs
KEEP=$OUT/kept
BASE=/workspace/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0
PY=/workspace/venv/bin/python
log() { echo "$(date -u +%FT%TZ) $*" >> $L/followup.log; }

until grep -qE "(DONE|FAILED) ai_risk_think" $L/followup.log; do sleep 300; done
log START long_writing
if $PY agents/scripts/long_writing_diagnostic.py --out $OUT/long_writing --checkpoint base=$BASE --checkpoint r1=$KEEP/r1 \
    --checkpoint r2=$KEEP/r2 --checkpoint r3=$RUN/round_003/final >> $L/long_writing.log 2>&1; then
  log DONE long_writing
else
  log FAILED long_writing
fi
log START perplexity_base
if $PY agents/scripts/constitution_perplexity.py --checkpoint base=$BASE --text C_001=$RUN/C_001.md --text C_002=$RUN/C_002.md \
    --text C_003=$RUN/C_003.md --out $OUT/perplexity_base.json >> $L/perplexity_base.log 2>&1; then
  log DONE perplexity_base
else
  log FAILED perplexity_base
fi
log "ALL FOLLOW-UPS FINISHED"
