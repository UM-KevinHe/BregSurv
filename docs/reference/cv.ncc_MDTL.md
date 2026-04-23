# Cross-Validated CLR with Mahalanobis Distance Transfer Learning

Performs K-fold cross-validation (CV) to select the integration
parameter `eta` for Conditional Logistic Regression with Mahalanobis
distance transfer learning, implemented via
[`ncc_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL.md).

This function is designed for 1:m matched case-control settings where
each stratum (matched set) contains exactly one case and \\m\\ controls.

## Usage

``` r
cv.ncc_MDTL(
  y,
  z,
  stratum,
  beta,
  vcov = NULL,
  etas = NULL,
  tol = 1e-04,
  Mstop = 100,
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
  matrix \\Q\\. Typically the precision matrix of the external
  estimator. If `NULL`, defaults to the identity matrix.

- etas:

  Numeric vector of candidate tuning values for \\\eta\\. **Required**.

- tol:

  Convergence tolerance passed to
  [`ncc_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL.md).
  Default `1e-4`.

- Mstop:

  Maximum Newton-Raphson iterations passed to
  [`ncc_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL.md).
  Default `100`.

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
  [`ncc_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL.md).

## Value

A list of class `"cv.ncc_MDTL"` containing:

- `internal_stat`:

  A `data.frame` with one row per `eta` and the CV metric for the chosen
  `cv.criteria`.

- `beta_full`:

  Matrix of coefficients from the full-data fit (columns correspond to
  `etas`).

- `best`:

  A list with `best_eta`, `best_beta`, and `criteria`.

- `criteria`:

  The criterion used for selection.

- `nfolds`:

  The number of folds used.

## Details

Cross-validation is performed at the stratum level: each matched set is
treated as an indivisible unit and assigned to a single fold using
`get_fold_cc`. This ensures that the conditional likelihood is
well-defined within each training and test split.

The `cv.criteria` argument controls the CV performance metric:

- `"loss"`: Average negative conditional log-likelihood on held-out
  strata (lower is better).

- `"AUC"`: Matched-set AUC based on within-stratum comparisons (higher
  is better).

- `"CIndex"`: Alias for `"AUC"` in the 1:m matched setting.

- `"Brier"`: Conditional Brier score based on within-stratum softmax
  probabilities (lower is better).

## See also

[`ncc_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_MDTL.md),
[`cv.ncckl`](https://um-kevinhe.github.io/SurvBregDiv/reference/cv.ncckl.md)

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc)
train_cc <- ExampleData_cc$train

y        <- train_cc$y
z        <- train_cc$z
sets     <- train_cc$stratum
beta_ext <- ExampleData_cc$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

cv_fit <- cv.ncc_MDTL(
  y        = y,
  z        = z,
  stratum  = sets,
  beta     = beta_ext,
  vcov     = NULL,
  etas     = eta_list,
  nfolds   = 5,
  cv.criteria = "loss",
  seed     = 42
)
cv_fit$best$best_eta
} # }
```
