<div id="main" class="col-md-9" role="main">

# Stability Selection for MDTL-Integrated Cox Elastic-Net Models

<div class="ref-description section level2">

Performs stability selection for the Mahalanobis-distance–based
transfer-learning Cox elastic-net model (`cox_MDTL_enet`) by repeatedly
refitting the model on bootstrap or subsampled datasets and aggregating
variable selection frequencies across replicates. This procedure yields
a more robust measure of variable importance that is less sensitive to a
single data split.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cox_MDTL_enet.StabSelect(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  vcov = NULL,
  etas = NULL,
  alpha = 1,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = 0.1,
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  B = 50,
  fraction_sample = 0.5,
  ncores = 1,
  ...
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   z:

    A numeric matrix or data frame of covariates (n x p).

-   delta:

    A numeric vector of event indicators (1 = event, 0 = censored).

-   time:

    A numeric vector of observed times.

-   stratum:

    Optional numeric or factor vector indicating strata. If `NULL`, all
    subjects are assumed to be in the same stratum.

-   beta:

    A numeric vector of external coefficients (length p).

-   vcov:

    Optional numeric matrix (p x p) representing the weighting matrix
    \\(Q\\) for the Mahalanobis penalty. Typically the inverse
    covariance matrix. If `NULL`, defaults to the identity matrix.

-   etas:

    A numeric vector of candidate `eta` values to be evaluated.

-   alpha:

    The Elastic Net mixing parameter, with \\(0 \\le \\alpha \\le 1\\).
    `alpha = 1` is the Lasso penalty, and `alpha = 0` is the Ridge
    penalty. If `NULL`, defaults to 1 (Lasso).

-   lambda:

    Optional user-supplied lambda sequence. If `NULL`, typical usage is
    to have the program compute its own `lambda` sequence based on
    `nlambda` and `lambda.min.ratio`.

-   nlambda:

    The number of `lambda` values. Default is 100.

-   lambda.min.ratio:

    Smallest value for `lambda`, as a fraction of `lambda.max`. Default
    depends on the sample size relative to the number of predictors.

-   nfolds:

    Integer. Number of cross-validation folds. Default is 5.

-   cv.criteria:

    Character string specifying the cross-validation criterion. Choices
    are:

    -   `"V&VH"` (default): Verweij & Van Houwelingen partial likelihood
        loss.

    -   `"LinPred"`: Loss based on the prognostic performance of the
        linear predictor.

    -   `"CIndex_pooled"`: Harrell's C-index computed by pooling
        predictions across folds.

    -   `"CIndex_foldaverage"`: Harrell's C-index computed within each
        fold and averaged.

-   c\_index\_stratum:

    Optional stratum vector. Required only when `cv.criteria` involves
    stratified C-index calculation but the model itself is unstratified.

-   message:

    Logical. If `TRUE`, progress messages are printed.

-   seed:

    Optional integer. Random seed for reproducible fold assignment.

-   B:

    Integer. Number of bootstrap/subsampling replicates used for
    stability selection. Default is `50`.

-   fraction\_sample:

    Numeric in `(0, 1]`. Fraction of the original sample size used in
    each replicate. Default is `0.5`.

-   ncores:

    Integer. Number of parallel cores. Default 1 (sequential execution).

-   ...:

    Additional arguments passed to the underlying fitting function.

</div>

<div class="section level2">

## Value

An object of class `"StabSelect"` containing:

-   `stability_path` — a numeric matrix storing selection probabilities
    for each variable–`lambda` pair across the `B` replicates.

-   `lambda` — the global `lambda` sequence used for the underlying
    elastic-net fits.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim      <- ExampleData_highdim$train
beta_external_highdim  <- ExampleData_highdim$beta_external

eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 10)

mdtl.StabSelect <- cox_MDTL_enet.StabSelect(
  z            = train_dat_highdim$z,
  delta        = train_dat_highdim$status,
  time         = train_dat_highdim$time,
  stratum      = train_dat_highdim$stratum,
  beta         = beta_external_highdim,
  vcov         = NULL,
  etas         = eta_list,
  cv.criteria  = "CIndex_pooled",
  B            = 20,
  message      = TRUE
)

# Visualize selection with a chosen threshold
plot(mdtl.StabSelect, threshold = 0.75)
} # }
```

</div>

</div>

</div>
