<div id="main" class="col-md-9" role="main">

# Predict Survival Probabilities From a Baseline-Hazard Object

<div class="ref-description section level2">

Given a per-subject linear predictor (risk score) and a baseline
cumulative hazard object as returned by `get_baseline_hazard`, returns
the predicted survival probability matrix at the supplied evaluation
times. Used internally by `test_eval` for IBS computation.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
predict_surv_prob(test_RS, eval_times, train_baseline_obj, test_stratum = NULL)
```

</div>

</div>

<div class="section level2">

## Arguments

-   test\_RS:

    Numeric vector of risk scores (\\(Z\\beta\\)) for the test subjects.

-   eval\_times:

    Numeric vector of times at which to evaluate \\(S(t)\\).

-   train\_baseline\_obj:

    A list with element `predict_baseline`, as returned by
    `get_baseline_hazard`.

-   test\_stratum:

    Optional stratum vector for the test subjects. Defaults to a single
    stratum.

</div>

<div class="section level2">

## Value

A numeric matrix of dimension `length(test_RS) x length(eval_times)` of
predicted survival probabilities
\\(\\exp(-e^{Z\\beta}\\,\\hat\\Lambda\_0(t))\\).

</div>

</div>
