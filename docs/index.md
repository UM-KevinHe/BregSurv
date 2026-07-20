<div id="main" class="col-md-9" role="main">

# BregSurv

<div class="section level1">

**Transfer learning for time-to-event modelling via Bregman
divergence.**

`BregSurv` enables principled borrowing of external information when
fitting Cox proportional hazards or nested case–control (NCC) models,
through a unified Bregman-divergence framework that accommodates
population heterogeneity between internal and external cohorts.

> #### Writing R code with an AI assistant?
>
> An AI-optimized reference is published at
> **<https://um-kevinhe.github.io/BregSurv/llms.txt>** (following the
> [llms.txt](https://llmstxt.org/) convention). Point your AI at that
> URL, or paste its contents into the chat, to give the assistant a
> compact map of the package — decision tree, parameter reference,
> worked examples, and common pitfalls — without ingesting the full
> website.

<div class="section level2">

## Running BregSurv with an AI assistant

The R API has many models (Cox / NCC × KL / MDTL / individual-level ×
low-dim / ridge / enet) and several CV criterion families. Choosing the
right combination — and tuning η — is the part non-statistician users
struggle with. We ship an AI **agent layer** on top of the package: you
describe your data and your question in plain English, the agent picks
the right model, runs it on your machine, and explains the result.

There are **three ways** to access the agent, picking different
trade-offs between setup, LLM cost, and data privacy:

| Path                         | Setup                                    | LLM                                  | Data                                                    | Best for                                    |
|------------------------------|------------------------------------------|--------------------------------------|---------------------------------------------------------|---------------------------------------------|
| **HF Space demo**            | None — open a URL + reviewer credentials | Qwen 2.5-7B-AWQ (vLLM, in-container) | Demo data only; chat stays inside the Space container   | Paper review, quick exploration             |
| **Claude Desktop extension** | Install R + `.mcpb`                      | Claude (your existing subscription)  | File paths stay local; only tool args + results in chat | Day-to-day use on your own data             |
| **Docker self-host**         | NVIDIA GPU + Docker                      | Qwen 2.5-7B-AWQ (vLLM, in-container) | 100% local; no external API call                        | PHI, air-gapped networks, paper experiments |

<div class="section level3">

### 1. Hugging Face Space (zero-install demo)

Open <https://huggingface.co/spaces/anon-bregsurv/BregSurv> in any
browser. The Space loads the same Gradio UI as the local install with
bundled example datasets pre-loaded, and serves the same Qwen 2.5-7B-AWQ
weights via vLLM as the Docker self-host path — so what you see is what
the paper claims, not a different model’s behaviour.

Access is gated by a reviewer login; credentials are provided in the
paper submission. The Space sleeps after 15 min of inactivity to control
GPU cost; the first request after sleep takes \~90 s to wake.

**Do not upload real patient data** — although Qwen runs inside the
container (chat does not leave the Space), the demo is a public-internet
service and we make no PHI guarantees here. Use the Docker self-host or
the Claude Desktop extension for actual research data.

</div>

<div class="section level3">

### 2. Claude Desktop extension (MCPB)

For day-to-day use with your own data on your own machine, but using
Claude as the LLM driver.

**Prerequisites:**

-   **R ≥ 4.0** with the `BregSurv` package installed (see
    [Installation](#installation) below).
-   **[Claude Desktop](https://claude.ai/download)** (free; macOS,
    Windows, or Linux).
-   *Nothing else.* Python and the `uv` runtime are bundled inside
    Claude Desktop. **Your data file never leaves your computer** — only
    file paths and analysis summaries (coefficients, CV scores) transit
    the Claude chat.

**Install.** Download `bregsurv-<version>.mcpb` from the [Releases
page](https://github.com/UM-KevinHe/BregSurv/releases), then in Claude
Desktop: **Settings → Extensions → Advanced settings → Extension
Developer → “Install Extension…”** and pick the file. Tell the install
dialog where your `Rscript` lives, then **toggle the extension ON** in
the Extensions list (new extensions are disabled by default — this is
the most common “I installed it but Claude doesn’t see it” problem).

Full walkthrough, troubleshooting, and privacy model:
[`mcp/INSTALL.md`](https://um-kevinhe.github.io/BregSurv/mcp/INSTALL.md).

</div>

<div class="section level3">

### 3. Docker self-host (fully local, no API egress)

For PHI workflows, hospital networks that block outbound LLM API calls,
or anyone who wants the agent stack to run entirely on hardware they
control. Bundles a local Qwen 2.5-7B-AWQ model (via vLLM) alongside the
R package and Gradio UI in a single Docker image.

**Prerequisites:**

-   Linux x86\_64 host with NVIDIA GPU (≥ 12 GB VRAM) + driver ≥ 550.
-   Docker 24+ with [NVIDIA Container
    Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

**Quick start:**

    git clone https://github.com/UM-KevinHe/BregSurv.git
    cd BregSurv
    docker compose up --build

Then open <http://localhost:7860>. First boot takes \~15 min (R compile
+ model download); subsequent boots \~60 s.

Full guide, troubleshooting, and offline-install (air-gapped):
[`mcp/DEPLOY.md`](https://um-kevinhe.github.io/BregSurv/mcp/DEPLOY.md).

------------------------------------------------------------------------

</div>

</div>

<div class="section level2">

## Installation

<div id="cb2" class="sourceCode">

``` r
# CRAN
install.packages("BregSurv")

# Development version from GitHub
remotes::install_github("UM-KevinHe/BregSurv")
```

</div>

Requires R ≥ 4.0.

</div>

<div class="section level2">

## Documentation

-   **Tutorials and methodology**:
    <https://um-kevinhe.github.io/BregSurv/>
-   **Function reference**:
    <https://um-kevinhe.github.io/BregSurv/reference/>

</div>

<div class="section level2">

## Getting help

The package is under active development; please report issues or
unexpected behavior to any of the maintainers:

-   Yubo Shao — <ybshao@umich.edu>
-   Junyi Qiu — <junyiqiu@umich.edu>
-   Kevin He — <kevinhe@umich.edu>

</div>

</div>

</div>
