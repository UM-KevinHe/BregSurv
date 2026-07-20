<div id="main" class="col-md-9" role="main">

# BregSurv Agent

<div id="bregsurv-agent" class="section level1">

A natural-language interface to
**[BregSurv](https://github.com/UM-KevinHe/BregSurv)** — a
Bregman-divergence-based transfer learning framework for survival
analysis (Cox PH and nested case-control regression with external
information borrowing).

Describe your analysis in plain English. The agent picks the correct
estimator from a fixed library of 33 statistically-derived tools, runs
it on the supplied data, and returns:

-   a natural-language summary of the results,
-   the coefficient table,
-   a CV-path plot (when applicable),
-   **`repro.R`** — a standalone R script that bit-matches the agent’s
    coefficients without any LLM in the loop,
-   **`trace.json`** — a per-tool-call audit trail recording every step
    the agent took.

<div class="section level2">

## How this is “verification-scaffolded”

The agent only ever chooses from a fixed catalogue of estimators whose
Bregman/KL/Mahalanobis form is derived in the accompanying paper. The
LLM acts as a router, not a numerical solver — every coefficient you see
comes from R. The two artifacts above (`repro.R` + `trace.json`) let a
reviewer reproduce and audit the run without trusting the LLM.

</div>

<div class="section level2">

## Try it

1.  Select one of the bundled sample datasets in the **Data** panel
    (left), e.g. `ExampleData_lowdim.rda`.

2.  In the **Conversation** panel type:

    > *Fit Cox KL on the lowdim sample with eta values \[0, 0.5, 1\]
    > using the good external beta.*

3.  The agent will route to `fit_coxkl`, run R locally inside this
    Space, and surface coefficients + downloads in the **Results**
    panel.

For a cross-validation example:

> *Cross-validate Cox KL on the lowdim sample with 20 exponential etas
> from 0 to 5 using the good external beta and C-index criterion.*

</div>

<div class="section level2">

## Privacy

In demo mode (this Space), file uploads are disabled — you can only run
the bundled `.rda` fixtures. The LLM **Qwen 2.5-7B-Instruct-AWQ** runs
locally inside this container via vLLM, so chat messages and tool-call
arguments stay inside the Space. The data files themselves are read by a
local R subprocess and never leave the container.

We still recommend the **Docker self-host** path for any real research
data — a public-internet service is the wrong place for PHI even when
the model is local. See
<https://github.com/UM-KevinHe/BregSurv/blob/main/mcp/DEPLOY.md> for the
self-host recipe.

</div>

<div class="section level2">

## Tech

-   **Statistical engine:**
    [BregSurv](https://github.com/UM-KevinHe/BregSurv) R package
    (Bregman / KL / Mahalanobis penalties; Cox PH, NCC, ties,
    high-dimensional enet/ridge).
-   **Agent loop:** Python; OpenAI-compatible Chat Completions API with
    tool use, served by vLLM (`Qwen/Qwen2.5-7B-Instruct-AWQ`).
-   **UI:** Gradio.

</div>

<div class="section level2">

## License

GPL-3.0, matching the BregSurv R package.

</div>

</div>

</div>
