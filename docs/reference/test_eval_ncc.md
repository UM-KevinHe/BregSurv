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

  Vector of matched set identifiers.

- betahat:

  Numeric vector of estimated coefficients.

- criteria:

  "loss", "CIndex", or "Brier".

## Value

Numeric performance metric.
