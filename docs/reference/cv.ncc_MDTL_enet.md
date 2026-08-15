# Cross-Validated CLR with Mahalanobis Distance Transfer Learning and Elastic Net Penalty

Performs K-fold cross-validation (CV) to jointly select the integration
parameter `eta` and the Elastic Net penalty parameter `lambda` for
Conditional Logistic Regression with Mahalanobis distance transfer
learning and Elastic Net penalty, implemented via
[`ncc_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/ncc_MDTL_enet.md).

This function is designed for 1:m matched case-control settings where
each stratum (matched set) contains exactly one case and \\m\\ controls.

## Usage

``` r
cv.ncc_MDTL_enet(
  y,
  z,
  stratum,
  beta,
  Q = NULL,
  etas = NULL,
  alpha = NULL,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.05, 0.001),
  nfolds = 5,
  cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
  message = FALSE,
  seed = NULL,
  ...
)
```

## Arguments

- y:

  Numeric vector of binary outcomes (0 = control, 1 = case).

- z:

  Numeric matrix of covariates.

- stratum:

  Numeric or factor vector defining the matched sets. **Required**.

- beta:

  Numeric vector of external coefficients. **Required**. If `beta` is
  named, names are matched against `colnames(z)`: covariates absent from
  `beta` are set to 0 (with a message) and the vector is reordered, so
  an external source covering only a subset of the internal covariates
  may be supplied directly. An unnamed `beta` is aligned positionally
  and must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).
  The bundled fixture `ExampleData_cc_highdim$beta_external` is named
  `Z1`–`Z20` and therefore takes the name-matching path.

- Q:

  Optional weighting (precision) matrix for the Mahalanobis penalty.
  Must be symmetric and positive semi-definite (both checked to a
  tolerance of 1e-8). If named, it is reordered and zero-padded to
  `colnames(z)`; only an unnamed `Q` must be exactly `ncol(z)` by
  `ncol(z)`. If `NULL`, a *masked identity* is used: 1 on covariates
  actually supplied by `beta` and 0 on zero-padded positions, so padded
  coefficients are left unpenalized. See
  [`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md).

- etas:

  Numeric vector of non-negative integration weights for \\\eta\\.
  **Required**; the function stops if `etas` is `NULL`. Must be finite
  and \\\ge 0\\. The values are sorted in ascending order internally,
  and the rows of `integrated_stat.full_results` /
  `integrated_stat.best_per_eta` and the columns of
  `integrated_stat.betahat_best` follow that sorted order.

- alpha:

  Elastic Net mixing parameter in \\(0,1\]\\. Default `NULL` (set to 1
  with a warning if not supplied).

- lambda:

  Optional numeric vector of lambda values. If `NULL`, a lambda path is
  generated automatically for each `eta`.

- nlambda:

  Integer. Number of lambda values. Default `100`.

- lambda.min.ratio:

  Smallest lambda as a fraction of `lambda.max`. Defaults to
  `ifelse(nrow(z) < ncol(z), 0.05, 1e-3)`, i.e. `0.05` when there are
  fewer observations than covariates and `1e-3` otherwise. This default
  is supplied directly in the formal argument list, so passing `NULL`
  explicitly does *not* trigger it.

- nfolds:

  Number of cross-validation folds. Default `5`.

- cv.criteria:

  Character string specifying the CV performance criterion. One of
  `"loss"` (default), `"AUC"`, `"CIndex"`, or `"Brier"`.

- message:

  Logical. If `TRUE`, prints progress messages. Default `FALSE`.

- seed:

  Optional integer seed for reproducible fold assignment. Default
  `NULL`.

- ...:

  Additional arguments passed to
  [`ncc_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/ncc_MDTL_enet.md).

## Value

A list of class `"cv.ncc_MDTL_enet"` containing:

- `best`:

  A list with the global best \\(\eta, \lambda)\\: `best_eta`,
  `best_lambda`, `best_beta`, `criteria`.

- `integrated_stat.full_results`:

  A `data.frame` with the CV score for every \\(\eta, \lambda)\\
  combination.

- `integrated_stat.best_per_eta`:

  A `data.frame` with the best `lambda` and score for each `eta`.

- `integrated_stat.betahat_best`:

  Matrix of full-data coefficients at the best `lambda` for each `eta`.

- `criteria`:

  The CV criterion used.

- `alpha`:

  The Elastic Net mixing parameter.

- `nfolds`:

  The number of folds used.

## Details

Cross-validation is performed at the stratum level: each matched set is
treated as an indivisible unit and assigned to a single fold using
`get_fold_cc`.

For each candidate `eta`, a full `lambda` path is fit on the complete
data, and then K-fold CV is used to evaluate each `lambda` along this
path. The function performs a 2D search over \\(\eta, \lambda)\\.

The `cv.criteria` argument controls the CV performance metric:

- `"loss"`: Average negative conditional log-likelihood on held-out
  strata (lower is better).

- `"AUC"`: Matched-set AUC based on within-stratum comparisons (higher
  is better).

- `"CIndex"`: Alias for `"AUC"` in the 1:m matched setting.

- `"Brier"`: Conditional Brier score based on within-stratum softmax
  probabilities (lower is better).

## See also

[`ncc_MDTL_enet`](https://um-kevinhe.github.io/BregSurv/reference/ncc_MDTL_enet.md),
[`cv.ncckl_enet`](https://um-kevinhe.github.io/BregSurv/reference/cv.ncckl_enet.md)

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc_highdim)
train_cc <- ExampleData_cc_highdim$train

y        <- train_cc$y
z        <- train_cc$z
sets     <- train_cc$stratum
beta_ext <- ExampleData_cc_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 30, max_eta = 20)

cv_fit <- cv.ncc_MDTL_enet(
  y        = y,
  z        = z,
  stratum  = sets,
  beta     = beta_ext,
  Q        = NULL,
  etas     = eta_list,
  alpha    = 1,
  nfolds   = 5,
  cv.criteria = "loss",
  seed     = 42
)
cv_fit$best$best_eta
cv_fit$best$best_lambda
} # }
```
