# Example internal/external matched case-control individual-level data

A simulated 1:4 matched case-control dataset for illustrating
[`ncc_indi`](https://um-kevinhe.github.io/BregSurv/reference/ncc_indi.md)
and
[`cv.ncc_indi`](https://um-kevinhe.github.io/BregSurv/reference/cv.ncc_indi.md).
The object contains both an internal cohort and an external cohort in
case-control form, so that the external cohort can be used as
individual-level external information when fitting the conditional
logistic regression model with external integration.

This is the individual-level analog of
[`ExampleData_cc_lowdim`](https://um-kevinhe.github.io/BregSurv/reference/ExampleData_cc_lowdim.md):
rather than supplying `beta_external` only, the external cohort is
provided in full (subject-level matched-set data).

## Usage

``` r
data(ExampleData_cc_indi)
```

## Format

A list containing two cohorts:

- internal:

  A list with components for the internal matched case-control study:

  z

  :   Numeric matrix of covariates of dimension \\1000\times 6\\ with
      columns named `Z1`–`Z6`.

  y

  :   Integer vector of binary outcomes (`1`=case, `0`=control).

  stratum

  :   Integer vector identifying the matched set for each observation
      (200 unique strata, exactly one case and four controls per set).

- external:

  A list with the same component names as `internal`, containing 500
  matched sets (\\n = 2500\\) with the same 1:4 matching design,
  intended to be passed as the external cohort to
  [`ncc_indi`](https://um-kevinhe.github.io/BregSurv/reference/ncc_indi.md).

## Details

Both the internal and external cohorts are 1:4 matched case-control
studies on six covariates `Z1`–`Z6`. The matching design (one case and
four controls per stratum) is preserved in both cohorts, which is
required by
[`ncc_indi`](https://um-kevinhe.github.io/BregSurv/reference/ncc_indi.md)
and the stratum-level fold construction in
[`cv.ncc_indi`](https://um-kevinhe.github.io/BregSurv/reference/cv.ncc_indi.md).

## Examples

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
