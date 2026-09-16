#!/usr/bin/env bash
set -euo pipefail
cd /workspace/value-drift
export HF_HOME=/workspace/huggingface
export PIP_CACHE_DIR=/workspace/pip-cache
python3 -m venv /workspace/venv
/workspace/venv/bin/python -m pip install --upgrade pip
/workspace/venv/bin/python -m pip install -r requirements-gpu.txt
/workspace/venv/bin/python -m pip install flash-linear-attention
/workspace/venv/bin/python -m pip freeze > runs/gpu-environment.txt
/workspace/venv/bin/python - <<'PY'
import torch, transformers
from huggingface_hub import snapshot_download
from pathlib import Path
import json
out={'torch':torch.__version__,'transformers':transformers.__version__,'cuda':torch.version.cuda,'device':torch.cuda.get_device_name(),'memory_gb':torch.cuda.get_device_properties(0).total_memory/1e9}
print(json.dumps(out),flush=True)
Path('runs/hardware.json').write_text(json.dumps(out,indent=2))
snapshot_download('Qwen/Qwen3.5-9B')
print('MODEL_DOWNLOAD_COMPLETE',flush=True)
PY
