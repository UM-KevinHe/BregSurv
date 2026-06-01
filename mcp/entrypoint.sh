#!/usr/bin/env bash
# Shared container entrypoint for both the HF Space (`Dockerfile`) and
# the local self-host (`Dockerfile.selfhost`).
#
# Boots vLLM in the background, waits for /v1/models to respond, then
# launches the Gradio app in the foreground. Forwards SIGTERM/SIGINT
# to both so `docker stop` (or HF Space sleep) shuts down cleanly.
#
# Env vars consumed (defaults set in Dockerfile / Dockerfile.selfhost):
#   VLLM_MODEL_ID            HF repo to serve (e.g. Qwen/Qwen2.5-7B-Instruct-AWQ)
#   SURVBREGDIV_MODEL_NAME   served-model-name (must match what app.py sends)
#   VLLM_HOST / VLLM_PORT    bind address
#   VLLM_MAX_MODEL_LEN       context window (Qwen2.5 supports 32768 natively)
#   VLLM_GPU_MEM_UTIL        fraction of GPU mem vLLM pre-allocates (0.5 is
#                            plenty for AWQ INT4 on A40/A6000; raise on
#                            smaller cards)
#   VLLM_READY_TIMEOUT       seconds to wait for /v1/models (default 900,
#                            generous because first boot downloads ~5.2 GB)
#   VLLM_EXTRA_ARGS          appended verbatim to `vllm serve` (e.g.
#                            "--quantization awq_marlin" if autodetect
#                            picks the wrong kernel)

set -euo pipefail

MODEL_ID="${VLLM_MODEL_ID:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
SERVED_NAME="${SURVBREGDIV_MODEL_NAME:-qwen2.5-7b-awq}"
HOST="${VLLM_HOST:-127.0.0.1}"
PORT="${VLLM_PORT:-8000}"
MAX_LEN="${VLLM_MAX_MODEL_LEN:-32768}"
GPU_MEM_UTIL="${VLLM_GPU_MEM_UTIL:-0.5}"
READY_TIMEOUT="${VLLM_READY_TIMEOUT:-900}"
EXTRA_ARGS="${VLLM_EXTRA_ARGS:-}"

log() {
    printf '[entrypoint %s] %s\n' "$(date -u +%H:%M:%S)" "$*"
}

# ---- start vLLM in background ----
#
# --disable-frontend-multiprocessing forces vLLM to run the API server and
# the engine in the SAME process (no ZMQ IPC between them). Required on
# HF Space because the container's syscall sandbox + restricted /dev/shm
# break vLLM's default multiprocess setup with
#     zmq.error.ZMQError: Operation not supported
# at MQLLMEngineClient.run_output_handler_loop. Harmless on real Docker
# hosts with proper --shm-size; documented in vLLM 0.6.x. Keep this flag.
log "starting vLLM serve  model=${MODEL_ID}  served-as=${SERVED_NAME}  bind=${HOST}:${PORT}"
# shellcheck disable=SC2086
vllm serve "${MODEL_ID}" \
    --host "${HOST}" --port "${PORT}" \
    --served-model-name "${SERVED_NAME}" \
    --tool-call-parser hermes --enable-auto-tool-choice \
    --max-model-len "${MAX_LEN}" \
    --gpu-memory-utilization "${GPU_MEM_UTIL}" \
    --disable-frontend-multiprocessing \
    ${EXTRA_ARGS} \
    &
VLLM_PID=$!
log "vLLM PID=${VLLM_PID}"

# ---- start Gradio in background (after vLLM is ready) ----
APP_PID=""

cleanup() {
    log "shutdown signal received; terminating children"
    if [[ -n "${APP_PID}" ]] && kill -0 "${APP_PID}" 2>/dev/null; then
        kill -TERM "${APP_PID}" 2>/dev/null || true
    fi
    if kill -0 "${VLLM_PID}" 2>/dev/null; then
        kill -TERM "${VLLM_PID}" 2>/dev/null || true
    fi
    # Give vLLM up to 15 s to release GPU memory before SIGKILL fallback.
    for _ in $(seq 1 15); do
        if ! kill -0 "${VLLM_PID}" 2>/dev/null; then break; fi
        sleep 1
    done
    if kill -0 "${VLLM_PID}" 2>/dev/null; then
        log "vLLM still alive after 15s; SIGKILL"
        kill -KILL "${VLLM_PID}" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup TERM INT

# ---- wait for /v1/models ----
log "waiting up to ${READY_TIMEOUT}s for vLLM /v1/models (first boot downloads ~5 GB)"
ready=0
for i in $(seq 1 "${READY_TIMEOUT}"); do
    if curl -fs "http://${HOST}:${PORT}/v1/models" >/dev/null 2>&1; then
        log "vLLM ready after ${i}s"
        ready=1
        break
    fi
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
        log "FATAL: vLLM process exited before becoming ready"
        wait "${VLLM_PID}" || true
        exit 1
    fi
    # Progress log every 30 s so users tailing logs know we're alive.
    if (( i % 30 == 0 )); then
        log "still waiting on vLLM (${i}s elapsed)…"
    fi
    sleep 1
done

if [[ "${ready}" -ne 1 ]]; then
    log "FATAL: vLLM did not respond within ${READY_TIMEOUT}s"
    kill -TERM "${VLLM_PID}" 2>/dev/null || true
    exit 1
fi

# ---- launch app.py ----
log "launching Gradio app"
cd /app
python app.py &
APP_PID=$!
log "app.py PID=${APP_PID}"

# Wait for whichever child exits first; propagate its exit code.
# `wait -n` returns when ANY backgrounded child exits.
set +e
wait -n "${VLLM_PID}" "${APP_PID}"
exit_code=$?
set -e

log "child exited (code=${exit_code}); shutting down siblings"
cleanup
exit "${exit_code}"
