# Conditional Logistic Regression with KL Divergence and Elastic Net Penalty (CLR-KL-ENet)

Fits a Conditional Logistic Regression model for matched case-control
(1:M) data by mapping the problem to a Cox proportional hazards model
with fixed event time, while integrating external information via
Kullback–Leibler (KL) divergence and applying an Elastic Net (Lasso +
Ridge) penalty for variable selection and regularization.

This function is a thin wrapper around
[`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md):
it maps the CLR problem to a Cox model with \\T = 1\\ and \\\delta = y\\
and then calls `coxkl_enet` as the core engine.

External information can be provided either as:

- `RS`: Precomputed external risk scores (aligned with the rows of `z`).

- `beta`: Externally derived coefficients (which are converted to risk
  scores internally).

The strength of integration is controlled by the tuning parameter `eta`,
while `alpha` and `lambda` govern the Elastic Net penalty.

## Usage

``` r
ncckl_enet(
  y,
  z,
  stratum,
  RS = NULL,
  beta = NULL,
  eta = NULL,
  alpha = NULL,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = 0.001,
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

  Numeric matrix of covariates (predictors). Rows are observations,
  columns are variables.

- stratum:

  Numeric or factor vector defining the matched sets (strata). Strongly
  recommended for conditional logistic regression: if omitted, a warning
  is issued and all observations are assumed to lie in a single stratum,
  which defeats the purpose of matching.

- RS:

  Optional numeric vector of external risk scores. Length must equal
  `nrow(z)`. If not provided, `beta` must be supplied.

- beta:

  Optional numeric vector of external coefficients; if provided, it is
  used to calculate risk scores, and if not provided, `RS` must be
  supplied. If `beta` is named, names are matched against `colnames(z)`:
  covariates absent from `beta` are set to 0 (with a message) and the
  vector is reordered, so an external source covering only a subset of
  the internal covariates may be supplied directly. An unnamed `beta` is
  aligned positionally and must have length `ncol(z)`. A one-column
  matrix with row names is accepted as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
  The bundled external beta `ExampleData_cc_lowdim$beta_external` is
  named `Z1`–`Z6`, so the examples below already exercise the
  name-matching path.

- eta:

  Numeric scalar. The tuning parameter for KL divergence (integration
  strength). Must be a single finite non-negative value. The formal
  default is `NULL`; a `NULL` `eta` is resolved to 0 (no external
  information) inside
  [`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md),
  which emits the warning
  `"eta is not provided. Setting eta = 0 (no external information used)."`

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha = 1` is the Lasso penalty, and `alpha` close to 0 approaches
  Ridge. If `NULL`, it is set to 1 with a warning inside
  [`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md).

- lambda:

  Optional numeric vector of penalty parameters. If `NULL`, a path is
  generated automatically.

- nlambda:

  Integer. Number of lambda values to generate when `lambda` is `NULL`.
  Default is 100.

- lambda.min.ratio:

  Numeric. Ratio of the smallest to the largest lambda in the sequence
  when `lambda` is `NULL`. Default is `1e-3`. Users may override this to
  mimic the behavior in
  [`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md).

- lambda.early.stop:

  Logical. If `TRUE`, stops the lambda path early if the loss
  improvement is small.

- tol:

  Numeric. Convergence tolerance for the optimization. Default is
  `1e-4`.

- Mstop:

  Integer. Maximum iterations for the inner loop per lambda. Default is
  `1000`.

- max.total.iter:

  Integer. Maximum total iterations across the entire lambda path.
  Default is `Mstop * nlambda`.

- group:

  Integer vector defining group membership for grouped penalties.
  Default treats each variable as its own group (`1:ncol(z)`).

- group.multiplier:

  Numeric vector. Multiplicative factors for penalties applied to each
  group.

- standardize:

  Logical. If `TRUE`, `z` is standardized internally. Coefficients are
  returned on the original scale. Default is `TRUE`.

- nvar.max:

  Integer. Maximum number of active variables allowed. Default is
  `ncol(z)`.

- group.max:

  Integer. Maximum number of active groups allowed. Default is the total
  number of unique groups.

- stop.loss.ratio:

  Numeric. Threshold for early stopping based on loss ratio. Default is
  `1e-2`.

- actSet:

  Logical. If `TRUE`, uses an active-set strategy for optimization.
  Default is `TRUE`.

- actIter:

  Integer. Iterations for active set refinement. Default is `Mstop`.

- actGroupNum:

  Integer. Limit on active groups in the active-set strategy. Default is
  `sum(unique(group) != 0)`.

- actSetRemove:

  Logical. Whether to allow removal of groups from the active set.
  Default is `FALSE`.

- returnX:

  Logical. If `TRUE`, returns the standardized design matrix and
  processed data in the result. Default is `FALSE`.

- trace.lambda:

  Logical. If `TRUE`, prints the lambda sequence progress. Default is
  `FALSE`.

- message:

  Logical. If `TRUE`, prints informative messages during fitting.
  Default is `FALSE`.

- ...:

  Additional arguments passed to
  [`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md).

## Value

An object of class `"ncckl_enet"` and `"coxkl_enet"` containing:

- `beta`:

  Matrix of coefficient estimates (p x nlambda).

- `group`:

  Factor recording the group membership supplied in `group`.

- `lambda`:

  Sequence of lambda values used, after saturated values are dropped.

- `alpha`:

  Elastic Net mixing parameter used.

- `likelihood`:

  Vector of KL-weighted log-partial likelihoods, one per lambda (larger
  values indicate better fit; this is *not* a loss). The contribution of
  each matched set is weighted by \\(\delta + \eta \tilde{\delta}) /
  (1 + \eta)\\, so this is not the same quantity as the unweighted
  log-partial likelihood reported by
  [`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md).

- `n`:

  Number of observations used in the fit.

- `df`:

  Vector of degrees of freedom (number of non-zero coefficients) for
  each lambda.

- `iter`:

  Vector of iteration counts for each lambda.

- `W`:

  Matrix of exponentiated linear predictors (risk scores) on the
  original scale.

- `group.multiplier`:

  Numeric vector of group penalty multipliers used.

- `data`:

  List containing the input data used, with the CLR-to-Cox mapping
  already applied: `z`, `stratum`, the external risk scores `RS`, the
  outcome stored under `delta`, and `time` (a vector of 1s). There is no
  `y` component: `fit$data$y` is `NULL`, and the outcome must be read
  from `fit$data$delta`.

If `returnX = TRUE`, the object additionally carries a `returnX`
component holding the standardized design matrix together with the
sorted `time`, `delta`, `stratum` and `RS`.

## Details

This function assumes a 1:M matched case-control design, where each
stratum corresponds to a matched set containing one case (`y = 1`) and
one or more controls (`y = 0`). The CLR likelihood is equivalent to a
Cox partial likelihood with a common event time within each matched set.
Thus, we define \\\delta_i = y_i\\ and \\T_i = 1\\ for all subjects and
fit a stratified Cox model with KL divergence and Elastic Net penalty
via
[`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md).

- If `eta = 0`, the method reduces to a standard Elastic Net CLR
  (ignoring external information).

- If `alpha = 1`, the penalty is Lasso.

- If `alpha` is close to 0, the penalty approaches Ridge.

## See also

[`coxkl_enet`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.md)
for the underlying Cox PH engine with KL divergence and Elastic Net
regularization.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc_lowdim)
train_cc <- ExampleData_cc_lowdim$train

y <- train_cc$y
z <- train_cc$z
sets <- train_cc$stratum

beta_external_cc <- ExampleData_cc_lowdim$beta_external

# Fit CLR-KL-ENet with eta = 0 (standard Elastic Net CLR)
ncckl_enet_fit <- ncckl_enet(
  y       = y,
  z       = z,
  stratum = sets,
  beta    = beta_external_cc,
  eta     = 0
)
} # }
```
