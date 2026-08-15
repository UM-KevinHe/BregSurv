# Align an external coefficient vector to the internal covariate space

Reconciles an external coefficient vector `beta` with the covariates of
the internal design matrix `z`, so that external information supplied on
a subset (or a differently ordered set) of covariates is placed
correctly. When `beta` carries names, they are matched against
`colnames(z)` and any covariate absent from `beta` is filled with 0 (the
external source is treated as providing no information for that
covariate). When `beta` is unnamed (or `z` has no column names), it is
aligned positionally and must already have length `ncol(z)`.

Name-based alignment signals an error if `beta` has duplicated names, or
if any name in `beta` is not one of `colnames(z)` (covariates that exist
only in the external source must be dropped by the caller). Whenever at
least one covariate is zero-padded, a
[`message()`](https://rdrr.io/r/base/message.html) listing the padded
covariates is emitted.

## Usage

``` r
align_beta(z, beta, arg = "beta")
```

## Arguments

- z:

  Internal covariate matrix or data frame. Its columns define the target
  coefficient space; column names, when present, are used for matching.

- beta:

  External coefficient vector (optionally named). A one-column matrix is
  also accepted – the shape in which a
  [`coef()`](https://rdrr.io/r/stats/coef.html) result or a stored
  external-model artifact typically arrives – and its row names are
  promoted to the names of the resulting vector.

- arg:

  Name used for `beta` in error messages.

## Value

A numeric vector of length `ncol(z)`, ordered to `colnames(z)` and named
with `colnames(z)` whenever `z` carries column names.

## See also

[`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md)
for the Mahalanobis-distance setting.

## Examples

``` r
# Six internal covariates; the external source estimated only four of them.
z <- matrix(seq_len(30), nrow = 5, ncol = 6,
            dimnames = list(NULL, paste0("Z", 1:6)))
beta_ext <- c(Z1 = 0.30, Z3 = 0.25, Z5 = -0.10, Z6 = 0.05)

# Z2 and Z4 are absent from the external vector and are zero-padded.
align_beta(z, beta_ext)
#> 2 covariate(s) absent from external 'beta' were set to 0: Z2, Z4.
#>    Z1    Z2    Z3    Z4    Z5    Z6 
#>  0.30  0.00  0.25  0.00 -0.10  0.05 

# A one-column matrix is accepted; its row names are used as the names.
beta_mat <- matrix(c(0.30, 0.25, -0.10, 0.05), ncol = 1,
                   dimnames = list(c("Z1", "Z3", "Z5", "Z6"), "coef"))
align_beta(z, beta_mat)
#> 2 covariate(s) absent from external 'beta' were set to 0: Z2, Z4.
#>    Z1    Z2    Z3    Z4    Z5    Z6 
#>  0.30  0.00  0.25  0.00 -0.10  0.05 

# An unnamed beta is aligned positionally and must have length ncol(z).
align_beta(z, c(0.30, 0, 0.25, 0, -0.10, 0.05))
#>    Z1    Z2    Z3    Z4    Z5    Z6 
#>  0.30  0.00  0.25  0.00 -0.10  0.05 
```
