<div id="main" class="col-md-9" role="main">

# Plot Validation Results for cox\_MDTL\_ridge Object

<div class="ref-description section level2">

Plots the validation performance against `lambda` for MDTL ridge
estimates.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

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

</div>

</div>

<div class="section level2">

## Arguments

-   x:

    An object of class `"cox_MDTL_ridge"`.

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
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
test_dat_highdim <- ExampleData_highdim$test
beta_external_highdim <- ExampleData_highdim$beta_external

mdtl_ridge_est <- cox_MDTL_ridge(z = train_dat_highdim$z,
                                 delta = train_dat_highdim$status,
                                 time = train_dat_highdim$time,
                                 beta = beta_external_highdim,
                                 vcov = NULL,
                                 eta = 0)

plot.cox_MDTL_ridge(mdtl_ridge_est,
                    test_z = test_dat_highdim$z,
                    test_time = test_dat_highdim$time,
                    test_delta = test_dat_highdim$status,
                    criteria = "CIndex")
} # }
```

</div>

</div>

</div>
