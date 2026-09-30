#!/usr/bin/env bash
# Set up a fresh RunPod H200 pod (official PyTorch template, CUDA 13 driver) for the OCT loop.
# Run from /workspace/value-drift after pushing the project (agents/notes/09_oct_loop/NOTES.md).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export HF_HOME="${HF_HOME:-/workspace/huggingface}"
REVISION=1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0   # Qwen/Qwen3.8-27B, pinned in configs/oct-loop/*.json

# 1. Training environment from the archived freeze (PyTorch 2.14 cu130, transformers 5.17, flash-linear-attention,
#    causal-conv1d built for SM90). Its old vLLM 0.29 environment goes aside: the loop uses 0.30.0 below.
STAGE2_INFERENCE_ENV=/workspace/venv-vllm-0.29 bash agents/scripts/bootstrap_stage2.sh

# 2. LoRA.
/workspace/venv/bin/python -m pip install -q --no-deps peft==0.21.0   # its dependencies are already pinned in the freeze

# 3. Inference environment: vLLM 0.30.0, the version that served the stage 07 chains, with CUDA 13 PyTorch.
#    The image's uv is too old for --torch-backend=cu130, so a newer uv is installed into the venv first.
uv venv /workspace/venv-vllm --python 3.12
/workspace/venv-vllm/bin/python -m ensurepip -q 2>/dev/null || true
VIRTUAL_ENV=/workspace/venv-vllm uv pip install -q -U uv
/workspace/venv-vllm/bin/uv pip install --python /workspace/venv-vllm/bin/python -q vllm==0.30.0 --torch-backend=cu130
/workspace/venv-vllm/bin/python -c "import vllm, torch; assert vllm.__version__ == '0.30.0' and torch.version.cuda.startswith('13'), (vllm.__version__, torch.version.cuda); print('vllm', vllm.__version__, 'torch', torch.__version__)"

# 4. Base model at the pinned revision.
/workspace/venv/bin/hf download Qwen/Qwen3.8-27B --revision "$REVISION" > /dev/null
test -f "$HF_HOME/hub/models--Qwen--Qwen3.8-27B/snapshots/$REVISION/config.json"

# 5. Records.
mkdir -p runs/oct-loop
/workspace/venv/bin/python -m pip freeze > runs/oct-loop/training-environment.freeze.txt
/workspace/venv-vllm/bin/uv pip freeze --python /workspace/venv-vllm/bin/python > runs/oct-loop/inference-environment.freeze.txt
test -f data/raw/lima/prompts.jsonl || { echo 'Missing data/raw/lima/prompts.jsonl: push it (agents/scripts/prepare_lima_prompts.py)' >&2; exit 2; }
echo 'Setup complete.'
