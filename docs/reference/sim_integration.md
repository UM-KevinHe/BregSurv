# Simulate Low-Dimensional Survival Data for Integration

Internal function. Generates simulated low-dimensional survival datasets
for internal (training/testing) and external cohorts with varying
heterogeneity levels via latent groups.

## Usage

``` r
sim_integration(
  n_int = 200,
  n_test = 1000,
  n_ext = 1000,
  beta_true = c(0.3, -0.3, 0.3, -0.3, 0.3, -0.3),
  int_cens_target = 0.3,
  ext_cens_target = 0.5,
  lambda0 = 1,
  nu0 = 2,
  heterogeneity = 1,
  seed = NULL
)
```

## Arguments

- n_int:

  Number of subjects in the internal training set. Default is 200.

- n_test:

  Number of subjects in the internal test set. Default is 1000.

- n_ext:

  Number of subjects in the external dataset. Default is 1000.

- beta_true:

  True regression coefficients. **Must have length 6.** The simulator
  names the vector `Z1`–`Z6` unconditionally and its internal generator
  hard-codes exactly six covariates, so any other length fails with
  `"'names' attribute [6] must be the same length as the vector"`.
  Default is `c(0.3, -0.3, 0.3, -0.3, 0.3, -0.3)`.

- int_cens_target:

  Target censoring rate for internal data. Default is 0.3.

- ext_cens_target:

  Target censoring rate for external data. Default is 0.5.

- lambda0, nu0:

  Weibull baseline hazard parameters. Defaults are 1 and 2.

- heterogeneity:

  Numeric in \\\[0, 1\]\\, used as a Bernoulli probability. Default is
  1.0. **Note the direction, which is the opposite of what the name
  suggests:** the internal cohorts are always generated with probability
  1.0, so `heterogeneity = 1.0` makes the external cohort
  distributionally *identical* to the internal ones – that is, the
  default corresponds to *zero* heterogeneity. *Smaller* values produce
  *more* divergence between the external and internal cohorts, with
  `heterogeneity = 0` the most divergent. Values outside \\\[0, 1\]\\
  are invalid (they are passed straight to `rbinom`) but are not
  validated.

- seed:

  Random seed. Default `NULL`.

## Value

A list containing `external`, `internal_train`, and `internal_test`
datasets.
