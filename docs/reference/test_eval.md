# Evaluate Survival Model Performance

Computes predictive performance metrics for stratified or unstratified
Cox models. Supports Loss, C-index, Integrated Brier Score (IBS), and
Time-Dependent AUC (tdAUC).

## Usage

``` r
test_eval(
  test_z,
  test_delta,
  test_time,
  betahat,
  test_stratum = NULL,
  train_baseline_obj = NULL,
  criteria = c("loss", "CIndex", "IBS", "tdAUC")
)
```

## Arguments

- test_z:

  Matrix of predictors for the test set.

- test_delta:

  Numeric vector of event indicators (1 for event, 0 for censored).

- test_time:

  Numeric vector of observed times.

- betahat:

  Numeric vector of estimated coefficients.

- test_stratum:

  Vector indicating strata for test subjects. Defaults to NULL (single
  stratum).

- train_baseline_obj:

  A list containing the baseline hazard function (typically from
  `get_baseline_hazard`). Required only when `criteria = "IBS"`.

- criteria:

  Metric to calculate: "loss" (Log-Partial Likelihood), "CIndex"
  (Concordance Index), "IBS" (Integrated Brier Score), or "tdAUC"
  (Integrated Time-Dependent AUC). Default is "loss".

## Value

A numeric value representing the performance metric. Returns `NA` if the
metric cannot be computed (e.g., no events in test set). Two silent-`NA`
paths are worth naming explicitly, because neither raises an error:

- `criteria = "IBS"` returns `NA` immediately whenever
  `train_baseline_obj` is `NULL`. Despite the wording of that argument's
  description, omitting it is not an error – the result is simply
  missing.

- Both `"IBS"` and `"tdAUC"` return `NA` whenever the test set contains
  fewer than two distinct event times, since neither quantity can be
  integrated over a single time point. `"loss"` and `"CIndex"` are
  returned before this check and are unaffected.

## Details

For "IBS", the function predicts survival probabilities and converts
them to risk (1 - S). If `riskRegression` fails to provide a
pre-computed IBS, the function manually integrates the Brier score using
the trapezoidal rule.
