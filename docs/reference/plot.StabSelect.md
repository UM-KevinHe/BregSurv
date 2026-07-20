<div id="main" class="col-md-9" role="main">

# Plot Stability Selection Path

<div class="ref-description section level2">

Generates a visualization of the stability paths. Variables that exceed
the specified probability threshold at any point in the path are
highlighted.

</div>

<div class="section level2">

## Usage

<div class="sourceCode">

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

</div>

</div>

<div class="section level2">

## Arguments

-   x:

    An object of class `StabSelect`.

-   threshold:

    Numeric. The selection probability threshold (0 to 1). Variables
    reaching this frequency are highlighted. Default is 0.75.

-   highlight\_color:

    Color for variables that are selected (stable). Default is "red".

-   background\_color:

    Color for variables that are not selected. Default is "gray".

-   ...:

    Additional arguments passed to methods.

</div>

</div>
