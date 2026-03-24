# Cross-Validated CLR with Individual-Level External Data and Elastic Net Penalty

Performs K-fold cross-validation (CV) to jointly select the integration
parameter `eta` and the Elastic Net penalty parameter `lambda` for
Conditional Logistic Regression with individual-level external data
integration and Elastic Net penalty, implemented via
[`ncc_indi_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_indi_enet.md).

This function is designed for 1:m matched case-control settings where
each stratum (matched set) contains exactly one case and \\m\\ controls.

## Usage

``` r
cv.ncc_indi_enet(
  y_int,
  z_int,
  stratum_int,
  y_ext,
  z_ext,
  stratum_ext,
  etas = NULL,
  alpha = 1,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = NULL,
  nfolds = 5,
  criteria = c("loss", "AUC", "CIndex", "Brier"),
  message = FALSE,
  seed = NULL,
  ...
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

- alpha:

  Elastic Net mixing parameter in \\(0,1\]\\. Default `1` (Lasso).

- lambda:

  Optional numeric vector of lambda values. If `NULL`, a lambda path is
  generated automatically for each `eta`.

- nlambda:

  Integer. Number of lambda values to generate. Default `100`.

- lambda.min.ratio:

  Numeric in \\(0,1)\\. Ratio of minimum to maximum lambda. If `NULL`,
  set internally based on sample size vs. number of covariates.

- nfolds:

  Number of cross-validation folds. Default `5`.

- criteria:

  Character string specifying the CV performance criterion. One of
  `"loss"` (default), `"AUC"`, `"CIndex"`, or `"Brier"`.

- message:

  Logical. If `TRUE`, prints progress messages. Default `FALSE`.

- seed:

  Optional integer seed for reproducible fold assignment. Default
  `NULL`.

- ...:

  Additional arguments passed to
  [`ncc_indi_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_indi_enet.md).

## Value

A list of class `"cv.ncc_indi_enet"` containing:

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

Cross-validation is performed at the stratum level on the *internal*
dataset: each matched set is treated as an indivisible unit and assigned
to a single fold using `get_fold_cc`. The external dataset is used in
full during every training fold.

For each candidate `eta`, a full `lambda` path is fit on the complete
internal + external data, and then K-fold CV is used to evaluate each
`lambda` along this path. The function performs a 2D search over
\\(\eta, \lambda)\\.

The `criteria` argument controls the CV performance metric:

- `"loss"`: Average negative conditional log-likelihood on held-out
  strata (lower is better).

- `"AUC"`: Matched-set AUC based on within-stratum comparisons (higher
  is better).

- `"CIndex"`: Alias for `"AUC"` in the 1:m matched setting.

- `"Brier"`: Conditional Brier score based on within-stratum softmax
  probabilities (lower is better).

## See also

[`ncc_indi_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncc_indi_enet.md),
[`cv.ncckl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/cv.ncckl_enet.md)
