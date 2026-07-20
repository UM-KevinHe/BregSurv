<div id="main" class="col-md-9" role="main">

# Example internal/external Cox individual-level data

<div class="ref-description section level2">

A simulated survival dataset for illustrating `cox_indi()` and
`cv.cox_indi()`. The object contains one internal cohort and one
external cohort, each stratified into multiple strata, along with the
true coefficient vector used in simulation.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
data(ExampleData_indi)
```

</div>

</div>

<div class="section level2">

## Format

A list containing:

-   internal:

    List with elements `z`, `time`, `status`, `stratum`.

-   external:

    List with elements `z`, `time`, `status`, `stratum`.

-   beta\_true:

    Numeric vector (length p) of true coefficients.

-   meta:

    List of simulation settings for internal and external cohorts.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
data(ExampleData_indi)
str(ExampleData_indi)
#> List of 2
#>  $ internal:List of 4
#>   ..$ z      : num [1:500, 1:10] 0.551 0.192 0.429 -0.86 0.278 ...
#>   .. ..- attr(*, "dimnames")=List of 2
#>   .. .. ..$ : NULL
#>   .. .. ..$ : chr [1:10] "Z1" "Z2" "Z3" "Z4" ...
#>   ..$ time   : num [1:500] 0.442 2.8 0.492 0.922 0.925 ...
#>   ..$ status : num [1:500] 1 0 1 1 0 1 1 1 0 0 ...
#>   ..$ stratum: int [1:500] 1 1 1 1 1 1 1 1 1 1 ...
#>  $ external:List of 4
#>   ..$ z      : num [1:2000, 1:10] 1.034 1.078 1.157 -1.373 -0.444 ...
#>   .. ..- attr(*, "dimnames")=List of 2
#>   .. .. ..$ : NULL
#>   .. .. ..$ : chr [1:10] "Z1" "Z2" "Z3" "Z4" ...
#>   ..$ time   : num [1:2000] 2.235 0.595 2.104 2.358 3.818 ...
#>   ..$ status : num [1:2000] 1 0 0 1 0 1 0 1 0 0 ...
#>   ..$ stratum: int [1:2000] 1 1 1 1 1 1 1 1 1 1 ...
```

</div>

</div>

</div>
