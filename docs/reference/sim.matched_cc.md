# Simulate 1:m matched case-control data with mean/SD control

Internal function to simulate 1:m matched data. Each stratum contains
exactly one case. The case is sampled with probability proportional to
exp(eta), where eta = theta_stratum + Z %\*% beta.

## Usage

``` r
sim.matched_cc(
  n_stratum,
  m,
  beta,
  rho = 0.8,
  mu_Z = 0,
  sd_Z = 1,
  stratum_sd = 0.5,
  seed = NULL
)
```

## Arguments

- n_stratum:

  Number of matched strata (sets).

- m:

  Number of controls per case (\>=1).

- beta:

  Numeric vector of coefficients (length p).

- rho:

  Correlation parameter for Z within stratum (equicorrelation).

- mu_Z:

  Mean vector for Z. Scalar or length p.

- sd_Z:

  Standard deviation vector for Z. Scalar or length p, must be positive.

- stratum_sd:

  SD of stratum random intercepts.

- seed:

  Optional RNG seed.

## Value

A list containing matched data frames and simulation metadata.
