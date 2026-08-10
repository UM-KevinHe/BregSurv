# Cox Proportional Hazards Model Integrated with External Individual-level Information

Fits a series of composite-likelihood (weighted) stratified Cox models
that integrate an external individual-level dataset via an external
likelihood weight `eta`.

## Usage

``` r
cox_indi(
  z_int,
  delta_int,
  time_int,
  stratum_int = NULL,
  z_ext,
  delta_ext,
  time_ext,
  stratum_ext = NULL,
  etas,
  max_iter = 100,
  tol = 1e-07,
  message = FALSE
)
```

## Arguments

- z_int:

  Matrix of covariates for the internal dataset (n_int x p).

- delta_int:

  Event indicators for the internal dataset (0/1).

- time_int:

  Survival times for the internal dataset.

- stratum_int:

  Optional stratum identifiers for the internal dataset (default `NULL`
  -\> single stratum).

- z_ext:

  Matrix of covariates for the external dataset (n_ext x p).

- delta_ext:

  Event indicators for the external dataset (0/1).

- time_ext:

  Survival times for the external dataset.

- stratum_ext:

  Optional stratum identifiers for the external dataset (default `NULL`
  -\> single stratum).

- etas:

  Numeric vector of nonnegative external weights. `eta = 0` gives
  internal-only fit.

- max_iter:

  Maximum Newton-Raphson iterations (default 100).

- tol:

  Convergence tolerance (default 1e-7).

- message:

  Logical; if `TRUE`, show a progress bar. Default `FALSE`.

## Value

An object of class `"cox_indi"` containing:

- `eta`:

  Sorted sequence of \\\eta\\ values used.

- `beta`:

  Matrix of estimated coefficients (\\p \times n\_{etas}\\). Columns
  correspond to `etas`.

- `linear.predictors_int`:

  Matrix of internal linear predictors for each `eta` (\\n\_{int} \times
  n\_{etas}\\).

- `linear.predictors_ext`:

  Matrix of external linear predictors for each `eta` (\\n\_{ext} \times
  n\_{etas}\\).

- `data`:

  List of inputs used.

## Details

The fitted objective is \$\$\ell\_\eta(\beta) =
\ell\_{\text{int}}(\beta) + \eta \\ \ell\_{\text{ext}}(\beta),\$\$ which
is equivalent to fitting a stratified Cox model on the stacked data with
observation weights 1 (internal) and `eta` (external), while keeping
internal and external strata separated (no mixing of risk sets across
cohorts).

The function fits one model per `eta` value. It uses a warm-start
strategy: the solution at the current `eta` is used as the initial value
for the next `eta` in the sorted sequence.

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
eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 100)

## Fit the composite-likelihood Cox model path
fit_path <- cox_indi(
  z_int = z_int,
  delta_int = delta_int,
  time_int = time_int,
  stratum_int = stratum_int,
  z_ext = z_ext,
  delta_ext = delta_ext,
  time_ext = time_ext,
  stratum_ext = stratum_ext,
  etas = eta_list
)

## Estimated coefficients along the eta path
fit_path$beta
} # }
```
