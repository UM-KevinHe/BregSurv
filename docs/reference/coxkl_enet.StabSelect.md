# Stability Selection for KL-Integrated Cox Elastic-Net Models

Performs stability selection for the KL-integrated Cox elastic-net model
by repeatedly refitting the model on bootstrap or subsampled datasets
and aggregating variable selection frequencies across replicates. This
procedure provides a robust measure of variable importance that is less
sensitive to a single split of the data.

## Usage

``` r
coxkl_enet.StabSelect(
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
  lambda.min.ratio = 0.1,
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  B = 50,
  fraction_sample = 0.5,
  ncores = 1,
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

  Optional numeric vector of external coefficients. If `beta` is named,
  names are matched against `colnames(z)`: covariates absent from `beta`
  are set to 0 (with a message) and the vector is reordered. An unnamed
  `beta` is aligned positionally and must have length `ncol(z)`. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).

- etas:

  Numeric vector of non-negative integration weights. Must be finite and
  \\\ge 0\\.

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

  Numeric. Smallest value for `lambda`, as a fraction of `lambda.max`.
  Default is `0.1` for this function. Only if it is explicitly set to
  `NULL` does the sample-size-dependent fallback apply (`0.05` when \\n
  \< p\\, `1e-03` otherwise).

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

- B:

  Integer. Number of bootstrap/subsampling replicates used for stability
  selection. Default is `50`.

- fraction_sample:

  Numeric in `(0, 1]`. Fraction of the original sample size used in each
  replicate (without replacement if subsampling is used). Default is
  `0.5`.

- ncores:

  Integer. Number of parallel cores. Default 1 (sequential execution).

- ...:

  Additional arguments passed to the underlying fitting function
  [`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md).

## Value

An object of class `"StabSelect"`, which is a list containing:

- stability_path:

  A numeric matrix of dimension `n_vars x n_lambda` giving, for each
  variable (rows) and each value of `lambda` (columns), the empirical
  selection probability across the `B` replicates.

- lambda:

  Numeric vector giving the global `lambda` sequence used for the
  underlying elastic-net fits.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim      <- ExampleData_highdim$train
beta_external_highdim  <- ExampleData_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 50)

coxkl.StabSelect <- coxkl_enet.StabSelect(
  z            = train_dat_highdim$z,
  delta        = train_dat_highdim$status,
  time         = train_dat_highdim$time,
  stratum      = train_dat_highdim$stratum,
  beta         = beta_external_highdim,
  etas         = eta_list,
  cv.criteria  = "CIndex_pooled",
  B            = 20,
  message      = TRUE
)

# Plot with different thresholds without re-running stability selection
plot(coxkl.StabSelect, threshold = 0.6)
plot(coxkl.StabSelect, threshold = 0.8)
} # }
```
