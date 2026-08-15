# Conditional Logistic Regression with Individual-level External Data and Elastic Net Penalty (CLR-Indi-ENet)

Fits a series of penalized Conditional Logistic Regression models for
matched case-control data that integrate external individual-level data
via a composite likelihood weight `etas`, while applying an Elastic Net
penalty for variable selection and regularization in high-dimensional
settings.

## Usage

``` r
ncc_indi_enet(
  y_int,
  z_int,
  stratum_int,
  y_ext,
  z_ext,
  stratum_ext,
  etas,
  alpha = 1,
  lambda = NULL,
  nlambda = 100,
  lambda.min.ratio = NULL,
  lambda.early.stop = FALSE,
  tol = 1e-04,
  Mstop = 1000,
  max.total.iter = (Mstop * nlambda),
  group = NULL,
  group.multiplier = NULL,
  standardize = TRUE,
  nvar.max = NULL,
  group.max = NULL,
  stop.loss.ratio = 0.01,
  actSet = TRUE,
  actIter = Mstop,
  actGroupNum = NULL,
  actSetRemove = FALSE,
  returnX = FALSE,
  trace.lambda = FALSE,
  message = FALSE,
  ...
)
```

## Arguments

- y_int:

  Numeric vector of binary outcomes for the internal dataset (0 =
  control, 1 = case).

- z_int:

  Numeric matrix of covariates for the internal dataset.

- stratum_int:

  Numeric or factor vector defining the internal matched sets.
  **Required**.

- y_ext:

  Numeric vector of binary outcomes for the external dataset (0 =
  control, 1 = case).

- z_ext:

  Numeric matrix of covariates for the external dataset.

- stratum_ext:

  Numeric or factor vector defining the external matched sets.
  **Required**.

- etas:

  Numeric vector of nonnegative external weights. Must be finite and
  \\\ge 0\\; `eta = 0` gives an internal-only fit. The values are sorted
  in ascending order internally, and the per-`eta` elements of the
  returned `beta` and `lambda` lists follow that sorted order.

- alpha:

  The Elastic Net mixing parameter, with \\0 \< \alpha \le 1\\.
  `alpha = 1` is Lasso; `alpha` close to 0 approaches Ridge. Default
  `1`.

- lambda:

  Optional numeric vector of penalty parameters. If `NULL`, a path is
  generated automatically for each `eta`.

- nlambda:

  Integer. Number of lambda values to generate. Default `100`.

- lambda.min.ratio:

  Numeric. Ratio of smallest to largest lambda. Default `NULL`
  (determined automatically based on sample size vs. number of
  covariates).

- lambda.early.stop:

  Logical. If `TRUE`, stops the lambda path early if the loss
  improvement is small. Default `FALSE`.

- tol:

  Convergence tolerance. Default `1e-4`.

- Mstop:

  Maximum coordinate descent iterations per lambda. Default `1000`.

- max.total.iter:

  Maximum total iterations across the entire lambda path. Default
  `Mstop * nlambda`.

- group:

  Integer vector defining group membership for grouped penalties. The
  formal default is `NULL`, which
  [`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md)
  resolves to `seq_len(ncol(z_int))`, i.e. each variable is treated as
  its own group.

- group.multiplier:

  Numeric vector of multiplicative factors for group penalties.

- standardize:

  Logical. If `TRUE`, `z` is standardized internally. Coefficients are
  returned on the original scale. Default `TRUE`.

- nvar.max:

  Integer. Maximum number of active variables. The formal default is
  `NULL`, resolved downstream to `ncol(z_int)`.

- group.max:

  Integer. Maximum number of active groups. The formal default is
  `NULL`, resolved downstream to `length(unique(group))` (after `group`
  itself has been resolved).

- stop.loss.ratio:

  Numeric. Threshold for early stopping. Default `1e-2`.

- actSet:

  Logical. If `TRUE`, uses active-set strategy. Default `TRUE`.

- actIter:

  Integer. Iterations for active set refinement. Default `Mstop`.

- actGroupNum:

  Integer. Limit on active groups in the active-set strategy. The formal
  default is `NULL`, resolved downstream to `sum(unique(group) != 0)`.

- actSetRemove:

  Logical. Whether to allow removal from active set. Default `FALSE`.

- returnX:

  Logical. If `TRUE`, returns the standardized design matrix. Default
  `FALSE`.

- trace.lambda:

  Logical. If `TRUE`, prints the lambda sequence progress. Default
  `FALSE`.

- message:

  Logical. If `TRUE`, shows a progress bar. Default `FALSE`.

- ...:

  Additional arguments passed to
  [`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md).

## Value

An object of class `"ncc_indi_enet"` and `"cox_indi_enet"`. See
[`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md)
for a description of the return components.

## Details

This function maps the CLR problem to a Cox PH model with fixed event
time \\T=1\\ and \\\delta=y\\ for both internal and external datasets,
then calls
[`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md)
as the core engine.

- If `alpha = 1`, the penalty is Lasso.

- If `alpha` is close to 0, the penalty approaches Ridge.

- If `eta = 0`, external data is ignored and the model reduces to a
  standard Elastic Net CLR on internal data only.

## See also

[`cox_indi_enet`](https://um-kevinhe.github.io/BregSurv/reference/cox_indi_enet.md),
[`ncc_indi`](https://um-kevinhe.github.io/BregSurv/reference/ncc_indi.md)

## Examples

``` r
if (FALSE) { # \dontrun{
## Load the matched case-control individual-level example data
data(ExampleData_cc_indi)

y_int       <- ExampleData_cc_indi$internal$y
z_int       <- ExampleData_cc_indi$internal$z
stratum_int <- ExampleData_cc_indi$internal$stratum

y_ext       <- ExampleData_cc_indi$external$y
z_ext       <- ExampleData_cc_indi$external$z
stratum_ext <- ExampleData_cc_indi$external$stratum

## Generate a sequence of eta values
eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 10)

## Fit the penalized composite-likelihood CLR path (alpha = 1 gives the Lasso)
fit_enet <- ncc_indi_enet(
  y_int       = y_int,
  z_int       = z_int,
  stratum_int = stratum_int,
  y_ext       = y_ext,
  z_ext       = z_ext,
  stratum_ext = stratum_ext,
  etas        = eta_list,
  alpha       = 1
)

## The eta grid actually used, in ascending order; the returned beta and lambda
## are lists with one element per eta, in this same order.
fit_enet$eta
} # }
```
