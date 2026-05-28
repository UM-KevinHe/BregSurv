---
title: BregSurv Agent
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: gpl-3.0
short_description: Verification-backed LLM agent for transfer-learning survival analysis (Cox + NCC).
---

# BregSurv Agent

A natural-language interface to **[BregSurv](https://github.com/UM-KevinHe/BregSurv)** — a Bregman-divergence-based transfer learning framework for survival analysis (Cox PH and nested case-control regression with external information borrowing).

Describe your analysis in plain English. The agent picks the correct estimator from a fixed library of 33 statistically-derived tools, runs it on the supplied data, and returns:

- a natural-language summary of the results,
- the coefficient table,
- a CV-path plot (when applicable),
- **`repro.R`** — a standalone R script that bit-matches the agent's coefficients without any LLM in the loop,
- **`trace.json`** — a per-tool-call audit trail recording every step the agent took.

## How this is "verification-backed"

The agent only ever chooses from a fixed catalogue of estimators whose Bregman/KL/Mahalanobis form is derived in the accompanying paper. The LLM acts as a router, not a numerical solver — every coefficient you see comes from R. The two artifacts above (`repro.R` + `trace.json`) let a reviewer reproduce and audit the run without trusting the LLM.

## Try it

1. Select one of the bundled sample datasets in the **Data** panel (left), e.g. `ExampleData_lowdim.rda`.
2. In the **Conversation** panel type:

   > *Fit Cox KL on the lowdim sample with eta values [0, 0.5, 1] using the good external beta.*

3. The agent will route to `fit_coxkl`, run R locally inside this Space, and surface coefficients + downloads in the **Results** panel.

For a cross-validation example:

> *Cross-validate Cox KL on the lowdim sample with 20 exponential etas from 0 to 5 using the good external beta and C-index criterion.*

## Privacy

In demo mode (this Space), file uploads are disabled — you can only run the bundled `.rda` fixtures. Chat messages and tool call arguments are sent to the configured LLM provider (default: OpenAI), but the data files themselves are read by a local R subprocess inside the Space and never leave it.

For your own data, run locally:

```bash
docker run -p 7860:7860 \
  -v $(pwd)/data:/app/data \
  -e DEPLOYMENT_MODE=local \
  -e OPENAI_API_KEY=sk-... \
  <docker-image-coordinate>
```

## Tech

- **Statistical engine:** [BregSurv](https://github.com/UM-KevinHe/BregSurv) R package (Bregman / KL / Mahalanobis penalties; Cox PH, NCC, ties, high-dimensional enet/ridge).
- **Agent loop:** Python; OpenAI-compatible Chat Completions API with tool use.
- **UI:** Gradio.

## License

GPL-3.0, matching the BregSurv R package.
