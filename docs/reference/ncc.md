# Conditional Logistic Regression (CLR) using Cox PH Core

Estimates the coefficients for a Conditional Logistic Regression model,
particularly suitable for 1:M matched case-control studies, by
leveraging the core Cox Proportional Hazards estimation function
([`cox`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox.md)).

## Usage

``` r
ncc(
  y,
  z,
  stratum,
  method = c("breslow", "exact", "efron"),
  max_iter = 100,
  tol = 1e-07,
  comb_max = 1e+07
)
```

## Arguments

- y:

  Numeric vector of binary outcomes (0 = control, 1 = case).

- z:

  Numeric matrix of covariates (rows = observations, columns =
  variables).

- stratum:

  Numeric or factor vector defining the matched sets. This is
  **required**    for CLR; if omitted, a warning is issued and all data
  is treated as one stratum,    which defeats the purpose of matching.

- method:

  Character string specifying the tie-handling method, which determines
     the conditional likelihood approximation. Choices are `"breslow"`,
  `"exact"`, or `"efron"`.    Default is to use the first match, but
  typically `"exact"` is preferred for CLR.

- max_iter:

  Maximum number of Newton-Raphson iterations passed to `cox`. Default
  `100`.

- tol:

  Convergence tolerance for the Newton-Raphson update passed to `cox`.
  Default `1e-7`.

- comb_max:

  Maximum number of combinations allowed for the `method = "exact"`
  calculation. Default `1e7`.

## Value

A `list` containing:

- `beta`:

  Estimated coefficient vector (length p).

- `loglik`:

  The log-conditional likelihood (which is the log-partial likelihood
  from `cox`) at convergence.

## Details

This function implements CLR by mapping it to a specialized Cox PH
model: the binary outcome `y` is treated as the event indicator
(`delta`), and all event times (`time`) are set to 1, ensuring all
"events" are tied. The `stratum` argument acts as the matched-set
indicator.

The three tie-handling methods (Breslow, Efron, and Exact) correspond to
different approximations of the Conditional Likelihood. **For
mathematically exact CLR results, the `method = "exact"` should be
used.**

## See also

[`cox`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox.md) for
the underlying Cox PH estimation function.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc)
train_cc <- ExampleData_cc$train

y <- train_cc$y
z <- train_cc$z
sets <- train_cc$stratum

# 1. Fit Conditional Logistic Regression using the Exact method
fit_exact <- ncc(y = y, z = z, stratum = sets, method = "exact")

# 2. Fit CLR using the Breslow approximation
fit_breslow <- ncc(y = y, z = z, stratum = sets, method = "breslow")
} # }
```
