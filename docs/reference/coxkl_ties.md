# Cox Proportional Hazards Model with KL Divergence for Data Integration (Ties Handling)

Fits a series of Cox proportional hazards models that integrate external
information, specified as external coefficients (`beta`), using
Kullback–Leibler (KL) divergence. This version of the function is
designed to **handle tied event times** using either the Breslow or
Exact partial likelihood approximation.

The strength of integration is controlled by a sequence of tuning
parameters (`etas`). The function fits a model for each `eta` value
provided.

## Usage

``` r
coxkl_ties(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  etas,
  ties = "breslow",
  tol = 1e-04,
  Mstop = 100,
  message = FALSE,
  data_sorted = FALSE,
  beta_initial = NULL,
  comb_max = 1e+07
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

- beta:

  Numeric vector of external coefficients (required). If `beta` is
  named, names are matched against `colnames(z)`: covariates absent from
  `beta` are set to 0 (with a message) and the vector is reordered, so
  an external source covering only a subset of the internal covariates
  may be supplied directly. An unnamed `beta` is aligned positionally
  and must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
  These are used to compute the external risk scores and the KL
  divergence term.

- etas:

  Numeric vector of non-negative integration weights. Must be finite and
  \\\ge 0\\. The values are sorted in ascending order internally, and
  the columns of the returned coefficient matrix follow that sorted
  order.

- ties:

  Character string specifying the method for handling ties. Must be one
  of `"breslow"` (default) or `"exact"`.

- tol:

  Numeric. Convergence tolerance for the optimization algorithm
  (Newton-Raphson). Default is `1e-4`.

- Mstop:

  Integer. Maximum number of iterations for the optimization. Default is
  `100`.

- message:

  Logical. If `TRUE`, prints progress messages (e.g., progress bar)
  during fitting. Default is `FALSE`.

- data_sorted:

  Logical. Internal use. If `TRUE`, assumes data is already sorted by
  stratum and time.

- beta_initial:

  Optional numeric vector. Initial values for the coefficients for the
  first `eta`. Default is zero vector.

- comb_max:

  Integer. Maximum number of combinations to check for the **Exact**
  partial likelihood calculation, preventing excessive computation time.
  Default is `1e7`. Only relevant if `ties = "exact"`.

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

  List containing the input data used (`z`, `time`, `delta`, `stratum`).

## Details

The objective function is a weighted combination of the internal partial
likelihood and the KL divergence from the external information derived
from `beta`.

- **KL Divergence and Weighting**: Larger values of `eta` place more
  weight on matching the risk set behavior implied by the external
  coefficients.

- **Standard Cox**: `eta = 0` corresponds to the standard Cox model,
  relying solely on the internal partial likelihood.

- **Ties Handling**: The calculation of the partial likelihood uses the
  method specified by the `ties` argument ("breslow" or "exact"). The
  exact method may be computationally intensive for datasets with many
  tied events.

The function uses a "warm start" strategy where the solution for the
current `eta` is used as the initial value for the next `eta` in the
sorted sequence.

## Examples

``` r
if (FALSE) { # \dontrun{
# Load example data
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
# Rounding the event times introduces ties for demonstration purposes
train_dat_lowdim$time <- round(train_dat_lowdim$time, 2)

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)

# 1. Fit the model using Breslow's approximation for ties (Default)
coxkl_ties.fit_Breslow <- coxkl_ties(
    z = train_dat_lowdim$z,
    delta = train_dat_lowdim$status,
    time = train_dat_lowdim$time,
    stratum = train_dat_lowdim$stratum,
    beta = ExampleData_lowdim$beta_external_fair,
    etas = eta_list,
    ties = "breslow"
)

# 2. Fit the model using the Exact method for ties
coxkl_ties.fit_Exact <- coxkl_ties(
    z = train_dat_lowdim$z,
    delta = train_dat_lowdim$status,
    time = train_dat_lowdim$time,
    stratum = train_dat_lowdim$stratum,
    beta = ExampleData_lowdim$beta_external_fair,
    etas = eta_list,
    ties = "exact"
)
} # }
```
