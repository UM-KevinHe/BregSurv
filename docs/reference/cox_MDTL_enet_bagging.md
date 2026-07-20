<div id="main" class="col-md-9" role="main">

# Bagging for MDTL-Integrated Cox Elastic-Net Models

<div class="ref-description section level2">

Performs bootstrap aggregation (bagging) for the
Mahalanobis-distance–based transfer-learning Cox elastic-net model
(`cv.cox_MDTL_enet`) by repeatedly refitting the model on bootstrap
resamples of the internal dataset and averaging the resulting fitted
coefficient vectors. This procedure reduces sampling variability and
improves robustness relative to a single data split.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cox_MDTL_enet_bagging(
  z,
  delta,
  time,
  stratum = NULL,
  beta = NULL,
  vcov = NULL,
  etas,
  alpha = 1,
  B = 100,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.01, 1e-04),
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  ncores = 1,
  ...
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   z:

    Matrix of predictors of dimension `n x p`.

-   delta:

    Event indicator vector.

-   time:

    Survival time vector.

-   stratum:

    Optional stratum indicator vector for stratified Cox modeling.

-   beta:

    External coefficient vector of length `p`. Treated as fixed prior
    information and not resampled across bootstrap replicates.

-   vcov:

    Optional weighting matrix (`p x p`) used in the Mahalanobis distance
    formulation.

-   etas:

    Vector of `eta` values for transfer-learning shrinkage.

-   alpha:

    Elastic-net mixing parameter between `0` and `1`. `alpha = 1`
    corresponds to lasso; `alpha = 0` to ridge. Default is `1.0`.

-   B:

    Number of bootstrap replicates. Default is `100`.

-   lambda:

    Optional user-specified `lambda` sequence.

-   nlambda:

    Number of `lambda` values to generate if `lambda` is not supplied.

-   lambda.min.ratio:

    Ratio of the smallest to the largest `lambda` when generating a
    sequence.

-   nfolds:

    Number of folds for inner cross-validation via `cv.cox_MDTL_enet`.

-   cv.criteria:

    Cross-validation criterion used for selecting the optimal
    `(eta, lambda)` pair.

-   c\_index\_stratum:

    Optional stratum assignment for stratified C-index evaluation (may
    differ from model stratification).

-   message:

    Logical indicating whether to print progress. Default is `FALSE`.

-   seed:

    Optional integer seed for reproducibility.

-   ncores:

    Integer. Number of parallel cores. Default 1 (sequential execution).

-   ...:

    Additional arguments passed to `cv.cox_MDTL_enet`.

</div>

<div class="section level2">

## Value

An object of class `"cox_MDTL_bagging"` containing:

-   `best_beta` — aggregated coefficient estimate obtained by averaging
    across valid bootstrap replicates.

-   `all_betas` — matrix of dimension `p x B_valid` containing
    coefficient vectors from each successful bootstrap fit.

-   `B` — total number of requested bootstrap replicates.

-   `valid_replicates` — number of successful (non-error) fits
    contributing to aggregation.

-   `seed` — seed used for reproducibility (if supplied).

</div>

<div class="section level2">

## Details

External information is supplied via a fixed coefficient vector (`beta`)
and, optionally, a weighting matrix (`vcov`). Both represent external
prior information and are **not** resampled across replicates.

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
if (FALSE) { # \dontrun{
data(ExampleData_highdim)
train_dat_highdim     <- ExampleData_highdim$train
beta_external_highdim <- ExampleData_highdim$beta_external

etas <- generate_eta(method = "exponential", n = 10, max_eta = 10)

bag.out <- cox_MDTL_enet_bagging(
  z            = train_dat_highdim$z,
  delta        = train_dat_highdim$status,
  time         = train_dat_highdim$time,
  stratum      = train_dat_highdim$stratum,
  beta         = beta_external_highdim,
  vcov         = NULL,
  etas         = etas,
  alpha        = 0.5,
  B            = 5,
  cv.criteria  = "CIndex_pooled",
  message      = TRUE,
  seed         = 123
)
} # }
```

</div>

</div>

</div>
