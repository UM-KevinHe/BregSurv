# Cross-Validation for Cox MDTL Model

Performs k-fold cross-validation to tune the hyperparameter `eta` for
the Cox Proportional Hazards Model with Mahalanobis Distance Transfer
Learning.

The function evaluates the model performance across a range of `eta`
values using specified cv.criteria (e.g., Verweij & Van Houwelingen
loss, C-index) to select the optimal weight for the external
information.

## Usage

``` r
cv.cox_MDTL(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  Q = NULL,
  etas = NULL,
  tol = 1e-04,
  Mstop = 100,
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

  A numeric vector of external coefficients. **Required**. If `beta` is
  named, names are matched against `colnames(z)`: covariates absent from
  `beta` are set to 0 (with a message) and the vector is reordered, so
  an external source covering only a subset of the internal covariates
  may be supplied directly. An unnamed `beta` is aligned positionally
  and must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
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
  evaluated. Must be finite and \\\ge 0\\. This argument is
  **required**: leaving it at its `NULL` default is an error. The values
  are sorted in ascending order internally, and the rows of
  `internal_stat` / columns of `beta_full` follow that sorted order.

- tol:

  Convergence tolerance for the optimization algorithm. Default is 1e-4.

- Mstop:

  Maximum number of iterations for the optimization. Default is 100.

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

  Additional arguments passed to the underlying fitting function
  [`cox_MDTL`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL.md).

## Value

An object of class `"cv.cox_MDTL"` containing:

- `internal_stat`:

  A `data.frame` with one row per candidate `eta`, in ascending `eta`
  order. It has a column `eta` plus *exactly one* metric column, whose
  name is determined by `cv.criteria`: `VVH_Loss` for `"V&VH"`,
  `LinPred_Loss` for `"LinPred"`, `CIndex_pooled` for `"CIndex_pooled"`,
  or `CIndex_foldaverage` for `"CIndex_foldaverage"`. The other three
  metrics are never computed.

- `beta_full`:

  A `ncol(z)` by `length(etas)` matrix of coefficients from the
  full-data fit, one column per candidate `eta`.

- `best`:

  A list containing the optimal results:

  - `best_eta`: The selected eta value.

  - `best_beta`: The coefficient vector corresponding to the optimal eta
    (refitted on full data).

  - `criteria`: The criterion used for selection.

- `criteria`:

  The selection criterion used.

- `nfolds`:

  The number of folds used.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

cv.cox_MDTL_est <- cv.cox_MDTL(
  z = train_dat_lowdim$z,
  delta = train_dat_lowdim$status,
  time = train_dat_lowdim$time,
  beta = beta_external_lowdim,
  Q = NULL,
  etas = eta_list,
  cv.criteria = "V&VH"
)
} # }
```
