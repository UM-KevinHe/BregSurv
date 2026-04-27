# Predict Survival Probabilities From a Baseline-Hazard Object

Given a per-subject linear predictor (risk score) and a baseline
cumulative hazard object as returned by
[`get_baseline_hazard`](https://um-kevinhe.github.io/SurvBregDiv/reference/get_baseline_hazard.md),
returns the predicted survival probability matrix at the supplied
evaluation times. Used internally by
[`test_eval`](https://um-kevinhe.github.io/SurvBregDiv/reference/test_eval.md)
for IBS computation.

## Usage

``` r
predict_surv_prob(test_RS, eval_times, train_baseline_obj, test_stratum = NULL)
```

## Arguments

- test_RS:

  Numeric vector of risk scores (\\Z\beta\\) for the test subjects.

- eval_times:

  Numeric vector of times at which to evaluate \\S(t)\\.

- train_baseline_obj:

  A list with element `predict_baseline`, as returned by
  [`get_baseline_hazard`](https://um-kevinhe.github.io/SurvBregDiv/reference/get_baseline_hazard.md).

- test_stratum:

  Optional stratum vector for the test subjects. Defaults to a single
  stratum.

## Value

A numeric matrix of dimension `length(test_RS) x length(eval_times)` of
predicted survival probabilities
\\\exp(-e^{Z\beta}\\\hat\Lambda_0(t))\\.
