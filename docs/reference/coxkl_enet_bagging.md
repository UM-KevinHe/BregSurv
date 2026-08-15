# Bagging for KL-Integrated Cox Elastic-Net Models

Performs bootstrap aggregation (bagging) for the KL-integrated Cox
elastic-net model by repeatedly applying `cv.coxkl_enet` on bootstrap
resamples of the data. The procedure aggregates fitted coefficient
vectors across replicates to produce a more stable estimate that is less
sensitive to sampling variation or a single data split.

## Usage

``` r
coxkl_enet_bagging(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas,
  alpha = 1,
  B = 100,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.05, 0.001),
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

  Optional stratum indicator vector for stratified Cox models.

- RS:

  Optional matrix or vector of external risk scores. If provided, it is
  resampled within each bootstrap replicate. If both `RS` and `beta` are
  supplied, `RS` takes precedence and `beta` is silently discarded.

- beta:

  Optional vector of external coefficients. If provided, it is treated
  as fixed and not resampled. It is passed through unchanged to
  `cv.coxkl_enet`, where a named `beta` is matched against `colnames(z)`
  and zero-padded for any covariate it does not cover, while an unnamed
  `beta` is aligned positionally and must have length `p` (see
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md)).
  Ignored when `RS` is supplied.

- etas:

  Numeric vector of non-negative integration weights. Must be finite and
  \\\ge 0\\.

- alpha:

  Elastic-net mixing parameter, with \\0 \< \alpha \le 1\\ (`alpha = 1`
  is the lasso penalty; values close to 0 approach ridge). Default is
  `1.0`. Values outside `(0, 1]` are rejected by `cv.coxkl_enet`;
  because each replicate is wrapped in
  [`tryCatch()`](https://rdrr.io/r/base/conditions.html), this surfaces
  as every replicate failing rather than as an immediate error.

- B:

  Number of bootstrap replicates. Default is `100`.

- lambda:

  Optional user-specified `lambda` sequence for the underlying
  elastic-net fit.

- nlambda:

  Number of `lambda` values to generate if `lambda` is not supplied.
  Default is `100`.

- lambda.min.ratio:

  Ratio of smallest to largest `lambda` value when generating a `lambda`
  sequence. Defaults to `0.05` when `nrow(z) < ncol(z)` and `1e-03`
  otherwise.

- nfolds:

  Number of folds for cross-validation in `cv.coxkl_enet`. Default is
  `5`.

- cv.criteria:

  Cross-validation criterion used for selecting `eta`–`lambda` pairs.
  One of `"V&VH"` (the default), `"LinPred"`, `"CIndex_pooled"` or
  `"CIndex_foldaverage"`.

- c_index_stratum:

  Optional stratum assignment for stratified C-index evaluation.

- message:

  Logical indicating whether to print progress.

- seed:

  Optional seed for reproducibility.

- ncores:

  Integer. Number of parallel cores. Default 1 (sequential execution).

- ...:

  Additional arguments passed to `cv.coxkl_enet`.

## Value

An object of class `"bagging"`, which is a list containing:

- `best_beta` — aggregated coefficient estimate obtained via averaging
  across valid replicates.

- `all_betas` — matrix of dimension `p x B_valid` containing coefficient
  vectors from each successful bootstrap fit.

- `B` — total number of bootstrap replicates.

- `seed` — seed used (if any).

- `valid_replicates` — number of successful (non-error) bootstrap fits
  used in aggregation.

## Details

External information may be supplied either as a fixed coefficient
vector (`beta`) or as pre-computed external risk scores (`RS`). When
`RS` is provided, it is resampled along with the bootstrap replicates;
when `beta` is provided, it is treated as fixed across replicates and
not resampled.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim     <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external
etas <- generate_eta(method = "exponential", n = 10, max_eta = 100)

bag.out <- coxkl_enet_bagging(
  z     = train_dat_highdim$z,
  delta = train_dat_highdim$status,
  time  = train_dat_highdim$time,
  stratum = train_dat_highdim$stratum,
  beta    = beta_external_highdim,
  etas    = etas,
  B       = 5,
  seed    = 1
)
} # }
```
