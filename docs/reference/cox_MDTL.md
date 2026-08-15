# Cox Proportional Hazards Model with Mahalanobis Distance Transfer Learning

Fits a Cox proportional hazards model incorporating external information
via a Mahalanobis distance penalty. This approach penalizes the
deviation of the estimated coefficients from external reference
coefficients (`beta`), weighted by a specified matrix (typically the
inverse covariance matrix).

## Usage

``` r
cox_MDTL(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  Q = NULL,
  etas,
  tol = 1e-04,
  Mstop = 50,
  backtrack = FALSE,
  message = FALSE,
  data_sorted = FALSE,
  beta_initial = NULL
)
```

## Arguments

- z:

  A numeric matrix or data frame of covariates (n x p).

- delta:

  A numeric vector of event indicators (1 = event, 0 = censored).

- time:

  A numeric vector of observed times.

- stratum:

  Optional numeric or factor vector indicating strata. If `NULL`, all
  subjects are assumed to be in the same stratum.

- beta:

  A numeric vector of external coefficients. If named, the names are
  matched against `colnames(z)` and covariates absent from `beta` are
  zero-padded; if unnamed, `beta` must have length `ncol(z)`.

- Q:

  Optional numeric matrix acting as the weighting matrix \\Q\\ in the
  Mahalanobis penalty. This should be a symmetric positive-semidefinite
  *precision* matrix (e.g. the inverse covariance / information matrix
  of the external estimator). If named, it is reordered and zero-padded
  to `colnames(z)`. If `NULL`, a masked identity is used.

- etas:

  A numeric vector of non-negative tuning parameters (scalars) to
  evaluate.

- tol:

  Convergence tolerance for the Newton-Raphson algorithm. Default is
  1e-4.

- Mstop:

  Maximum number of iterations for Newton-Raphson. Default is 50.

- backtrack:

  Logical. If `TRUE`, uses backtracking line search. Default is `FALSE`.

- message:

  Logical. If `TRUE`, progress messages are printed.

- data_sorted:

  Logical. If `TRUE`, assumes input data is already sorted by stratum
  and time.

- beta_initial:

  Optional initial coefficient vector for warm start.

## Value

An object of class `"cox_MDTL"` containing:

- `eta`:

  The vector of eta values evaluated.

- `beta`:

  A matrix of estimated coefficients (p x n_eta).

- `linear.predictors`:

  A matrix of linear predictors (n x n_eta).

- `likelihood`:

  A vector of log-partial likelihoods for each eta.

- `data`:

  A list containing the input data used.

## Details

The objective function minimizes the negative log-partial likelihood
plus a penalty term: \$\$P(\beta) = \frac{\eta}{2} (\beta -
\beta\_{ext})^T Q (\beta - \beta\_{ext})\$\$ where:

- \\\beta\_{ext}\\ is the vector of external coefficients.

- \\Q\\ is the weighting (precision) matrix.

- \\\eta\\ is the tuning parameter controlling the strength of the
  external information.

If `Q` is `NULL`, it defaults to a masked identity (the identity on the
covariates supplied by `beta`, and 0 on covariates the external source
does not cover), reducing the penalty to a Ridge-type shrinkage towards
`beta`.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 5)

cox_MDTL_est <- cox_MDTL(
  z = train_dat_lowdim$z,
  delta = train_dat_lowdim$status,
  time = train_dat_lowdim$time,
  beta = beta_external_lowdim,
  Q = NULL,
  etas = eta_list
)
} # }
```
