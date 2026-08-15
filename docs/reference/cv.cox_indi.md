# Cross-Validated cox_indi to Tune etas

Performs K-fold cross-validation over candidate `etas`. Internal data
are split into folds. For each fold, the model is trained on the
internal training split plus the full external dataset, then evaluated
on the held-out internal fold.

## Usage

``` r
cv.cox_indi(
  z_int,
  delta_int,
  time_int,
  stratum_int = NULL,
  z_ext,
  delta_ext,
  time_ext,
  stratum_ext = NULL,
  etas,
  nfolds = 5,
  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
  c_index_stratum = NULL,
  max_iter = 100,
  tol = 1e-07,
  message = FALSE,
  seed = NULL
)
```

## Arguments

- z_int, delta_int, time_int, stratum_int:

  Internal data. If `stratum_int` is `NULL`, all internal observations
  are treated as a single stratum; unlike the other cross-validation
  functions in the package, no warning is issued in that case.

- z_ext, delta_ext, time_ext, stratum_ext:

  External data (always fully included in training).

- etas:

  Numeric vector of non-negative candidate eta values (must be provided;
  omitting it is an error). Must be finite and \\\ge 0\\. The values are
  sorted in ascending order internally, and the rows of `internal_stat`
  / columns of `beta_full` follow that sorted order.

- nfolds:

  Number of folds (default 5).

- cv.criteria:

  Performance criterion. One of `"V&VH"` (default), `"LinPred"`,
  `"CIndex_pooled"`, or `"CIndex_foldaverage"`.

- c_index_stratum:

  Optional stratum vector used for C-index evaluation on internal data.
  When supplied it must have the same length as the internal data.

- max_iter, tol:

  Passed to `cox_indi`. Defaults are `max_iter = 100` and
  `tol = 1.0e-7`; note that this `tol` is an order of magnitude tighter
  than the `1e-4` used elsewhere in the package.

- message:

  Logical; print progress (default FALSE).

- seed:

  Optional seed for reproducible folds.

## Value

An object of class `"cv.cox_indi"` with components:

- `internal_stat`: data.frame of CV stats by eta, one row per candidate
  `eta` in ascending order. It has a column `eta` plus *exactly one*
  metric column, whose name is determined by `cv.criteria`: `VVH_Loss`
  for `"V&VH"`, `LinPred_Loss` for `"LinPred"`, `CIndex_pooled` for
  `"CIndex_pooled"`, or `CIndex_foldaverage` for `"CIndex_foldaverage"`.
  The other three metrics are never computed.

- `beta_full`: matrix of full-data estimates (p x length(etas))

- `best`: list with `best_eta`, `best_beta`, `criteria`

- `criteria`: the criterion used for selection

- `nfolds`: the number of folds used

## Examples

``` r
if (FALSE) { # \dontrun{
## Load example individual-level data
data(ExampleData_indi)

z_int       <- ExampleData_indi$internal$z
delta_int   <- ExampleData_indi$internal$status
time_int    <- ExampleData_indi$internal$time
stratum_int <- ExampleData_indi$internal$stratum

z_ext       <- ExampleData_indi$external$z
delta_ext   <- ExampleData_indi$external$status
time_ext    <- ExampleData_indi$external$time
stratum_ext <- ExampleData_indi$external$stratum

## Generate candidate eta values
eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 20)

## Cross-validated tuning of eta
cv_fit <- cv.cox_indi(
  z_int = z_int,
  delta_int = delta_int,
  time_int = time_int,
  stratum_int = stratum_int,
  z_ext = z_ext,
  delta_ext = delta_ext,
  time_ext = time_ext,
  stratum_ext = stratum_ext,
  etas = eta_list,
  nfolds = 5,
  cv.criteria = "CIndex_pooled"
)
} # }
```
