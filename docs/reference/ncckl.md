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

  Numeric or factor vector defining the matched sets (strata). This is
  **required** for CLR.

- etas:

  Numeric vector of tuning parameters. Controls the strength of external
  information integration.

- beta:

  Numeric vector of external coefficients. Used to compute the KL
  divergence penalty.

- method:

  Character string specifying the tie-handling method ("breslow" or
  "exact").

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

An object of class `"coxkl"` (inherited from
[`coxkl_ties`](https://um-kevinhe.github.io/SurvBregDiv/reference/coxkl_ties.md))
containing the estimation results for each `eta` value, including
estimated coefficients, linear predictors, and log-partial likelihoods.

## Details

This function maps the Conditional Logistic Regression problem to the
Cox Proportional Hazards model with fixed event time \\T=1\\ and event
indicator \\\delta=y\\. It utilizes the
[`coxkl_ties`](https://um-kevinhe.github.io/SurvBregDiv/reference/coxkl_ties.md)
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

[`coxkl_ties`](https://um-kevinhe.github.io/SurvBregDiv/reference/coxkl_ties.md)
for the core function documentation.

## Examples

``` r
if (FALSE) { # \dontrun{
# Load the matched case-control example data
data(ExampleData_cc)
train_cc <- ExampleData_cc$train

y <- train_cc$y
z <- train_cc$z
sets <- train_cc$stratum

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
external_beta <- ExampleData_cc$beta_external

# Fit CLR-KL using the Breslow approximation
ncckl.fit_breslow <- ncckl(y = y, z = z, stratum = sets, 
                                 eta = eta_list, beta = external_beta,
                                 method = "breslow")
} # }
```
