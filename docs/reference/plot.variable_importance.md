# Plot Variable Importance (Selection Frequency)

Plots selection frequencies as a horizontal bar chart, ordered from
highest to lowest. By default (threshold = 1), all variables are shown.
If threshold != 1, only variables with selection frequency \> threshold
are shown. If the number of displayed variables exceeds `top`, only the
top `top` variables are plotted.

## Usage

``` r
# S3 method for class 'variable_importance'
plot(
  x,
  threshold = 1,
  top = length(x$freq),
  title = "Top variables by selection frequency",
  ...
)
```

## Arguments

- x:

  An object of class `variable_importance`.

- threshold:

  Numeric between 0 and 1. Default is 1, meaning no threshold filtering.
  If not equal to 1, variables with `SelectionFreq > threshold` are
  plotted.

- top:

  Integer. Maximum number of variables to plot. Default is all
  variables.

- title:

  Character. Plot title. Default "Top variables by selection frequency".

- ...:

  Unused.
