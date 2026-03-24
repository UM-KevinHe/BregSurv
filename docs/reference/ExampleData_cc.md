# Example Data for Conditional Logistic Regression

A simulated dataset generated for 1:M matched case-control studies
(Conditional Logistic Regression, CLR). The data is organized into
matched sets (strata), with exactly one case (`y=1`) and \\m=4\\
controls (`y=0`) per set.

## Usage

``` r
data(ExampleData_cc)
```

## Format

A list containing the following elements:

- train:

  A list with components for training the CLR model:

  z

  :   Numeric matrix of covariates (dimension
      \\n\_{\mathrm{train}}\times 6\\) with columns named `Z1`–`Z6`.

  y

  :   Binary outcome vector (`1`=case, `0`=control).

  stratum

  :   Integer vector identifying the matched set for each observation
      (200 unique strata in `train`).

- test:

  A list with the same structure as `train`, used for external
  evaluation (500 unique strata in `test`).

- beta_external:

  Numeric vector (length 6) of CLR coefficients estimated on a separate
  external dataset using all `Z1`–`Z6`.

## Details

Data-generating mechanism:

- **Study design:** 1:4 matched case-control study (\\m=4\\ controls per
  case).

- **Covariates:** 6 variables (`Z1`–`Z6`) drawn from a correlated
  multivariate normal distribution.

- **True coefficients:** \\\beta = (1, -1, 1, -1, 1, -1)\\.

- **Set-specific effect:** A random stratum-specific intercept
  \\\theta_i \sim N(0, 0.5^2)\\ is added to the linear predictor; it is
  eliminated by CLR conditioning.

- **Outcome generation:** Within each stratum \\i\\, the single case
  (`y=1`) is selected with probability proportional to \\\exp(\theta_i +
  Z^\top \beta)\\.

- **External beta estimation:** `beta_external` is obtained by fitting
  `ncc` on a separate simulated dataset with a slightly different true
  coefficient vector \\\beta\_{\mathrm{ext}} = (0.8, -0.8, \dots)\\ and
  correlation \\\rho = 0.3\\, using the `"breslow"` tie approximation.

## Examples

``` r
data(ExampleData_cc)
```
