# Example high-dimensional matched case-control data

A simulated 1:9 matched case-control dataset with 20 covariates, where
10 covariates are truly non-zero. Each matched set contains ten subjects
(one case and nine controls): the training set has 50 matched sets (\\n
= 500\\) and the test set has 500 matched sets (\\n = 5000\\). The data
include both the true underlying coefficients and an externally supplied
coefficient vector for KL-based integration.

## Usage

``` r
data(ExampleData_cc_highdim)
```

## Format

A list containing:

- train:

  List with elements `y`, `z`, `stratum`, and `beta_true` (numeric,
  length 20, named `Z1`–`Z20`).

- test:

  Same structure as `train`.

- beta_external:

  Numeric vector (length 20; named `Z1`–`Z20`) representing external
  coefficients.

## Details

**External coefficients: name present-and-zero vs. name absent.**
`beta_external` is fully populated and fully named over `Z1`–`Z20`, so
[`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md)
never zero-pads it and
[`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md)
with `Q = NULL` returns the full identity rather than a masked identity.
In general, a covariate whose name is *present* with value 0 asserts an
external estimate of exactly zero and is penalized toward zero, whereas
a covariate whose name is *absent* is treated as carrying no external
information – it is zero-padded and, under the Mahalanobis penalty, left
unpenalized.

## Examples

``` r
data(ExampleData_cc_highdim)
```
