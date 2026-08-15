# Plot Method for Multi-Source KL-Integrated Cox Elastic-Net Models

Produces a line plot of model performance (loss or C-index) as a
function of the transfer-learning shrinkage parameter \\\eta\\ for each
external source in a `coxkl_enet.multi` object. Each source is displayed
as a separate line with a distinct color and linetype.

## Usage

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

## Arguments

- x:

  An object of class `"coxkl_enet.multi"`, as returned by
  [`coxkl_enet.multi`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.multi.md).

- test_z:

  Numeric matrix of test predictors of dimension `n_test x p`. Required:
  evaluation is always carried out on test data.

- test_time:

  Numeric vector of test survival times of length `n_test`. Required,
  together with `test_z` and `test_delta`.

- test_delta:

  Numeric vector of test event indicators of length `n_test`. Required,
  together with `test_z` and `test_time`.

- test_stratum:

  Optional vector of stratum indicators of length `n_test` for
  stratified Cox models. When `NULL` (default), the test set is
  evaluated as a single stratum.

- criteria:

  Character string specifying the performance metric to plot. Either
  `"loss"` (default, negative log partial likelihood scaled by sample
  size) or `"CIndex"` (Harrell's concordance index).

- ...:

  Currently unused. Reserved for future extensions.

## Value

A [`ggplot`](https://ggplot2.tidyverse.org/reference/ggplot.html)
object. The plot can be further customized with standard ggplot2 layers
and themes.

## Details

For each valid source fit stored in `x$source_fits`, the function
extracts the `p x n_eta` coefficient matrix
`integrated_stat.betahat_best`, where each column corresponds to one
value of \\\eta\\. It then calls
[`test_eval()`](https://um-kevinhe.github.io/BregSurv/reference/test_eval.md)
on every column to compute the chosen performance metric, and overlays
the resulting curves on a single ggplot2 figure.

Colors are assigned automatically via
[`hue_pal`](https://scales.r-lib.org/reference/pal_hue.html) and
linetypes cycle through `"solid"`, `"dashed"`, `"dotdash"`,
`"longdash"`, and `"twodash"` to remain distinguishable when printed in
grayscale.

## See also

[`coxkl_enet.multi`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_enet.multi.md)
for fitting the multi-source model,
[`plot.coxkl`](https://um-kevinhe.github.io/BregSurv/reference/plot.coxkl.md)
for the analogous plot method for single-source `"coxkl"` objects.

## Examples

``` r
if (FALSE) { # \dontrun{
fit <- coxkl_enet.multi(
  z         = z_train,
  delta     = delta_train,
  time      = time_train,
  beta_list = list(beta_ext1, beta_ext2, beta_ext3),
  etas      = seq(0, 1, by = 0.1)
)

# Out-of-sample evaluation on a held-out test set
plot(fit,
     test_z     = z_test,
     test_time  = time_test,
     test_delta = delta_test,
     criteria   = "loss")
} # }
```
