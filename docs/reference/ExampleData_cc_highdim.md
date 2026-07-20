<div id="main" class="col-md-9" role="main">

# Example high-dimensional matched case-control data

<div class="ref-description section level2">

A simulated 1:5 matched case-control dataset with 20 covariates, where
10 covariates are truly non-zero. The data are split into training and
test sets and include both the true underlying coefficients and an
externally supplied coefficient vector for KL-based integration.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
data(ExampleData_cc_highdim)
```

</div>

</div>

<div class="section level2">

## Format

A list containing:

-   train:

    List with elements `y`, `z`, and `stratum`.

-   test:

    Same structure as `train`.

-   beta\_true:

    Numeric vector (length 50) of true coefficients.

-   beta\_external:

    Numeric vector (length 50) representing external coefficients.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
data(ExampleData_cc_highdim)
```

</div>

</div>

</div>
