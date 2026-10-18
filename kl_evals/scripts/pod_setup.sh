#!/usr/bin/env bash
# One-time setup on a RunPod GPU pod (official PyTorch template, one 80 GB+ Hopper GPU). Run from kl_evals/.
#
#   export HF_TOKEN=...  OPENROUTER_API_KEY=...        (ANTHROPIC_API_KEY instead if you judge with Claude directly)
#   bash scripts/pod_setup.sh
#   source scripts/pod_env.sh                            # every new terminal, before running anything
#
# The recipe follows the project's own working pod setup (constitutional_self_edit/agents/scripts/
# setup_oct_loop_pod.sh and reports/methods/REPRODUCING_ENVIRONMENT.md): vLLM 0.30.0 with CUDA 13 PyTorch.
# If the host driver is older than 580 (a "CUDA 12.8" host), this installs NVIDIA's official
# cuda-compat-13-0 package, which is how the project ran CUDA 13 builds on a driver-570 H200.
set -euo pipefail
export HF_HOME=${HF_HOME:-/workspace/huggingface}
VENV=/workspace/venv-adherence
COMPAT=/workspace/cuda-compat-13
mkdir -p "$HF_HOME" /workspace/ckpt
df -h /workspace | tail -1
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

# 0. Driver check. CUDA 13 wheels need driver >= 580; older drivers need NVIDIA's forward-compat libraries.
DRV=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
if [ "${DRV%%.*}" -lt 580 ] && [ ! -d "$COMPAT/usr/local/cuda-13.0/compat" ]; then
  echo "driver $DRV < 580: installing cuda-compat-13-0 (official NVIDIA package, pinned by the project)"
  DEB=cuda-compat-13-0_580.178.04-1ubuntu1_amd64.deb
  wget -q -O "/tmp/$DEB" "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/$DEB"
  echo "f7e29a545c1334bb5ca4b054213de9c9ceb70f8bf561aa214075020c4e0b60cf  /tmp/$DEB" | sha256sum -c -
  mkdir -p "$COMPAT" && dpkg-deb -x "/tmp/$DEB" "$COMPAT"
fi

# 1. Environment file, sourced before every run.
cat > scripts/pod_env.sh <<EOF
export HF_HOME=$HF_HOME
[ -d $COMPAT/usr/local/cuda-13.0/compat ] && export LD_LIBRARY_PATH=$COMPAT/usr/local/cuda-13.0/compat\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}
source $VENV/bin/activate
EOF
source scripts/pod_env.sh 2>/dev/null || true

# 2. Python environment. A newer uv than the image's is needed for --torch-backend.
pip install -q -U uv
[ -d "$VENV" ] || uv venv "$VENV" --python 3.12
source scripts/pod_env.sh
uv pip install -q vllm==0.30.0 --torch-backend=cu130
uv pip install -q peft==0.21.0 accelerate huggingface_hub datasets anthropic numpy matplotlib pytest

# 3. Real checks, not just imports.
python - <<'PY'
import torch, transformers, vllm
print("torch", torch.__version__, "cuda", torch.version.cuda, "| transformers", transformers.__version__, "| vllm", vllm.__version__)
assert torch.cuda.is_available(), "torch cannot see the GPU: wrong driver/CUDA combination"
x = torch.randn(512, 512, device="cuda", dtype=torch.bfloat16); y = (x @ x).sum(); torch.cuda.synchronize()
print("GPU bf16 matmul ok on", torch.cuda.get_device_name(0))
from transformers import Qwen3_5ForConditionalGeneration  # the class the adapters were trained against
print("Qwen3_5ForConditionalGeneration importable")
PY

# HF_TOKEN in the environment is picked up by huggingface_hub automatically (the old `huggingface-cli` command no
# longer exists in current releases). Ariana's 164-adapter registry is only needed for the MSM arm: SYNC_ARIANA=1.
python - <<'PY'
import os
from huggingface_hub import HfApi
print("HF user:", HfApi().whoami(token=os.environ.get("HF_TOKEN"))["name"]) if os.environ.get("HF_TOKEN") else print("HF_TOKEN not set: downloads are anonymous and rate limited")
PY
if [ -n "${SYNC_ARIANA:-}" ]; then python -m evals.models sync; fi
echo "setup done. In each new terminal:  cd kl_evals && source scripts/pod_env.sh   (and export OPENROUTER_API_KEY / HF_TOKEN again)"
