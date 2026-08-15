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

  Number of matched strata (sets). No default; integer \\\ge 1\\.

- m:

  Number of controls per case (\>=1). No default.

- beta:

  Numeric vector of coefficients (length p). No default; must be finite.

- rho:

  Correlation parameter for Z within stratum (equicorrelation). Default
  is 0.8; must lie in \\\[0, 1)\\.

- mu_Z:

  Mean vector for Z. Scalar or length p. Default is 0.

- sd_Z:

  Standard deviation vector for Z. Scalar or length p, must be positive.
  Default is 1.

- stratum_sd:

  SD of stratum random intercepts. Default is 0.5.

- seed:

  Optional RNG seed. Default `NULL`.

## Value

A list with five components:

- `data_combined`: a single `data.frame` with columns `stratum`, `y`,
  and covariates `Z1...Zp`, stacking all matched sets.

- `data`: a list containing `stratum`, `Z`, and `y`.

- `true_beta`: numeric vector of the coefficients used.

- `char`: a list of column-name metadata (`stratum`, `Z.char`,
  `Outcome.char`).

- `meta`: a list of simulation metadata including `n_stratum`, `m`,
  `set_size`, `theta_stratum`, `stratum_sd`, `rho`, `mu_Z`, `sd_Z`, and
  `case_prop`.
