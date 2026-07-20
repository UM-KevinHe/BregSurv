<div id="main" class="col-md-9" role="main">

# Cox Proportional Hazards Model with Mahalanobis Distance Transfer Learning

<div class="ref-description section level2">

Fits a Cox proportional hazards model incorporating external information
via a Mahalanobis distance penalty. This approach penalizes the
deviation of the estimated coefficients from external reference
coefficients (`beta`), weighted by a specified matrix (typically the
inverse covariance matrix).

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cox_MDTL(
  z,
  delta,
  time,
  stratum = NULL,
  beta,
  vcov = NULL,
  etas,
  tol = 1e-04,
  Mstop = 50,
  backtrack = FALSE,
  message = FALSE,
  data_sorted = FALSE,
  beta_initial = NULL
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

    Optional numeric matrix (p x p) acting as the weighting matrix
    \\(Q\\) in the Mahalanobis penalty. **Note:** In standard
    Mahalanobis distance formulations, this should be the *inverse* of
    the covariance matrix (precision matrix). If not provided, an
    identity matrix is used.

-   etas:

    A numeric vector of tuning parameters (scalars) to evaluate.

-   tol:

    Convergence tolerance for the Newton-Raphson algorithm. Default is
    1e-4.

-   Mstop:

    Maximum number of iterations for Newton-Raphson. Default is 50.

-   backtrack:

    Logical. If `TRUE`, uses backtracking line search. Default is
    `FALSE`.

-   message:

    Logical. If `TRUE`, progress messages are printed.

-   data\_sorted:

    Logical. If `TRUE`, assumes input data is already sorted by stratum
    and time.

-   beta\_initial:

    Optional initial coefficient vector for warm start.

</div>

<div class="section level2">

## Value

An object of class `"Cox_MDTL"` containing:

-   `eta`:

    The vector of eta values evaluated.

-   `beta`:

    A matrix of estimated coefficients (p x n\_eta).

-   `linear.predictors`:

    A matrix of linear predictors (n x n\_eta).

-   `likelihood`:

    A vector of log-partial likelihoods for each eta.

-   `data`:

    A list containing the input data used.

</div>

<div class="section level2">

## Details

The objective function minimizes the negative log-partial likelihood
plus a penalty term: $$P(\\beta) = \\frac{\\eta}{2} (\\beta -
\\beta\_{ext})^T Q (\\beta - \\beta\_{ext})$$ where:

-   \\(\\beta\_{ext}\\) is the vector of external coefficients.

-   \\(Q\\) is the weighting matrix (derived from `vcov`).

-   \\(\\eta\\) is the tuning parameter controlling the strength of the
    external information.

If `vcov` is `NULL`, \\(Q\\) defaults to the identity matrix, reducing
the penalty to a standard Euclidean distance (Ridge-type shrinkage
towards `beta`).

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
beta_external_lowdim <- ExampleData_lowdim$beta_external_fair

eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 5)

cox_MDTL_est <- cox_MDTL(
  z = train_dat_lowdim$z,
  delta = train_dat_lowdim$status,
  time = train_dat_lowdim$time,
  beta = beta_external_lowdim,
  vcov = NULL,
  etas = eta_list
)
} # }
```

</div>

</div>

</div>
