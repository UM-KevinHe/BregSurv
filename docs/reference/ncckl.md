# Conditional Logistic Regression with KL Divergence (CLR-KL)

Fits a series of Conditional Logistic Regression models that integrate
external coefficient information (`beta`) using Kullback–Leibler (KL)
divergence, suitable for matched case-control studies.

## Usage

``` r
ncckl(
  y,
  z,
  stratum,
  etas,
  beta,
  method = c("breslow", "exact"),
  Mstop = 100,
  tol = 1e-04,
  message = FALSE,
  comb_max = 1e+07
)
```

## Arguments

- y:

  Numeric vector of binary outcomes (0 = control, 1 = case).

- z:

  Numeric matrix of covariates.

- stratum:

  Numeric or factor vector defining the matched sets (strata). Strongly
  recommended for CLR: if omitted, a warning is issued and all
  observations are assumed to lie in a single stratum, which defeats the
  purpose of matching.

- etas:

  Numeric vector of non-negative integration weights, controlling the
  strength of external information integration. Must be finite and \\\ge
  0\\. The values are sorted in ascending order internally, and the
  columns of the returned coefficient matrix follow that sorted order.

- beta:

  Numeric vector of external coefficients, used to compute the KL
  divergence penalty. Required. If `beta` is named, names are matched
  against `colnames(z)`: covariates absent from `beta` are set to 0
  (with a message) and the vector is reordered, so an external source
  covering only a subset of the internal covariates may be supplied
  directly. An unnamed `beta` is aligned positionally and must have
  length `ncol(z)`. A one-column matrix with row names is accepted as a
  named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
  The bundled external beta `ExampleData_cc_lowdim$beta_external` is
  named `Z1`–`Z6`, so the examples below already exercise the
  name-matching path.

- method:

  Character string specifying the tie-handling method, resolved by
  [`match.arg`](https://rdrr.io/r/base/match.arg.html). One of
  `"breslow"` (the default) or `"exact"`.

- Mstop:

  Integer. Maximum number of Newton-Raphson iterations. Default `100`.

- tol:

  Numeric. Convergence tolerance. Default `1e-4`.

- message:

  Logical. If `TRUE`, prints progress during fitting. Default `FALSE`.

- comb_max:

  Integer. Maximum number of combinations for the `method = "exact"`
  calculation. Default `1e7`.

## Value

An object of class `"coxkl"`, returned unchanged from
[`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md),
containing the estimation results for each `eta` value:

- `eta`:

  The sorted sequence of \\\eta\\ values used. Because `etas` is sorted
  internally, this is the only way to recover which column of `beta`
  corresponds to which weight.

- `beta`:

  Matrix of estimated coefficients (\\p \times n\_{etas}\\); columns
  follow the sorted `eta` values.

- `linear.predictors`:

  Matrix of linear predictors, in the original row order.

- `likelihood`:

  Vector of log-partial likelihoods, one per `eta`.

- `data`:

  List of the input data used (`z`, `time`, `delta`, `stratum`). Note
  the CLR-to-Cox mapping: the outcome `y` is stored under `delta`, and
  `time` is a vector of 1s.

## Details

This function maps the Conditional Logistic Regression problem to the
Cox Proportional Hazards model with fixed event time \\T=1\\ and event
indicator \\\delta=y\\. It utilizes the
[`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md)
core engine to perform the data integration via the KL divergence
penalty.

- **Method**: The `method` ("breslow" or "exact") specifies which form
  of the partial likelihood is used. For 1:M matched case-control
  studies, "breslow" and "exact" yield identical results, but "exact" is
  theoretically preferable. For \\n:m\\ matched designs (\\n\>1\\), the
  results will differ.

- **External Information**: Larger values of the tuning parameter `eta`
  enforce stronger agreement with the external coefficients `beta`.

- **Standard CLR**: Setting `etas = 0` (or including 0 in the sequence)
  recovers the standard Maximum Likelihood Estimates for Conditional
  Logistic Regression.

## See also

[`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md)
for the core function documentation.

## Examples

``` r
if (FALSE) { # \dontrun{
# Load the matched case-control example data
data(ExampleData_cc_lowdim)
train_cc <- ExampleData_cc_lowdim$train

y <- train_cc$y
z <- train_cc$z
sets <- train_cc$stratum

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
external_beta <- ExampleData_cc_lowdim$beta_external

# Fit CLR-KL using the Breslow approximation
ncckl.fit_breslow <- ncckl(y = y, z = z, stratum = sets,
                                 etas = eta_list, beta = external_beta,
                                 method = "breslow")
} # }
```
