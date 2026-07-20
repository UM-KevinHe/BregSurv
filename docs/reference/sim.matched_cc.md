<div id="main" class="col-md-9" role="main">

# Simulate 1:m matched case-control data with mean/SD control

<div class="ref-description section level2">

Internal function to simulate 1:m matched data. Each stratum contains
exactly one case. The case is sampled with probability proportional to
exp(eta), where eta = theta\_stratum + Z %\*% beta.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
sim.matched_cc(
  n_stratum,
  m,
  beta,
  rho = 0.8,
  mu_Z = 0,
  sd_Z = 1,
  stratum_sd = 0.5,
  seed = NULL
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   n\_stratum:

    Number of matched strata (sets).

-   m:

    Number of controls per case (&gt;=1).

-   beta:

    Numeric vector of coefficients (length p).

-   rho:

    Correlation parameter for Z within stratum (equicorrelation).

-   mu\_Z:

    Mean vector for Z. Scalar or length p.

-   sd\_Z:

    Standard deviation vector for Z. Scalar or length p, must be
    positive.

-   stratum\_sd:

    SD of stratum random intercepts.

-   seed:

    Optional RNG seed.

</div>

<div class="section level2">

## Value

A list containing matched data frames and simulation metadata.

</div>

</div>
