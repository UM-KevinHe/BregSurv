# Self-host the BregSurv agent

This guide walks you through running the full BregSurv agent — Gradio Web UI + verified MCP tool layer + local Qwen 2.5-7B-AWQ LLM — on a single machine with an NVIDIA GPU. Nothing leaves your network.

If you don't have a GPU, use the public demo at <https://huggingface.co/spaces/anon-bregsurv/BregSurv> or install the Claude Desktop extension (`mcp/INSTALL.md`) — both are zero-GPU paths.

---

## What you get

- **Web UI** at `http://localhost:7860` — natural-language query box, coefficient tables, CV plots, downloadable reports.
- **Local LLM** — Qwen 2.5-7B-Instruct-AWQ runs in-container via vLLM. No API key, no per-token cost, no data egress.
- **R + BregSurv + 33 MCP tools** — every fit / CV / NCC / highdim model in the package.
- **Audit artifacts** — every chat produces `trace.json` (tool-call log) and `repro.R` (standalone reproducer); both downloadable from the UI.

---

## Prerequisites

| | Minimum | Recommended |
|---|---|---|
| NVIDIA GPU VRAM | 12 GB (RTX 3060 12 GB / 4060 Ti 16 GB) | 24 GB+ (A40, A6000, A100, RTX 4090) |
| NVIDIA driver | ≥ 550 (CUDA 12.4 runtime) | latest |
| System RAM | 16 GB | 32 GB |
| Disk | 30 GB free | 50 GB free |
| OS | Linux x86_64 | Linux x86_64 |

Software:

1. **Docker Engine 24+** with Compose v2 — <https://docs.docker.com/engine/install/>
2. **NVIDIA Container Toolkit** — <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html>. Test with:
   ```
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```
   You should see a table of your GPU(s). If you don't, fix this before going further.

macOS and Windows are not supported for self-host (vLLM does not run on Apple Silicon, and WSL2 + GPU passthrough is too fragile to recommend). Use the HF Space demo on those platforms.

---

## Quick start (Docker Compose — recommended)

```
git clone https://github.com/UM-KevinHe/BregSurv.git
cd BregSurv

docker compose up --build
```

First run takes **~10 min** to build the image (R compile is the slow step) and **another ~5 min** on first boot to download Qwen 2.5-7B-AWQ (~5.2 GB) from Hugging Face. Subsequent boots reuse the cached weights and start in ~60 s.

When you see

```
[entrypoint HH:MM:SS] vLLM ready after Ns
[entrypoint HH:MM:SS] launching Gradio app
```

open <http://localhost:7860> in your browser. Drop a `.rda` file into `./data_in/` on the host — it appears at `/data/your_file.rda` inside the container, which is what you reference in the Gradio chat.

Stop with `Ctrl-C` (foreground) or `docker compose down` (detached).

---

## Quick start (plain `docker run`)

```
docker build -f Dockerfile.selfhost -t bregsurv-agent:selfhost .

docker run --rm --gpus all -p 7860:7860 \
    --shm-size=8g \
    -v bregsurv-models:/root/.cache/huggingface \
    -v "$PWD/data_in:/data:ro" \
    bregsurv-agent:selfhost
```

Notes:

- `--gpus all` and `--shm-size=8g` are both required. Without them you get `RuntimeError: CUDA not available` and `Bus error` respectively.
- The named volume `bregsurv-models` persists the model cache across `--rm` runs.

---

## Configuration

All knobs are environment variables. The defaults in `Dockerfile.selfhost` work for a single 24 GB GPU and a 12 GB AWQ model. Override with `-e KEY=value` (`docker run`) or `environment:` block (compose).

| Variable | Default | Purpose |
|---|---|---|
| `VLLM_MODEL_ID` | `Qwen/Qwen2.5-7B-Instruct-AWQ` | HF repo of the model to serve. To swap to BF16 (paper-comparison only), use `Qwen/Qwen2.5-7B-Instruct` and set `VLLM_GPU_MEM_UTIL=0.9` — needs 24 GB+. |
| `SURVBREGDIV_MODEL_NAME` | `qwen2.5-7b-awq` | `served-model-name` for vLLM. **Must match** what `app.py` sends; if you change one, change both. |
| `VLLM_GPU_MEM_UTIL` | `0.5` | Fraction of GPU VRAM vLLM pre-allocates. AWQ INT4 only needs ~12 GB; 0.5 caps pool size so `nvidia-smi` reflects real footprint. Raise to 0.9 for BF16 or if you hit `OutOfMemoryError`. |
| `VLLM_MAX_MODEL_LEN` | `32768` | Context window. Qwen 2.5 supports 32K natively. Lower to 16384 on smaller GPUs to halve KV cache. |
| `VLLM_READY_TIMEOUT` | `900` | Seconds the entrypoint waits for `/v1/models`. Raise on slow networks (first boot only). |
| `VLLM_EXTRA_ARGS` | (empty) | Appended verbatim to `vllm serve`. Example: `--quantization awq_marlin` if vLLM picks the wrong AWQ kernel for your GPU. |
| `DEPLOYMENT_MODE` | `local` | Set to `demo` to hide the file-upload widget and switch the banner to red ("public demo, do not upload PHI"). |
| `SURVBREGDIV_MODEL_ENDPOINT` | `http://127.0.0.1:8000/v1` | Point the agent at a different LLM. Set to `https://api.openai.com/v1` (and supply `OPENAI_API_KEY`) to bypass vLLM entirely; the container still works as a UI + R bridge. |

---

## Troubleshooting

**`RuntimeError: Could not find nvcc and default cuda_home='/usr/local/cuda' doesn't exist`**

You built against a CUDA *runtime* base image. The Dockerfile already uses `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04` (devel, ships `nvcc`); if you changed the `FROM` line, change it back. Flashinfer JIT-compiles a kernel at vLLM startup and needs nvcc.

**`Bus error (core dumped)` shortly after vLLM startup**

`/dev/shm` is too small. Add `--shm-size=8g` to `docker run` or `shm_size: "8gb"` to compose (already in our `docker-compose.yml`).

**`torch.cuda.OutOfMemoryError` during model load**

Either your GPU is too small for AWQ INT4 (need ≥ 12 GB free) or `VLLM_GPU_MEM_UTIL` is set too high relative to other GPU users. Lower it (`-e VLLM_GPU_MEM_UTIL=0.3`) or close other GPU processes.

**vLLM stuck at `Loading checkpoint shards: 0%`**

First boot is downloading weights from Hugging Face. Tail with `docker compose logs -f bregsurv` — you should see HTTP progress. If stuck >10 min, check egress to `huggingface.co`; behind a corporate proxy, set `HTTPS_PROXY` and `HF_ENDPOINT` env vars. Hospitals / air-gapped sites: see "Offline install" below.

**404 errors in the Gradio UI when sending a chat**

Your `SURVBREGDIV_MODEL_NAME` doesn't match vLLM's `--served-model-name`. The defaults match; if you overrode one, override the other to the same string.

**Port 7860 already in use**

Change the host-side port: `-p 7870:7860` (or edit `docker-compose.yml`).

**`nvidia-container-cli: initialization error: nvml error: driver not loaded`**

The NVIDIA driver isn't loaded on the host, or `nvidia-container-toolkit` isn't configured. Run `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` to isolate — it must succeed before our image will.

---

## Offline install (air-gapped sites)

The default boot downloads Qwen weights from Hugging Face. For hospitals / networks that block `huggingface.co`:

1. On an internet-connected machine:
   ```
   hf download Qwen/Qwen2.5-7B-Instruct-AWQ --local-dir ./qwen-awq
   ```
2. Copy `./qwen-awq` to the offline host.
3. Mount it into the container and point `VLLM_MODEL_ID` at the local path:
   ```
   docker run --rm --gpus all -p 7860:7860 --shm-size=8g \
       -v "$PWD/qwen-awq:/models/qwen-awq:ro" \
       -e VLLM_MODEL_ID=/models/qwen-awq \
       bregsurv-agent:selfhost
   ```

The image itself does not phone home for anything else once built — `R CMD INSTALL` is from local source, and `bregsurv_agent` is pure Python with no callout.

---

## Updating

To pick up a new BregSurv release or a Stage 4 hotfix:

```
git pull
docker compose build --no-cache
docker compose up
```

The named model-cache volume is preserved, so you don't re-download weights.

---

## Cross-references

- `Dockerfile.selfhost` — the build recipe. Mirrors the HF Space `Dockerfile` for R + BregSurv; adds CUDA + vLLM.
- `mcp/entrypoint.sh` — boots vLLM, waits for `/v1/models`, launches Gradio. Handles SIGTERM cleanly. (Shared with the HF Space `Dockerfile`.)
- `docker-compose.yml` — one-command launcher with GPU + volume wired up.
- `mcp/INSTALL.md` — Claude Desktop / MCPB install (no Docker, no GPU; uses Claude's LLM via your existing subscription).
- HF Space demo: <https://huggingface.co/spaces/anon-bregsurv/BregSurv>.
