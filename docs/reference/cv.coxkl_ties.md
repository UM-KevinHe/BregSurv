# Cross-Validated Cox–KL with Ties Handling to Tune the Integration Parameter (eta)

Performs K-fold cross-validation (CV) to select the optimal integration
parameter `eta` for the Cox Proportional Hazards model with
Kullback–Leibler (KL) divergence data integration, using the Breslow or
Exact partial likelihood for tied event times.

## Usage

``` r
cv.coxkl_ties(
  z,
  delta,
  time,
  stratum = NULL,
  beta = NULL,
  etas = NULL,
  ties = c("breslow", "exact"),
  tol = 1e-04,
  Mstop = 100,
  nfolds = 5,
  cv.criteria = c("CIndex_pooled", "V&VH", "LinPred", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  message = FALSE,
  seed = NULL,
  comb_max = 1e+07,
  ...
)
```

## Arguments

- z:

  Numeric matrix of covariates (rows = observations, columns =
  variables).

- delta:

  Numeric vector of event indicators (1 = event, 0 = censored).

- time:

  Numeric vector of observed event or censoring times.

- stratum:

  Optional numeric or factor vector defining strata. If `NULL`, all
  observations are treated as a single stratum; a warning to that effect
  is issued only when `message = TRUE`.

- beta:

  Numeric vector of external coefficients. **Required**. If `beta` is
  named, names are matched against `colnames(z)`: covariates absent from
  `beta` are set to 0 (with a message) and the vector is reordered, so
  an external source covering only a subset of the internal covariates
  may be supplied directly. An unnamed `beta` is aligned positionally
  and must have length `ncol(z)`. A one-column matrix with row names is
  accepted as a named vector. See
  [`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md).

- etas:

  Numeric vector of non-negative candidate tuning values to be
  cross-validated. Must be finite and \\\ge 0\\. This argument is
  **required**: leaving it at its `NULL` default is an error. The values
  are sorted in ascending order internally, and the rows of
  `internal_stat` / columns of `beta_full` follow that sorted order.

- ties:

  Character string specifying the method for handling ties. Must be one
  of `"breslow"` (default) or `"exact"`.

- tol:

  Convergence tolerance for the optimizer used inside `coxkl_ties`.
  Default `1e-4`.

- Mstop:

  Maximum number of Newton iterations used inside `coxkl_ties`. Default
  `100`.

- nfolds:

  Number of cross-validation folds. Default `5`.

- cv.criteria:

  Character string specifying the performance criterion. Choices are
  `"CIndex_pooled"`, `"V&VH"`, `"LinPred"`, or `"CIndex_foldaverage"`.
  Default `"CIndex_pooled"` (note this differs from the other Cox
  cross-validation functions, whose default is `"V&VH"`).

- c_index_stratum:

  Optional stratum vector. Used for C-index calculation on test sets.

- message:

  Logical; if `TRUE`, prints progress messages. Default `FALSE`.

- seed:

  Optional integer seed for reproducible fold assignment. Default
  `NULL`.

- comb_max:

  Integer. Maximum number of combinations for the **Exact** partial
  likelihood calculation. Only relevant if `ties = "exact"`. Default
  `1e7`.

- ...:

  Additional arguments (currently ignored).

## Value

A `list` of class `"cv.coxkl"` (deliberately shared with
[`cv.coxkl`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl.md)
so that downstream methods apply to both) containing:

- `internal_stat`:

  A `data.frame` with one row per `eta`, in ascending `eta` order. It
  has a column `eta` plus *exactly one* metric column, whose name is
  determined by `cv.criteria`: `VVH_Loss` for `"V&VH"`, `LinPred_Loss`
  for `"LinPred"`, `CIndex_pooled` for `"CIndex_pooled"`, or
  `CIndex_foldaverage` for `"CIndex_foldaverage"`. The other three
  metrics are never computed.

- `beta_full`:

  A `ncol(z)` by `length(etas)` matrix of coefficients from the
  full-data fit, one column per candidate `eta`.

- `best`:

  A list containing the `best_eta`, the corresponding `best_beta` from
  the full model fit, and the `criteria` used.

- `criteria`:

  The criterion used for selection.

- `nfolds`:

  The number of folds used.

## Details

The function returns results in the format of a `cv.coxkl` object,
allowing downstream processing compatible with non-ties-handling Cox-KL
models. The `ties` argument controls which form of the partial
likelihood (PL) is used for both model fitting and CV criterion
calculation.

## Examples

``` r
if (FALSE) { # \dontrun{
data(ExampleData_lowdim)
train_dat_lowdim <- ExampleData_lowdim$train
# Rounding the event times introduces ties for demonstration purposes
train_dat_lowdim$time <- round(train_dat_lowdim$time, 2)
eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)

coxkl_ties.fit_breslow <- cv.coxkl_ties(
    z = train_dat_lowdim$z,
    delta = train_dat_lowdim$status,
    time = train_dat_lowdim$time,
    stratum = train_dat_lowdim$stratum,
    beta = ExampleData_lowdim$beta_external_fair,
    etas = eta_list,
    ties = "breslow",
    nfolds = 5,
    cv.criteria = "V&VH",
    seed = 42
)
} # }
```
