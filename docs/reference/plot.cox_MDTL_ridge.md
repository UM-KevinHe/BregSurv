# Plot Validation Results for cox_MDTL_ridge Object

Plots the validation performance against `lambda` for MDTL ridge
estimates.

## Usage

``` r
# S3 method for class 'cox_MDTL_ridge'
plot(
  x,
  test_z = NULL,
  test_time = NULL,
  test_delta = NULL,
  test_stratum = NULL,
  criteria = c("loss", "CIndex"),
  ...
)
```

## Arguments

- x:

  An object of class `"cox_MDTL_ridge"`.

- test_z:

  Matrix of test covariates.

- test_time:

  Vector of test survival times.

- test_delta:

  Vector of test status indicators.

- test_stratum:

  Vector of test strata.

- criteria:

  Metric to plot: `"loss"` or `"CIndex"`.

- ...:

  Additional arguments.

## Value

A `ggplot` object.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
test_dat_highdim <- ExampleData_highdim$test
beta_external_highdim <- ExampleData_highdim$beta_external

mdtl_ridge_est <- cox_MDTL_ridge(z = train_dat_highdim$z,
                                 delta = train_dat_highdim$status,
                                 time = train_dat_highdim$time,
                                 beta = beta_external_highdim,
                                 Q = NULL,
                                 eta = 0)

plot.cox_MDTL_ridge(mdtl_ridge_est,
                    test_z = test_dat_highdim$z,
                    test_time = test_dat_highdim$time,
                    test_delta = test_dat_highdim$status,
                    criteria = "CIndex")
} # }
```
