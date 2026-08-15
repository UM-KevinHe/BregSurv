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

  Matrix of test covariates. Optional; see Details.

- test_time:

  Vector of test survival times. Optional; see Details.

- test_delta:

  Vector of test status indicators. Optional; see Details.

- test_stratum:

  Vector of test strata. Optional; see Details.

- criteria:

  Metric to plot: `"loss"` or `"CIndex"`.

- ...:

  Additional arguments.

## Value

A `ggplot` object.

## Details

The four `test_*` arguments act as a single unit. The training data
stored in the fitted object are used for evaluation only when *all four*
of `test_z`, `test_time`, `test_delta` and `test_stratum` are `NULL`.
Supplying any one of them selects the external-test path, so leaving
`test_z` `NULL` while passing any of the others does not fall back to
the training data – it produces an error. The one exception is
`test_time`: on the external-test path, if it alone is omitted all test
times are set to 1.

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

plot(coxkl_enet_est,
     test_z = test_dat_highdim$z,
     test_time = test_dat_highdim$time,
     test_delta = test_dat_highdim$status,
     test_stratum = test_dat_highdim$stratum,
     criteria = "CIndex")
} # }
```
