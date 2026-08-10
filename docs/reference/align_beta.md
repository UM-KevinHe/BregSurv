# Align an external coefficient vector to the internal covariate space

Reconciles an external coefficient vector `beta` with the covariates of
the internal design matrix `z`, so that external information supplied on
a subset (or a differently ordered set) of covariates is placed
correctly. When `beta` carries names, they are matched against
`colnames(z)` and any covariate absent from `beta` is filled with 0 (the
external source is treated as providing no information for that
covariate). When `beta` is unnamed (or `z` has no column names), it is
aligned positionally and must already have length `ncol(z)`.

## Usage

``` r
align_beta(z, beta, arg = "beta")
```

## Arguments

- z:

  Internal covariate matrix or data frame. Its columns define the target
  coefficient space; column names, when present, are used for matching.

- beta:

  External coefficient vector (optionally named).

- arg:

  Name used for `beta` in error messages.

## Value

A numeric vector of length `ncol(z)`, ordered to `colnames(z)`.

## See also

[`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md)
for the Mahalanobis-distance setting.
