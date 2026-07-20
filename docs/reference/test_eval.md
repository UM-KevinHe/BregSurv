<div id="main" class="col-md-9" role="main">

# Evaluate Survival Model Performance

<div class="ref-description section level2">

Computes predictive performance metrics for stratified or unstratified
Cox models. Supports Loss, C-index, Integrated Brier Score (IBS), and
Time-Dependent AUC (tdAUC).

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

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

</div>

</div>

<div class="section level2">

## Arguments

-   test\_z:

    Matrix of predictors for the test set.

-   test\_delta:

    Numeric vector of event indicators (1 for event, 0 for censored).

-   test\_time:

    Numeric vector of observed times.

-   betahat:

    Numeric vector of estimated coefficients.

-   test\_stratum:

    Vector indicating strata for test subjects. Defaults to NULL (single
    stratum).

-   train\_baseline\_obj:

    A list containing the baseline hazard function (typically from
    `get_baseline_hazard`). Required only when `criteria = "IBS"`.

-   criteria:

    Metric to calculate: "loss" (Log-Partial Likelihood), "CIndex"
    (Concordance Index), "IBS" (Integrated Brier Score), or "tdAUC"
    (Integrated Time-Dependent AUC).

</div>

<div class="section level2">

## Value

A numeric value representing the performance metric. Returns `NA` if the
metric cannot be computed (e.g., no events in test set).

</div>

<div class="section level2">

## Details

For "IBS", the function predicts survival probabilities and converts
them to risk (1 - S). If `riskRegression` fails to provide a
pre-computed IBS, the function manually integrates the Brier score using
the trapezoidal rule.

</div>

</div>
