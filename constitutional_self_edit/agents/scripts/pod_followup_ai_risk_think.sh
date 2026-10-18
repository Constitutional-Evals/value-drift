#!/bin/bash
# AI risk with thinking on (eval_checkpoints.py task ai_risk_think) for the self-drafting MSM chain (user, 2026-10-13):
# the untrained model and the models after rounds 1-3, once the chain's driver (pod_driver_self_draft_msm.sh) has
# finished. The run deletes a round's merged weights after the next round's training, so each of rounds 1 and 2 is
# kept as hard links as soon as the round is done (the same files, no extra disk). The untrained model also gets the
# thinking-off test here, so both are in the same folder; rounds 1-3 have it from their evaluations.
# Log: runs/msm-loop/eval/self-draft/logs/followup.log.
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

keep() {   # hard-link round $1's final checkpoint once the round is done
  [ -d $KEEP/r$1 ] && return 0
  until grep -q "DONE round$1" $L/driver.log; do sleep 300; done
  if [ -f $RUN/round_00$1/final/weights_deleted.json ]; then log "FAILED round $1 weights already deleted"; exit 1; fi
  mkdir -p $KEEP && cp -al $RUN/round_00$1/final $KEEP/r$1 && log "kept r$1"
}

log START waiting
keep 1
keep 2
until grep -q "ALL STEPS FINISHED" $L/driver.log; do sleep 300; done
log START ai_risk_think
if $PY agents/scripts/eval_checkpoints.py --config $RUN/config.json --checkpoint base=$BASE --checkpoint r1=$KEEP/r1 \
    --checkpoint r2=$KEEP/r2 --checkpoint r3=$RUN/round_003/final --out $OUT --tasks ai_risk ai_risk_think \
    >> $L/ai_risk_think.log 2>&1; then
  touch $L/ai_risk_think.done; log DONE ai_risk_think
else
  log FAILED ai_risk_think
fi
