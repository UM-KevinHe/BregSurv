# Cox Proportional Hazards Model with KL Divergence for Data Integration

Fits a series of Cox proportional hazards models that incorporate
external information using Kullback–Leibler (KL) divergence.

External information can be supplied either as:

- Precomputed external risk scores (`RS`).

- Externally derived coefficients (`beta`).

The strength of integration is controlled by a sequence of tuning
parameters (`etas`). The function fits a model for each `eta` value
provided.

## Usage

``` r
coxkl(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas,
  tol = 1e-04,
  Mstop = 100,
  backtrack = FALSE,
  message = FALSE,
  data_sorted = FALSE,
  beta_initial = NULL
)
```

## Arguments

- z:

  Numeric matrix of covariates. Rows represent observations, columns
  represent predictor variables.

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of observed event or censoring times.

- stratum:

  Optional numeric or factor vector defining strata.

- RS:

  Optional numeric vector of external risk scores, one per observation
  (a one-column matrix is also accepted); its length must equal the
  number of observations. Only a single risk score per observation is
  supported. If not supplied, `beta` must be provided.

- beta:

  Optional numeric vector of external coefficients. If `beta` is named,
  names are matched against `colnames(z)`: covariates absent from `beta`
  are set to 0 (with a message) and the vector is reordered, so an
  external source covering only a subset of the internal covariates may
  be supplied directly. An unnamed `beta` is aligned positionally and
  must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
  If provided, it is used to calculate risk scores internally. If not
  supplied, `RS` must be provided.

- etas:

  Numeric vector of non-negative integration weights. Must be finite and
  \\\ge 0\\. The values are sorted in ascending order internally, and
  the columns of the returned coefficient matrix follow that sorted
  order.

- tol:

  Numeric. Convergence tolerance for the optimization algorithm. Default
  is `1e-4`.

- Mstop:

  Integer. Maximum number of iterations for the optimization. Default is
  `100`.

- backtrack:

  Logical. If `TRUE`, applies backtracking line search during
  optimization. Default is `FALSE`.

- message:

  Logical. If `TRUE`, prints progress messages (e.g., progress bar)
  during fitting. Default is `FALSE`.

- data_sorted:

  Logical. Internal use. If `TRUE`, assumes data is already sorted by
  stratum and time.

- beta_initial:

  Optional numeric vector. Initial values for the coefficients for the
  first `eta`. Default is a zero vector.

## Value

An object of class `"coxkl"` containing:

- `eta`:

  The sorted sequence of \\\eta\\ values used.

- `beta`:

  Matrix of estimated coefficients (\\p \times n\_{etas}\\). Columns
  correspond to `eta` values.

- `linear.predictors`:

  Matrix of linear predictors (risk scores) for each `eta`.

- `likelihood`:

  Vector of log-partial likelihoods, one per `eta` (larger values
  indicate better fit; this is *not* a loss).

- `data`:

  List containing the input data used (`z`, `time`, `delta`, `stratum`,
  `RS`).

## Details

The objective function is a weighted combination of the internal partial
likelihood and the KL divergence from the external information.

- Larger values of `eta` place more weight on the external information.

- `eta = 0` corresponds to the standard Cox model relying solely on
  internal data.

The function uses a "warm start" strategy where the solution for the
current `eta` is used as the initial value for the next `eta` in the
sorted sequence.

## Examples

``` r
if (FALSE) { # \dontrun{
# Load example data
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair

# Generate a sequence of eta values
eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

# Fit the model
coxkl_est <- coxkl(
  z = train_dat_lowdim$z,
  delta = train_dat_lowdim$status,
  time = train_dat_lowdim$time,
  stratum = train_dat_lowdim$stratum,
  beta = beta_external_lowdim,
  etas = eta_list
)
} # }
```
