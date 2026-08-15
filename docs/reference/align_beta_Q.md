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

Symmetry of `Q` is checked with
[`isSymmetric()`](https://rdrr.io/r/base/isSymmetric.html) at tolerance
`1e-8`, and positive semi-definiteness by requiring the smallest
eigenvalue to be at least `-1e-8`; violations of either are errors.
Name-based alignment of `Q` engages only when `rownames(Q)` is
non-`NULL` *and* `z` has column names; otherwise `Q` is used
positionally and must be exactly `ncol(z)` by `ncol(z)`. Name-based
alignment signals an error if `rownames(Q)` contains duplicates, if any
of them is not one of `colnames(z)`, or if `colnames(Q)` is present but
does not contain the same names as `rownames(Q)`.

## Usage

``` r
align_beta_Q(z, beta, Q = NULL, arg_beta = "beta", arg_Q = "Q")
```

## Arguments

- z:

  Internal covariate matrix or data frame.

- beta:

  External coefficient vector (optionally named). A one-column matrix
  with row names is accepted as a named vector; see
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).

- Q:

  Optional weighting/precision matrix (optionally with dimnames). If
  `NULL`, a masked identity is used.

- arg_beta, arg_Q:

  Names used for `beta` and `Q` in error messages.

## Value

A list with components `beta` (numeric, length `ncol(z)`), `Q`
(`ncol(z)` by `ncol(z)` matrix, carrying `colnames(z)` as both its row
and column names whenever `z` has column names), and `provided` (logical
mask of covariates supplied by the external source).

## See also

[`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md)

## Examples

``` r
z <- matrix(seq_len(30), nrow = 5, ncol = 6,
            dimnames = list(NULL, paste0("Z", 1:6)))
beta_ext <- c(Z1 = 0.30, Z3 = 0.25, Z5 = -0.10, Z6 = 0.05)

# Q = NULL gives the masked identity: 1 on the covariates the external source
# supplied, 0 on the zero-padded ones (Z2, Z4), which are left unpenalized.
aligned <- align_beta_Q(z, beta_ext)
#> 2 covariate(s) absent from external 'beta' were set to 0: Z2, Z4.
aligned$beta
#>    Z1    Z2    Z3    Z4    Z5    Z6 
#>  0.30  0.00  0.25  0.00 -0.10  0.05 
diag(aligned$Q)
#> Z1 Z2 Z3 Z4 Z5 Z6 
#>  1  0  1  0  1  1 
aligned$provided
#> [1]  TRUE FALSE  TRUE FALSE  TRUE  TRUE

# A named information matrix is reordered and zero-padded to colnames(z).
Q_ext <- diag(c(4, 2, 1, 3))
dimnames(Q_ext) <- list(names(beta_ext), names(beta_ext))
align_beta_Q(z, beta_ext, Q = Q_ext)$Q
#> 2 covariate(s) absent from external 'beta' were set to 0: Z2, Z4.
#>    Z1 Z2 Z3 Z4 Z5 Z6
#> Z1  4  0  0  0  0  0
#> Z2  0  0  0  0  0  0
#> Z3  0  0  2  0  0  0
#> Z4  0  0  0  0  0  0
#> Z5  0  0  0  0  1  0
#> Z6  0  0  0  0  0  3
```
