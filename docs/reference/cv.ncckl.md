# Cross-Validated Conditional Logistic Regression with KL Integration

Performs K-fold cross-validation (CV) to select the integration
parameter `eta` for Conditional Logistic Regression with
Kullback–Leibler (KL) divergence data integration, implemented via
[`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md).

This function is designed for 1:m matched case–control settings where
each stratum (matched set) contains exactly one case and \\m\\ controls.

## Usage

``` r
cv.ncckl(
  y,
  z,
  stratum,
  beta = NULL,
  etas = NULL,
  method = c("breslow", "exact"),
  tol = 1e-04,
  Mstop = 100,
  nfolds = 5,
  cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
  message = FALSE,
  seed = NULL,
  comb_max = 1e+07,
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

- beta:

  Numeric vector of external coefficients. **Required**. These are used
  by [`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md)
  /
  [`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md)
  to construct the KL divergence penalty. If `beta` is named, names are
  matched against `colnames(z)`: covariates absent from `beta` are set
  to 0 (with a message) and the vector is reordered, so an external
  source covering only a subset of the internal covariates may be
  supplied directly. An unnamed `beta` is aligned positionally and must
  have length `ncol(z)`. A one-column matrix with row names is accepted
  as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).
  The bundled fixture `ExampleData_cc_lowdim$beta_external` is named
  `Z1`–`Z6` and therefore takes the name-matching path.

- etas:

  Numeric vector of non-negative integration weights for the parameter
  \\\eta\\ to be cross-validated. **Required**; the function stops if
  `etas` is `NULL`. Must be finite and \\\ge 0\\. The values are sorted
  in ascending order internally, and the rows of `internal_stat` /
  columns of `beta_full` follow that sorted order.

- method:

  Character string specifying the tie-handling method used in the
  underlying Cox partial likelihood. Must be one of `"breslow"` (the
  default) or `"exact"`. The value is passed through
  [`tolower()`](https://rdrr.io/r/base/chartr.html) before matching, so
  `"Breslow"` / `"EXACT"` are also accepted. For 1:m matched sets, these
  yield identical parameter estimates, but `"exact"` is theoretically
  preferable.

- tol:

  Convergence tolerance for the optimizer used inside
  [`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md) /
  [`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md).
  Default `1e-4`.

- Mstop:

  Maximum number of Newton iterations used inside
  [`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md) /
  [`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md).
  Default `100`.

- nfolds:

  Number of cross-validation folds. Default `5`.

- cv.criteria:

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

  Logical; if `TRUE`, prints progress messages and fold-wise evaluation
  progress bars. Default `FALSE`.

- seed:

  Optional integer seed for reproducible fold assignment. Default
  `NULL`.

- comb_max:

  Integer. Maximum number of combinations for the `method = "exact"`
  calculation, passed down to
  [`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md) /
  [`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md).
  Default `1e7`.

- ...:

  Additional arguments (currently ignored).

## Value

A `list` of class `"cv.ncckl"` containing:

- `internal_stat`:

  A `data.frame` with one row per `eta` and the CV metric results for
  the chosen `cv.criteria`.

- `beta_full`:

  The matrix of coefficients from the full-data fit (columns correspond
  to `etas`).

- `best`:

  A list containing the `best_eta`, the corresponding `best_beta` from
  the full-data fit, and `criteria` (the CV criterion used).

- `criteria`:

  The criterion used for selection.

- `nfolds`:

  The number of folds used.

## Details

The matched case–control problem is handled via
[`ncckl`](https://um-kevinhe.github.io/BregSurv/reference/ncckl.md),
which maps Conditional Logistic Regression to a Cox model with fixed
event time and uses
[`coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md)
as the core engine.

Cross-validation is performed at the stratum level: each matched set is
treated as an indivisible unit and assigned to a single fold using
`get_fold_cc`. This ensures that the conditional likelihood is
well-defined within each training and test split.

The `cv.criteria` argument controls the CV performance metric:

- `"loss"`: Average negative conditional log-likelihood on the held-out
  data, normalized per observation. For each fold, the conditional
  log-likelihood is computed over the test matched sets using the fitted
  \\\hat\beta\\ from the corresponding training data and divided by the
  number of held-out *observations* in that fold; the resulting
  fold-wise losses are then averaged (unweighted) across folds.

- `"AUC"`: A matched-set AUC based on within-stratum comparisons. For
  each stratum, the case score is compared to the control scores,
  counting concordant/discordant/tied pairs and aggregating across all
  strata. Higher AUC indicates better discrimination.

- `"CIndex"`: Alias for `"AUC"`. In the 1:m matched case–control
  setting, the matched-set AUC is equivalent to the conditional
  concordance index, and is computed using the same path as `"AUC"`.

- `"Brier"`: A conditional Brier score based on within-stratum softmax
  probabilities. For each stratum, a probability is assigned to each
  member via \\\hat p\_{si} = \exp(\eta\_{si}) / \sum\_{j \in S_s}
  \exp(\eta\_{sj})\\, and the Brier score is the mean squared error
  \\(Y\_{si} - \hat p\_{si})^2\\ across all observations. Lower Brier
  indicates better conditional calibration and sharpness.

The returned object has the same structure as `"cv.coxkl"` objects from
[`cv.coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_ties.md),
facilitating downstream code reuse.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_cc_lowdim)
train_cc <- ExampleData_cc_lowdim$train

y        <- train_cc$y
z        <- train_cc$z
sets     <- train_cc$stratum
beta_ext <- ExampleData_cc_lowdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

cv_clr_kl <- cv.ncckl(
  y        = y,
  z        = z,
  stratum  = sets,
  beta     = beta_ext,
  etas     = eta_list,
  method   = "exact",
  nfolds   = 5,
  cv.criteria = "loss",
  seed     = 42
)

cv_clr_kl$best$best_eta
} # }
```
