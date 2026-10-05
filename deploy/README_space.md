---
title: BregSurv agent
emoji: 🩺
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
suggested_hardware: l4x1
pinned: false
license: other
short_description: Local survival agent that borrows from published models
---

# BregSurv agent

A survival-analysis agent that borrows from a published model or registry only when that helps.
Everything runs inside this container: the language model (Qwen3-8B-AWQ on vLLM), the harness, and
the R estimator library BregSurv. No external API is called.

The page opens on a synthetic example cohort and a synthetic registry release. Press **Tab** in the
message box for an example request, then **Enter**.

## Run it on your own GPU

Your data then never leaves your machine. You need Docker with the NVIDIA container toolkit and a
GPU with at least 16 GB of memory.

```
git clone https://huggingface.co/spaces/anon-bregsurv/BregSurv
cd BregSurv
docker build -t bregsurv-agent .
docker run --gpus all -p 7860:7860 bregsurv-agent
```

Open http://localhost:7860. The first start takes a few minutes while the model loads.
