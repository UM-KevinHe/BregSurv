# Estimate Cox Proportional Hazards Model Coefficients

Estimates the coefficients of a Cox Proportional Hazards model using the
Newton-Raphson method implemented in C++ (Rcpp). It supports
stratification, observation weights, and different tie-handling methods
(Breslow, Efron, Exact).

## Usage

``` r
cox(
  z,
  delta,
  time,
  stratum,
  ties = NULL,
  max_iter = 100,
  tol = 1e-07,
  comb_max = 1e+07
)
```

## Arguments

- z:

  A matrix or data frame of covariates (n x p).

- delta:

  A binary event indicator vector (length n), where 1 = event and 0 =
  censored.

- time:

  A numeric vector of observed times (length n).

- stratum:

  A vector indicating strata for a stratified Cox model. If missing, all
  data is assumed to belong to a single stratum.

- ties:

  A character string specifying the method for tie handling. Options are
  "breslow" (default), "efron", or "exact".

- max_iter:

  Maximum number of Newton-Raphson iterations (default = 100).

- tol:

  Convergence tolerance for the Newton-Raphson update (default = 1e-7).

- comb_max:

  Maximum number of combinations allowed for the "exact" method (default
  = 1e7).

## Value

A list containing:

- beta:

  Estimated coefficient vector (length p).

- loglik:

  The log-partial likelihood at convergence.

- ...:

  Additional outputs returned by the underlying Rcpp function.

## Examples

``` r
# \donttest{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
train_dat_lowdim$time <- round(train_dat_lowdim$time, 2)  #make ties

fit <- cox(z = train_dat_lowdim$z,
           delta = train_dat_lowdim$status,
           time = train_dat_lowdim$time)
#> Warning: Stratum information not provided. All data is assumed to originate from a single stratum!

# Breslow method for tied data
fit_Breslow <- cox(z = train_dat_lowdim$z,
                   delta = train_dat_lowdim$status,
                   time = train_dat_lowdim$time,
                   ties = "breslow")
#> Warning: Stratum information not provided. All data is assumed to originate from a single stratum!
# }
```
