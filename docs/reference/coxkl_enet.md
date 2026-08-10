# Cox Proportional Hazards Model with KL Divergence and Elastic Net Penalty

Fits a Cox proportional hazards model that integrates external
information using Kullback–Leibler (KL) divergence, while applying an
Elastic Net (Lasso + Ridge) penalty for variable selection and
regularization.

External information can be provided as:

- `RS`: Precomputed external risk scores.

- `beta`: Externally derived coefficients (which are converted to risk
  scores internally).

The strength of integration is controlled by the tuning parameter `eta`.

## Usage

``` r
coxkl_enet(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
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

## Arguments

- z:

  Numeric matrix of covariates (predictors). Rows are observations,
  columns are variables.

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of follow-up times (observed event or censoring time).

- stratum:

  Optional numeric or factor vector for stratified analysis.

- RS:

  Optional numeric vector of external risk scores. Length must equal
  `nrow(z)`. If not provided, `beta` must be supplied.

- beta:

  Optional numeric vector of external coefficients. Length must equal
  `ncol(z)`. If provided, it is used to calculate risk scores. If not
  provided, `RS` must be supplied.

- eta:

  Numeric scalar. The tuning parameter for KL divergence (integration
  strength). Defaults to 0 (no external information).

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha = 1` is the lasso penalty, and `alpha` close to 0 approaches
  ridge. Defaults to 1.

- lambda:

  Optional numeric vector of penalty parameters. If `NULL`, a path is
  generated automatically.

- nlambda:

  Integer. The number of lambda values to generate. Default is 100.

- lambda.min.ratio:

  Numeric. The ratio of the smallest to the largest lambda in the
  sequence. Default depends on sample size relative to features (0.05 if
  n \< p, else 1e-3).

- lambda.early.stop:

  Logical. If `TRUE`, stops the lambda path early if the loss
  improvement is small.

- tol:

  Numeric. Convergence tolerance for the optimization. Default is 1e-4.

- Mstop:

  Integer. Maximum iterations for the inner loop per lambda. Default is
  1000.

- max.total.iter:

  Integer. Maximum total iterations across the entire path.

- group:

  Integer vector defining group membership for grouped penalties.
  Default treats each variable as its own group.

- group.multiplier:

  Numeric vector. Multiplicative factors for penalties applied to each
  group.

- standardize:

  Logical. If `TRUE`, `z` is standardized internally. Coefficients are
  returned on the original scale.

- nvar.max:

  Integer. Maximum number of active variables allowed.

- group.max:

  Integer. Maximum number of active groups allowed.

- stop.loss.ratio:

  Numeric. Threshold for early stopping based on loss ratio.

- actSet:

  Logical. If `TRUE`, uses an active-set strategy for optimization.

- actIter:

  Integer. Iterations for active set refinement.

- actGroupNum:

  Integer. Limit on active groups in active set strategy.

- actSetRemove:

  Logical. Whether to allow removal from the active set.

- returnX:

  Logical. If `TRUE`, returns the standardized design matrix and data in
  the result.

- trace.lambda:

  Logical. If `TRUE`, prints the lambda sequence progress.

- message:

  Logical. If `TRUE`, prints informative messages during fitting.

- data_sorted:

  Logical. Internal use. Indicates if data is already sorted by
  time/stratum.

- ...:

  Additional arguments.

## Value

An object of class `"coxkl_enet"`. A list containing:

- `beta`:

  Matrix of coefficient estimates (p x nlambda).

- `lambda`:

  The sequence of lambda values used.

- `alpha`:

  The elastic-net mixing parameter used.

- `likelihood`:

  Vector of negative log-partial likelihoods (loss) for each lambda.

- `df`:

  Vector of degrees of freedom (number of non-zero coefficients) for
  each lambda.

- `iter`:

  Vector of iteration counts for each lambda.

- `W`:

  Matrix of exponentiated linear predictors (risk scores) on the
  original scale.

- `data`:

  List containing the input data used.

## Details

The objective function optimizes the partial likelihood penalized by the
KL divergence from the external information and the Elastic Net norm.

- If `eta = 0`, the method reduces to a standard Elastic Net Cox model
  (ignoring external info).

- If `alpha = 1`, the penalty is Lasso.

- If `alpha` is close to 0, the penalty approaches Ridge.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

# Fit the Elastic Net Cox model with KL divergence
coxkl_enet_est <- coxkl_enet(
  z = train_dat_highdim$z,
  delta = train_dat_highdim$status,
  time = train_dat_highdim$time,
  stratum = train_dat_highdim$stratum,
  beta = beta_external_highdim,
  eta = 0  # eta=0 implies standard elastic net (ignoring external beta)
)
} # }
```
