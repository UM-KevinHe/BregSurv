# Stability Selection for MDTL-Integrated Cox Elastic-Net Models

Performs stability selection for the Mahalanobis-distance–based
transfer-learning Cox elastic-net model (`cox_MDTL_enet`) by repeatedly
refitting the model on bootstrap or subsampled datasets and aggregating
variable selection frequencies across replicates. This procedure yields
a more robust measure of variable importance that is less sensitive to a
single data split.

## Usage

``` r
cox_MDTL_enet.StabSelect(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  Q = NULL,
  etas = NULL,
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

  Optional numeric vector of external coefficients. If `beta` is named,
  names are matched against `colnames(z)`: covariates absent from `beta`
  are set to 0 (with a message) and the vector is reordered. An unnamed
  `beta` is aligned positionally and must have length `ncol(z)`. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).

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

  Numeric vector of non-negative integration weights. Must be finite and
  \\\ge 0\\. This argument is **required**: leaving it at its `NULL`
  default is an error.

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha = 1` is the Lasso penalty, and `alpha` close to 0 approaches
  ridge. Values outside \\(0, 1\]\\ are an error. If `NULL` (the
  default), `alpha` is set to 1 (Lasso) and a warning is issued.

- lambda:

  Optional user-supplied lambda sequence. If `NULL`, typical usage is to
  have the program compute its own `lambda` sequence based on `nlambda`
  and `lambda.min.ratio`.

- nlambda:

  The number of `lambda` values. Default is 100.

- lambda.min.ratio:

  Numeric. Smallest value for `lambda`, as a fraction of `lambda.max`.
  Default is `0.1` for this function. Only if it is explicitly set to
  `NULL` does the sample-size-dependent fallback apply (`0.05` when \\n
  \< p\\, `1e-03` otherwise).

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

- B:

  Integer. Number of bootstrap/subsampling replicates used for stability
  selection. Default is `50`.

- fraction_sample:

  Numeric in `(0, 1]`. Fraction of the original sample size used in each
  replicate. Default is `0.5`.

- ncores:

  Integer. Number of parallel cores. Default 1 (sequential execution).

- ...:

  Additional arguments passed to the underlying fitting function.

## Value

An object of class `"StabSelect"` containing:

- `stability_path` — a numeric matrix storing selection probabilities
  for each variable–`lambda` pair across the `B` replicates.

- `lambda` — the global `lambda` sequence used for the underlying
  elastic-net fits.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim      <- ExampleData_highdim$train
beta_external_highdim  <- ExampleData_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 10)

mdtl.StabSelect <- cox_MDTL_enet.StabSelect(
  z            = train_dat_highdim$z,
  delta        = train_dat_highdim$status,
  time         = train_dat_highdim$time,
  stratum      = train_dat_highdim$stratum,
  beta         = beta_external_highdim,
  Q            = NULL,
  etas         = eta_list,
  cv.criteria  = "CIndex_pooled",
  B            = 20,
  message      = TRUE
)

# Visualize selection with a chosen threshold
plot(mdtl.StabSelect, threshold = 0.75)
} # }
```
