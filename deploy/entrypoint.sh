#!/usr/bin/env bash
# Start vLLM (Qwen3-8B-AWQ, the flags the agent was evaluated with), wait until it serves the model,
# then start the Gradio app in the foreground. Either process exiting stops the container.
set -uo pipefail
log() { printf '[entrypoint %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
MEM=${VLLM_GPU_MEM_UTIL:-0.85}; LEN=${VLLM_MAX_MODEL_LEN:-32768}
log "starting vLLM (gpu memory ${MEM}, context ${LEN})"
vllm serve "$VLLM_MODEL_PATH" --host 127.0.0.1 --port 8000 \
    --served-model-name "$SURVBREGDIV_MODEL_NAME" \
    --max-model-len "$LEN" --gpu-memory-utilization "$MEM" --enforce-eager \
    --structured-outputs-config '{"backend": "xgrammar", "disable_any_whitespace": true}' \
    --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}' \
    ${VLLM_EXTRA_ARGS:-} &
VP=$!
trap 'kill -TERM $VP ${AP:-} 2>/dev/null; wait; exit 0' TERM INT
for i in $(seq 1 600); do
  curl -fs http://127.0.0.1:8000/v1/models | grep -q "\"$SURVBREGDIV_MODEL_NAME\"" && { log "model ready after ${i}s"; break; }
  kill -0 $VP 2>/dev/null || { log "vLLM exited before it was ready"; exit 1; }
  sleep 1
done
cd /app && /opt/appenv/bin/python app.py & AP=$!
log "app started on port ${GRADIO_SERVER_PORT}"
wait -n $VP $AP; rc=$?
log "a process exited (code $rc); stopping"
kill -TERM $VP $AP 2>/dev/null; wait
exit $rc
