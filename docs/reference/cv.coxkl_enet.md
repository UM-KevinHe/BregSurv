<div id="main" class="col-md-9" role="main">

# Cross-Validation for CoxKL Model with Elastic Net & Lasso Penalty

<div class="ref-description section level2">

Performs k-fold cross-validation to tune the hyperparameters for the
high-dimensional Cox proportional hazards model with Kullback–Leibler
(KL) divergence penalty.

This function primarily tunes the external information weight `eta`. For
each candidate `eta`, it internally validates the optimal regularization
parameter `lambda`.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cv.coxkl_enet(
  z,
  delta,
  time,
  stratum = NULL,
  RS = NULL,
  beta = NULL,
  etas,
  alpha = 1,
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

</div>

</div>

<div class="section level2">

## Arguments

-   z:

    Numeric matrix of covariates. Rows represent individuals and columns
    represent predictors.

-   delta:

    Numeric vector of event indicators (1 = event, 0 = censored).

-   time:

    Numeric vector of observed times (event or censoring).

-   stratum:

    Optional numeric or factor vector indicating strata. If `NULL`, all
    subjects are assumed to be in the same stratum.

-   RS:

    Optional numeric vector or matrix of external risk scores. If not
    provided, `beta` must be supplied.

-   beta:

    Optional numeric vector of external coefficients (length equal to
    `ncol(z)`). If provided, it is used to compute external risk scores.
    If not provided, `RS` must be supplied.

-   etas:

    Numeric vector of candidate `eta` values to be evaluated.

-   alpha:

    Elastic-net mixing parameter in \\((0,1\]\\). Default is `1` (lasso
    penalty).

-   lambda:

    Optional numeric vector of lambda values. If `NULL`, a path is
    generated automatically.

-   nlambda:

    Integer. Number of lambda values to generate if `lambda` is NULL.
    Default is 100.

-   lambda.min.ratio:

    Numeric. Ratio of min/max lambda. Default depends on sample size vs
    dimension (0.05 if n &lt; p, else 1e-03).

-   nfolds:

    Integer. Number of cross-validation folds. Default is `5`.

-   cv.criteria:

    Character string specifying the cross-validation criterion for
    selecting both `eta` and `lambda`. Choices are:

    -   `"V&VH"` (default): V&VH loss.

    -   `"LinPred"`: Loss based on cross-validated linear predictors.

    -   `"CIndex_pooled"`: Pooled C-Index.

    -   `"CIndex_foldaverage"`: Average C-Index across folds.

-   c\_index\_stratum:

    Optional stratum vector. Required only when `cv.criteria` is set to
    `"CIndex_pooled"` or `"CIndex_foldaverage"`, and a stratified
    C-index needs to be computed while the fitted model is
    non-stratified. Default is `NULL`.

-   message:

    Logical. Whether to print progress messages. Default is `FALSE`.

-   seed:

    Optional integer. Random seed for reproducible fold assignment.

-   ...:

    Additional arguments passed to the underlying fitting function
    `coxkl_enet`.

</div>

<div class="section level2">

## Value

An object of class `"cv.coxkl_enet"`. A list containing:

-   `best`:

    A list with the optimal parameters:

    -   `best_eta`: The selected eta value.

    -   `best_lambda`: The selected lambda value.

    -   `best_beta`: The coefficient vector corresponding to the best
        eta and lambda.

    -   `criteria`: The criterion used for selection.

-   `integrated_stat.full_results`:

    A `data.frame` containing the performance metric for every
    combination of `eta` and `lambda`.

-   `integrated_stat.best_per_eta`:

    A `data.frame` containing the best lambda and corresponding score
    for each candidate `eta`.

-   `integrated_stat.betahat_best`:

    A matrix of coefficients where each column corresponds to the
    optimal model for a specific `eta`.

-   `criteria`:

    The selection criterion used.

-   `alpha`:

    The elastic net mixing parameter used.

-   `nfolds`:

    The number of folds used.

</div>

<div class="section level2">

## Details

The function iterates through the provided `etas`. For each `eta`, it
performs cross-validation (based on `nfolds`) to select the optimal
`lambda` and computes the corresponding cross-validation score.

The available criteria for selection are:

-   `"V&VH"`: The Verweij & Van Houwelingen partial likelihood loss
    (default).

-   `"LinPred"`: Loss based on the prognostic performance of the linear
    predictor.

-   `"CIndex_pooled"`: Harrell's C-index computed by pooling linear
    predictors across folds.

-   `"CIndex_foldaverage"`: Harrell's C-index computed within each fold
    and averaged.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 100)

cv.coxkl_enet_est <- cv.coxkl_enet(
   z = train_dat_highdim$z,
   delta = train_dat_highdim$status,
   time = train_dat_highdim$time,
   stratum = train_dat_highdim$stratum,
   beta = beta_external_highdim,
   etas = eta_list,
   alpha = 1,
   cv.criteria = "CIndex_pooled"
)
} # }
```

</div>

</div>

</div>
