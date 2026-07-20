<div id="main" class="col-md-9" role="main">

# Fit Cox Model with Multi-Domain Transfer Learning and Elastic Net Penalty

<div class="ref-description section level2">

Fits a Cox Proportional Hazards model that integrates external
information (Transfer Learning) using an Elastic Net regularization
path. The method incorporates prior knowledge from external coefficients
(`beta`) and an optional weight matrix (`vcov`), controlled by the
transfer learning parameter `eta`.

The objective function minimizes the negative partial likelihood plus a
transfer learning penalty term \\(\\eta (\\beta - \\beta\_{ext})^T Q
(\\beta - \\beta\_{ext})\\) and the Elastic Net penalty.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cox_MDTL_enet(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  vcov = NULL,
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
  data_sorted = FALSE,
  ...
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   z:

    Matrix of predictors (n x p).

-   delta:

    Vector of event indicators (1 for event, 0 for censored).

-   time:

    Vector of observed survival times.

-   stratum:

    Vector indicating the stratum membership. If NULL, all observations
    are assumed to be in the same stratum.

-   beta:

    Vector of external coefficients (length p). This represents the
    prior knowledge or "source" model coefficients.

-   vcov:

    Optional weighting matrix (p x p) for the external information.
    Typically the inverse covariance matrix (precision matrix) of the
    external estimator. If NULL, defaults to the identity matrix.

-   eta:

    Scalar. The transfer learning parameter (&gt;= 0). Controls the
    strength of the external information. `eta = 0` ignores external
    info.

-   alpha:

    The Elastic Net mixing parameter, with \\(0 \\le \\alpha \\le 1\\).
    `alpha=1` is the lasso penalty, and `alpha=0` the ridge penalty.

-   lambda:

    Optional user-supplied lambda sequence. If NULL, the algorithm
    generates its own sequence.

-   nlambda:

    The number of lambda values. Default is 100.

-   lambda.min.ratio:

    Smallest value for lambda, as a fraction of lambda.max. Default
    depends on sample size relative to features.

-   lambda.early.stop:

    Logical. Whether to stop early if the deviance changes minimally.

-   tol:

    Convergence threshold for coordinate descent.

-   Mstop:

    Maximum number of iterations per lambda step.

-   max.total.iter:

    Maximum total iterations across all lambda values.

-   group:

    Vector describing the grouping of the coefficients. Default is
    `1:ncol(z)` (no grouping).

-   group.multiplier:

    Vector of multipliers for each group size.

-   standardize:

    Logical. Should the predictors be standardized before fitting?
    Default is TRUE.

-   nvar.max:

    Maximum number of variables allowed in the model.

-   group.max:

    Maximum number of groups allowed in the model.

-   stop.loss.ratio:

    Ratio of loss change to stop the path early.

-   actSet:

    Logical. Whether to use active set convergence strategy.

-   actIter:

    Number of iterations for active set.

-   actGroupNum:

    Number of active groups.

-   actSetRemove:

    Logical. Whether to remove inactive groups from the active set.

-   returnX:

    Logical. If TRUE, returns the standardized design matrix and other
    data details.

-   trace.lambda:

    Logical. If TRUE, prints the current lambda during fitting.

-   message:

    Logical. If TRUE, prints warnings and progress messages.

-   data\_sorted:

    Logical. Internal flag indicating if data is already sorted by
    time/stratum.

-   ...:

    Additional arguments.

</div>

<div class="section level2">

## Value

An object of class `"cox_MDTL_enet"` containing:

-   `beta`: Matrix of estimated coefficients (p x nlambda).

-   `lambda`: The sequence of lambda values used.

-   `likelihood`: Vector of negative partial log-likelihood values.

-   `df`: Degrees of freedom for each lambda.

-   `W`: Matrix of exponential linear predictors.

-   `iter`: Number of iterations for each lambda.

-   `data`: List of input data.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

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
  vcov = NULL,
  eta = 0,
  alpha = 1
)
# }
```

</div>

</div>

</div>
