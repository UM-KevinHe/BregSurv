# Fit Cox Model with Mahalanobis Distance Transfer Learning and Elastic Net Penalty

Fits a Cox Proportional Hazards model that integrates external
information (Transfer Learning) using an Elastic Net regularization
path. The method incorporates prior knowledge from external coefficients
(`beta`) and an optional weight matrix (`Q`), controlled by the transfer
learning parameter `eta`.

The objective function minimizes the negative partial likelihood plus a
transfer learning penalty term \\\frac{\eta}{2} (\beta - \beta\_{ext})^T
Q (\beta - \beta\_{ext})\\ and the Elastic Net penalty.

## Usage

``` r
cox_MDTL_enet(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  Q = NULL,
  eta = NULL,
  alpha = NULL,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(n < p, 0.05, 0.001),
  lambda.early.stop = FALSE,
  tol = 1e-04,
  Mstop = 1000,
  max.total.iter = (Mstop * nlambda),
  group = 1:ncol(z),
  group.multiplier = NULL,
  standardize = T,
  nvar.max = ncol(z),
  group.max = length(unique(group)),
  stop.loss.ratio = 0.01,
  actSet = TRUE,
  actIter = Mstop,
  actGroupNum = sum(unique(group) != 0),
  actSetRemove = F,
  returnX = FALSE,
  trace.lambda = FALSE,
  message = FALSE,
  data_sorted = FALSE
)
```

## Arguments

- z:

  Matrix of predictors (n x p).

- delta:

  Vector of event indicators (1 for event, 0 for censored).

- time:

  Vector of observed survival times.

- stratum:

  Vector indicating the stratum membership. If NULL, all observations
  are assumed to be in the same stratum.

- beta:

  Vector of external coefficients representing the prior knowledge or
  "source" model coefficients. If named, the names are matched against
  `colnames(z)` and covariates absent from `beta` are zero-padded; if
  unnamed, `beta` must have length `ncol(z)`.

- Q:

  Optional weighting (precision) matrix for the Mahalanobis penalty.
  Must be symmetric and positive semi-definite (both checked to a
  tolerance of 1e-8). If named, it is reordered and zero-padded to
  `colnames(z)`; only an unnamed `Q` must be exactly `ncol(z)` by
  `ncol(z)`. If `NULL`, a *masked identity* is used: 1 on covariates
  actually supplied by `beta` and 0 on zero-padded positions, so padded
  coefficients are left unpenalized. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).

- eta:

  Scalar. The transfer learning parameter (\>= 0). Controls the strength
  of the external information. `eta = 0` ignores external info. The
  formal default is `NULL`, which resolves to `eta = 0` with the warning
  "eta is not provided. Setting eta = 0 (no external information used)."

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha=1` is the lasso penalty, and values close to 0 approach ridge.
  The formal default is `NULL`, which resolves to `alpha = 1` with the
  warning "alpha is not provided. Setting alpha = 1 (lasso penalty)."

- lambda:

  Optional user-supplied lambda sequence. If NULL, the algorithm
  generates its own sequence.

- nlambda:

  The number of lambda values. Default is 100.

- lambda.min.ratio:

  Smallest value for lambda, as a fraction of lambda.max. Default is
  `ifelse(n < p, 0.05, 1e-03)`.

- lambda.early.stop:

  Logical. Whether to stop early if the deviance changes minimally.

- tol:

  Convergence threshold for coordinate descent.

- Mstop:

  Maximum number of iterations per lambda step. Default is 1000.

- max.total.iter:

  Maximum total iterations across all lambda values. Default is
  `Mstop * nlambda`.

- group:

  Vector describing the grouping of the coefficients. Default is
  `1:ncol(z)` (no grouping).

- group.multiplier:

  Vector of multipliers for each group size. Default is `NULL`.

- standardize:

  Logical. Should the predictors be standardized before fitting? Default
  is TRUE.

- nvar.max:

  Maximum number of variables allowed in the model. Default is
  `ncol(z)`.

- group.max:

  Maximum number of groups allowed in the model. Default is
  `length(unique(group))`.

- stop.loss.ratio:

  Ratio of loss change to stop the path early. Default is 1e-2.

- actSet:

  Logical. Whether to use active set convergence strategy.

- actIter:

  Number of iterations for active set. Default is `Mstop`.

- actGroupNum:

  Number of active groups. Default is `sum(unique(group) != 0)`.

- actSetRemove:

  Logical. Whether to remove inactive groups from the active set.
  Default is `FALSE`.

- returnX:

  Logical. If TRUE, returns the standardized design matrix and other
  data details. Default is `FALSE`.

- trace.lambda:

  Logical. If TRUE, prints the current lambda during fitting. Default is
  `FALSE`.

- message:

  Logical. If TRUE, prints warnings and progress messages.

- data_sorted:

  Logical. Internal flag indicating if data is already sorted by
  time/stratum. Default is `FALSE`.

## Value

An object of class `"cox_MDTL_enet"` containing:

- `beta`: Matrix of estimated coefficients (p x nlambda).

- `group`: Factor vector of the group assignments supplied for each
  covariate.

- `lambda`: The sequence of lambda values used.

- `alpha`: The Elastic Net mixing parameter used.

- `likelihood`: Vector of log-partial likelihoods, one per lambda
  (larger values indicate better fit; this is *not* a loss). Unlike the
  Kullback-Leibler variants, this value is unweighted.

- `n`: Number of observations used in the fit.

- `df`: Degrees of freedom for each lambda.

- `iter`: Number of iterations for each lambda.

- `W`: Matrix of exponential linear predictors.

- `group.multiplier`: Numeric vector of group penalty multipliers used.

- `data`: List of input data.

When `returnX = TRUE`, an additional component `returnX` is attached, a
list with the standardized design object `XX` and the sorted `time`,
`delta` and `stratum` vectors.

## Examples

``` r
# \donttest{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

cox_MDTL_enet_est <- cox_MDTL_enet(
  z = train_dat_highdim$z,
  delta = train_dat_highdim$status,
  time = train_dat_highdim$time,
  stratum = train_dat_highdim$stratum,
  beta = beta_external_highdim,
  Q = NULL,
  eta = 0,
  alpha = 1
)
# }
```
