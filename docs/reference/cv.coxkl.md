# Cross-Validated Cox–KL to Tune the Integration Parameter (eta)

Performs K-fold cross-validation to select the integration parameter
`eta` for the Cox–KL model. Each fold fits the model on a training split
and evaluates on the held-out split using the specified performance
criterion.

## Usage

``` r
cv.coxkl(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas = NULL,
  tol = 1e-04,
  Mstop = 100,
  backtrack = FALSE,
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

  Numeric matrix of covariates (rows = observations, columns =
  variables).

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of observed event or censoring times.

- stratum:

  Optional numeric or factor vector defining strata. If `NULL`, a
  warning is issued and all observations are treated as a single
  stratum.

- RS:

  Optional numeric vector or matrix of external risk scores. If omitted,
  `beta` must be supplied.

- beta:

  Optional numeric vector of external coefficients. If omitted, `RS`
  must be supplied. If `beta` is named, names are matched against
  `colnames(z)`: covariates absent from `beta` are set to 0 (with a
  message) and the vector is reordered, so an external source covering
  only a subset of the internal covariates may be supplied directly. An
  unnamed `beta` is aligned positionally and must have length `ncol(z)`.
  A one-column matrix with row names is accepted as a named vector. See
  [`align_beta()`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).

- etas:

  Numeric vector of non-negative candidate tuning values to be
  cross-validated. Must be finite and \\\ge 0\\. This argument is
  **required**: leaving it at its `NULL` default is an error. The values
  are sorted in ascending order internally, and the rows of
  `internal_stat` / columns of `beta_full` follow that sorted order.

- tol:

  Convergence tolerance for the optimizer used inside `coxkl`. Default
  `1e-4`.

- Mstop:

  Maximum number of Newton iterations used inside `coxkl`. Default
  `100`.

- backtrack:

  Logical; if `TRUE`, backtracking line search is applied during
  optimization. Default is `FALSE`.

- nfolds:

  Number of cross-validation folds. Default `5`.

- cv.criteria:

  Character string specifying the performance criterion. Choices are
  `"V&VH"`, `"LinPred"`, `"CIndex_pooled"`, or `"CIndex_foldaverage"`.
  Default `"V&VH"`.

- c_index_stratum:

  Optional stratum vector. Only required when `cv.criteria` is set to
  `"CIndex_pooled"` or `"CIndex_foldaverage"`, and a stratified C-index
  is desired while the fitted model is non-stratified. That use case is
  therefore only reachable when `stratum = NULL`: if `stratum` is
  supplied and `c_index_stratum` is not identical to it, the function
  stops with an error. Default `NULL`.

- message:

  Logical; if `TRUE`, prints progress messages. Default `FALSE`.

- seed:

  Optional integer seed for reproducible fold assignment. Default
  `NULL`.

- ...:

  Additional arguments passed to
  [`coxkl`](https://um-kevinhe.github.io/BregSurv/reference/coxkl.md).

## Value

An object of class `"cv.coxkl"`: a list with the following five
components.

- `internal_stat`:

  A `data.frame` with one row per candidate `eta`, in ascending `eta`
  order. It has a column `eta` plus *exactly one* metric column, whose
  name is determined by `cv.criteria`: `VVH_Loss` for `"V&VH"`
  (cross-validated V&VH loss), `LinPred_Loss` for `"LinPred"` (loss
  based on the cross-validated linear predictors), `CIndex_pooled` for
  `"CIndex_pooled"` (pooled cross-validated C-index), or
  `CIndex_foldaverage` for `"CIndex_foldaverage"` (average fold-wise
  C-index). The other three metrics are never computed, so only one of
  them ever appears.

- `beta_full`:

  A `ncol(z)` by `length(etas)` matrix of coefficients from the
  full-data fit, one column per candidate `eta` (in the same sorted
  order as `internal_stat`).

- `best`:

  A list with three components: `best_eta`, the selected `eta` (the loss
  is minimized for `"V&VH"` / `"LinPred"`, the C-index is maximized
  otherwise); `best_beta`, the corresponding column of `beta_full`; and
  `criteria`, the criterion used.

- `criteria`:

  The criterion used for selection.

- `nfolds`:

  The number of cross-validation folds used.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair
etas <- generate_eta(method = "exponential", n = 50, max_eta = 10)
cv.result <- cv.coxkl(
  z = train_dat_lowdim$z,
  delta = train_dat_lowdim$status,
  time = train_dat_lowdim$time,
  stratum = train_dat_lowdim$stratum,
  beta = beta_external_lowdim,
  etas = etas,
  nfolds = 5,
  cv.criteria = "CIndex_pooled")
} # }
```
