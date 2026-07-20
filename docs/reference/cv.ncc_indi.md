<div id="main" class="col-md-9" role="main">

# Cross-Validated CLR with Individual-Level External Data

<div class="ref-description section level2">

Performs K-fold cross-validation (CV) to select the integration
parameter `eta` for Conditional Logistic Regression with
individual-level external data integration, implemented via `ncc_indi`.

This function is designed for 1:m matched case-control settings where
each stratum (matched set) contains exactly one case and \\(m\\)
controls.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cv.ncc_indi(
  y_int,
  z_int,
  stratum_int,
  y_ext,
  z_ext,
  stratum_ext,
  etas = NULL,
  nfolds = 5,
  cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
  max_iter = 100,
  tol = 1e-07,
  message = FALSE,
  seed = NULL
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   y\_int:

    Numeric vector of binary outcomes for the internal dataset (0 =
    control, 1 = case).

-   z\_int:

    Numeric matrix of covariates for the internal dataset.

-   stratum\_int:

    Numeric or factor vector defining the internal matched sets.
    **Required**.

-   y\_ext:

    Numeric vector of binary outcomes for the external dataset (0 =
    control, 1 = case).

-   z\_ext:

    Numeric matrix of covariates for the external dataset.

-   stratum\_ext:

    Numeric or factor vector defining the external matched sets.
    **Required**.

-   etas:

    Numeric vector of candidate tuning values for \\(\\eta\\).
    **Required**.

-   nfolds:

    Number of cross-validation folds. Default `5`.

-   cv.criteria:

    Character string specifying the CV performance criterion. One of
    `"loss"` (default), `"AUC"`, `"CIndex"`, or `"Brier"`.

-   max\_iter:

    Maximum number of Newton-Raphson iterations passed to `ncc_indi`.
    Default `100`.

-   tol:

    Convergence tolerance passed to `ncc_indi`. Default `1e-7`.

-   message:

    Logical. If `TRUE`, prints progress messages. Default `FALSE`.

-   seed:

    Optional integer seed for reproducible fold assignment. Default
    `NULL`.

</div>

<div class="section level2">

## Value

A list of class `"cv.ncc_indi"` containing:

-   `internal_stat`:

    A `data.frame` with one row per `eta` and the CV metric for the
    chosen `cv.criteria`.

-   `beta_full`:

    Matrix of coefficients from the full-data fit (columns correspond to
    `etas`).

-   `best`:

    A list with `best_eta`, `best_beta`, and `criteria`.

-   `criteria`:

    The criterion used for selection.

-   `nfolds`:

    The number of folds used.

</div>

<div class="section level2">

## Details

Cross-validation is performed at the stratum level on the *internal*
dataset: each matched set is treated as an indivisible unit and assigned
to a single fold using `get_fold_cc`. The external dataset is used in
full during every training fold.

The `cv.criteria` argument controls the CV performance metric:

-   `"loss"`: Average negative conditional log-likelihood on held-out
    strata.

-   `"AUC"`: Matched-set AUC based on within-stratum comparisons.

-   `"CIndex"`: Alias for `"AUC"` in the 1:m matched setting.

-   `"Brier"`: Conditional Brier score based on within-stratum softmax
    probabilities.

</div>

<div class="section level2">

## See also

<div class="dont-index">

`ncc_indi`, `cv.ncckl`

</div>

</div>

<div class="section level2">

## Examples

<div class="sourceCode">

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

## Generate candidate eta values
eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

## Cross-validated tuning of eta
cv_fit <- cv.ncc_indi(
  y_int       = y_int,
  z_int       = z_int,
  stratum_int = stratum_int,
  y_ext       = y_ext,
  z_ext       = z_ext,
  stratum_ext = stratum_ext,
  etas        = eta_list,
  nfolds      = 5,
  cv.criteria = "loss",
  seed        = 42
)

cv_fit$best$best_eta
} # }
```

</div>

</div>

</div>
