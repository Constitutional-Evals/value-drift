#!/usr/bin/env bash
# MMLU with lm-evaluation-harness on vLLM, 5-shot, chat template off (the harness default).
#   bash scripts/mmlu.sh <model path or id> <output dir>
# Round one reported 82.8% (base) and 83.5% (after round one); confirm with Jinzhou which
# shot count / template setting he used before comparing numbers directly.
set -euo pipefail
MODEL=$1
OUTDIR=$2
TP=${TP:-1}
lm_eval --model vllm \
  --model_args "pretrained=$MODEL,tensor_parallel_size=$TP,dtype=bfloat16,gpu_memory_utilization=0.9,max_model_len=8192,trust_remote_code=True" \
  --tasks mmlu --num_fewshot 5 --batch_size auto \
  --output_path "$OUTDIR"
