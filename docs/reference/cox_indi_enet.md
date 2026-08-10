# Cox Proportional Hazards Model Integrated with External Individual-level Data and Elastic Net Penalty

Fits a series of penalized stratified Cox models that integrate an
external individual-level dataset via a composite likelihood weight
`eta`, while applying an Elastic Net (Lasso + Ridge) penalty for
variable selection and regularization in high-dimensional settings.

## Usage

``` r
cox_indi_enet(
  z_int,
  delta_int,
  time_int,
  stratum_int = NULL,
  z_ext,
  delta_ext,
  time_ext,
  stratum_ext = NULL,
  etas,
  alpha = 1,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = NULL,
  lambda.early.stop = FALSE,
  tol = 1e-04,
  Mstop = 1000,
  max.total.iter = (Mstop * nlambda),
  group = NULL,
  group.multiplier = NULL,
  standardize = TRUE,
  nvar.max = NULL,
  group.max = NULL,
  stop.loss.ratio = 0.01,
  actSet = TRUE,
  actIter = Mstop,
  actGroupNum = NULL,
  actSetRemove = FALSE,
  returnX = FALSE,
  trace.lambda = FALSE,
  message = FALSE,
  ...
)
```

## Arguments

- z_int:

  Numeric matrix of covariates for the internal dataset
  (\\n\_{\text{int}} \times p\\).

- delta_int:

  Numeric vector of event indicators for the internal dataset (1 =
  event, 0 = censored).

- time_int:

  Numeric vector of survival times for the internal dataset.

- stratum_int:

  Optional stratum identifiers for the internal dataset. Default `NULL`
  assigns all internal observations to a single stratum.

- z_ext:

  Numeric matrix of covariates for the external dataset
  (\\n\_{\text{ext}} \times p\\). Must have the same number of columns
  as `z_int`.

- delta_ext:

  Numeric vector of event indicators for the external dataset (1 =
  event, 0 = censored).

- time_ext:

  Numeric vector of survival times for the external dataset.

- stratum_ext:

  Optional stratum identifiers for the external dataset. Default `NULL`
  assigns all external observations to a single stratum.

- etas:

  Numeric vector of nonnegative external weights. `eta = 0` gives an
  internal-only penalized fit. The vector is sorted internally in
  ascending order.

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha = 1` is the lasso penalty, and `alpha` close to 0 approaches
  ridge. Defaults to 1.

- lambda:

  Optional numeric vector of penalty parameters applied to all `eta`
  values. If `NULL`, a lambda path is generated automatically for each
  `eta`.

- nlambda:

  Integer. The number of lambda values to generate per `eta`. Default is
  100.

- lambda.min.ratio:

  Numeric. The ratio of the smallest to the largest lambda in the
  sequence. Default is 0.05 if \\n\_{\text{all}} \< p\\, and 1e-3
  otherwise.

- lambda.early.stop:

  Logical. If `TRUE`, stops the lambda path early if the loss
  improvement is small. Default `FALSE`.

- tol:

  Numeric. Convergence tolerance for the coordinate descent
  optimization. Default is 1e-4.

- Mstop:

  Integer. Maximum coordinate descent iterations per lambda. Default is
  1000.

- max.total.iter:

  Integer. Maximum total iterations across the entire lambda path.
  Default is `Mstop * nlambda`.

- group:

  Integer vector defining group membership for grouped penalties.
  Default treats each variable as its own group (standard Elastic Net /
  Lasso).

- group.multiplier:

  Numeric vector. Multiplicative factors for penalties applied to each
  group.

- standardize:

  Logical. If `TRUE`, the stacked design matrix `z_all` is standardized
  internally. Coefficients are returned on the original scale. Default
  `TRUE`.

- nvar.max:

  Integer. Maximum number of active variables allowed. Defaults to `p`.

- group.max:

  Integer. Maximum number of active groups allowed. Defaults to the
  total number of unique groups.

- stop.loss.ratio:

  Numeric. Threshold for early stopping based on loss ratio. Default is
  1e-2.

- actSet:

  Logical. If `TRUE`, uses an active-set strategy for coordinate
  descent. Default `TRUE`.

- actIter:

  Integer. Maximum iterations for active set refinement. Default is
  `Mstop`.

- actGroupNum:

  Integer. Limit on active groups in the active set strategy.

- actSetRemove:

  Logical. Whether to allow removal from the active set. Default
  `FALSE`.

- returnX:

  Logical. If `TRUE`, the standardized design matrix object `std.Z` is
  included in the returned result. Default `FALSE`.

- trace.lambda:

  Logical. If `TRUE`, prints the lambda sequence progress. Default
  `FALSE`.

- message:

  Logical. If `TRUE`, shows a progress bar over the `etas` loop. Default
  `FALSE`.

- ...:

  Additional arguments (currently unused).

## Value

An object of class `"cox_indi_enet"` containing:

- `eta`:

  Sorted sequence of \\\eta\\ values used.

- `beta`:

  Named list of length `length(etas)`. Each element is a matrix of
  estimated coefficients (\\p \times n\_\lambda\\) on the original
  covariate scale, with columns named by the corresponding `lambda`
  values.

- `lambda`:

  Named list of length `length(etas)`. Each element is the vector of
  lambda values actually used for that `eta`.

- `alpha`:

  The Elastic Net mixing parameter used.

- `linear.predictors_int`:

  List of matrices (\\n\_{\text{int}} \times n\_\lambda\\) of internal
  linear predictors in the original observation order, one per `eta`.

- `linear.predictors_ext`:

  List of matrices (\\n\_{\text{ext}} \times n\_\lambda\\) of external
  linear predictors in the original observation order, one per `eta`.

- `group`:

  Factor vector of group assignments for each covariate.

- `group.multiplier`:

  Numeric vector of group penalty multipliers used.

- `data`:

  List of the original input data used.

## Details

The fitted objective is \$\$\ell\_{\eta,\lambda}(\beta) =
\ell\_{\text{int}}(\beta) + \eta \\ \ell\_{\text{ext}}(\beta) -
\text{Pen}\_{\lambda,\alpha}(\beta),\$\$ where
\\\text{Pen}\_{\lambda,\alpha}\\ is the Elastic Net penalty. This is
equivalent to fitting a penalized stratified Cox model on the stacked
data with observation weights 1 (internal) and `eta` (external), while
keeping internal and external strata separated (no mixing of risk sets
across cohorts).

- If `alpha = 1`, the penalty is Lasso.

- If `alpha` is close to 0, the penalty approaches Ridge.

- If `eta = 0`, external data is effectively ignored and the model
  reduces to a standard Elastic Net Cox model on internal data only.

The function fits one full lambda path per `eta` value. Standardization
is performed once on the stacked design matrix before the loop, so the
lambda sequence is recomputed for each `eta` (since \\\lambda\_{\max}\\
depends on the weighted score at \\\beta = 0\\).

## Examples

``` r
if (FALSE) { # \dontrun{
## Load example individual-level data
data(ExampleData_indi)

z_int       <- ExampleData_indi$internal$z
delta_int   <- ExampleData_indi$internal$status
time_int    <- ExampleData_indi$internal$time
stratum_int <- ExampleData_indi$internal$stratum

z_ext       <- ExampleData_indi$external$z
delta_ext   <- ExampleData_indi$external$status
time_ext    <- ExampleData_indi$external$time
stratum_ext <- ExampleData_indi$external$stratum

## Generate a sequence of eta values
eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 5)

## Fit the composite-likelihood Elastic Net Cox model path
fit.cox_indi_enet <- cox_indi_enet(
  z_int       = z_int,
  delta_int   = delta_int,
  time_int    = time_int,
  stratum_int = stratum_int,
  z_ext       = z_ext,
  delta_ext   = delta_ext,
  time_ext    = time_ext,
  stratum_ext = stratum_ext,
  etas        = eta_list,
  alpha       = 1,      # Lasso penalty
  nlambda     = 100
)

## Coefficient matrix for the first eta value
fit.cox_indi_enet$beta[[1]]
} # }
```
