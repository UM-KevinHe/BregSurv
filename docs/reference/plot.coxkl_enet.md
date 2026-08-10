# Plot Validation Results for coxkl_enet Object

Plots the validation performance against the penalty parameter `lambda`
(on log scale). The optimal lambda is marked with a dashed orange line.

## Usage

``` r
# S3 method for class 'coxkl_enet'
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

  An object of class `"coxkl_enet"`.

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

coxkl_enet_est <- coxkl_enet(z = train_dat_highdim$z,
                             delta = train_dat_highdim$status,
                             time = train_dat_highdim$time,
                             stratum = train_dat_highdim$stratum,
                             beta = beta_external_highdim,
                             eta = 0)

plot.coxkl_enet(coxkl_enet_est,
                test_z = test_dat_highdim$z,
                test_time = test_dat_highdim$time,
                test_delta = test_dat_highdim$status,
                test_stratum = test_dat_highdim$stratum,
                criteria = "CIndex")
} # }
```
