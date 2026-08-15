# Conditional Logistic Regression with Mahalanobis Distance Transfer Learning (CLR-MDTL)

Fits a series of Conditional Logistic Regression models that incorporate
external coefficient information via a Mahalanobis distance penalty,
suitable for matched case-control studies.

## Usage

``` r
ncc_MDTL(
  y,
  z,
  stratum,
  beta,
  Q = NULL,
  etas,
  tol = 1e-04,
  Mstop = 50,
  backtrack = FALSE,
  message = FALSE,
  beta_initial = NULL
)
```

## Arguments

- y:

  Numeric vector of binary outcomes (0 = control, 1 = case).

- z:

  Numeric matrix of covariates.

- stratum:

  Numeric or factor vector defining the matched sets (strata).
  **Required**.

- beta:

  Numeric vector of external coefficients. **Required**. If `beta` is
  named, names are matched against `colnames(z)`: covariates absent from
  `beta` are set to 0 (with a message) and the vector is reordered, so
  an external source covering only a subset of the internal covariates
  may be supplied directly. An unnamed `beta` is aligned positionally
  and must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).
  The bundled external beta `ExampleData_cc_lowdim$beta_external` is
  named `Z1`–`Z6`, so the examples below already exercise the
  name-matching path.

- Q:

  Optional weighting (precision) matrix for the Mahalanobis penalty,
  typically the inverse of the external covariance. Must be symmetric
  and positive semi-definite (both checked to a tolerance of 1e-8). If
  named, it is reordered and zero-padded to `colnames(z)`; only an
  unnamed `Q` must be exactly `ncol(z)` by `ncol(z)`. If `NULL`, a
  *masked identity* is used: 1 on covariates actually supplied by `beta`
  and 0 on zero-padded positions, so padded coefficients are left
  unpenalized. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).

- etas:

  Numeric vector of non-negative tuning parameters to evaluate.
  **Required**. Must be finite and \\\ge 0\\. The values are sorted in
  ascending order internally, and the columns of the returned
  coefficient matrix follow that sorted order.

- tol:

  Convergence tolerance for the Newton-Raphson algorithm. Default
  `1e-4`.

- Mstop:

  Maximum number of Newton-Raphson iterations. Default `50`.

- backtrack:

  Logical. If `TRUE`, uses backtracking line search. Default `FALSE`.

- message:

  Logical. If `TRUE`, progress messages are printed. Default `FALSE`.

- beta_initial:

  Optional initial coefficient vector for warm start.

## Value

An object of class `"ncc_MDTL"` and `"cox_MDTL"` containing the
estimation results for each `eta` value. See
[`cox_MDTL`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL.md)
for a description of the return components.

## Details

This function maps the Conditional Logistic Regression problem to a Cox
PH model with fixed event time \\T=1\\ and event indicator \\\delta=y\\,
then calls
[`cox_MDTL`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL.md)
as the core engine.

The objective function minimizes the negative conditional log-likelihood
plus a Mahalanobis distance penalty: \$\$P(\beta) = \frac{\eta}{2}
(\beta - \beta\_{ext})^T Q (\beta - \beta\_{ext})\$\$ where \\Q\\ is the
weighting matrix (a *masked* identity when `Q` is `NULL`; see the `Q`
argument).

- Setting `etas = 0` recovers the standard CLR (no external
  information).

- Larger `eta` enforces stronger agreement with `beta`.

- If `Q = NULL`, a *masked identity* is used: 1 on the covariates
  actually supplied by `beta` and 0 on zero-padded positions. This gives
  Euclidean/Ridge-type shrinkage towards `beta` on the covariates the
  external source covers, while leaving padded coefficients unpenalized.

## See also

[`cox_MDTL`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL.md),
[`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md)

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc_lowdim)
train_cc <- ExampleData_cc_lowdim$train

y       <- train_cc$y
z       <- train_cc$z
sets    <- train_cc$stratum
beta_ext <- ExampleData_cc_lowdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)

fit <- ncc_MDTL(
  y      = y,
  z      = z,
  stratum = sets,
  beta   = beta_ext,
  Q      = NULL,
  etas   = eta_list
)
} # }
```
