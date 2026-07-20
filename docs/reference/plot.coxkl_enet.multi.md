<div id="main" class="col-md-9" role="main">

# Plot Method for Multi-Source KL-Integrated Cox Elastic-Net Models

<div class="ref-description section level2">

Produces a line plot of model performance (loss or C-index) as a
function of the transfer-learning shrinkage parameter \\(\\eta\\) for
each external source in a `coxkl_enet.multi` object. Each source is
displayed as a separate line with a distinct color and linetype.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
# S3 method for class 'coxkl_enet.multi'
plot(
  x,
  test_z = NULL,
  test_time = NULL,
  test_delta = NULL,
  test_stratum = NULL,
  criteria = c("loss", "CIndex"),
  ...
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   x:

    An object of class `"coxkl_enet.multi"`, as returned by
    `coxkl_enet.multi`.

-   test\_z:

    Optional numeric matrix of test predictors of dimension
    `n_test x p`. If `NULL` (default), training data stored inside each
    source fit are used for evaluation.

-   test\_time:

    Optional numeric vector of test survival times of length `n_test`.
    Must be provided together with `test_z` and `test_delta` when
    evaluating on external test data.

-   test\_delta:

    Optional numeric vector of test event indicators of length `n_test`.
    Must be provided together with `test_z` and `test_time` when
    evaluating on external test data.

-   test\_stratum:

    Optional vector of stratum indicators of length `n_test` for
    stratified Cox models. Ignored if `NULL` (default).

-   criteria:

    Character string specifying the performance metric to plot. Either
    `"loss"` (default, negative log partial likelihood scaled by sample
    size) or `"CIndex"` (Harrell's concordance index).

-   ...:

    Currently unused. Reserved for future extensions.

</div>

<div class="section level2">

## Value

A `ggplot` object. The plot can be further customized with standard
ggplot2 layers and themes.

</div>

<div class="section level2">

## Details

For each valid source fit stored in `x$source_fits`, the function
extracts the `p x n_eta` coefficient matrix
`integrated_stat.betahat_best`, where each column corresponds to one
value of \\(\\eta\\). It then calls `test_eval()` on every column to
compute the chosen performance metric, and overlays the resulting curves
on a single ggplot2 figure.

If all four test arguments (`test_z`, `test_time`, `test_delta`,
`test_stratum`) are `NULL`, evaluation is performed on the training data
embedded in each source fit object. This is useful for a quick in-sample
diagnostic but may give optimistic estimates of performance.

Colors are assigned automatically via `hue_pal` and linetypes cycle
through `"solid"`, `"dashed"`, `"dotdash"`, `"longdash"`, and
`"twodash"` to remain distinguishable when printed in grayscale.

</div>

<div class="section level2">

## See also

<div class="dont-index">

`coxkl_enet.multi` for fitting the multi-source model, `plot.coxkl` for
the analogous plot method for single-source `"coxkl"` objects.

</div>

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
if (FALSE) { # \dontrun{
fit <- coxkl_enet.multi(
  z         = z_train,
  delta     = delta_train,
  time      = time_train,
  beta_list = list(beta_ext1, beta_ext2, beta_ext3),
  etas      = seq(0, 1, by = 0.1)
)

# In-sample diagnostic (uses training data stored in each source fit)
plot(fit, criteria = "CIndex")

# Out-of-sample evaluation on a held-out test set
plot(fit,
     test_z     = z_test,
     test_time  = time_test,
     test_delta = delta_test,
     criteria   = "loss")
} # }
```

</div>

</div>

</div>
