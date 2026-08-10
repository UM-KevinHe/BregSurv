# Plot Stability Selection Path

Generates a visualization of the stability paths. Variables that exceed
the specified probability threshold at any point in the path are
highlighted.

## Usage

``` r
# S3 method for class 'StabSelect'
plot(
  x,
  threshold = 0.75,
  highlight_color = "red",
  background_color = "gray",
  ...
)
```

## Arguments

- x:

  An object of class `StabSelect`.

- threshold:

  Numeric. The selection probability threshold (0 to 1). Variables
  reaching this frequency are highlighted. Default is 0.75.

- highlight_color:

  Color for variables that are selected (stable). Default is "red".

- background_color:

  Color for variables that are not selected. Default is "gray".

- ...:

  Additional arguments passed to methods.
