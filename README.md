# BregSurv

**Transfer learning for time-to-event modelling via Bregman divergence.**

`BregSurv` enables principled borrowing of external information when fitting
Cox proportional hazards or nested case–control (NCC) models, through a unified
Bregman-divergence framework that accommodates population heterogeneity between
internal and external cohorts.

> #### Writing R code with an AI assistant?
>
> An AI-optimized reference is published at
> **<https://um-kevinhe.github.io/BregSurv/llms.txt>**
> (following the [llms.txt](https://llmstxt.org/) convention).
> Point your AI at that URL, or paste its contents into the chat, to give the
> assistant a compact map of the package — decision tree, parameter reference,
> worked examples, and common pitfalls — without ingesting the full website.

## Running BregSurv from Claude Desktop

We also ship a **Claude Desktop extension** (an MCP server) that lets the
AI assistant run `BregSurv` analyses *for* you, instead of generating R
code for you to run yourself. You describe your data and your question in
plain English (or Chinese); Claude picks the right model from the package,
calls the R function on your machine, and explains the result.

**Why this exists.** The R API has many models (Cox / NCC × KL / MDTL /
individual-level × low-dim / ridge / enet) and several CV criterion
families. Choosing the right combination — and tuning η — is the part
non-statistician users struggle with. The extension exposes a guided
5-question wizard plus all model fitters as MCP tools, so the assistant
can do the bookkeeping while you focus on the science.

**What you need on your machine:**

- **R ≥ 4.0** with the `BregSurv` package installed (see
  [Installation](#installation) below).
- **[Claude Desktop](https://claude.ai/download)** (free; macOS, Windows,
  or Linux).
- *Nothing else.* Python and the `uv` runtime are bundled inside Claude
  Desktop and set up automatically the first time you install the
  extension. **Your data never leaves your computer** — the extension
  only sends file paths and analysis summaries (coefficients, CV scores)
  back through the chat.

**Quick install.** Download `bregsurv-<version>.mcpb` from the
[Releases page](https://github.com/UM-KevinHe/BregSurv/releases),
then in Claude Desktop: **Settings → Extensions → Advanced settings →
Extension Developer → "Install Extension…"** and pick the file. Tell the
install dialog where your `Rscript` lives, then **toggle the extension
ON** in the Extensions list (new extensions are disabled by default —
this is the most common "I installed it but Claude doesn't see it"
problem).

Full step-by-step instructions, troubleshooting, and the privacy model:
[`mcp/INSTALL.md`](mcp/INSTALL.md).


## Installation

```r
# CRAN
install.packages("BregSurv")

# Development version from GitHub
remotes::install_github("UM-KevinHe/BregSurv")
```

Requires R ≥ 4.0.

## Documentation

- **Tutorials and methodology**: <https://um-kevinhe.github.io/BregSurv/>
- **Function reference**: <https://um-kevinhe.github.io/BregSurv/reference/>

## Getting help

The package is under active development; please report issues or unexpected
behavior to any of the maintainers:

- Yubo Shao — <ybshao@umich.edu>
- Junyi Qiu — <junyiqiu@umich.edu>
- Kevin He — <kevinhe@umich.edu>
