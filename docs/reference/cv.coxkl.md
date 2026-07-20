<div id="main" class="col-md-9" role="main">

# Cross-Validated Cox–KL to Tune the Integration Parameter (eta)

<div class="ref-description section level2">

Performs K-fold cross-validation to select the integration parameter
`eta` for the Cox–KL model. Each fold fits the model on a training split
and evaluates on the held-out split using the specified performance
criterion.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cv.coxkl(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas = NULL,
  tol = 1e-04,
  Mstop = 100,
  backtrack = FALSE,
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  ...
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   z:

    Numeric matrix of covariates (rows = observations, columns =
    variables).

-   delta:

    Numeric vector of event indicators (1 = event, 0 = censored).

-   time:

    Numeric vector of observed event or censoring times.

-   stratum:

    Optional numeric or factor vector defining strata.

-   RS:

    Optional numeric vector or matrix of external risk scores. If
    omitted, `beta` must be supplied.

-   beta:

    Optional numeric vector of external coefficients. If omitted, `RS`
    must be supplied.

-   etas:

    Numeric vector of candidate tuning values to be cross-validated.
    Default is `NULL`, which sets `etas = 0`.

-   tol:

    Convergence tolerance for the optimizer used inside `coxkl`. Default
    `1e-4`.

-   Mstop:

    Maximum number of Newton iterations used inside `coxkl`. Default
    `100`.

-   backtrack:

    Logical; if `TRUE`, backtracking line search is applied during
    optimization. Default is `FALSE`.

-   nfolds:

    Number of cross-validation folds. Default `5`.

-   cv.criteria:

    Character string specifying the performance criterion. Choices are
    `"V&VH"`, `"LinPred"`, `"CIndex_pooled"`, or `"CIndex_foldaverage"`.
    Default `"V&VH"`.

-   c\_index\_stratum:

    Optional stratum vector. Only required when `cv.criteria` is set to
    `"CIndex_pooled"` or `"CIndex_foldaverage"`, and a stratified
    C-index is desired while the fitted model is non-stratified. Default
    `NULL`.

-   message:

    Logical; if `TRUE`, prints progress messages. Default `FALSE`.

-   seed:

    Optional integer seed for reproducible fold assignment. Default
    `NULL`.

-   ...:

    Additional arguments passed to `coxkl`.

</div>

<div class="section level2">

## Value

A `data.frame` with one row per candidate `eta` and columns:

-   `eta`:

    The candidate `eta` values.

-   `VVH_Loss`:

    If `cv.criteria = "V&VH"`, the cross-validated V&VH loss.

-   `LinPred_Loss`:

    If `cv.criteria = "LinPred"`, the loss based on linear predictors.

-   `CIndex_pooled`:

    If `cv.criteria = "CIndex_pooled"`, the pooled cross-validated
    C-index.

-   `CIndex_foldaverage`:

    If `cv.criteria = "CIndex_foldaverage"`, the average fold-wise
    C-index.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair
etas <- generate_eta(method = "exponential", n = 50, max_eta = 10)
cv.result <- cv.coxkl(
  z = train_dat_lowdim$z,
  delta = train_dat_lowdim$status,
  time = train_dat_lowdim$time,
  stratum = train_dat_lowdim$stratum,
  beta = beta_external_lowdim,
  etas = etas,
  nfolds = 5,
  cv.criteria = "CIndex_pooled")
} # }
```

</div>

</div>

</div>
