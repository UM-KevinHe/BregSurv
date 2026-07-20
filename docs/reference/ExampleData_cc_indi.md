<div id="main" class="col-md-9" role="main">

# Example internal/external matched case-control individual-level data

<div class="ref-description section level2">

A simulated 1:4 matched case-control dataset for illustrating `ncc_indi`
and `cv.ncc_indi`. The object contains both an internal cohort and an
external cohort in case-control form, so that the external cohort can be
used as individual-level external information when fitting the
conditional logistic regression model with external integration.

This is the individual-level analog of `ExampleData_cc_lowdim`: rather
than supplying `beta_external` only, the external cohort is provided in
full (subject-level matched-set data).

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
data(ExampleData_cc_indi)
```

</div>

</div>

<div class="section level2">

## Format

A list containing two cohorts:

-   internal:

    A list with components for the internal matched case-control study:

    z

    :   Numeric matrix of covariates of dimension \\(1000\\times 6\\)
        with columns named `Z1`–`Z6`.

    y

    :   Integer vector of binary outcomes (`1`=case, `0`=control).

    stratum

    :   Integer vector identifying the matched set for each observation
        (200 unique strata, exactly one case and four controls per set).

-   external:

    A list with the same component names as `internal`, containing 500
    matched sets (\\(n = 2500\\)) with the same 1:4 matching design,
    intended to be passed as the external cohort to `ncc_indi`.

</div>

<div class="section level2">

## Details

Both the internal and external cohorts are 1:4 matched case-control
studies on six covariates `Z1`–`Z6`. The matching design (one case and
four controls per stratum) is preserved in both cohorts, which is
required by `ncc_indi` and the stratum-level fold construction in
`cv.ncc_indi`.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
data(ExampleData_cc_indi)
str(ExampleData_cc_indi, max.level = 2)
#> List of 2
#>  $ internal:List of 3
#>   ..$ z      : num [1:1000, 1:6] 1.4209 1.8271 1.2201 -0.0173 1.0239 ...
#>   .. ..- attr(*, "dimnames")=List of 2
#>   ..$ y      : int [1:1000] 0 1 0 0 0 0 0 1 0 0 ...
#>   ..$ stratum: int [1:1000] 1 1 1 1 1 2 2 2 2 2 ...
#>  $ external:List of 3
#>   ..$ z      : num [1:2500, 1:6] -1.523 0.711 -0.674 -0.956 -0.805 ...
#>   .. ..- attr(*, "dimnames")=List of 2
#>   ..$ y      : int [1:2500] 0 0 0 1 0 0 0 0 0 1 ...
#>   ..$ stratum: int [1:2500] 1 1 1 1 1 2 2 2 2 2 ...
```

</div>

</div>

</div>
