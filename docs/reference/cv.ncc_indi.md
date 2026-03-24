# Cross-Validated CLR with Individual-Level External Data

Performs K-fold cross-validation (CV) to select the integration
parameter `eta` for Conditional Logistic Regression with
individual-level external data integration, implemented via
[`ncc_indi`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_indi.md).

This function is designed for 1:m matched case-control settings where
each stratum (matched set) contains exactly one case and \\m\\ controls.

## Usage

``` r
cv.ncc_indi(
  y_int,
  z_int,
  stratum_int,
  y_ext,
  z_ext,
  stratum_ext,
  etas = NULL,
  nfolds = 5,
  criteria = c("loss", "AUC", "CIndex", "Brier"),
  max_iter = 100,
  tol = 1e-07,
  message = FALSE,
  seed = NULL
)
```

## Arguments

- y_int:

  Numeric vector of binary outcomes for the internal dataset (0 =
  control, 1 = case).

- z_int:

  Numeric matrix of covariates for the internal dataset.

- stratum_int:

  Numeric or factor vector defining the internal matched sets.
  **Required**.

- y_ext:

  Numeric vector of binary outcomes for the external dataset (0 =
  control, 1 = case).

- z_ext:

  Numeric matrix of covariates for the external dataset.

- stratum_ext:

  Numeric or factor vector defining the external matched sets.
  **Required**.

- etas:

  Numeric vector of candidate tuning values for \\\eta\\. **Required**.

- nfolds:

  Number of cross-validation folds. Default `5`.

- criteria:

  Character string specifying the CV performance criterion. One of
  `"loss"` (default), `"AUC"`, `"CIndex"`, or `"Brier"`.

- max_iter:

  Maximum number of Newton-Raphson iterations passed to
  [`ncc_indi`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_indi.md).
  Default `100`.

- tol:

  Convergence tolerance passed to
  [`ncc_indi`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_indi.md).
  Default `1e-7`.

- message:

  Logical. If `TRUE`, prints progress messages. Default `FALSE`.

- seed:

  Optional integer seed for reproducible fold assignment. Default
  `NULL`.

## Value

A list of class `"cv.ncc_indi"` containing:

- `internal_stat`:

  A `data.frame` with one row per `eta` and the CV metric for the chosen
  `criteria`.

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

Cross-validation is performed at the stratum level on the *internal*
dataset: each matched set is treated as an indivisible unit and assigned
to a single fold using `get_fold_cc`. The external dataset is used in
full during every training fold.

The `criteria` argument controls the CV performance metric:

- `"loss"`: Average negative conditional log-likelihood on held-out
  strata.

- `"AUC"`: Matched-set AUC based on within-stratum comparisons.

- `"CIndex"`: Alias for `"AUC"` in the 1:m matched setting.

- `"Brier"`: Conditional Brier score based on within-stratum softmax
  probabilities.

## See also

[`ncc_indi`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_indi.md),
[`cv.ncckl`](https://um-kevinhe.github.io/SurvBregDiv/reference/cv.ncckl.md)
