# Cross-Validation for Cox MDTL with Ridge Regularization

Performs k-fold cross-validation to simultaneously tune the
hyperparameter `eta` (transfer learning weight) and the regularization
parameter `lambda` for the Cox MDTL model with a Ridge penalty
(L2-norm).

This function evaluates the model performance across a grid of `eta` and
`lambda` values. It is efficient for high-dimensional data where an
Elastic Net penalty is not required, focusing purely on Ridge regression
to handle multicollinearity and overfitting.

## Usage

``` r
cv.cox_MDTL_ridge(
  z,
  delta,
  time,
  stratum = NULL,
  beta = NULL,
  Q = NULL,
  etas,
  lambda = NULL,
  nlambda = 100,
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  ...
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

  Optional numeric or factor vector indicating strata. If `NULL`, a
  warning is issued and all subjects are assumed to be in the same
  stratum.

- beta:

  A numeric vector of external coefficients. If `beta` is named, names
  are matched against `colnames(z)`: covariates absent from `beta` are
  set to 0 (with a message) and the vector is reordered, so an external
  source covering only a subset of the internal covariates may be
  supplied directly. An unnamed `beta` is aligned positionally and must
  have length `ncol(z)`. A one-column matrix with row names is accepted
  as a named vector. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).

- Q:

  Optional weighting (precision) matrix for the Mahalanobis penalty
  (typically the inverse covariance / information matrix of the external
  estimator). Must be symmetric and positive semi-definite; both are
  checked to a tolerance of 1e-8 and violations are errors. If named, it
  is reordered and zero-padded to `colnames(z)`; only an unnamed `Q`
  must be exactly `ncol(z)` by `ncol(z)`. If `NULL`, a *masked identity*
  is used: 1 on covariates actually supplied by `beta` and 0 on
  zero-padded positions, so padded coefficients are left unpenalized.
  See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).

- etas:

  A numeric vector of non-negative candidate `eta` values to be
  evaluated. Must be finite and \\\ge 0\\. The values are sorted in
  ascending order internally, and the rows of
  `integrated_stat.best_per_eta` / columns of
  `integrated_stat.betahat_best` follow that sorted order.

- lambda:

  Optional user-supplied lambda sequence. If `NULL`, the function
  computes its own sequence based on `nlambda`.

- nlambda:

  The number of `lambda` values. Default is 100.

- nfolds:

  Integer. Number of cross-validation folds. Default is 5.

- cv.criteria:

  Character string specifying the cross-validation criterion. Choices
  are:

  - `"V&VH"` (default): Verweij & Van Houwelingen partial likelihood
    loss.

  - `"LinPred"`: Loss based on the prognostic performance of the linear
    predictor.

  - `"CIndex_pooled"`: Harrell's C-index computed by pooling predictions
    across folds.

  - `"CIndex_foldaverage"`: Harrell's C-index computed within each fold
    and averaged.

- c_index_stratum:

  Optional stratum vector. Required only when `cv.criteria` involves
  stratified C-index calculation but the model itself is unstratified.
  That use case is therefore only reachable when `stratum = NULL`: if
  `stratum` is supplied and `c_index_stratum` is not identical to it,
  the function stops with an error.

- message:

  Logical. If `TRUE`, progress messages are printed.

- seed:

  Optional integer. Random seed for reproducible fold assignment.

- ...:

  Additional arguments passed to the underlying fitting function.

## Value

An object of class `"cv.cox_MDTL_ridge"` containing:

- `best`:

  A list containing the optimal results:

  - `best_eta`: The selected eta value.

  - `best_lambda`: The selected lambda value.

  - `best_beta`: The coefficient vector corresponding to the optimal
    parameters.

  - `criteria`: The selection criterion used.

- `integrated_stat.full_results`:

  A data frame of performance metrics for all combinations of eta and
  lambda. Besides `eta` and `lambda` it carries a single metric column
  named after the selected criterion: `Loss` for `"V&VH"` and
  `"LinPred"`, otherwise `CIndex_pooled` or `CIndex_foldaverage`.

- `integrated_stat.best_per_eta`:

  A data frame summarizing the best lambda and performance metric for
  each eta, with the same criterion-named metric column.

- `integrated_stat.betahat_best`:

  A matrix of coefficients for the best lambda at each eta.

- `criteria`:

  The selection criterion used.

- `nfolds`:

  The number of folds used.

## Details

When `lambda` is not supplied, the Ridge lambda sequence is generated
internally by
[`cox_MDTL_ridge`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL_ridge.md)
and always spans from `lambda.max` down to an exact `0`, i.e. the last
element of the path is the unpenalized solution. This behaviour is fixed
for the Ridge path and is therefore *not* configurable through a
minimum-ratio argument; only the number of grid points (`nlambda`), or
an explicit `lambda` vector, is under user control.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

cv.cox_MDTL_ridge_est <- cv.cox_MDTL_ridge(
  z = train_dat_highdim$z,
  delta = train_dat_highdim$status,
  time = train_dat_highdim$time,
  stratum = train_dat_highdim$stratum,
  beta = beta_external_highdim,
  Q = NULL,
  etas = eta_list,
  cv.criteria = "CIndex_pooled"
)
} # }
```
