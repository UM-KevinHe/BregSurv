# SurvBregDiv: Transfer Learning for Time-to-Event Modelling via Bregman Divergence

> #### Using SurvBregDiv with an AI assistant (ChatGPT, Claude, etc.)?
>
> We provide an AI-optimized reference at
> **<https://um-kevinhe.github.io/SurvBregDiv/llms.txt>**
> (following the [llms.txt](https://llmstxt.org/) convention).
>
> Point your AI assistant at that URL — or paste the file contents into the
> chat — and it will have a compact map of the package: decision tree for
> choosing the right function, parameter reference, worked examples, and a
> list of common pitfalls. No need to upload the whole documentation site.

The **SurvBregDiv** package implements a Bregman-divergence-based transfer learning
framework for survival analysis, enabling principled borrowing of external
information while explicitly accommodating population heterogeneity between the
internal study and external sources.

The package supports two primary study designs: full-cohort Cox proportional hazards models 
and nested case–control (NCC) designs based on conditional logistic regression on sampled risk sets.

### Key Features

**Three external data integration modes**  
Depending on the type of external data available, the package supports:

- **Individual-level data**: when full covariate and outcome data from an external
  cohort are accessible, integration is performed via a weighted pseudo-likelihood
  framework.
- **Coefficient-level summaries**: when only external regression coefficients
  $\widetilde{\boldsymbol{\beta}}$ are available, integration proceeds via
  Kullback–Leibler divergence penalization.
- **Coefficient + curvature summaries**: when an additional positive semidefinite
  matrix $\mathbf{A}$ (e.g., information matrix or variance–covariance matrix)
  is provided, integration proceeds via Mahalanobis distance penalization.

**Robustness to clustered and tied event times data**  
The package accounts for two structural features common in real-world survival data. Between-cluster heterogeneity arising from multi-site enrollment, matched designs, or hierarchical sampling is accommodated via stratified partial likelihoods, which allow the baseline hazard to vary freely across strata rather than imposing a common baseline. Tied event times frequently occur when follow-up is recorded on a coarse time scale such as daily records, scheduled clinical visits, or discretized follow-up intervals, and are handled through tie-correction methods. 

**High-dimensional variable selection**
Penalized estimation with ridge, lasso, and elastic net penalties is supported for variable selection and shrinkage, with tuning parameters selected via cross-validation as default. However, cross-validation optimizes predictive performance rather than variable selection stability, and the selected predictor set can vary considerably across repeated runs or minor perturbations of the data. For settings where a reproducible and trustworthy shortlist of predictors is needed, stability selection is also available, which aggregates variable inclusion frequencies across subsamples to identify predictors that are consistently selected regardless of which subjects happen to be in the training set.

**Ensemble integration via bagged estimation**  
Besides cross-validated LASSO and stability selection, the package supports an
ensemble strategy that combines bootstrapping, external-data integration, and
model aggregation—conceptually similar to bootstrap aggregation (bagging).
This bagged integration approach reduces variance and improves predictive
robustness compared to relying solely on a single cross-validated integrated
LASSO model.

**Flexible cross-validation criteria**  
Model tuning supports a broad range of cross-validation criteria. Discrimination-
based measures include Harrell's concordance index (C-index)
[@harrell1982evaluating], and partial likelihood–based criteria include the 
Verweij & Van Houwelingen (V&VH) loss and the cross-validated linear predictor 
loss. For full details on each criterion, see **Appendix: CV Criteria**.

**Pathwise solution for integration weights**  
To select the integration weight $\eta$ that governs the strength of external
borrowing, the package provides two complementary tuning strategies: (i) a grid
search approach based on a pre-specified sequence of candidate values, and (ii)
an adaptive tuning strategy using Bayesian optimization to directly explore the
integration weight space, which is particularly efficient when evaluating each
candidate is computationally expensive.

## Installation

> **Note:** This package is currently under active development. Please report any issues or unexpected behavior.  
> Requires **R ≥ 4.0.0**.

Install from CRAN:

    install.packages("SurvBregDiv")

Or install the development version from GitHub:

    require("devtools")
    require("remotes")
    remotes::install_github("UM-KevinHe/SurvBregDiv")

## Detailed Tutorial

Full package documentation and parameter explanations: [here](https://um-kevinhe.github.io/SurvBregDiv/)

## Getting Help

If you encounter problems or bugs, please contact us:

- ybshao@umich.edu
- junyiqiu@umich.edu
- kevinhe@umich.edu


