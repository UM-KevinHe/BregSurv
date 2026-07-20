<div id="main" class="col-md-9" role="main">

# Plot Cross-Validation Results vs Eta

<div class="ref-description section level2">

Plots cross-validation performance across eta values for `cv.coxkl`,
`cv.coxkl_ridge`, `cv.coxkl_enet`, `cv.cox_MDTL`, `cv.cox_MDTL_ridge`,
`cv.cox_MDTL_enet`, `cv.ncckl`, `cv.ncckl_enet`, `cv.ncc_indi`,
`cv.ncc_MDTL`, or `cv.cox_indi_enet` objects in a Biometrics-style
figure. It displays the cross-validated performance curve (each eta at
its best lambda), a baseline reference at `eta = 0`, and marks the
optimal `eta`.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

``` r
cv.plot(object, line_color = "#7570B3", baseline_color = "#1B9E77", ...)
```

</div>

</div>

<div class="section level2">

## Arguments

-   object:

    A fitted cross-validation result object.

-   line\_color:

    Color for the CV performance curve. Default is `"#7570B3"`.

-   baseline\_color:

    Color for the baseline line. Default is `"#1B9E77"`.

-   ...:

    Additional arguments (currently ignored).

</div>

<div class="section level2">

## Value

A ggplot object (cowplot combined).

</div>

</div>
