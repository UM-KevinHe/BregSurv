# Example high-dimensional matched case-control data

A simulated 1:5 matched case-control dataset with 20 covariates, where
10 covariates are truly non-zero. The data are split into training and
test sets and include both the true underlying coefficients and an
externally supplied coefficient vector for KL-based integration.

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

## Examples

``` r
data(ExampleData_cc_highdim)
```
