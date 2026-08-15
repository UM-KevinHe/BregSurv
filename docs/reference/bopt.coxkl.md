# Bayesian Optimization for the Cox–KL Integration Parameter (eta)

Employs Bayesian Optimization to find the optimal integration parameter
`eta` for the Cox–KL model by maximizing a cross-validated performance
criterion. The function wraps
[`cv.coxkl`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl.md)
and uses the rBayesianOptimization framework to efficiently search the
parameter space.

## Usage

``` r
bopt.coxkl(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  bounds_list = list(eta = c(0, 10)),
  init_grid_dt = data.frame(eta = c(0, 1, 5)),
  init_points = 0,
  n_iter = 10,
  acq = "ucb",
  kappa = 2.576,
  seed = NULL,
  verbose = TRUE,
  ...
)
```

## Arguments

- z:

  Numeric matrix of covariates.

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of observed event or censoring times.

- stratum:

  Optional numeric or factor vector defining strata.

- RS:

  Optional numeric vector or matrix of external risk scores.

- beta:

  Optional numeric vector of external coefficients.

- criteria:

  Character string specifying the performance criterion. Choices are
  `"V&VH"`, `"LinPred"`, `"CIndex_pooled"`, or `"CIndex_foldaverage"`.

- bounds_list:

  A named list defining the search range for `eta`, e.g.,
  `list(eta = c(0, 10))`. Default `list(eta = c(0, 10))`. The lower
  bound must be non-negative.

- init_grid_dt:

  A `data.frame` of initial points at which to evaluate the criterion
  before the Bayesian search begins. Default
  `data.frame(eta = c(0, 1, 5))`. All `eta` values in it must be
  non-negative.

- init_points:

  Number of randomly drawn initial points to evaluate before the
  Bayesian search begins, in addition to those supplied via
  `init_grid_dt`. Default `0`.

- n_iter:

  Number of iterations for the Bayesian Optimization process. Default
  `10`.

- acq:

  Acquisition function type. Default is `"ucb"`.

- kappa:

  Numeric tuning parameter controlling the exploration–exploitation
  trade-off of the upper confidence bound (UCB) acquisition function.
  Larger values favour exploration. Default `2.576`.

- seed:

  Optional integer seed to ensure reproducible CV fold assignments.

- verbose:

  Logical; if `TRUE`, progress of the optimization is printed.

- ...:

  Additional arguments passed to
  [`cv.coxkl`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl.md)
  and
  [`coxkl`](https://um-kevinhe.github.io/BregSurv/reference/coxkl.md).

## Value

A list containing:

- `best_eta`:

  The optimal `eta` value discovered.

- `best_beta`:

  The coefficient vector corresponding to `best_eta`.

- `best_score`:

  The raw performance metric value at `best_eta`.

- `full_stats`:

  A `data.frame` of all evaluated `eta` values and their scores, sorted
  by `eta`.

- `beta_matrix`:

  A matrix where each column corresponds to the fitted `beta` for each
  `eta` in `full_stats`.

- `bo_object`:

  The raw object returned by `BayesianOptimization`.

- `criteria`:

  The criterion used for optimization.

## Details

Each objective evaluation is a call to
[`cv.coxkl`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl.md)
at a single candidate `eta`, and this function consumes that call's S3
return directly: the scalar criterion is read from the metric column of
`internal_stat` (its second column, whose name depends on `criteria`),
and the coefficient vector from `beta_full`. Loss criteria (`"V&VH"`,
`"LinPred"`) are negated before being handed to the optimizer, which
always maximizes, while the C-index criteria are passed through
unchanged; `best_score` and `full_stats` report the raw, un-negated
values in either case.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat <- ExampleData_lowdim$train
beta_ext <- ExampleData_lowdim$beta_external_fair

opt_res <- bopt.coxkl(
  z = train_dat$z,
  delta = train_dat$status,
  time = train_dat$time,
  stratum = train_dat$stratum,
  beta = beta_ext,
  criteria = "CIndex_pooled",
  bounds_list = list(eta = c(0, 10)),
  init_grid_dt = data.frame(eta = c(0, 1, 5)),
  n_iter = 20,
  nfolds = 5,
  seed = 2024
)
} # }
```
