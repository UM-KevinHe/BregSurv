# Bootstrap Variable Importance via Selection Frequency

Performs bootstrap resampling and refits the CoxKL elastic-net/LASSO CV
procedure B times, then summarizes each variable's selection frequency
(proportion of times the variable is selected with nonzero coefficient
in the best model).

## Usage

``` r
variable_importance(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas,
  B = 10,
  nonzero_tol = 1e-10,
  seed = NULL,
  message = FALSE,
  ncores = 1,
  ...
)
```

## Arguments

- z:

  Numeric covariate matrix/data.frame (n x p). If a data.frame is
  provided, it will be converted to a numeric matrix via `as.matrix(z)`.

- delta:

  Numeric vector of event indicators.

- time:

  Numeric vector of observed times.

- stratum:

  Optional stratum vector. Default NULL.

- RS:

  Optional external risk scores. Default NULL.

- beta:

  Optional numeric vector of external coefficients. Default NULL. It is
  forwarded to
  [`cv.coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_enet.md),
  which aligns it: if `beta` is named, names are matched against
  `colnames(z)`, covariates absent from `beta` are set to 0 (with a
  message) and the vector is reordered. An unnamed `beta` is aligned
  positionally and must have length `ncol(z)`. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).

- etas:

  Numeric vector of non-negative candidate eta values. Must be finite
  and \\\ge 0\\; this is validated by
  [`cv.coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_enet.md).

- B:

  Integer. Number of bootstrap replications. Default is 10.

- nonzero_tol:

  Numeric tolerance for defining "selected". Default 1e-10.

- seed:

  Optional integer seed for reproducibility.

- message:

  Logical. Whether to print progress messages. Default FALSE.

- ncores:

  Integer. Number of parallel cores. Default 1 (sequential execution).

- ...:

  Additional arguments passed to
  [`cv.coxkl_enet()`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_enet.md)
  (e.g., `alpha`, `lambda`, `nlambda`, `lambda.min.ratio`, `nfolds`,
  `cv.criteria`, `c_index_stratum`, etc.).

## Value

An object of class "variable_importance" with fields:

- freq:

  Named numeric vector of selection frequencies (length p).

- count:

  Named integer vector of selection counts (length p).

- B:

  Number of bootstrap replications.

- nonzero_tol:

  The tolerance used to define "selected".

- call:

  Matched call.
