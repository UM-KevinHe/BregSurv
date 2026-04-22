# SurvBregDiv

**Transfer learning for time-to-event modelling via Bregman divergence.**

`SurvBregDiv` enables principled borrowing of external information when fitting
Cox proportional hazards or nested case–control (NCC) models, through a unified
Bregman-divergence framework that accommodates population heterogeneity between
internal and external cohorts.

> #### Using SurvBregDiv with an AI assistant?
>
> An AI-optimized reference is published at
> **<https://um-kevinhe.github.io/SurvBregDiv/llms.txt>**
> (following the [llms.txt](https://llmstxt.org/) convention).
> Point your AI at that URL, or paste its contents into the chat, to give the
> assistant a compact map of the package — decision tree, parameter reference,
> worked examples, and common pitfalls — without ingesting the full website.

## Scope

Pick a function by the **external data available** and the **internal study design**:

| External data | Integration | Cox PH (full cohort) | Nested case–control |
|---|---|---|---|
| Individual-level covariates + outcomes | Composite likelihood | `cox_indi` | `ncc_indi` |
| External coefficients β̃ only | KL divergence | `coxkl`, `coxkl_ties` | `ncckl` |
| β̃ + information / covariance matrix | Mahalanobis distance | `cox_MDTL` | `ncc_MDTL` |

Each function has **low-dimensional**, **ridge**, and **elastic-net / LASSO**
variants, plus cross-validation, stability selection, bagging, and Bayesian-
optimization helpers for tuning the integration weight η.

## Installation

```r
# CRAN
install.packages("SurvBregDiv")

# Development version from GitHub
remotes::install_github("UM-KevinHe/SurvBregDiv")
```

Requires R ≥ 4.0.

## Quick start

```r
library(SurvBregDiv)
data(ExampleData_lowdim)

train    <- ExampleData_lowdim$train
beta_ext <- ExampleData_lowdim$beta_external_fair
etas     <- generate_eta("exponential", n = 50, max_eta = 10)

# Fit KL-integrated Cox model over a grid of integration weights
fit <- coxkl(
  z       = train$z,
  delta   = train$status,
  time    = train$time,
  stratum = train$stratum,
  beta    = beta_ext,
  etas    = etas
)

# Tune η via 5-fold cross-validation
cvfit <- cv.coxkl(
  z = train$z, delta = train$status, time = train$time,
  stratum = train$stratum, beta = beta_ext,
  etas = etas, nfolds = 5, criteria = "V&VH"
)
cv.plot(cvfit)
```

## Documentation

- **Tutorials and methodology**: <https://um-kevinhe.github.io/SurvBregDiv/>
- **Function reference**: <https://um-kevinhe.github.io/SurvBregDiv/reference/>
- **Vignettes**: `SurvBregDiv`, `coxkl`, `coxkl_ties`, `ncc`, `CV_Criteria`

## Getting help

The package is under active development; please report issues or unexpected
behavior to any of the maintainers:

- Yubo Shao — <ybshao@umich.edu>
- Junyi Qiu — <junyiqiu@umich.edu>
- Kevin He — <kevinhe@umich.edu>
