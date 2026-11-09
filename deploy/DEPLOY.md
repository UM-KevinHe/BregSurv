# Running the BregSurv agent

One image holds everything the agent needs: the language model (Qwen3-8B, 4-bit AWQ) served by
vLLM, a small embedding and reranking model for its worked examples, R with this repository's
estimator library and the discrete-time packages, and the Gradio interface. No external API is
called; your data never leaves the machine.

## Requirements

| | |
|---|---|
| GPU | NVIDIA, 16 GB of memory or more |
| driver | recent enough for CUDA 12.9 |
| software | Docker 24+ with Compose v2 and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) |
| disk | about 40 GB for the image, of which the model weights are about 7 GB |

The image is Linux x86_64. Docker Desktop on Windows with WSL 2 GPU support can run it; macOS cannot,
since vLLM needs CUDA.

## Quick start

```
git clone https://github.com/UM-KevinHe/BregSurv.git
cd BregSurv
docker compose up --build
```

Open <http://localhost:7860>. The build compiles R packages and downloads the model weights, so the
first one takes a while; starting the container afterwards takes a few minutes while vLLM loads the
model. The page opens on a synthetic example cohort and a synthetic registry release: press **Tab** in
the message box for an example request, then **Enter**.

## Settings

Set these with `environment:` in `docker-compose.yml` or `-e` on `docker run`.

| variable | default | what it does |
|---|---|---|
| `VLLM_GPU_MEM_UTIL` | `0.75` | share of GPU memory vLLM may take |
| `VLLM_MAX_MODEL_LEN` | `32768` | context window |
| `BREGSURV_PLANNER` | `on` | `off` fits every member the data admit on default grids instead of the model's plan |
| `BREGSURV_THINKING` | `auto` | lets the planning calls reason before they answer |
| `BREGSURV_FIT_BUDGET` | `20` | cost units a plan may spend |
| `BREGSURV_AUTH_USER`, `BREGSURV_AUTH_PASS` | unset | when both are set, the page asks for a login |
| `DEPLOYMENT_MODE` | `local` | `demo` shows the banner for a shared host |

Analyses are kept under `~/.bregsurv/sessions` inside the container and can be reopened from the
sidebar; mount a volume there to keep them across containers.

## Without Docker

The agent is a Python program that calls R. With R 4.0+, this package
(`remotes::install_github("UM-KevinHe/BregSurv")`) and DiscreteKL
(`R CMD INSTALL mcp/r_pkgs/DiscreteKL`) installed:

```
pip install -r deploy/requirements.txt
python app.py
```

Point it at any OpenAI-compatible server with `SURVBREGDIV_MODEL_ENDPOINT` and
`SURVBREGDIV_MODEL_NAME`; the planning and reading calls need constrained (JSON-schema) decoding, which
vLLM provides. With no endpoint configured the agent still runs: it asks for the roles of your columns
by numbered questions, fits every member the data admit, and returns the same report, audit trail and
replay script.

## Hosted demo

The Hugging Face Space runs the same image, built from `deploy/Dockerfile` in a folder laid out as the
Space expects: `deploy/Dockerfile`, `deploy/entrypoint.sh`, `deploy/requirements.txt` and
`deploy/README_space.md` (renamed `README.md`) at its top; `app/` holding `app.py`, `bregsurv_agent/`,
`demo/`, `mcp/r_scripts/` and `mcp/py_scripts/`; and `r_pkgs/` holding this R package (`DESCRIPTION`,
`NAMESPACE`, `R/`, `src/`, `man/`, `data/`) and `mcp/r_pkgs/DiscreteKL`. Use hardware with one L4 GPU or
larger, set `DEPLOYMENT_MODE=demo`, and set the two `BREGSURV_AUTH_*` secrets if access should be
restricted.
