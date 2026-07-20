<div id="main" class="col-md-9" role="main">

# Evaluate NCC Model: Loss, C-Index, and Brier Score

<div class="ref-description section level2">

Evaluate NCC Model: Loss, C-Index, and Brier Score

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
test_eval_ncc(
  z_ncc,
  case,
  set_id,
  betahat,
  criteria = c("loss", "CIndex", "Brier")
)
```

</div>

</div>

<div class="section level2">

## Arguments

-   z\_ncc:

    Matrix of covariates for NCC data (rows = subjects).

-   case:

    Integer or logical vector (0/1) indicating cases.

-   set\_id:

    Vector of matched set identifiers.

-   betahat:

    Numeric vector of estimated coefficients.

-   criteria:

    "loss", "CIndex", or "Brier".

</div>

<div class="section level2">

## Value

Numeric performance metric.

</div>

</div>
