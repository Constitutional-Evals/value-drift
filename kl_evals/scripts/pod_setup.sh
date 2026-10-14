#!/usr/bin/env bash
# One-time setup on a RunPod H200 (PyTorch template). Run from kl_evals/.
#
#   1. Attach a network volume (~500 GB) mounted at /workspace BEFORE starting the pod.
#   2. export HF_TOKEN=... ANTHROPIC_API_KEY=... [OPENROUTER_API_KEY=...]
#   3. bash scripts/pod_setup.sh
#
# Everything big lives on the volume so a restarted pod loses nothing.
set -euo pipefail
export HF_HOME=${HF_HOME:-/workspace/huggingface}
mkdir -p "$HF_HOME" /workspace/ckpt
df -h /workspace | tail -1

python -m venv /workspace/venv-adherence --system-site-packages
source /workspace/venv-adherence/bin/activate
pip install -q -r requirements.txt

# Qwen3.5/3.6/3.8 need a recent vLLM and Transformers. The training pipeline's own notes
# (constitutional_self_edit/reports/methods/method.md) record vLLM 0.29.0 + Transformers 5.17.0.
# requirements.txt only says vllm>=0.11, so check what you got and pin if loading fails.
python - <<'PY'
import torch, transformers
print("torch", torch.__version__, "| transformers", transformers.__version__, "| gpus", torch.cuda.device_count())
try:
    import vllm; print("vllm", vllm.__version__)
except Exception as e:
    print("vllm import failed:", e)
PY

[ -L ckpt ] || ln -s /workspace/ckpt ckpt
huggingface-cli whoami >/dev/null 2>&1 || huggingface-cli login --token "${HF_TOKEN:?set HF_TOKEN}"
python -m evals.models sync          # constitutions, adapter configs, Ariana manifest (small)
echo "setup done. Next: SMOKE=1 bash scripts/kl_jinzhou.sh, then bash scripts/adherence_oct.sh"
