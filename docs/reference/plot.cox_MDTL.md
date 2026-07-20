<div id="main" class="col-md-9" role="main">

# Plot Validation Results for Cox\_MDTL Object

<div class="ref-description section level2">

Plots the validation performance against `eta` for MDTL estimates.
Compares the "Integrated" estimator (solid line) against the "Internal"
baseline (dotted line, eta=0).

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

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

</div>

</div>

<div class="section level2">

## Arguments

-   x:

    An object of class `"Cox_MDTL"`.

-   test\_z:

    Matrix of test covariates.

-   test\_time:

    Vector of test survival times.

-   test\_delta:

    Vector of test status indicators.

-   test\_stratum:

    Vector of test strata.

-   criteria:

    Metric to plot: `"loss"` or `"CIndex"`.

-   ...:

    Additional arguments.

</div>

<div class="section level2">

## Value

A `ggplot` object.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

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
                         vcov = NULL,
                         etas = eta_list)

plot.cox_MDTL(cox_MDTL_est,
              test_z = test_dat_lowdim$z,
              test_time = test_dat_lowdim$time,
              test_delta = test_dat_lowdim$status,
              test_stratum = test_dat_lowdim$stratum,
              criteria = "CIndex")
} # }
```

</div>

</div>

</div>
