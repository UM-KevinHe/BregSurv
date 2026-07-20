<div id="main" class="col-md-9" role="main">

# Estimate the Baseline Cumulative Hazard for a Cox Fit

<div class="ref-description section level2">

Computes the Breslow estimator of the baseline cumulative hazard
\\(\\hat\\Lambda\_0(t)\\) corresponding to a coefficient vector `beta`,
optionally stratified, by fitting an offset-only Cox model on the
supplied training data. Returns a closure that evaluates
\\(\\hat\\Lambda\_0(t)\\) at arbitrary times. Used internally by
`test_eval` (criterion `"IBS"`).

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
get_baseline_hazard(z, delta, time, beta, stratum = NULL)
```

</div>

</div>

<div class="section level2">

## Arguments

-   z:

    Numeric matrix of training covariates.

-   delta:

    Numeric event-indicator vector (1 = event, 0 = censored).

-   time:

    Numeric vector of observed event/censoring times.

-   beta:

    Numeric vector of estimated coefficients.

-   stratum:

    Optional stratum vector. If supplied, a separate baseline hazard is
    estimated within each stratum.

</div>

<div class="section level2">

## Value

A list with one element, `predict_baseline`, a function with signature
`function(times, strat_id = NULL)` returning
\\(\\hat\\Lambda\_0(\\text{times})\\) for the requested stratum.

</div>

</div>
