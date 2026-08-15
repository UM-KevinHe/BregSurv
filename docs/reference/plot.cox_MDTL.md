# Plot Validation Results for cox_MDTL Object

Plots the validation performance against `eta` for MDTL estimates.
Compares the "Integrated" estimator (solid line) against the "Internal"
baseline (dotted line, eta=0).

## Usage

``` r
# S3 method for class 'cox_MDTL'
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

  An object of class `"cox_MDTL"`.

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
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
test_dat_lowdim <- ExampleData_lowdim$test
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 5)
cox_MDTL_est <- cox_MDTL(z = train_dat_lowdim$z,
                         delta = train_dat_lowdim$status,
                         time = train_dat_lowdim$time,
                         beta = beta_external_lowdim,
                         Q = NULL,
                         etas = eta_list)

plot(cox_MDTL_est,
     test_z = test_dat_lowdim$z,
     test_time = test_dat_lowdim$time,
     test_delta = test_dat_lowdim$status,
     test_stratum = test_dat_lowdim$stratum,
     criteria = "CIndex")
} # }
```
