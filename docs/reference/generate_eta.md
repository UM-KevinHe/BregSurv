# Generate a Sequence of Tuning Parameters (eta)

Produces a numeric vector of `eta` values to be used in Cox–KL model.

## Usage

``` r
generate_eta(method = "exponential", n = 10, max_eta = 5, min_eta = 0)
```

## Arguments

- method:

  Character string selecting how to generate `eta`: “linear” or
  “exponential”. Default is “exponential”. for an exponentially spaced
  sequence scaled to `max_eta`. Default is `"exponential"`.

- n:

  Integer, the number of `eta` values to generate. Default is 10.

- max_eta:

  Numeric, the maximum value of `eta` in the sequence. Default is 5.

- min_eta:

  Numeric, the minimum value of `eta` in the sequence. Default is 0.

## Value

Numeric vector of length `n` containing the generated `eta` values.

## Details

- *Exponential*: values are formed by exponentiating a grid from
  `log(1)` to `log(100)`, then linearly rescaling to the interval
  `[0, max_eta]`. Thus the smallest value equals `0` and the largest
  equals `max_eta`.

- *Linear*: the current implementation calls
  `seq(min_eta, max_eta, length.out = n)` and therefore assumes a
  numeric object `min_eta` exists in the calling environment.

Only the exact strings “linear” and “exponential” are supported; other
values for `method` will result in an error because `eta_values` is
never created.

## Examples

``` r
# Generate 10 exponentially spaced eta values up to 5
generate_eta(method = "exponential", n = 10, max_eta = 5)
#>  [1] 0.00000000 0.03374245 0.09002825 0.18391863 0.34053721 0.60179276
#>  [7] 1.03759328 1.76455236 2.97719318 5.00000000

# Generate 5 linearly spaced eta values up to 3
generate_eta(method = "linear", n = 5, min_eta= 0, max_eta = 3)
#> [1] 0.00 0.75 1.50 2.25 3.00
```
