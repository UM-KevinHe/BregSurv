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

  Internal data.

- z_ext, delta_ext, time_ext, stratum_ext:

  External data (always fully included in training).

- etas:

  Numeric vector of candidate eta values (must be provided).

- nfolds:

  Number of folds (default 5).

- cv.criteria:

  Performance criterion.

- c_index_stratum:

  Optional stratum vector used for C-index evaluation on internal data.

- max_iter, tol:

  Passed to `cox_indi`.

- message:

  Logical; print progress (default FALSE).

- seed:

  Optional seed for reproducible folds.

## Value

An object of class `"cv.cox_indi"` with components:

- `internal_stat`: data.frame of CV stats by eta

- `beta_full`: matrix of full-data estimates (p x length(etas))

- `best`: list with `best_eta`, `best_beta`, `criteria`

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
