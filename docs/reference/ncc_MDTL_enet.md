# Conditional Logistic Regression with Mahalanobis Distance Transfer Learning and Elastic Net (CLR-MDTL-ENet)

Fits a Conditional Logistic Regression model for matched case-control
(1:M) data by mapping the problem to a Cox proportional hazards model
with fixed event time, while incorporating external coefficient
information via a Mahalanobis distance penalty and applying an Elastic
Net (Lasso + Ridge) penalty for variable selection.

## Usage

``` r
ncc_MDTL_enet(
  y,
  z,
  stratum,
  beta,
  vcov = NULL,
  eta = NULL,
  alpha = NULL,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.05, 0.001),
  lambda.early.stop = FALSE,
  tol = 1e-04,
  Mstop = 1000,
  max.total.iter = (Mstop * nlambda),
  group = 1:ncol(z),
  group.multiplier = NULL,
  standardize = TRUE,
  nvar.max = ncol(z),
  group.max = length(unique(group)),
  stop.loss.ratio = 0.01,
  actSet = TRUE,
  actIter = Mstop,
  actGroupNum = sum(unique(group) != 0),
  actSetRemove = FALSE,
  returnX = FALSE,
  trace.lambda = FALSE,
  message = FALSE,
  ...
)
```

## Arguments

- y:

  Numeric vector of binary outcomes (0 = control, 1 = case).

- z:

  Numeric matrix of covariates (rows = observations, columns =
  variables).

- stratum:

  Numeric or factor vector defining the matched sets (strata).
  **Required**.

- beta:

  Numeric vector of external coefficients (length `ncol(z)`).
  **Required**.

- vcov:

  Optional numeric matrix (`ncol(z)` x `ncol(z)`) acting as the
  weighting matrix \\Q\\. Typically the precision matrix of the external
  estimator. If `NULL`, defaults to the identity matrix.

- eta:

  Numeric scalar. The transfer learning parameter (\\\geq 0\\). Controls
  the strength of external information. `eta = 0` ignores external info.

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha = 1` is Lasso; `alpha` close to 0 approaches Ridge. Default
  `NULL` (set to 1 with a warning if not supplied).

- lambda:

  Optional user-supplied lambda sequence. If `NULL`, the algorithm
  generates its own sequence based on `nlambda` and `lambda.min.ratio`.

- nlambda:

  Integer. Number of lambda values. Default `100`.

- lambda.min.ratio:

  Smallest value for lambda as a fraction of `lambda.max`. Default
  depends on sample size relative to number of covariates.

- lambda.early.stop:

  Logical. Whether to stop early if deviance changes minimally. Default
  `FALSE`.

- tol:

  Convergence tolerance for coordinate descent. Default `1e-4`.

- Mstop:

  Maximum iterations per lambda step. Default `1000`.

- max.total.iter:

  Maximum total iterations across all lambda values. Default
  `Mstop * nlambda`.

- group:

  Integer vector describing group membership of coefficients. Default
  `1:ncol(z)` (no grouping).

- group.multiplier:

  Numeric vector of multipliers for each group.

- standardize:

  Logical. If `TRUE`, predictors are standardized before fitting.
  Default `TRUE`.

- nvar.max:

  Maximum number of variables in the model. Default `ncol(z)`.

- group.max:

  Maximum number of groups in the model.

- stop.loss.ratio:

  Ratio of loss change for early path stopping. Default `1e-2`.

- actSet:

  Logical. Whether to use active set convergence strategy. Default
  `TRUE`.

- actIter:

  Iterations for active set. Default `Mstop`.

- actGroupNum:

  Number of active groups.

- actSetRemove:

  Logical. Whether to remove inactive groups from active set. Default
  `FALSE`.

- returnX:

  Logical. If `TRUE`, returns the standardized design matrix. Default
  `FALSE`.

- trace.lambda:

  Logical. If `TRUE`, prints current lambda during fitting. Default
  `FALSE`.

- message:

  Logical. If `TRUE`, prints warnings and progress messages. Default
  `FALSE`.

- ...:

  Additional arguments passed to
  [`cox_MDTL_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL_enet.md).

## Value

An object of class `"ncc_MDTL_enet"` and `"cox_MDTL_enet"`. See
[`cox_MDTL_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL_enet.md)
for a description of the return components.

## Details

This function maps the CLR problem to a Cox model with \\T = 1\\ and
\\\delta = y\\, then calls
[`cox_MDTL_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL_enet.md)
as the core engine.

The objective function minimizes the negative conditional log-likelihood
plus: \$\$\frac{\eta}{2}(\beta - \beta\_{ext})^T Q (\beta -
\beta\_{ext}) + \text{Pen}\_{\lambda,\alpha}(\beta)\$\$ where \\Q\\ is
the weighting matrix and \\\text{Pen}\_{\lambda,\alpha}\\ is the Elastic
Net penalty.

- If `eta = 0`, the method reduces to a standard Elastic Net CLR.

- If `alpha = 1`, the penalty is Lasso.

- If `alpha` is close to 0, the penalty approaches Ridge.

- If `vcov = NULL`, \\Q = I\\ (Euclidean distance shrinkage towards
  `beta`).

## See also

[`cox_MDTL_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL_enet.md),
[`ncckl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncckl_enet.md)

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc_highdim)
train_cc <- ExampleData_cc_highdim$train

y        <- train_cc$y
z        <- train_cc$z
sets     <- train_cc$stratum
beta_ext <- ExampleData_cc_highdim$beta_external

fit <- ncc_MDTL_enet(
  y       = y,
  z       = z,
  stratum = sets,
  beta    = beta_ext,
  vcov    = NULL,
  eta     = 0,
  alpha   = 1
)
} # }
```
