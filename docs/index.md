# SurvBregDiv

**Transfer learning for time-to-event modelling via Bregman
divergence.**

`SurvBregDiv` enables principled borrowing of external information when
fitting Cox proportional hazards or nested case–control (NCC) models,
through a unified Bregman-divergence framework that accommodates
population heterogeneity between internal and external cohorts.

> #### Using SurvBregDiv with an AI assistant?
>
> An AI-optimized reference is published at
> **<https://um-kevinhe.github.io/SurvBregDiv/llms.txt>** (following the
> [llms.txt](https://llmstxt.org/) convention). Point your AI at that
> URL, or paste its contents into the chat, to give the assistant a
> compact map of the package — decision tree, parameter reference,
> worked examples, and common pitfalls — without ingesting the full
> website.

## Installation

``` r
# CRAN
install.packages("SurvBregDiv")

# Development version from GitHub
remotes::install_github("UM-KevinHe/SurvBregDiv")
```

Requires R ≥ 4.0.

## Documentation

- **Tutorials and methodology**:
  <https://um-kevinhe.github.io/SurvBregDiv/>
- **Function reference**:
  <https://um-kevinhe.github.io/SurvBregDiv/reference/>

## Getting help

The package is under active development; please report issues or
unexpected behavior to any of the maintainers:

- Yubo Shao — <ybshao@umich.edu>
- Junyi Qiu — <junyiqiu@umich.edu>
- Kevin He — <kevinhe@umich.edu>
