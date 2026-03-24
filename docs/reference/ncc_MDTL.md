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
  vcov = NULL,
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

  Numeric vector of external coefficients (length `ncol(z)`).
  **Required**.

- vcov:

  Optional numeric matrix (`ncol(z)` x `ncol(z)`) acting as the
  weighting matrix \\Q\\ in the Mahalanobis penalty. Typically the
  inverse of the external covariance (precision matrix). If `NULL`,
  defaults to the identity matrix.

- etas:

  Numeric vector of tuning parameters to evaluate. **Required**.

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
[`cox_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL.md)
for a description of the return components.

## Details

This function maps the Conditional Logistic Regression problem to a Cox
PH model with fixed event time \\T=1\\ and event indicator \\\delta=y\\,
then calls
[`cox_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL.md)
as the core engine.

The objective function minimizes the negative conditional log-likelihood
plus a Mahalanobis distance penalty: \$\$P(\beta) = \frac{\eta}{2}
(\beta - \beta\_{ext})^T Q (\beta - \beta\_{ext})\$\$ where \\Q\\ is the
weighting matrix (identity if `vcov` is `NULL`).

- Setting `etas = 0` recovers the standard CLR (no external
  information).

- Larger `eta` enforces stronger agreement with `beta`.

- If `vcov = NULL`, \\Q = I\\ (Euclidean/Ridge-type shrinkage towards
  `beta`).

## See also

[`cox_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL.md),
[`ncckl`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncckl.md)

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc)
train_cc <- ExampleData_cc$train

y       <- train_cc$y
z       <- train_cc$z
sets    <- train_cc$stratum
beta_ext <- ExampleData_cc$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)

fit <- ncc_MDTL(
  y      = y,
  z      = z,
  stratum = sets,
  beta   = beta_ext,
  vcov   = NULL,
  etas   = eta_list
)
} # }
```
