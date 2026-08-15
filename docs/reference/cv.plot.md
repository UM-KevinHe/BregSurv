# Plot Cross-Validation Results vs Eta

Plots cross-validation performance across eta values for `cv.coxkl`,
`cv.cox_MDTL`, `cv.cox_indi`, `cv.ncckl`, `cv.ncc_MDTL`, `cv.ncc_indi`,
`cv.coxkl_ridge`, `cv.cox_MDTL_ridge`, `cv.coxkl_enet`,
`cv.cox_MDTL_enet`, `cv.cox_indi_enet`, `cv.ncckl_enet`,
`cv.ncc_MDTL_enet`, or `cv.ncc_indi_enet` objects in a Biometrics-style
figure. It displays the cross-validated performance curve (each eta at
its best lambda), a baseline reference at `eta = 0`, and marks the
optimal `eta`.

The output of
[`cv.coxkl_ties`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_ties.md)
is also covered, because it carries class `"cv.coxkl"`.

## Usage

``` r
cv.plot(object, line_color = "#7570B3", baseline_color = "#1B9E77", ...)
```

## Arguments

- object:

  The S3 object returned by one of the supported `cv.*` functions listed
  above – not a plain `data.frame`. The unpenalized classes are read
  from their `internal_stat` component and the ridge/elastic-net classes
  from their `integrated_stat.best_per_eta` component; the `criteria`
  component of either is used to label the axis and to decide whether
  the optimum is a minimum or a maximum. An object of any other class
  stops with an error.

- line_color:

  Color for the CV performance curve. Default is `"#7570B3"`.

- baseline_color:

  Color for the baseline line. Default is `"#1B9E77"`.

- ...:

  Additional arguments (currently ignored).

## Value

A ggplot object (cowplot combined).
