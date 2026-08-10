# Plot Validation Results for coxkl Object

Plots the validation performance (Loss or C-Index) against the tuning
parameter `eta`. Compares the "Integrated" estimator (solid line)
against the "Internal" baseline (dotted line, eta=0).

## Usage

``` r
# S3 method for class 'coxkl'
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

  An object of class `"coxkl"`.

- test_z:

  Matrix of test covariates. If NULL, training data is used.

- test_time:

  Vector of test survival times.

- test_delta:

  Vector of test status indicators.

- test_stratum:

  Vector of test strata (optional).

- criteria:

  Metric to plot: `"loss"` or `"CIndex"`.

- ...:

  Additional arguments.

## Value

A `ggplot` object.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
test_dat_lowdim <- ExampleData_lowdim$test
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
coxkl_est <- coxkl(z = train_dat_lowdim$z,
                   delta = train_dat_lowdim$status,
                   time = train_dat_lowdim$time,
                   stratum = train_dat_lowdim$stratum,
                   beta = beta_external_lowdim,
                   etas = eta_list)

plot.coxkl(coxkl_est,
           test_z = test_dat_lowdim$z,
           test_time = test_dat_lowdim$time,
           test_delta = test_dat_lowdim$status,
           test_stratum = test_dat_lowdim$stratum,
           criteria = "CIndex")
} # }
```
