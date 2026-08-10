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

  Number of subjects in the internal training set.

- n_test:

  Number of subjects in the internal test set.

- n_ext:

  Number of subjects in the external dataset.

- beta_true:

  True regression coefficients.

- int_cens_target:

  Target censoring rate for internal data.

- ext_cens_target:

  Target censoring rate for external data.

- lambda0, nu0:

  Weibull baseline hazard parameters.

- heterogeneity:

  Numeric. Controls the mixture difference between cohorts.

- seed:

  Random seed.

## Value

A list containing `external`, `internal_train`, and `internal_test`
datasets.
