# Align an external coefficient vector and weighting matrix for MDTL

Extends
[`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md)
to the Mahalanobis-distance transfer-learning (MDTL) setting, where the
external information is a coefficient vector `beta` together with a
symmetric positive-semidefinite weighting (precision) matrix `Q`. `beta`
is aligned to `colnames(z)` exactly as in
[`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
`Q`, when supplied, is checked for symmetry and
positive-semidefiniteness and, if named, reordered and zero-padded to
the same covariate space; rows and columns for covariates the external
source did not estimate are set to 0 so those coordinates are left
unpenalized. When `Q` is `NULL`, a *masked identity* is returned: a
diagonal matrix with 1 on covariates actually supplied by `beta` and 0
on padded positions. This ensures that padded-zero coefficients are not
penalized as if they were genuine external information.

## Usage

``` r
align_beta_Q(z, beta, Q = NULL, arg_beta = "beta", arg_Q = "Q")
```

## Arguments

- z:

  Internal covariate matrix or data frame.

- beta:

  External coefficient vector (optionally named).

- Q:

  Optional weighting/precision matrix (optionally with dimnames). If
  `NULL`, a masked identity is used.

- arg_beta, arg_Q:

  Names used for `beta` and `Q` in error messages.

## Value

A list with components `beta` (numeric, length `ncol(z)`), `Q`
(`ncol(z)` by `ncol(z)` matrix), and `provided` (logical mask of
covariates supplied by the external source).

## See also

[`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md)
