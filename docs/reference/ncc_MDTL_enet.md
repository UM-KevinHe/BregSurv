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
  Q = NULL,
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

  Numeric vector of external coefficients. **Required**. If `beta` is
  named, names are matched against `colnames(z)`: covariates absent from
  `beta` are set to 0 (with a message) and the vector is reordered, so
  an external source covering only a subset of the internal covariates
  may be supplied directly. An unnamed `beta` is aligned positionally
  and must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).
  The bundled external beta `ExampleData_cc_highdim$beta_external` is
  named `Z1`–`Z20`, so the examples below already exercise the
  name-matching path.

- Q:

  Optional weighting (precision) matrix for the Mahalanobis penalty,
  typically the precision matrix of the external estimator. Must be
  symmetric and positive semi-definite (both checked to a tolerance of
  1e-8). If named, it is reordered and zero-padded to `colnames(z)`;
  only an unnamed `Q` must be exactly `ncol(z)` by `ncol(z)`. If `NULL`,
  a *masked identity* is used: 1 on covariates actually supplied by
  `beta` and 0 on zero-padded positions, so padded coefficients are left
  unpenalized. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).

- eta:

  Numeric scalar. The transfer learning parameter controlling the
  strength of external information; `eta = 0` ignores external info.
  Must be a single finite non-negative (\\\geq 0\\) value. The formal
  default is `NULL`; a `NULL` `eta` is resolved to 0 inside
  [`cox_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL_enet.md),
  which emits the warning
  `"eta is not provided. Setting eta = 0 (no external information used)."`

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
  [`cox_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL_enet.md).

## Value

An object of class `"ncc_MDTL_enet"` and `"cox_MDTL_enet"`. See
[`cox_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL_enet.md)
for a description of the return components.

## Details

This function maps the CLR problem to a Cox model with \\T = 1\\ and
\\\delta = y\\, then calls
[`cox_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL_enet.md)
as the core engine.

The objective function minimizes the negative conditional log-likelihood
plus: \$\$\frac{\eta}{2}(\beta - \beta\_{ext})^T Q (\beta -
\beta\_{ext}) + \text{Pen}\_{\lambda,\alpha}(\beta)\$\$ where \\Q\\ is
the weighting matrix and \\\text{Pen}\_{\lambda,\alpha}\\ is the Elastic
Net penalty.

- If `eta = 0`, the method reduces to a standard Elastic Net CLR.

- If `alpha = 1`, the penalty is Lasso.

- If `alpha` is close to 0, the penalty approaches Ridge.

- If `Q = NULL`, a *masked identity* is used: 1 on the covariates
  actually supplied by `beta` and 0 on zero-padded positions. This gives
  Euclidean-distance shrinkage towards `beta` on the covariates the
  external source covers, while leaving padded coefficients unpenalized.

## See also

[`cox_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_MDTL_enet.md),
[`ncckl_enet`](https://um-kevinhe.github.io/BregSurv/reference/ncckl_enet.md)

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
  Q       = NULL,
  eta     = 0,
  alpha   = 1
)
} # }
```
