#!/usr/bin/env bash
# ON THE POD. Only the GPU work: every model answers every question. Judging needs no GPU and happens afterwards
# (scripts/adherence_judge_all.sh, on the laptop), so the pod can be stopped as soon as the answers are copied off.
#
#   bash scripts/pod_setup.sh && source scripts/pod_env.sh      # once per pod
#   nohup bash scripts/adherence_generate_all.sh > gpu.log 2>&1 &  ;  tail -f gpu.log
set -euo pipefail
source scripts/pod_env.sh
echo "== 1/2  OCT targeted: base and r1_sft on 44 direct + 40 targeted probes  ($(date -u +%H:%M) UTC)"
CFG=configs/oct_targeted.json bash scripts/adherence_oct.sh gpu
rm -rf ckpt/r1_sft                                  # free ~51 GB before the chain starts
echo "== 2/2  MSM self-draft chain: base, then rounds 1-3                     ($(date -u +%H:%M) UTC)"
bash scripts/adherence_msm_selfdraft.sh gpu
echo "== GPU work finished                                                    ($(date -u +%H:%M) UTC)"
tar czf adherence_answers.tgz results/adherence/oct_targeted/responses results/adherence/msm_selfdraft/responses
ls -lh adherence_answers.tgz
cat <<'MSG'

NEXT, from your LAPTOP (adjust the host and port from the RunPod "SSH over exposed TCP" line):
  scp -P <port> -i ~/.ssh/id_ed25519 root@<ip>:/workspace/value-drift/kl_evals/adherence_answers.tgz ~/Desktop/
Check it opened (tar tzf ~/Desktop/adherence_answers.tgz | head), THEN stop the pod.
MSG
