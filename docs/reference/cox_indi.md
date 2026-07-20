<div id="main" class="col-md-9" role="main">

# Cox Proportional Hazards Model Integrated with External Individual-level Information

<div class="ref-description section level2">

Fits a series of composite-likelihood (weighted) stratified Cox models
that integrate an external individual-level dataset via an external
likelihood weight `eta`.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

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

</div>

</div>

<div class="section level2">

## Arguments

-   z\_int:

    Matrix of covariates for the internal dataset (n\_int x p).

-   delta\_int:

    Event indicators for the internal dataset (0/1).

-   time\_int:

    Survival times for the internal dataset.

-   stratum\_int:

    Optional stratum identifiers for the internal dataset (default
    `NULL` -&gt; single stratum).

-   z\_ext:

    Matrix of covariates for the external dataset (n\_ext x p).

-   delta\_ext:

    Event indicators for the external dataset (0/1).

-   time\_ext:

    Survival times for the external dataset.

-   stratum\_ext:

    Optional stratum identifiers for the external dataset (default
    `NULL` -&gt; single stratum).

-   etas:

    Numeric vector of nonnegative external weights. `eta = 0` gives
    internal-only fit.

-   max\_iter:

    Maximum Newton-Raphson iterations (default 100).

-   tol:

    Convergence tolerance (default 1e-7).

-   message:

    Logical; if `TRUE`, show a progress bar. Default `FALSE`.

</div>

<div class="section level2">

## Value

An object of class `"cox_indi"` containing:

-   `eta`:

    Sorted sequence of \\(\\eta\\) values used.

-   `beta`:

    Matrix of estimated coefficients (\\(p \\times n\_{etas}\\)).
    Columns correspond to `etas`.

-   `linear.predictors_int`:

    Matrix of internal linear predictors for each `eta` (\\(n\_{int}
    \\times n\_{etas}\\)).

-   `linear.predictors_ext`:

    Matrix of external linear predictors for each `eta` (\\(n\_{ext}
    \\times n\_{etas}\\)).

-   `data`:

    List of inputs used.

</div>

<div class="section level2">

## Details

The fitted objective is $$\\ell\_\\eta(\\beta) =
\\ell\_{\\text{int}}(\\beta) + \\eta \\, \\ell\_{\\text{ext}}(\\beta),$$
which is equivalent to fitting a stratified Cox model on the stacked
data with observation weights 1 (internal) and `eta` (external), while
keeping internal and external strata separated (no mixing of risk sets
across cohorts).

The function fits one model per `eta` value. It uses a warm-start
strategy: the solution at the current `eta` is used as the initial value
for the next `eta` in the sorted sequence.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

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

</div>

</div>

</div>
