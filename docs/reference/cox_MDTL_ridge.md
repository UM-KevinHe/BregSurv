# Cox MDTL with Ridge Regularization

Fits a Cox Proportional Hazards model that simultaneously incorporates:

1.  **Transfer Learning**: A Mahalanobis distance penalty that shrinks
    coefficients towards external reference coefficients (`beta`),
    controlled by the parameter `eta`.

2.  **Ridge Regularization**: An L2-norm penalty on the coefficients to
    handle high-dimensional data or multicollinearity, controlled by the
    sequence of `lambda` values.

The function computes the solution path over a sequence of `lambda`
values for a fixed `eta`.

## Usage

``` r
cox_MDTL_ridge(
  z,
  delta,
  time,
  stratum = NULL,
  beta = NULL,
  Q = NULL,
  eta = NULL,
  lambda = NULL,
  nlambda = 100,
  penalty.factor = 0.999,
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

  A numeric vector of external coefficients. The formal default is
  `NULL`, but the argument is in practice mandatory: if it is not
  supplied the function stops with the message "External beta must be
  provided." If named, the names are matched against `colnames(z)` and
  covariates absent from `beta` are zero-padded; if unnamed, `beta` must
  have length `ncol(z)`.

- Q:

  Optional numeric matrix acting as the weighting matrix \\Q\\ in the
  Mahalanobis penalty. This should be a symmetric positive-semidefinite
  *precision* matrix (e.g. the inverse covariance / information matrix
  of the external estimator). If named, it is reordered and zero-padded
  to `colnames(z)`. If `NULL`, a masked identity is used.

- eta:

  A single non-negative numeric value controlling the weight of the
  external information (Mahalanobis distance penalty). If `NULL`,
  defaults to 0 (no transfer learning).

- lambda:

  Optional numeric vector of regularization parameters. If `NULL`, a
  sequence is generated automatically.

- nlambda:

  Integer. The number of lambda values to generate if `lambda` is
  `NULL`. Default is 100.

- penalty.factor:

  Numeric value used to determine the elastic net mixing parameter
  `alpha`. The function sets `alpha = 1 - penalty.factor`. A value close
  to 1 (default 0.999) results in `alpha` close to 0, enforcing a
  Ridge-like penalty.

- tol:

  Convergence tolerance for the optimization algorithm. Default is 1e-4.

- Mstop:

  Maximum number of iterations. Default is 50.

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

An object of class `"cox_MDTL_ridge"` containing:

- `lambda`:

  The sequence of lambda values used.

- `beta`:

  A matrix of estimated coefficients (p x nlambda).

- `linear.predictors`:

  A matrix of linear predictors (n x nlambda).

- `likelihood`:

  A vector of log-partial likelihoods for each lambda.

- `data`:

  A list containing the input data (z, time, delta, stratum).

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

cox_MDTL_ridge_est <- cox_MDTL_ridge(
  z = train_dat_highdim$z,
  delta = train_dat_highdim$status,
  time = train_dat_highdim$time,
  stratum = train_dat_highdim$stratum,
  beta = beta_external_highdim,
  Q = NULL,
  eta = 0.5
)
} # }
```
