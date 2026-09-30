# Start command for the stage-08 RunPod template (image vllm/vllm-openai:v0.30.0 with entrypoint /bin/bash -c).
# Same server flags as the 27B runs (agents/notes/06_selfhost_pilot/NOTES.md); only the model differs.
# runpodctl splits --docker-start-cmd on commas: this file must contain none.
apt-get update -qq && apt-get install -y -qq openssh-server > /dev/null
mkdir -p /root/.ssh /run/sshd && chmod 700 /root/.ssh
echo "$PUBLIC_KEY" >> /root/.ssh/authorized_keys
echo "$VD_PUBKEY" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
/usr/sbin/sshd
vllm serve Qwen/Qwen3.5-9B --served-model-name qwen3.5-9b --host 127.0.0.1 --port 8000 --max-model-len 131072 --language-model-only --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml --gpu-memory-utilization 0.92 --max-num-seqs 64 --enable-prefix-caching 2>&1 | tee /root/vllm.log
sleep infinity
