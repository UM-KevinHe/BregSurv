# Cross-Validated CLR with Mahalanobis Distance Transfer Learning and Elastic Net Penalty

Performs K-fold cross-validation (CV) to jointly select the integration
parameter `eta` and the Elastic Net penalty parameter `lambda` for
Conditional Logistic Regression with Mahalanobis distance transfer
learning and Elastic Net penalty, implemented via
[`ncc_MDTL_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL_enet.md).

This function is designed for 1:m matched case-control settings where
each stratum (matched set) contains exactly one case and \\m\\ controls.

## Usage

``` r
cv.ncc_MDTL_enet(
  y,
  z,
  stratum,
  beta,
  vcov = NULL,
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

  Numeric vector of external coefficients (length `ncol(z)`).
  **Required**.

- vcov:

  Optional numeric matrix (`ncol(z)` x `ncol(z)`) as the weighting
  matrix \\Q\\. If `NULL`, defaults to the identity matrix.

- etas:

  Numeric vector of candidate tuning values for \\\eta\\. **Required**.

- alpha:

  Elastic Net mixing parameter in \\(0,1\]\\. Default `NULL` (set to 1
  with a warning if not supplied).

- lambda:

  Optional numeric vector of lambda values. If `NULL`, a lambda path is
  generated automatically for each `eta`.

- nlambda:

  Integer. Number of lambda values. Default `100`.

- lambda.min.ratio:

  Smallest lambda as a fraction of `lambda.max`. Default depends on
  sample size relative to number of covariates.

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
  [`ncc_MDTL_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL_enet.md).

## Value

A list of class `"cv.ncc_MDTL_enet"` containing:

- `best`:

  A list with the global best \\(\eta, \lambda)\\: `best_eta`,
  `best_lambda`, `best_beta`, `cv.criteria`.

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

[`ncc_MDTL_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL_enet.md),
[`cv.ncckl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/cv.ncckl_enet.md)

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
  vcov     = NULL,
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
