#!/usr/bin/env bash
# Recreate Linux/H200 environments; tiny CUDA readiness checks, no model jobs.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash agents/scripts/bootstrap_stage2.sh [--check-only] [--download-models]
Requires Linux x86_64, Python 3.12, g++, and the archived environment freezes
and build_support files under runs/. Run from the restored project directory.
Default: install dependencies and compile the H200 causal-convolution extension.
--check-only: verify installed versions and real CUDA allocation/BF16 backward.
--download-models: also fetch the two pinned official checkpoints into HF_HOME.
Set LD_LIBRARY_PATH before launch if using NVIDIA's CUDA forward compatibility.
Does not provision resources, launch model inference/training, or modify scientific inputs.
EOF
}
check_only=0
download_models=0
for argument in "$@"; do
  case "$argument" in
    --help|-h) usage; exit 0 ;;
    --check-only) check_only=1 ;;
    --download-models) download_models=1 ;;
    *) usage >&2; exit 2 ;;
  esac
done
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_root"
export HF_HOME="${HF_HOME:-/workspace/huggingface}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/workspace/pip-cache}"
train_env="${STAGE2_TRAIN_ENV:-/workspace/venv}"
inference_env="${STAGE2_INFERENCE_ENV:-/workspace/venv-vllm}"
python_bin="${STAGE2_PYTHON:-python3}"
record_dir="${STAGE2_RECORD_DIR:-$project_root/runs/stage2-bootstrap}"
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'This recorded build targets Linux x86_64/H200.' >&2; exit 2
fi
"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'
mkdir -p "$record_dir"
# Check the driver API actually loaded, not just nvidia-smi's kernel-driver
# version. A supported forward-compatibility setup may run on an R570 host.
# This fails before expensive installs/downloads and does not import PyTorch.
"$python_bin" - "$record_dir" <<'PY'
import ctypes,json,sys
from pathlib import Path
try:
    driver=ctypes.CDLL('libcuda.so.1')
except OSError as exc:
    raise SystemExit('CUDA driver library unavailable; check GPU passthrough and LD_LIBRARY_PATH') from exc
status=driver.cuInit(0)
if status:
    raise SystemExit(f'CUDA driver initialization failed with code {status}; verify native/forward-compatible driver support')
version=ctypes.c_int()
status=driver.cuDriverGetVersion(ctypes.byref(version))
if status or version.value<13000:
    raise SystemExit(f'CUDA13 driver API required; loaded version={version.value}, status={status}. '
                     'Use a compatible host or explicitly configured NVIDIA cuda-compat package.')
Path(sys.argv[1],'driver-readiness.json').write_text(json.dumps({'driver_api_version':version.value,'cuInit':0},indent=2)+'\n')
PY
# Both workers use this known-working CUDA 13.0 compiler/runtime layout.
export CUDA_HOME="$train_env/lib/python3.12/site-packages/nvidia/cu13"
export PATH="$train_env/bin:$CUDA_HOME/bin:$PATH"

if [[ "$check_only" == 0 ]]; then
  command -v g++ >/dev/null
  for artifact in training-environment.freeze.txt inference-environment.freeze.txt \
                  build_support/build-source.json build_support/causalconv-sm90-setup.py; do
    test -f "runs/$artifact" || { echo "Missing archived artifact: runs/$artifact" >&2; exit 2; }
  done
  "$python_bin" -m venv "$train_env"
  "$python_bin" -m venv "$inference_env"
  # The freeze's local file URL is rebuilt below, never silently omitted.
  "$python_bin" - "$record_dir" <<'PY'
from pathlib import Path
import sys
lines=Path('runs/training-environment.freeze.txt').read_text().splitlines()
local=[line for line in lines if ' @ file:' in line]
assert len(local)==1 and local[0].startswith('causal_conv1d @ file:'), local
Path(sys.argv[1], 'training-packages.txt').write_text('\n'.join(x for x in lines if x not in local)+'\n')
PY
  "$train_env/bin/python" -m pip install -r "$record_dir/training-packages.txt"
  # Match setup.py's import order; pinned setuptools supplies its wheel tooling.
  "$train_env/bin/python" -c 'import setuptools; from wheel.bdist_wheel import bdist_wheel'
  "$inference_env/bin/python" -m pip install -r runs/inference-environment.freeze.txt
  test -f "$CUDA_HOME/include/nv/target"
  test -x "$CUDA_HOME/bin/nvcc"
  "$CUDA_HOME/bin/nvcc" --version > "$record_dir/nvcc.txt"
  "$train_env/bin/python" - "$CUDA_HOME" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
assert (root/'lib/libcudart.so.13').is_file()
for link,target in [(root/'lib/libcudart.so','libcudart.so.13'),(root/'lib64','lib')]:
    if link.exists() or link.is_symlink():
        assert link.resolve()==(link.parent/target).resolve(), f'Unexpected CUDA path: {link}'
    else:
        link.symlink_to(target)
PY
  # Download public source with a PyPI-provided SHA256; preserve the manifest.
  "$train_env/bin/python" - "$record_dir" <<'PY'
import hashlib,json,shutil,sys,tarfile,urllib.request
from pathlib import Path
out=Path(sys.argv[1]); metadata=json.loads(Path('runs/build_support/build-source.json').read_text())
release=json.load(urllib.request.urlopen('https://pypi.org/pypi/causal-conv1d/1.7.0/json'))
source=next(x for x in release['urls'] if x['packagetype']=='sdist')
assert source['url']==metadata['source_url'], 'Archived source URL differs from PyPI release'
archive=out/'causal_conv1d-1.7.0.tar.gz'
urllib.request.urlretrieve(source['url'],archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==source['digests']['sha256']
with tarfile.open(archive) as bundle:
    bundle.extractall(out,filter='data')
setup=out/'causal_conv1d-1.7.0/setup.py'
shutil.copyfile('runs/build_support/causalconv-sm90-setup.py',setup)
assert 'arch=compute_90,code=sm_90' in setup.read_text()
(out/'source_verified.json').write_text(json.dumps({'source':source['url'],'sha256':source['digests']['sha256'],
    'setup_sha256':hashlib.sha256(setup.read_bytes()).hexdigest()},indent=2)+'\n')
PY
  export CAUSAL_CONV1D_FORCE_BUILD=TRUE
  export MAX_JOBS="${MAX_JOBS:-4}"
  "$train_env/bin/python" -m pip install --no-build-isolation --no-deps \
    "$record_dir/causal_conv1d-1.7.0"
  "$train_env/bin/python" -m pip freeze > "$record_dir/training-environment.freeze.txt"
  "$inference_env/bin/python" -m pip freeze > "$record_dir/inference-environment.freeze.txt"
fi

"$train_env/bin/python" - "$record_dir" <<'PY'
import importlib.metadata,json,sys
from pathlib import Path
import torch,transformers,causal_conv1d,causal_conv1d_cuda,fla
assert torch.__version__=='2.14.0+cu130',torch.__version__
assert transformers.__version__=='5.17.0'
assert importlib.metadata.version('causal-conv1d')=='1.7.0'
assert importlib.metadata.version('flash-linear-attention')=='0.5.2'
# FLA can initialize CUDA while detecting the device during import. Readiness
# depends on real computation below, not on whether detection happened early.
initialized_during_import = torch.cuda.is_initialized()
assert torch.cuda.is_available(), 'Training environment cannot initialize CUDA'
assert torch.cuda.device_count()==1, 'Expected one visible engineering GPU'
x=torch.ones((16,16),device='cuda',dtype=torch.bfloat16,requires_grad=True)
loss=(x@x).float().mean()
loss.backward()
torch.cuda.synchronize()
assert loss.item()==16 and torch.isfinite(x.grad).all().item(), 'CUDA BF16 forward/backward failed'
device=torch.cuda.get_device_properties(0)
result={'torch':torch.__version__,'transformers':transformers.__version__,'cuda_initialized':True,
        'cuda_initialized_during_import':initialized_during_import,
        'device':device.name,'memory_gb':device.total_memory/1e9,'bf16_forward_backward':True}
Path(sys.argv[1],'training-imports.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
PY
PATH="$inference_env/bin:$PATH" "$inference_env/bin/python" - "$record_dir" <<'PY'
import importlib.metadata,json,shutil,sys
from pathlib import Path
import torch,transformers,vllm
assert torch.__version__=='2.13.0+cu130',torch.__version__
assert transformers.__version__=='5.17.0'
assert importlib.metadata.version('vllm')=='0.29.0'
assert shutil.which('ninja'), 'Inference ninja missing from PATH'
initialized_during_import = torch.cuda.is_initialized()
assert torch.cuda.is_available(), 'Inference environment cannot initialize CUDA'
assert torch.cuda.device_count()==1, 'Expected one visible engineering GPU'
x=torch.ones((16,16),device='cuda',dtype=torch.bfloat16,requires_grad=True)
loss=(x@x).float().mean()
loss.backward()
torch.cuda.synchronize()
assert loss.item()==16 and torch.isfinite(x.grad).all().item(), 'CUDA BF16 forward/backward failed'
device=torch.cuda.get_device_properties(0)
result={'torch':torch.__version__,'vllm':vllm.__version__,'ninja':shutil.which('ninja'),'cuda_initialized':True,
        'cuda_initialized_during_import':initialized_during_import,
        'device':device.name,'memory_gb':device.total_memory/1e9,'bf16_forward_backward':True}
Path(sys.argv[1],'inference-imports.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
PY
if [[ "$download_models" == 1 && "$check_only" == 0 ]]; then
  "$train_env/bin/python" - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('Qwen/Qwen3.5-9B',revision='c202236235762e1c871ad0ccb60c8ee5ba337b9a')
snapshot_download('Qwen/Qwen3.5-27B',revision='fc05daec18b0a78c049392ed2e771dde82bdf654')
PY
fi
echo 'Bootstrap and real CUDA readiness checks complete. Model/kernel integration validation remains separate.'
