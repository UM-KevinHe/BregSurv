# Conditional Logistic Regression with Individual-level External Data (CLR-Indi)

Fits a series of Conditional Logistic Regression models that integrate
external individual-level data via a composite likelihood weight `etas`,
suitable for matched case-control studies.

## Usage

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

## Arguments

- y_int:

  Numeric vector of binary outcomes for the internal dataset (0 =
  control, 1 = case).

- z_int:

  Numeric matrix of covariates for the internal dataset.

- stratum_int:

  Numeric or factor vector defining the matched sets (strata) for the
  internal dataset. **Required**.

- y_ext:

  Numeric vector of binary outcomes for the external dataset (0 =
  control, 1 = case).

- z_ext:

  Numeric matrix of covariates for the external dataset. Must have the
  same number of columns as `z_int`.

- stratum_ext:

  Numeric or factor vector defining the matched sets (strata) for the
  external dataset. **Required**.

- etas:

  Numeric vector of nonnegative external weights. `eta = 0` gives an
  internal-only fit.

- max_iter:

  Maximum number of Newton-Raphson iterations. Default `100`.

- tol:

  Convergence tolerance. Default `1e-7`.

- message:

  Logical. If `TRUE`, shows a progress bar. Default `FALSE`.

## Value

An object of class `"ncc_indi"` and `"cox_indi"` containing the
estimation results for each `eta` value. See
[`cox_indi`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_indi.md)
for a description of the return components.

## Details

This function maps the Conditional Logistic Regression problem to a Cox
PH model with fixed event time \\T=1\\ and event indicator \\\delta=y\\
for both the internal and external matched case-control datasets, then
calls
[`cox_indi`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_indi.md)
as the core engine.

The fitted objective is \$\$\ell\_\eta(\beta) =
\ell\_{\text{int}}(\beta) + \eta \\ \ell\_{\text{ext}}(\beta),\$\$ where
both likelihoods are the conditional (partial) log-likelihoods of the
respective matched datasets, with internal and external risk sets kept
separated.

## See also

[`cox_indi`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_indi.md)
for the core function documentation.
