# Cross-Validation for Cox Model Integrated with External Individual-level Data and Elastic Net Penalty

Performs k-fold cross-validation on the **internal** dataset to jointly
tune the external weight `eta` and the regularisation parameter `lambda`
for
[`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md).

## Usage

``` r
cv.cox_indi_enet(
  z_int,
  delta_int,
  time_int,
  stratum_int = NULL,
  z_ext,
  delta_ext,
  time_ext,
  stratum_ext = NULL,
  etas,
  alpha = 1,
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

- z_int:

  Numeric matrix of covariates for the internal dataset
  (\\n\_{\text{int}} \times p\\).

- delta_int:

  Numeric vector of event indicators for the internal dataset (1 =
  event, 0 = censored).

- time_int:

  Numeric vector of survival times for the internal dataset.

- stratum_int:

  Optional stratum identifiers for the internal dataset. Default `NULL`
  assigns all internal observations to a single stratum.

- z_ext:

  Numeric matrix of covariates for the external dataset
  (\\n\_{\text{ext}} \times p\\). Must have the same number of columns
  as `z_int`.

- delta_ext:

  Numeric vector of event indicators for the external dataset (1 =
  event, 0 = censored).

- time_ext:

  Numeric vector of survival times for the external dataset.

- stratum_ext:

  Optional stratum identifiers for the external dataset. Default `NULL`
  assigns all external observations to a single stratum.

- etas:

  Numeric vector of nonnegative candidate external weights. `eta = 0`
  corresponds to an internal-only penalised fit. The vector is sorted
  internally in ascending order.

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha = 1` is the lasso penalty, and `alpha` close to 0 approaches
  ridge. Defaults to 1.

- lambda:

  Optional numeric vector of penalty parameters shared across all `eta`
  values and folds. If `NULL`, the lambda path is derived from the
  full-data fit at each `eta`.

- nlambda:

  Integer. Number of lambda values to generate per `eta` when `lambda`
  is `NULL`. Default is 100.

- lambda.min.ratio:

  Numeric. Ratio of the smallest to the largest lambda. Default is 0.05
  if \\n\_{\text{all}} \< p\\, and 1e-3 otherwise.

- nfolds:

  Integer. Number of cross-validation folds (applied to internal data
  only). Default is 5.

- cv.criteria:

  Character string specifying the cross-validation criterion. One of
  `"V&VH"` (default), `"LinPred"`, `"CIndex_pooled"`, or
  `"CIndex_foldaverage"`.

- c_index_stratum:

  Optional stratum vector for the internal dataset. Only needed when
  `cv.criteria` is `"CIndex_pooled"` or `"CIndex_foldaverage"` and a
  stratified C-index is desired while the fitted model uses a different
  (or no) stratification. Default `NULL`.

- message:

  Logical. If `TRUE`, shows a progress bar over the `etas` loop. Default
  `FALSE`.

- seed:

  Optional integer. Random seed for reproducible fold assignment.

- ...:

  Additional arguments passed to the underlying fitting function
  [`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md).

## Value

An object of class `"cv.cox_indi_enet"`. A list containing:

- `best`:

  A list with the optimal tuning parameters:

  - `best_eta`: The selected \\\eta\\ value.

  - `best_lambda`: The selected \\\lambda\\ value.

  - `best_beta`: Coefficient vector at the optimal (`eta`, `lambda`).

  - `criteria`: The criterion used for selection.

- `integrated_stat.full_results`:

  A `data.frame` with the cross-validation score for every (`eta`,
  `lambda`) combination evaluated.

- `integrated_stat.best_per_eta`:

  A `data.frame` with the best `lambda` and corresponding score for each
  candidate `eta`.

- `integrated_stat.betahat_best`:

  A coefficient matrix (\\p \times n\_{\text{eta}}\\) where each column
  is the optimal-`lambda` coefficient vector for a given `eta`,
  estimated on the full data.

- `criteria`:

  The selection criterion used.

- `alpha`:

  The Elastic Net mixing parameter used.

- `nfolds`:

  The number of folds used.

## Details

Cross-validation is applied exclusively to the internal cohort; the
external dataset is used in full during every training fold (weighted by
`eta`), exactly mirroring how
[`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md)
stacks the two cohorts with separate risk sets.

The procedure:

1.  For each candidate `eta`, fit
    [`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md)
    on the full internal + external data to obtain the lambda path and
    the full-data coefficient matrices.

2.  Split the *internal* observations into `nfolds` folds (stratified by
    event indicator and, optionally, stratum).

3.  For each fold and each `eta`, refit
    [`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md)
    on the training portion of the internal data (+ full external data)
    at the common lambda sequence, then evaluate the chosen criterion on
    the held-out internal test fold.

4.  Aggregate across folds and select the (`eta`, `lambda`) pair that
    optimises the criterion.

Available cross-validation criteria:

- `"V&VH"` (default): Verweij & Van Houwelingen partial likelihood loss
  (lower is better).

- `"LinPred"`: Cross-validated partial likelihood evaluated at the
  out-of-fold linear predictors (lower is better).

- `"CIndex_pooled"`: Harrell's C-index computed by pooling numerators
  and denominators across folds (higher is better).

- `"CIndex_foldaverage"`: Harrell's C-index computed within each fold
  and averaged (higher is better).

## Examples

``` r
if (FALSE) { # \dontrun{
## Load example individual-level data
data(ExampleData_indi)

z_int       <- ExampleData_indi$internal$z
delta_int   <- ExampleData_indi$internal$status
time_int    <- ExampleData_indi$internal$time
stratum_int <- ExampleData_indi$internal$stratum

z_ext       <- ExampleData_indi$external$z
delta_ext   <- ExampleData_indi$external$status
time_ext    <- ExampleData_indi$external$time
stratum_ext <- ExampleData_indi$external$stratum

## Generate a sequence of eta values
eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 3)

## Run cross-validation
cv_fit.cox_indi_enet <- cv.cox_indi_enet(
  z_int       = z_int,
  delta_int   = delta_int,
  time_int    = time_int,
  stratum_int = stratum_int,
  z_ext       = z_ext,
  delta_ext   = delta_ext,
  time_ext    = time_ext,
  stratum_ext = stratum_ext,
  etas        = eta_list,
  alpha       = 1,
  nfolds      = 5,
  cv.criteria = "CIndex_pooled",
  message = TRUE
)
} # }
```
