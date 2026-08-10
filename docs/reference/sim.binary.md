# Simulate stratified binary outcomes

Internal function to simulate stratified binary data (logistic or
probit) with random intercepts and no prevalence calibration.

## Usage

``` r
sim.binary(
  n_stratum,
  beta,
  stratum.size.mean = 80,
  rho = 0.8,
  link = c("logit", "probit"),
  stratum_sd = 0.5,
  seed = NULL
)
```

## Arguments

- n_stratum:

  Number of strata.

- beta:

  Numeric vector of coefficients (length p).

- stratum.size.mean:

  Mean stratum size (Poisson distributed).

- rho:

  Correlation parameter for Z within stratum.

- link:

  Link function, one of "logit" or "probit".

- stratum_sd:

  Standard deviation of stratum random intercepts.

- seed:

  Optional RNG seed.

## Value

A list with combined data frame, data list, and metadata.
