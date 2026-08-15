# Cox Proportional Hazards Model with Ridge Penalty and External Information

Fits a Cox proportional hazards model using a Ridge (L2) penalty on all
covariates, while integrating external information via Kullback–Leibler
(KL) divergence.

This function is useful for high-dimensional data or situations with
collinearity, allowing the incorporation of prior knowledge (external
coefficients or risk scores) to improve estimation.

## Usage

``` r
coxkl_ridge(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
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

  Numeric matrix of covariates. Rows represent individuals and columns
  represent predictors.

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of observed times (event or censoring).

- stratum:

  Optional numeric or factor vector specifying strata. If `NULL`, all
  observations are in the same stratum.

- RS:

  Optional numeric vector of external risk scores, one per observation
  (a one-column matrix is also accepted). Only a single risk score per
  observation is supported. If not provided, `beta` must be supplied.

- beta:

  Optional numeric vector of external coefficients. If `beta` is named,
  names are matched against `colnames(z)`: covariates absent from `beta`
  are set to 0 (with a message) and the vector is reordered, so an
  external source covering only a subset of the internal covariates may
  be supplied directly. An unnamed `beta` is aligned positionally and
  must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
  If provided, used to calculate risk scores. If not provided, `RS` must
  be supplied.

- eta:

  Single finite non-negative integration weight controlling the strength
  of external information integration. `eta = 0` implies a standard
  Ridge Cox model. The formal default is `NULL`, which resolves to
  `eta = 0` with the warning "eta is not provided. Setting eta = 0 (no
  external information used)."

- lambda:

  Optional numeric scalar or vector of penalty parameters. If `NULL`, a
  sequence is generated automatically.

- nlambda:

  Integer. Number of lambda values to generate if `lambda` is `NULL`.
  Default is 100.

- penalty.factor:

  Numeric scalar in `[0, 1)`. Controls the internal mixing parameter
  used to generate the lambda sequence when `lambda = NULL`. A value
  close to 1 generates a sequence suitable for Ridge-like behavior.
  Default is `0.999`.

- tol:

  Convergence tolerance for the iterative estimation algorithm. Default
  is 1e-4.

- Mstop:

  Integer. Maximum number of iterations for estimation. Default is 50.

- backtrack:

  Logical. If `TRUE`, uses backtracking line search during optimization.

- message:

  Logical. If `TRUE`, progress messages are printed during model
  fitting.

- data_sorted:

  Logical. Internal optimization. If `TRUE`, assumes input data is
  already sorted by strata and time.

- beta_initial:

  Optional numeric vector. Initial values for the coefficients. Default
  is 0.

## Value

An object of class `"coxkl_ridge"` containing:

- `lambda`:

  The sequence of lambda values used for estimation.

- `beta`:

  A matrix of estimated coefficients (p x nlambda).

- `linear.predictors`:

  A matrix of linear predictors (n x nlambda), restored to the original
  data order.

- `likelihood`:

  Vector of log-partial likelihoods, one per lambda (larger values
  indicate better fit; this is *not* a loss).

- `data`:

  A list containing the input data used (`z`, `time`, `delta`,
  `stratum`), as supplied by the caller (i.e. in the original row order,
  before the internal sorting by stratum and time).

## Details

The objective function optimizes the partial likelihood penalized by two
terms:

1.  The KL divergence between the current model's predictions and the
    external information (weighted by `eta`).

2.  The Ridge (L2) norm of the coefficients (weighted by `lambda`).

Unlike Lasso, Ridge regression does not perform variable selection
(coefficients are shrunk towards zero but not set to exactly zero),
making it suitable for retaining all features while controlling
overfitting.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

coxkl_ridge_est <- coxkl_ridge(
  z = train_dat_highdim$z,
  delta = train_dat_highdim$status,
  time = train_dat_highdim$time,
  stratum = train_dat_highdim$stratum,
  beta = beta_external_highdim,
  eta = 0
)
} # }
```
