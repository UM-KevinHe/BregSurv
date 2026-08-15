# Multi-Source Integration for KL-Integrated Cox Elastic-Net Models

Fits multiple KL-integrated Cox elastic-net models on the full data
using multiple external sources, and combines the fitted coefficient
vectors across sources to produce a single aggregated estimate.

## Usage

``` r
coxkl_enet.multi(
  z,
  delta,
  time,
  stratum = NULL,
  beta_list = NULL,
  RS_list = NULL,
  etas,
  combine = c("mean", "median"),
  message = FALSE,
  seed = NULL,
  ...
)
```

## Arguments

- z:

  Matrix/data.frame of predictors of dimension `n x p`.

- delta:

  Event indicator vector.

- time:

  Survival time vector.

- stratum:

  Optional stratum indicator vector for stratified Cox models.

- beta_list:

  A list of external coefficient vectors, one per external source. Each
  element is aligned to the internal covariate space independently: if
  the element is named, names are matched against `colnames(z)`,
  covariates absent from that element are set to 0 (with a message) and
  the vector is reordered, so different sources may cover different
  subsets of the internal covariates. An unnamed element is aligned
  positionally and must have length `p`. A one-column matrix with row
  names is accepted as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
  If provided, `RS_list` should be `NULL`.

- RS_list:

  Optional list of external risk score vectors/matrices. Each element
  should be conformable with `n`. If provided, `beta_list` is ignored.

- etas:

  Numeric vector of non-negative integration weights. Must be finite and
  \\\ge 0\\.

- combine:

  How to combine coefficients across sources. Either `"mean"` (default)
  or `"median"`.

- message:

  Logical indicating whether to print progress.

- seed:

  Optional seed for reproducibility (passed to each CV run with an
  offset).

- ...:

  Additional arguments passed to
  [`cv.coxkl_enet()`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_enet.md)
  (e.g., `alpha`, `lambda`, `nlambda`, `lambda.min.ratio`, `nfolds`,
  `cv.criteria`, `c_index_stratum`, etc.).

## Value

An object of class `"coxkl_enet.multi"`, which is a list containing:

- `best_beta` — combined coefficient estimate across sources.

- `all_betas` — matrix of dimension `p x K_valid` of coefficient vectors
  from each successful fit.

- `etas` — the `etas` argument exactly as supplied by the caller (raw
  and unsorted); each
  [`cv.coxkl_enet()`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_enet.md)
  run sorts its own copy internally.

- `K` — total number of external sources provided.

- `valid_sources` — number of successful (non-error) fits used in
  aggregation.

- `combine` — combination rule used.

- `seed` — seed used (if any).

- `source_fits` — list of the `cv.coxkl_enet` fit objects for the valid
  sources, in the same order as the columns of `all_betas`.

## Details

Unlike
[`coxkl_enet_bagging()`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet_bagging.md),
this function does not bootstrap the data. Instead, it runs
[`cv.coxkl_enet()`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_enet.md)
once per external source on the full dataset. The resulting coefficient
vectors are then aggregated (by default, averaged) to obtain a combined
estimate.
