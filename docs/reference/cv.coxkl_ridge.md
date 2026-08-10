# Cross-Validation for CoxKL Ridge Model (Tuning Eta and Lambda)

Performs k-fold cross-validation to tune the hyperparameters for the Cox
proportional hazards model with Kullback–Leibler (KL) divergence penalty
and Ridge (L2) regularization.

The function operates in two layers:

1.  **Outer Loop (Eta):** Iterates through user-provided `etas` to
    control the weight of external information.

2.  **Inner Loop (Lambda):** For each `eta`, performs cross-validation
    to select the optimal Ridge penalty parameter `lambda`.

## Usage

``` r
cv.coxkl_ridge(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = NULL,
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

  Numeric matrix of covariates. Rows represent individuals and columns
  represent predictors.

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of observed times (event or censoring).

- stratum:

  Optional numeric or factor vector indicating strata. If `NULL`, all
  subjects are assumed to be in the same stratum.

- RS:

  Optional numeric vector or matrix of external risk scores. If not
  provided, `beta` must be supplied.

- beta:

  Optional numeric vector of external coefficients (length equal to
  `ncol(z)`). If provided, used to compute external risk scores. If not
  provided, `RS` must be supplied.

- etas:

  Numeric vector of candidate `eta` values to be evaluated.

- lambda:

  Optional numeric vector of lambda values. If `NULL`, a path is
  generated automatically.

- nlambda:

  Integer. Number of lambda values to generate if `lambda` is `NULL`.
  Default is 100.

- lambda.min.ratio:

  Numeric. Ratio of min/max lambda. If `NULL` (default), it is set to
  0.01 if `n < p` and 1e-04 otherwise.

- nfolds:

  Integer. Number of cross-validation folds. Default is `5`.

- cv.criteria:

  Character string specifying the cross-validation criterion for
  selecting parameters. Choices are:

  - `"V&VH"` (default): Verweij & Van Houwelingen partial likelihood
    loss.

  - `"LinPred"`: Loss based on the prognostic performance of the linear
    predictor.

  - `"CIndex_pooled"`: Harrell's C-index computed by pooling predictions
    across folds.

  - `"CIndex_foldaverage"`: Harrell's C-index computed within each fold
    and averaged.

- c_index_stratum:

  Optional stratum vector. Required only when `cv.criteria` is set to
  `"CIndex_pooled"` or `"CIndex_foldaverage"` and stratification is
  needed for evaluation but not for model fitting. Default is `NULL`.

- message:

  Logical. Whether to print progress messages. Default is `FALSE`.

- seed:

  Optional integer. Random seed for reproducible fold assignment.

- ...:

  Additional arguments passed to the underlying fitting function
  [`coxkl_ridge`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ridge.md).

## Value

An object of class `"cv.coxkl_ridge"`. A list containing:

- `best`:

  A list with the optimal parameters:

  - `best_eta`: The selected eta value.

  - `best_lambda`: The selected lambda value.

  - `best_beta`: The coefficient vector corresponding to the best
    parameters.

  - `criteria`: The criterion used for selection.

- `integrated_stat.full_results`:

  A `data.frame` containing the performance score (and loss if
  applicable) for every combination of `eta` and `lambda`.

- `integrated_stat.best_per_eta`:

  A `data.frame` summarizing the best lambda and corresponding score for
  each candidate `eta`.

- `integrated_stat.betahat_best`:

  A matrix of coefficients where each column corresponds to the optimal
  model for a specific `eta`.

- `criteria`:

  The selection criterion used.

- `nfolds`:

  The number of folds used.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external
eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

cv.coxkl_ridge_est <- cv.coxkl_ridge(
   z = train_dat_highdim$z,
   delta = train_dat_highdim$status,
   time = train_dat_highdim$time,
   stratum = train_dat_highdim$stratum,
   beta = beta_external_highdim,
   etas = eta_list,
   cv.criteria = "CIndex_pooled"
)
} # }
```
