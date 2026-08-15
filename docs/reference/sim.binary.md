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

  Number of strata. No default.

- beta:

  Numeric vector of coefficients (length p). No default; must be finite.

- stratum.size.mean:

  Mean stratum size (Poisson distributed). Default is 80.

- rho:

  Covariance parameter for Z within stratum. Default is 0.8. See Details
  – `rho` is *not* the resulting correlation.

- link:

  Link function, one of "logit" or "probit". Default is "logit".

- stratum_sd:

  Standard deviation of stratum random intercepts. Default is 0.5.

- seed:

  Optional RNG seed. Default `NULL`.

## Value

A list with five components:

- `data_combined`: a `data.frame` with columns `stratum`, `y`, and
  covariates `Z1...Zp`.

- `data`: a list containing `stratum`, `Z`, and `y`.

- `true_beta`: numeric vector of the coefficients used.

- `char`: a list of column-name metadata (`stratum`, `Z.char`,
  `Outcome.char`).

- `meta`: a list of simulation metadata including `n_stratum`,
  `stratum_size`, `theta_stratum`, `link`, `alpha0`, `stratum_sd`,
  `rho`, and the achieved prevalence `actual_prev`.

## Details

**`rho` is not the correlation of `Z`.** The within-stratum covariance
is built as `diag(1 - rho, p) + (rho - rho^2) * matrix(1, p, p)`, whose
diagonal is \\1-\rho^2\\ and whose off-diagonal is \\\rho(1-\rho)\\. The
implied correlation is therefore \\\rho/(1+\rho)\\, not \\\rho\\: at the
default `rho = 0.8` the actual correlation is \\0.444\\ and the variance
of each covariate is \\0.36\\.

**Covariates are confounded with the stratum effect by construction.**
The mean of `Z` within stratum \\i\\ is set to \\(\theta_i \rho /
0.4)\mathbf{1}\\, a function of that stratum's random intercept
\\\theta_i\\. Covariates and stratum effects are thus deliberately
dependent, which is the intended design for testing stratified
estimators; it is not a neutral covariate-generating mechanism.
