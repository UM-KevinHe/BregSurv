<div id="main" class="col-md-9" role="main">

# Conditional Logistic Regression with Individual-level External Data (CLR-Indi)

<div class="ref-description section level2">

Fits a series of Conditional Logistic Regression models that integrate
external individual-level data via a composite likelihood weight `etas`,
suitable for matched case-control studies.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
ncc_indi(
  y_int,
  z_int,
  stratum_int,
  y_ext,
  z_ext,
  stratum_ext,
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

-   y\_int:

    Numeric vector of binary outcomes for the internal dataset (0 =
    control, 1 = case).

-   z\_int:

    Numeric matrix of covariates for the internal dataset.

-   stratum\_int:

    Numeric or factor vector defining the matched sets (strata) for the
    internal dataset. **Required**.

-   y\_ext:

    Numeric vector of binary outcomes for the external dataset (0 =
    control, 1 = case).

-   z\_ext:

    Numeric matrix of covariates for the external dataset. Must have the
    same number of columns as `z_int`.

-   stratum\_ext:

    Numeric or factor vector defining the matched sets (strata) for the
    external dataset. **Required**.

-   etas:

    Numeric vector of nonnegative external weights. `eta = 0` gives an
    internal-only fit.

-   max\_iter:

    Maximum number of Newton-Raphson iterations. Default `100`.

-   tol:

    Convergence tolerance. Default `1e-7`.

-   message:

    Logical. If `TRUE`, shows a progress bar. Default `FALSE`.

</div>

<div class="section level2">

## Value

An object of class `"ncc_indi"` and `"cox_indi"` containing the
estimation results for each `eta` value. See `cox_indi` for a
description of the return components.

</div>

<div class="section level2">

## Details

This function maps the Conditional Logistic Regression problem to a Cox
PH model with fixed event time \\(T=1\\) and event indicator
\\(\\delta=y\\) for both the internal and external matched case-control
datasets, then calls `cox_indi` as the core engine.

The fitted objective is $$\\ell\_\\eta(\\beta) =
\\ell\_{\\text{int}}(\\beta) + \\eta \\, \\ell\_{\\text{ext}}(\\beta),$$
where both likelihoods are the conditional (partial) log-likelihoods of
the respective matched datasets, with internal and external risk sets
kept separated.

</div>

<div class="section level2">

## See also

<div class="dont-index">

`cox_indi` for the core function documentation.

</div>

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
if (FALSE) { # \dontrun{
## Load the matched case-control individual-level example data
data(ExampleData_cc_indi)

y_int       <- ExampleData_cc_indi$internal$y
z_int       <- ExampleData_cc_indi$internal$z
stratum_int <- ExampleData_cc_indi$internal$stratum

y_ext       <- ExampleData_cc_indi$external$y
z_ext       <- ExampleData_cc_indi$external$z
stratum_ext <- ExampleData_cc_indi$external$stratum

## Generate a sequence of eta values
eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

## Fit the composite-likelihood CLR path
fit_path <- ncc_indi(
  y_int       = y_int,
  z_int       = z_int,
  stratum_int = stratum_int,
  y_ext       = y_ext,
  z_ext       = z_ext,
  stratum_ext = stratum_ext,
  etas        = eta_list
)
} # }
```

</div>

</div>

</div>
