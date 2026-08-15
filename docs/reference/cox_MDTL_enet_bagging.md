# Bagging for MDTL-Integrated Cox Elastic-Net Models

Performs bootstrap aggregation (bagging) for the
Mahalanobis-distance–based transfer-learning Cox elastic-net model
(`cv.cox_MDTL_enet`) by repeatedly refitting the model on bootstrap
resamples of the internal dataset and averaging the resulting fitted
coefficient vectors. This procedure reduces sampling variability and
improves robustness relative to a single data split.

## Usage

``` r
cox_MDTL_enet_bagging(
  z,
  delta,
  time,
  stratum = NULL,
  beta = NULL,
  Q = NULL,
  etas,
  alpha = 1,
  B = 100,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.01, 1e-04),
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  ncores = 1,
  ...
)
```

## Arguments

- z:

  Matrix of predictors of dimension `n x p`.

- delta:

  Event indicator vector.

- time:

  Survival time vector.

- stratum:

  Optional stratum indicator vector for stratified Cox modeling.

- beta:

  Numeric vector of external coefficients. If `beta` is named, names are
  matched against `colnames(z)`: covariates absent from `beta` are set
  to 0 (with a message) and the vector is reordered, so an external
  source covering only a subset of the internal covariates may be
  supplied directly. An unnamed `beta` is aligned positionally and must
  have length `ncol(z)`. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).
  Treated as fixed prior information and not resampled across bootstrap
  replicates.

- Q:

  Optional weighting (precision) matrix for the Mahalanobis penalty.
  Must be symmetric and positive semi-definite (both checked to a
  tolerance of 1e-8). If named, it is reordered and zero-padded to
  `colnames(z)`; only an unnamed `Q` must be exactly `ncol(z)` by
  `ncol(z)`. If `NULL`, a *masked identity* is used: 1 on covariates
  actually supplied by `beta` and 0 on zero-padded positions, so padded
  coefficients are left unpenalized. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).

- etas:

  Numeric vector of non-negative integration weights. Must be finite and
  \\\ge 0\\.

- alpha:

  Elastic-net mixing parameter, with \\0 \< \alpha \le 1\\. `alpha = 1`
  corresponds to lasso; values close to 0 approach ridge. Default is
  `1.0`.

- B:

  Number of bootstrap replicates. Default is `100`.

- lambda:

  Optional user-specified `lambda` sequence.

- nlambda:

  Number of `lambda` values to generate if `lambda` is not supplied.
  Default is `100`.

- lambda.min.ratio:

  Ratio of the smallest to the largest `lambda` when generating a
  sequence. Default is `ifelse(nrow(z) < ncol(z), 0.01, 1e-04)`.

- nfolds:

  Number of folds for inner cross-validation via `cv.cox_MDTL_enet`.
  Default is `5`.

- cv.criteria:

  Cross-validation criterion used for selecting the optimal
  `(eta, lambda)` pair. One of `"V&VH"`, `"LinPred"`, `"CIndex_pooled"`
  or `"CIndex_foldaverage"`; the default is `"V&VH"`.

- c_index_stratum:

  Optional stratum assignment for stratified C-index evaluation (may
  differ from model stratification).

- message:

  Logical indicating whether to print progress. Default is `FALSE`.

- seed:

  Optional integer seed for reproducibility. Default is `NULL`.

- ncores:

  Integer. Number of parallel cores. Default 1 (sequential execution).

- ...:

  Additional arguments passed to `cv.cox_MDTL_enet`.

## Value

An object of class `"cox_MDTL_bagging"` containing:

- `best_beta` — aggregated coefficient estimate obtained by averaging
  across valid bootstrap replicates.

- `all_betas` — matrix of dimension `p x B_valid` containing coefficient
  vectors from each successful bootstrap fit.

- `B` — total number of requested bootstrap replicates.

- `valid_replicates` — number of successful (non-error) fits
  contributing to aggregation.

- `seed` — seed used for reproducibility (if supplied).

## Details

External information is supplied via a fixed coefficient vector (`beta`)
and, optionally, a weighting matrix (`Q`). Both represent external prior
information and are **not** resampled across replicates.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim     <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

etas <- generate_eta(method = "exponential", n = 10, max_eta = 10)

bag.out <- cox_MDTL_enet_bagging(
  z            = train_dat_highdim$z,
  delta        = train_dat_highdim$status,
  time         = train_dat_highdim$time,
  stratum      = train_dat_highdim$stratum,
  beta         = beta_external_highdim,
  Q            = NULL,
  etas         = etas,
  alpha        = 0.5,
  B            = 5,
  cv.criteria  = "CIndex_pooled",
  message      = TRUE,
  seed         = 123
)
} # }
```
