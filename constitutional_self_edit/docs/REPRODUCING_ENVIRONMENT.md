# Reproducing the working environment

This records the environment that passed the H200 engineering checks and executed `full-001`. It is an installation record, not a tested one-command rebuild. Recreating dependencies, restoring models, and rerunning engineering checks are separate steps; the converged scientific run must not be reopened.

## Recorded platform and environments

The pod used Ubuntu 24.04.3 LTS, Python 3.12.3, NVIDIA driver 580.126.09, and one H200 SXM reporting 150.10988032 GB device memory. The project lived at `/workspace/value-drift`; `HF_HOME=/workspace/huggingface` selected the shared model cache.

| Component | Training: `/workspace/venv` | Inference: `/workspace/venv-vllm` |
|---|---|---|
| PyTorch | 2.14.0+cu130 | 2.13.0+cu130 |
| Transformers | 5.17.0 | 5.17.0 |
| Main engine | Transformers, Accelerate 1.15.0 | vLLM 0.29.0 |
| Training optimizer | bitsandbytes 0.50.2, AdamW8bit | Not used |
| Other kernels | flash-linear-attention/fla-core 0.5.2; causal-conv1d 1.7.0 local build | FlashInfer 0.6.18; Triton 3.7.1 |
| Triton for training | 3.8.0 | — |

The complete resolved package inventories are private artifacts `runs/training-environment.freeze.txt` and `runs/inference-environment.freeze.txt`. `runs/gpu-environment.txt` is the earlier bootstrap inventory, before compiler and causal-convolution additions. The final training freeze includes a local `causal_conv1d @ file:///workspace/build/...` entry: this requires restoring/rebuilding that source, rather than blindly installing the freeze on another machine.

[`bootstrap_gpu.sh`](../scripts/bootstrap_gpu.sh) creates the training environment, installs [`requirements-gpu.txt`](../requirements-gpu.txt) and unpinned FLA, records hardware, and downloads the default 9B checkpoint. It does **not** create the vLLM environment, install the compiler toolchain, build causal-conv1d, apply the linker fixes, or restore the revision-pinned 27B model. Its default model download is not a revision pin. It is therefore only the initial bootstrap portion of the recorded setup.

## CUDA compiler and linker additions

The working compiler root was `/workspace/venv/lib/python3.12/site-packages/nvidia/cu13`, with these training-environment additions:

```text
nvidia-cuda-nvcc==13.0.88
nvidia-cuda-crt==13.0.88
nvidia-nvvm==13.0.88
nvidia-cuda-cccl==13.0.85
ninja==1.13.2
```

CCCL supplied the missing `nv/target` header. The official causal-conv1d 1.7.0 source hardcoded multiple architectures, so the saved `setup.py` overrides its final `cc_flag` to `['-gencode', 'arch=compute_90,code=sm_90']`. Kernel numerical source was unchanged. Source provenance and the modified setup are archived in `runs/build_support/build-source.json` and `runs/build_support/causalconv-sm90-setup.py`. Compiled objects were not archived; rebuild the recorded source when restoring this environment.

The build used `CUDA_HOME` set to that compiler root, `CAUSAL_CONV1D_FORCE_BUILD=TRUE`, `MAX_JOBS=4`, and pip `--no-build-isolation --no-deps`. Ninja was initially outside the SSH subprocess PATH, so the first build used distutils. Compilation succeeded; linking initially failed because the runtime package supplied `libcudart.so.13` without the unversioned linker name. The working root contains these relative symlinks:

```text
cu13/lib/libcudart.so -> libcudart.so.13
cu13/lib64 -> lib
```

The first symlink enabled linking the existing causal-convolution objects without recompiling. The second made the same runtime directory visible to FlashInfer's `CUDA_HOME/lib64` lookup. These links must resolve to the actual runtime installation on a recreated host; do not assume all CUDA packages use this layout. See `runs/causalconv-install-3.log`, `causalconv-link-fix.log`, `causalconv-install-4.log`, and `vllm-sampling-relink.log` for the executed build/link steps. The successful FlashInfer sampling relink also used the host's CUDA driver library through the normal linker search path.

## Isolated vLLM environment

The successful initial installation created a second Python 3.12 environment and installed `vllm==0.29.0` from its default PyPI packages; the resulting versions and later additions are recorded in the final freeze. The installed build uses CUDA 13.0. The pod's older `uv` did not accept `--torch-backend=cu130`; that flag was not used for the successful installation. [`requirements-inference.txt`](../requirements-inference.txt) records the top-level pins; the final freeze is the full inventory. Do not install vLLM into the training environment, because its resolved Torch version differs.

The worker launcher in [`vllm_session.py`](../recursive_oct/vllm_session.py) prepends the inference interpreter's directory to PATH, making `/workspace/venv-vllm/bin/ninja` discoverable, and adds the repository to PYTHONPATH. It inherits `HF_HOME` and `CUDA_HOME`. The working experiment launch exported:

```bash
export HF_HOME=/workspace/huggingface
export CUDA_HOME=/workspace/venv/lib/python3.12/site-packages/nvidia/cu13
```

Although the inference environment contains newer compiler packages in its freeze, the validated FlashInfer JIT used this explicit **training-environment CUDA 13.0 compiler root**. Preserve that distinction when diagnosing a rebuild. `runs/vllm-attempt-001.log` through `003.log` retain failures; `runs/vllm_benchmark/report.json` records successful M0, saved FP32-checkpoint reload, native tool parsing, and 27B generation/judging checks.

## Restoring model paths

Paths below are relative to the local repository on the archive side. Copy the complete model directory, including tokenizer/configuration files and every weight shard; copying weights alone is insufficient.

| Local archive | Revision | Remote path referenced by frozen config |
|---|---|---|
| `checkpoints/M_000` (`Qwen/Qwen3.5-9B`) | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | `/workspace/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| `checkpoints/T_fixed` (`Qwen/Qwen3.5-27B`) | `fc05daec18b0a78c049392ed2e771dde82bdf654` | `/workspace/huggingface/hub/models--Qwen--Qwen3.5-27B/snapshots/fc05daec18b0a78c049392ed2e771dde82bdf654` |
| `runs/engineering_smoke/final` | Locally trained DPO→SFT checkpoint; see its completion metadata | `/workspace/value-drift/runs/engineering_smoke/final` |

The first two archive locations and revisions are recorded in `runs/checkpoint_locations.json`; lead archival verification determines copy completeness. Restoring self-contained directories at these exact paths supports direct path loading without reconstructing Hugging Face cache symlinks. If downloading again, specify the exact revisions rather than `main`. A future run using different paths must use a separately labeled configuration; never rewrite the preserved `full-001` snapshots.

## Validation after restoration

Run CPU tests first, then separately authorized engineering GPU checks for real tokenization/EOS, full DPO/SFT updates and reload, causal-convolution numerical behavior, and vLLM ordinary/tool generation. The recorded successful results are in [`TRAINING_BENCHMARK.md`](TRAINING_BENCHMARK.md), `runs/pre-main-tests.log`, and `runs/vllm_benchmark/`. A successful package install alone does not establish those properties. Full-parameter training uses FP32 saved weights with BF16 autocast; inference explicitly loads BF16. No training adapter, quantized-weight substitute, or vision-backbone update is implied by reproducing these environments.

## Stage-two host using CUDA forward compatibility

The initial restored host used driver570.195.03 / CUDA12.8. A requested native CUDA13 H200 was unavailable in US-GA-2. The separate volume preserved all installs and model downloads across replacement.

The replacement H200 reported native driver **570.172.08**, which cannot directly initialize the installed CUDA 13 PyTorch builds. The lead extracted NVIDIA's official `cuda-compat-13-0` package, version **580.178.04-1ubuntu1**, into persistent `/workspace/cuda-compat-13`. [Official package](https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-compat-13-0_580.178.04-1ubuntu1_amd64.deb); SHA256: `f7e29a545c1334bb5ca4b054213de9c9ceb70f8bf561aa214075020c4e0b60cf`.

Before every bootstrap, test, or runner launch on that host, the lead exports:

```bash
export LD_LIBRARY_PATH=/workspace/cuda-compat-13/usr/local/cuda-13.0/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export CUDA_HOME=/workspace/venv/lib/python3.12/site-packages/nvidia/cu13
export HF_HOME=/workspace/huggingface
```

This replaces user-mode CUDA driver libraries for these processes; it does not replace the host kernel driver. The vLLM subprocess inherits the environment. NVIDIA lists CUDA 13.0 compatibility support for R570 data-center GPUs, with feature restrictions that still require workload validation. [Compatibility documentation](https://docs.nvidia.com/deploy/cuda-compatibility/forward-compatibility.html)

Both installed Torch environments passed driver initialization, reported CUDA driver API 13000, and completed BF16 matrix multiplication/backward with finite gradients and synchronization on this replacement. These are readiness checks, not a substitute for model integration. `bootstrap_stage2.sh --check-only` now performs these real CUDA checks in both environments; its early driver check accepts a working compatibility setup without requiring the native driver to be R580. The full DPO→post-DPO introspection→SFT→vLLM reload validation subsequently passed; evidence is preserved in `runs/stage2_engineering`. On a future native-driver host, reassess/remove the compatibility-library override rather than carrying it forward automatically.
