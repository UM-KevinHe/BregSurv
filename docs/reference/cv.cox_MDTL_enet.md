# Cross-Validation for Cox MDTL with Elastic Net Regularization

Performs k-fold cross-validation to simultaneously tune the
hyperparameter `eta` (transfer learning weight) and the regularization
parameter `lambda` for the Cox MDTL model with an Elastic Net penalty.

This function evaluates the model performance across a grid of `eta` and
`lambda` values to select the optimal combination that minimizes the
chosen loss function or maximizes the C-index.

## Usage

``` r
cv.cox_MDTL_enet(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  Q = NULL,
  etas = NULL,
  alpha = NULL,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(n < p, 0.05, 0.001),
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  ...
)
```

## Arguments

- z:

  A numeric matrix or data frame of covariates (n x p).

- delta:

  A numeric vector of event indicators (1 = event, 0 = censored).

- time:

  A numeric vector of observed times.

- stratum:

  Optional numeric or factor vector indicating strata. If `NULL`, all
  subjects are assumed to be in the same stratum.

- beta:

  A numeric vector of external coefficients (length p).

- Q:

  Optional numeric matrix (p x p) representing the weighting matrix
  \\Q\\ for the Mahalanobis penalty. This should be a symmetric
  positive-semidefinite *precision* matrix (typically the inverse
  covariance / information matrix of the external estimator). If named,
  it is reordered and zero-padded to `colnames(z)`. If `NULL`, a masked
  identity is used.

- etas:

  A numeric vector of candidate `eta` values to be evaluated.

- alpha:

  The Elastic Net mixing parameter, with \\0 \le \alpha \le 1\\.
  `alpha = 1` is the Lasso penalty, and `alpha = 0` is the Ridge
  penalty. If `NULL`, defaults to 1 (Lasso).

- lambda:

  Optional user-supplied lambda sequence. If `NULL`, typical usage is to
  have the program compute its own `lambda` sequence based on `nlambda`
  and `lambda.min.ratio`.

- nlambda:

  The number of `lambda` values. Default is 100.

- lambda.min.ratio:

  Smallest value for `lambda`, as a fraction of `lambda.max`. Default
  depends on the sample size relative to the number of predictors.

- nfolds:

  Integer. Number of cross-validation folds. Default is 5.

- cv.criteria:

  Character string specifying the cross-validation criterion. Choices
  are:

  - `"V&VH"` (default): Verweij & Van Houwelingen partial likelihood
    loss.

  - `"LinPred"`: Loss based on the prognostic performance of the linear
    predictor.

  - `"CIndex_pooled"`: Harrell's C-index computed by pooling predictions
    across folds.

  - `"CIndex_foldaverage"`: Harrell's C-index computed within each fold
    and averaged.

- c_index_stratum:

  Optional stratum vector. Required only when `cv.criteria` involves
  stratified C-index calculation but the model itself is unstratified.

- message:

  Logical. If `TRUE`, progress messages are printed.

- seed:

  Optional integer. Random seed for reproducible fold assignment.

- ...:

  Additional arguments passed to the underlying fitting function.

## Value

An object of class `"cv.cox_MDTL_enet"` containing:

- `best`:

  A list containing the optimal results:

  - `best_eta`: The selected eta value.

  - `best_lambda`: The selected lambda value.

  - `best_beta`: The coefficient vector corresponding to the optimal
    parameters.

  - `criteria`: The selection criterion used.

- `integrated_stat.full_results`:

  A data frame of performance metrics for all combinations of eta and
  lambda.

- `integrated_stat.best_per_eta`:

  A data frame summarizing the best lambda and performance metric for
  each eta.

- `integrated_stat.betahat_best`:

  A matrix of coefficients for the best lambda at each eta.

- `criteria`:

  The selection criterion used.

- `alpha`:

  The elastic net mixing parameter used.

- `nfolds`:

  The number of folds used.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

cv.cox_MDTL_enet_est <- cv.cox_MDTL_enet(
  z = train_dat_highdim$z,
  delta = train_dat_highdim$status,
  time = train_dat_highdim$time,
  stratum = train_dat_highdim$stratum,
  beta = beta_external_highdim,
  Q = NULL,
  etas = eta_list,
  alpha = 1,
  cv.criteria = "CIndex_pooled",
  message = TRUE
)
} # }
```
