<div id="main" class="col-md-9" role="main">

# Multi-Source Integration for KL-Integrated Cox Elastic-Net Models

<div class="ref-description section level2">

Fits multiple KL-integrated Cox elastic-net models on the full data
using multiple external sources, and combines the fitted coefficient
vectors across sources to produce a single aggregated estimate.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
coxkl_enet.multi(
  z,
  delta,
  time,
  stratum = NULL,
  beta_list = NULL,
  RS_list = NULL,
  etas,
  combine = c("mean", "median"),
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

    Matrix/data.frame of predictors of dimension `n x p`.

-   delta:

    Event indicator vector.

-   time:

    Survival time vector.

-   stratum:

    Optional stratum indicator vector for stratified Cox models.

-   beta\_list:

    A list of external coefficient vectors. Each element must have
    length `p`. If provided, `RS_list` should be `NULL`.

-   RS\_list:

    Optional list of external risk score vectors/matrices. Each element
    should be conformable with `n`. If provided, `beta_list` is ignored.

-   etas:

    Vector of `eta` values for transfer-learning shrinkage.

-   combine:

    How to combine coefficients across sources. Either `"mean"`
    (default) or `"median"`.

-   message:

    Logical indicating whether to print progress.

-   seed:

    Optional seed for reproducibility (passed to each CV run with an
    offset).

-   ...:

    Additional arguments passed to `cv.coxkl_enet()` (e.g., `alpha`,
    `lambda`, `nlambda`, `lambda.min.ratio`, `nfolds`, `cv.criteria`,
    `c_index_stratum`, etc.).

</div>

<div class="section level2">

## Value

An object of class `"coxkl_enet.multi"`, which is a list containing:

-   `best_beta` — combined coefficient estimate across sources.

-   `all_betas` — matrix of dimension `p x K_valid` of coefficient
    vectors from each successful fit.

-   `K` — total number of external sources provided.

-   `valid_sources` — number of successful (non-error) fits used in
    aggregation.

-   `combine` — combination rule used.

-   `seed` — seed used (if any).

</div>

<div class="section level2">

## Details

Unlike `coxkl_enet_bagging()`, this function does not bootstrap the
data. Instead, it runs `cv.coxkl_enet()` once per external source on the
full dataset. The resulting coefficient vectors are then aggregated (by
default, averaged) to obtain a combined estimate.

</div>

</div>
