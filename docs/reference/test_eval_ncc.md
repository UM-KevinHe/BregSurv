# Evaluate NCC Model: Loss, C-Index, and Brier Score

Evaluate NCC Model: Loss, C-Index, and Brier Score

## Usage

``` r
test_eval_ncc(
  z_ncc,
  case,
  set_id,
  betahat,
  criteria = c("loss", "CIndex", "Brier")
)
```

## Arguments

- z_ncc:

  Matrix of covariates for NCC data (rows = subjects).

- case:

  Integer or logical vector (0/1) indicating cases.

- set_id:

  Vector of matched set identifiers. Every matched set must contain
  exactly one case; a set with zero or more than one case is an error
  ("Each matched set must contain exactly one case.").

- betahat:

  Numeric vector of estimated coefficients. **This argument is strictly
  positional**: the linear predictor is formed as the matrix product of
  `z_ncc` and `betahat`, with no name matching, so `length(betahat)`
  must equal `ncol(z_ncc)` and any names it carries are ignored. This is
  a deliberate asymmetry with the model-fitting and cross-validation
  functions of the package, which align a named `beta` to `colnames(z)`
  via
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md);
  align the vector yourself before calling this function if it may be
  partial or differently ordered.

- criteria:

  "loss", "CIndex", or "Brier". Default is "loss".

## Value

Numeric performance metric.

- `"loss"`: \\-2\\ times the conditional log-partial likelihood divided
  by the **number of matched sets**. Note that the Cox counterpart
  [`test_eval`](https://um-kevinhe.github.io/BregSurv/reference/test_eval.md)
  divides its `"loss"` by the number of **subjects**, so the two losses
  are on different scales and must not be compared directly.

- `"CIndex"`: despite the name, this is the matched-set AUC (the
  pair-weighted average of within-set case-versus-control rank
  comparisons). For 1:M matched sets the matched-set concordance index
  and the matched-set AUC coincide, which is why the two names are used
  interchangeably here.

- `"Brier"`: mean squared difference between the case indicator and the
  within-set multinomial probability implied by the linear predictor.
