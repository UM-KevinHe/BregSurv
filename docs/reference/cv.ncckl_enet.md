# Cross-Validated CLR-KL with Elastic Net Penalty

Performs K-fold cross-validation (CV) to jointly select the integration
parameter `eta` and the Elastic Net penalty parameter `lambda` for
Conditional Logistic Regression with Kullback–Leibler (KL) divergence
and Elastic Net penalty, implemented via
[`ncckl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncckl_enet.md).

This function is designed for 1:m matched case–control settings where
each stratum (matched set) contains exactly one case and \\m\\ controls.

## Usage

``` r
cv.ncckl_enet(
  y,
  z,
  stratum,
  RS = NULL,
  beta = NULL,
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

- y:

  Numeric vector of binary outcomes (0 = control, 1 = case). In the 1:m
  matched case–control setting, each stratum must contain exactly one
  case.

- z:

  Numeric matrix of covariates (rows = observations, columns =
  variables).

- stratum:

  Numeric or factor vector defining the matched sets (strata). Each
  unique value identifies one matched set.

- RS:

  Optional numeric vector or matrix of external risk scores. If not
  provided, `beta` must be supplied.

- beta:

  Optional numeric vector of external coefficients. If provided, length
  must equal the number of columns in `z`. Either `RS` or `beta` must be
  non-`NULL`.

- etas:

  Numeric vector of candidate tuning values for the integration
  parameter \\\eta\\. The values will be sorted in ascending order.

- alpha:

  Elastic Net mixing parameter in \\(0,1\]\\. Default is `1` (lasso
  penalty).

- lambda:

  Optional numeric vector of lambda values. If `NULL`, a lambda path is
  generated automatically for each `eta`.

- nlambda:

  Integer. Number of lambda values to generate when `lambda` is `NULL`.
  Default `100`.

- lambda.min.ratio:

  Numeric in \\(0,1)\\. Ratio of minimum to maximum lambda when `lambda`
  is `NULL`. If `NULL`, it is set internally to `0.05` when `n < p`, and
  `1e-3` otherwise.

- nfolds:

  Number of cross-validation folds. Default `5`.

- criteria:

  Character string specifying the CV performance criterion. Choices are:

  - `"loss"`: Average negative conditional log-likelihood (lower is
    better).

  - `"AUC"`: Matched-set AUC based on within-stratum comparisons (higher
    is better).

  - `"CIndex"`: Concordance index in the matched-set setting,
    implemented via the same matched-set AUC calculation as `"AUC"`
    (higher is better).

  - `"Brier"`: Conditional Brier score using within-stratum softmax
    probabilities (lower is better).

  Default is `"loss"`.

- message:

  Logical; if `TRUE`, prints progress messages. Default `FALSE`.

- seed:

  Optional integer seed for reproducible fold assignment. Default
  `NULL`.

- ...:

  Additional arguments passed to
  [`ncckl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncckl_enet.md).

## Value

A `list` of class `"cv.ncckl_enet"` containing:

- `best`:

  A list with the global best \\(\eta, \lambda)\\:

  - `best_eta`: Selected `eta`.

  - `best_lambda`: Selected `lambda`.

  - `best_beta`: Coefficient vector from the full-data fit at
    `(best_eta, best_lambda)`.

  - `criteria`: The criterion used.

- `integrated_stat.full_results`:

  A `data.frame` with one row per `(eta, lambda)` combination and the
  corresponding CV score.

- `integrated_stat.best_per_eta`:

  A `data.frame` with one row per `eta`, containing the best `lambda`
  and its score.

- `integrated_stat.betahat_best`:

  A matrix of coefficients where each column is the full-data
  coefficient vector corresponding to the best `lambda` for a given
  `eta`.

- `criteria`:

  The CV criterion used.

- `alpha`:

  The Elastic Net mixing parameter.

- `nfolds`:

  The number of folds used.

## Details

The matched case–control problem is handled via
[`ncckl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncckl_enet.md),
which maps Conditional Logistic Regression to a Cox model with fixed
event time and uses
[`coxkl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/coxkl_enet.md)
as the core engine.

Cross-validation is performed at the stratum level: each matched set is
treated as an indivisible unit and assigned to a single fold using
`get_fold_cc`. This ensures that the conditional likelihood is
well-defined within each training and test split.

For each candidate `eta`, a full `lambda` path is fit on the complete
data (via
[`ncckl_enet`](https://um-kevinhe.github.io/SurvBregDiv/reference/ncckl_enet.md)),
and then K-fold CV is used to evaluate each `lambda` along this path
according to the chosen `criteria`. The function therefore performs a 2D
search over \\(\eta, \lambda)\\.

The `criteria` argument controls the CV performance metric:

- `"loss"`: Average negative conditional log-likelihood on held-out
  strata (lower is better).

- `"AUC"`: Matched-set AUC based on within-stratum comparisons (higher
  is better).

- `"CIndex"`: Alias for `"AUC"` in the 1:m matched setting (higher is
  better).

- `"Brier"`: Conditional Brier score based on within-stratum softmax
  probabilities (lower is better).

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

cv_fit <- cv.ncckl_enet(
  y        = y,
  z        = z,
  stratum  = sets,
  beta     = beta_ext,
  etas     = eta_list,
  alpha    = 1,
  nfolds   = 5,
  criteria = "loss",
  seed     = 42
)

cv_fit$best$best_eta
cv_fit$best$best_lambda
} # }
```
