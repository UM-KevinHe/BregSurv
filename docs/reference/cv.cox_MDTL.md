# Cross-Validation for Cox MDTL Model

Performs k-fold cross-validation to tune the hyperparameter `eta` for
the Cox Proportional Hazards Model with Mahalanobis Distance Transfer
Learning.

The function evaluates the model performance across a range of `eta`
values using specified cv.criteria (e.g., Verweij & Van Houwelingen
loss, C-index) to select the optimal weight for the external
information.

## Usage

``` r
cv.cox_MDTL(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  vcov = NULL,
  etas = NULL,
  tol = 1e-04,
  Mstop = 100,
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

- vcov:

  Optional numeric matrix (p x p) representing the weighting matrix
  \\Q\\ for the Mahalanobis penalty. Typically the inverse covariance
  matrix. If `NULL`, defaults to the identity matrix.

- etas:

  A numeric vector of candidate `eta` values to be evaluated.

- tol:

  Convergence tolerance for the optimization algorithm. Default is 1e-4.

- Mstop:

  Maximum number of iterations for the optimization. Default is 100.

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

  Additional arguments passed to the underlying fitting function
  [`cox_MDTL`](https://um-kevinhe.github.io/SurvBregDiv/reference/cox_MDTL.md).

## Value

An object of class `"cv.Cox_MDTL"` containing:

- `internal_stat`:

  A `data.frame` summarizing the performance metric (loss or C-index)
  for each candidate `eta`.

- `best`:

  A list containing the optimal results:

  - `best_eta`: The selected eta value.

  - `best_beta`: The coefficient vector corresponding to the optimal eta
    (refitted on full data).

  - `criteria`: The criterion used for selection.

- `criteria`:

  The selection criterion used.

- `nfolds`:

  The number of folds used.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

cv.cox_MDTL_est <- cv.cox_MDTL(
  z = train_dat_lowdim$z,
  delta = train_dat_lowdim$status,
  time = train_dat_lowdim$time,
  beta = beta_external_lowdim,
  vcov = NULL,
  etas = eta_list,
  cv.criteria = "V&VH"
)
} # }
```
