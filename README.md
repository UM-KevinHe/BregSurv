<div align="center">

# 🧬 BregSurv Agent

**A local AI agent for survival analysis that learns from external data — published models or other cohorts — and only when it helps.**

[![Try it on Hugging Face](https://img.shields.io/badge/🤗%20Try%20it-Hugging%20Face%20Space-yellow)](https://huggingface.co/spaces/anon-bregsurv/BregSurv)
[![R ≥ 4.5](https://img.shields.io/badge/R-%E2%89%A5%204.5-276DC3?logo=r)](https://www.r-project.org/)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Model: Qwen3-8B](https://img.shields.io/badge/LLM-Qwen3--8B%20(local)-6f42c1)](https://huggingface.co/Qwen/Qwen3-8B-AWQ)
[![License: GPL-3](https://img.shields.io/badge/License-GPL--3-green)](LICENSE.md)

<img src="assets/demo.gif" width="820" alt="BregSurv Agent demo"/>

<sub>▶️ Full demo video: <a href="assets/demo.mp4">assets/demo.mp4</a></sub>

</div>

---

> **Two parts, one repository.** **BregSurv Agent** is a chat application: you describe the analysis in
> your own words, and it plans, fits and reports it. **BregSurv** is the R package the agent runs on,
> its statistical core, and it can be used on its own: you specify the target model, the external
> release and the divergence, and it fits. Every number the agent reports is computed by the package.

## 📖 Overview

You have a small local **cohort**, and someone else has **more data**: a published risk model from a national registry, or another centre's patient records. Borrowing from that external information can make your survival analysis far more precise. Borrowing blindly can also make it worse, because the external population is never quite yours.

**BregSurv Agent** does this analysis for you from a single sentence:

> *"Follow-up is in `followup_days`, `died` is 1 when the patient died. Adjust for age, BMI, eGFR, haemoglobin, albumin, dialysis years, donor age and cold ischaemia time. We also have coefficients from a registry model — borrow from them if that helps."*

It reads your request and your files, checks how well the external information fits your data, plans which analyses are worth running, fits them, and lets cross-validation decide — including the two honest baselines, **your data alone** and **the external model as it is**. You get a plain-language answer in the chat and a full PDF report.

🔒 **Everything runs on your own machine.** The language model (Qwen3-8B) is served locally; no patient row ever leaves your computer, and no external API is called.

---

## ✨ Why BregSurv Agent?

| | |
|---|---|
| 🎯 **Borrows only when it helps** | Your data alone and the external model unchanged are always in the comparison, so the agent can — and does — tell you when borrowing does *not* pay. |
| 🧠 **The LLM plans, the statistics decide** | The model reads diagnostics of how your data and the external information agree and plans the analysis; a verified R estimator library fits it; cross-validation picks the winner. |
| 🔢 **No number is written by the model** | Every estimate in the chat and the report is inserted from the fitted objects. The model writes words, never digits. |
| ♻️ **Fully reproducible** | Each run ships a script that reproduces the analysis from the R library alone, with no language model involved. |
| 💬 **Made for clinicians** | Drop files into the chat and describe the analysis in your own words. The agent asks only what the data cannot tell it. |
| 🖥️ **Small and local** | An 8B model on a single GPU (≥ 16 GB). No cloud account, no API key, no data transfer. |

---

## 🚀 Quick Start

### Option 1 — Try it online (no installation)

Open the **[Hugging Face Space](https://huggingface.co/spaces/anon-bregsurv/BregSurv)** and click **Try the example data**. The demo uses synthetic data only; for real patient data, run it locally.

### Option 2 — Run it on your own GPU (recommended for real data)

You need [Docker](https://docs.docker.com/get-docker/) with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) and a GPU with at least 16 GB of memory.

```bash
git clone https://github.com/UM-KevinHe/BregSurv.git
cd BregSurv
docker build -t bregsurv-agent .
docker run --gpus all -p 7860:7860 bregsurv-agent
```

Open **http://localhost:7860**. The first start takes a few minutes while the model loads. The same chat interface as the online demo runs entirely on your machine — your data stays there. Settings, and running without Docker or without any language model, are in [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

### Option 3 — Use the R package directly

The agent's statistical core is a standalone R package. Without the agent, you state the analysis
yourself: the target model, the external release and the divergence.

```r
# install.packages("remotes")
remotes::install_github("UM-KevinHe/BregSurv")
library(BregSurv)
fit <- cv.bregsurv(target     = target_cox(time, event, z),
                   release    = release_coef(beta_registry),   # what the external source published
                   divergence = "kl")                          # how it enters the objective
```

See [the R package](#-the-r-package-the-agents-statistical-core-on-its-own) below and the
[package website](https://um-kevinhe.github.io/BregSurv/).

---

## 💬 How a conversation goes

1. **Drop your files** into the message box: your cohort (`.csv`, `.xlsx`, `.rds`, …) and, optionally, the external information — a coefficient table, a JSON with coefficients and covariance, a baseline-hazard table, or another cohort's records. A second file with the same columns can be your **test set**.
2. **Say what you want** in plain words. Name the follow-up time, the event, and what to adjust for.
3. **Watch it work.** The chat shows each step as it happens:

   ```
   ✓ Reading your request
   ✓ Finding the columns you named
   ✓ Checking your data
   ✓ Checking how well the external data fits your cohort
   ✓ Planning which models to fit
   ✓ Fitting the planned models
   ✓ Comparing the models and choosing the best
   ✓ Writing the report
   ```

4. **Read the answer.** A short summary in the chat — what was compared, whether borrowing helped, and the coefficients of the recommended model — with the **full PDF report** attached.
5. **Ask follow-up questions** — *"Why was that model chosen instead of just using my own data?"* — and get plain-language answers grounded in the fitted results.

<div align="center">
<img src="assets/screenshot_home.png" width="45%" alt="The agent's home screen"/> &nbsp; <img src="assets/screenshot_result.png" width="45%" alt="An analysis result in the agent"/>
</div>

---

## 📦 The R package: the agent's statistical core, on its own

Every number the agent reports is computed by **BregSurv**, an R package that also works on its own,
without the agent or any language model. Where the agent reads your request and plans the analysis,
with the package you specify it yourself, in one call:

```r
cv.bregsurv(target, release, divergence, ...)
```

| argument | what you specify |
|---|---|
| `target` | the **target model**: the model you fit to your local data |
| `release` | the **external release**: what the external source made available |
| `divergence` | the **divergence**: how the release enters the objective |
| `penalty` | optionally, a penalty on the coefficients |

`cv.bregsurv()` then chooses how strongly to borrow, by cross-validation on your data. Behind the call
is one objective,

$$
Q_\eta(\theta) = -\ell(\theta) + \eta\,\mathcal{B}_G(\theta), \qquad \eta \ge 0,
$$

where $\ell$ is your cohort's log-likelihood, $\mathcal{B}_G$ is a Bregman divergence between your
model and the external one, and $\eta$ is how strongly to borrow ($\eta = 0$ is your data alone).

### A first fit

```r
library(BregSurv)
data(ExampleData_lowdim)
tr <- ExampleData_lowdim$train

target  <- target_cox(time = tr$time, event = tr$status, z = tr$z)
release <- release_coef(ExampleData_lowdim$beta_external_poor)   # a published model on 2 of 6 covariates

kl  <- cv.bregsurv(target, release, divergence = "kl")
euc <- cv.bregsurv(target, release, divergence = "mahalanobis")
own <- cv.bregsurv(target)                                        # your data alone

# the cross-validated losses compare directly (lower is better)
c(target_only = own$value, kullback_leibler = kl$value, euclidean = euc$value)
#>      target_only kullback_leibler        euclidean
#>            2.625            2.513            2.520
```

The same call fits the other targets:

```r
cv.bregsurv(target_ncc(case, set, z), release_coef(beta), divergence = "kl", penalty = "lasso")
cv.bregsurv(target_discrete(interval, event, z), release_model(beta, baseline = dH0))
cv.bregsurv(target_discrete(interval, event, z, score = nn_score()), release_model(beta, baseline = dH0))
```

### Installation

Not yet on CRAN. Install from GitHub:

```r
install.packages("remotes")
remotes::install_github("UM-KevinHe/BregSurv")
```

Requires R ≥ 4.0 and a C++17 compiler; neural targets also need `install.packages("torch")`.

### Documentation

- **Get started**: <https://um-kevinhe.github.io/BregSurv/articles/BregSurv.html>
- **The framework**, the objective and where every function sits in it:
  <https://um-kevinhe.github.io/BregSurv/articles/framework.html>
- **Function reference**: <https://um-kevinhe.github.io/BregSurv/reference/>
- **For AI coding assistants**, a compact map of the package following the
  [llms.txt](https://llmstxt.org/) convention: <https://um-kevinhe.github.io/BregSurv/llms.txt>

---

## 📁 Repository layout

```
BregSurv/
├── app.py               # the chat interface (Gradio)
├── bregsurv_agent/      # the agent: reading, planning, checks, reports
├── mcp/r_scripts/       # the R side of the agent (profiling, fitting, diagnostics)
├── mcp/r_pkgs/          # DiscreteKL, used by the agent's discrete-time models
├── R/ src/ man/ data/   # the BregSurv R package: the agent's statistical core
├── vignettes/ docs/     # the package website and its articles
├── demo/                # synthetic example data
├── eval/                # synthetic example banks and the fixtures the tests read
├── tests/               # the agent's test suites (*.py) and the package's tests (testthat/)
├── deploy/              # deployment guide and the Hugging Face Space files
└── Dockerfile           # one-command local deployment
```

---
## ✉️ Contact

Questions and issues: please open a [GitHub issue](https://github.com/UM-KevinHe/BregSurv/issues).
