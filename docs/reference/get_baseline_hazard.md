# Estimate the Baseline Cumulative Hazard for a Cox Fit

Computes the Breslow estimator of the baseline cumulative hazard
\\\hat\Lambda_0(t)\\ corresponding to a coefficient vector `beta`,
optionally stratified, by fitting an offset-only Cox model on the
supplied training data. Returns a closure that evaluates
\\\hat\Lambda_0(t)\\ at arbitrary times. Used internally by
[`test_eval`](https://um-kevinhe.github.io/BregSurv/reference/test_eval.md)
(criterion `"IBS"`).

## Usage

``` r
get_baseline_hazard(z, delta, time, beta, stratum = NULL)
```

## Arguments

- z:

  Numeric matrix of training covariates.

- delta:

  Numeric event-indicator vector (1 = event, 0 = censored).

- time:

  Numeric vector of observed event/censoring times.

- beta:

  Numeric vector of estimated coefficients.

- stratum:

  Optional stratum vector. If supplied, a separate baseline hazard is
  estimated within each stratum.

## Value

A list with one element, `predict_baseline`, a function with signature
`function(times, strat_id = NULL)` returning
\\\hat\Lambda_0(\text{times})\\ for the requested stratum.
