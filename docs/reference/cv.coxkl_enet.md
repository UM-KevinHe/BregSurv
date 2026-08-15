# Cross-Validation for CoxKL Model with Elastic Net & Lasso Penalty

Performs k-fold cross-validation to tune the hyperparameters for the
high-dimensional Cox proportional hazards model with Kullback–Leibler
(KL) divergence penalty.

This function primarily tunes the external information weight `eta`. For
each candidate `eta`, it internally validates the optimal regularization
parameter `lambda`.

## Usage

``` r
cv.coxkl_enet(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas,
  alpha = 1,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(n < p, 0.05, 0.001),
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

  Numeric matrix of covariates. Rows represent individuals and columns
  represent predictors.

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of observed times (event or censoring).

- stratum:

  Optional numeric or factor vector indicating strata. If `NULL`, a
  warning is issued and all subjects are assumed to be in the same
  stratum.

- RS:

  Optional numeric vector or matrix of external risk scores. If not
  provided, `beta` must be supplied.

- beta:

  Optional numeric vector of external coefficients. If provided, it is
  used to compute external risk scores; if not provided, `RS` must be
  supplied. If `beta` is named, names are matched against `colnames(z)`:
  covariates absent from `beta` are set to 0 (with a message) and the
  vector is reordered, so an external source covering only a subset of
  the internal covariates may be supplied directly. An unnamed `beta` is
  aligned positionally and must have length `ncol(z)`. A one-column
  matrix with row names is accepted as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).

- etas:

  Numeric vector of non-negative candidate `eta` values to be evaluated.
  Must be finite and \\\ge 0\\. The values are sorted in ascending order
  internally, and the rows of `integrated_stat.best_per_eta` / columns
  of `integrated_stat.betahat_best` follow that sorted order.

- alpha:

  Elastic-net mixing parameter in \\(0,1\]\\. Default is `1` (lasso
  penalty).

- lambda:

  Optional numeric vector of lambda values. If `NULL`, a path is
  generated automatically.

- nlambda:

  Integer. Number of lambda values to generate if `lambda` is NULL.
  Default is 100.

- lambda.min.ratio:

  Numeric. Ratio of min/max lambda. Default depends on sample size vs
  dimension (0.05 if n \< p, else 1e-03).

- nfolds:

  Integer. Number of cross-validation folds. Default is `5`.

- cv.criteria:

  Character string specifying the cross-validation criterion for
  selecting both `eta` and `lambda`. Choices are:

  - `"V&VH"` (default): V&VH loss.

  - `"LinPred"`: Loss based on cross-validated linear predictors.

  - `"CIndex_pooled"`: Pooled C-Index.

  - `"CIndex_foldaverage"`: Average C-Index across folds.

- c_index_stratum:

  Optional stratum vector. Required only when `cv.criteria` is set to
  `"CIndex_pooled"` or `"CIndex_foldaverage"`, and a stratified C-index
  needs to be computed while the fitted model is non-stratified. That
  use case is therefore only reachable when `stratum = NULL`: if
  `stratum` is supplied and `c_index_stratum` is not identical to it,
  the function stops with an error. Default is `NULL`.

- message:

  Logical. Whether to print progress messages. Default is `FALSE`.

- seed:

  Optional integer. Random seed for reproducible fold assignment.

- ...:

  Additional arguments passed to the underlying fitting function
  [`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md).

## Value

An object of class `"cv.coxkl_enet"`. A list containing:

- `best`:

  A list with the optimal parameters:

  - `best_eta`: The selected eta value.

  - `best_lambda`: The selected lambda value.

  - `best_beta`: The coefficient vector corresponding to the best eta
    and lambda.

  - `criteria`: The criterion used for selection.

- `integrated_stat.full_results`:

  A `data.frame` containing the performance metric for every combination
  of `eta` and `lambda`. Besides `eta` and `lambda` it carries a single
  metric column named after the selected criterion: `Loss` for `"V&VH"`
  and `"LinPred"`, otherwise `CIndex_pooled` or `CIndex_foldaverage`.

- `integrated_stat.best_per_eta`:

  A `data.frame` containing the best lambda and corresponding score for
  each candidate `eta`, with the same criterion-named metric column.

- `integrated_stat.betahat_best`:

  A matrix of coefficients where each column corresponds to the optimal
  model for a specific `eta`.

- `criteria`:

  The selection criterion used.

- `alpha`:

  The elastic net mixing parameter used.

- `nfolds`:

  The number of folds used.

## Details

The function iterates through the provided `etas`. For each `eta`, it
performs cross-validation (based on `nfolds`) to select the optimal
`lambda` and computes the corresponding cross-validation score.

The available criteria for selection are:

- `"V&VH"`: The Verweij & Van Houwelingen partial likelihood loss
  (default).

- `"LinPred"`: Loss based on the prognostic performance of the linear
  predictor.

- `"CIndex_pooled"`: Harrell's C-index computed by pooling linear
  predictors across folds.

- `"CIndex_foldaverage"`: Harrell's C-index computed within each fold
  and averaged.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 100)

cv.coxkl_enet_est <- cv.coxkl_enet(
   z = train_dat_highdim$z,
   delta = train_dat_highdim$status,
   time = train_dat_highdim$time,
   stratum = train_dat_highdim$stratum,
   beta = beta_external_highdim,
   etas = eta_list,
   alpha = 1,
   cv.criteria = "CIndex_pooled"
)
} # }
```
