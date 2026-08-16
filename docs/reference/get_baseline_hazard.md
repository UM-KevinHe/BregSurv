# Estimate the Baseline Cumulative Hazard for a Cox Fit

Computes the Breslow estimator of the baseline cumulative hazard
\\\hat\Lambda_0(t)\\ corresponding to a coefficient vector `beta`,
optionally stratified. Returns a closure that evaluates
\\\hat\Lambda_0(t)\\ at arbitrary times. Used by
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
\\\hat\Lambda_0(\text{times})\\ for the requested stratum. When
`stratum` is `NULL` the `strat_id` argument is ignored; otherwise an
unseen `strat_id` is an error.

## Details

Within each stratum the estimator is \$\$\hat\Lambda_0(t) = \sum\_{t_k
\le t} \frac{d_k}{\sum\_{j:\\ T_j \ge t_k} \exp(Z_j^\top \beta)},\$\$
where \\t_1 \< t_2 \< \cdots\\ are the distinct observed event times and
\\d_k\\ is the number of events at \\t_k\\ (Breslow handling of ties).
Each risk set is weighted by \\\exp(Z^\top\beta)\\, so the returned
quantity is the baseline hazard of the supplied model rather than the
marginal (Nelson-Aalen) hazard of the sample; the two coincide only when
`beta` is zero.

The returned function is a right-continuous step function: it is \\0\\
before the first event time and constant at \\\hat\Lambda_0\\ of the
last event time thereafter. A stratum containing no events yields an
identically-zero baseline rather than an error.
