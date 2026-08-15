# Example high-dimensional survival data

A simulated high-dimensional survival dataset under a linear Cox model
with 50 covariates (6 signals + 44 noise variables), a Weibull baseline
hazard, and controlled censoring. The dataset includes internal
train/test samples and multiple externally estimated coefficient vectors
representing different forms of coefficient perturbation.

## Usage

``` r
data(ExampleData_highdim)
```

## Format

A list with the following components:

- train:

  A list containing:

  z

  :   A data frame of dimension \\n\_{\mathrm{train}} \times 50\\
      containing covariates `Z1`–`Z50`.

  status

  :   A numeric vector of event indicators (`1`=event, `0`=censored).

  time

  :   A numeric vector of observed survival times \\\min(T, C)\\.

  stratum

  :   A vector of stratum labels (here all equal to `1`).

- test:

  A list with the same structure as `train`, with covariates of
  dimension \\n\_{\mathrm{test}} \times 50\\.

- beta_external:

  A numeric vector of length 50 (named `Z1`–`Z50`) containing Cox
  regression coefficients estimated from an external dataset using only
  `Z1`–`Z6`, with zeros for `Z7`–`Z50`.

- beta_external.multi1:

  External coefficient vector with additive Gaussian noise applied to
  the nonzero entries of `beta_external`, preserving the original
  sparsity pattern.

- beta_external.multi2:

  External coefficient vector with weak Gaussian noise applied to all 50
  coefficients, yielding a dense but low-magnitude perturbation.

- beta_external.multi3:

  A scaled version of `beta_external` with uniformly attenuated signal
  strength.

- beta_external.multi4:

  External coefficient vector in which a subset of the nonzero
  coefficients in `beta_external` have their signs randomly flipped.

- beta_external.multi5:

  External coefficient vector with weakened original signals and a small
  number of newly introduced weak signals among previously zero
  coefficients.

## Details

Data-generating mechanism:

- **Covariates:** 50 covariates with true signals in `Z1`–`Z6` and noise
  variables in `Z7`–`Z50`.

  - `Z1`, `Z2`: bivariate normal with AR(1) correlation \\\rho = 0.5\\.

  - `Z3`, `Z4`: independent Bernoulli(0.5).

  - `Z5` \\\sim N(2, 1)\\, `Z6` \\\sim N(-2, 1)\\.

  - `Z7`–`Z50`: multivariate normal with AR(1) correlation \\\rho =
    0.5\\.

- **True coefficients:** \\\beta = (0.3, -0.3, 0.3, -0.3, 0.3, -0.3, 0,
  \ldots, 0)\\.

- **Event times:** Weibull baseline hazard \\h_0(t) = \lambda \nu
  t^{\nu - 1}\\ with \\\lambda = 1\\ and \\\nu = 2\\. Given linear
  predictor \\\eta = Z^\top \beta\\, event times are generated as \$\$T
  = \left(\frac{-\log U}{\lambda e^{\eta}}\right)^{1/\nu}, \quad U \sim
  \mathrm{Unif}(0,1).\$\$

- **Censoring:** \\C \sim \mathrm{Unif}(0, \mathrm{ub})\\, where `ub` is
  tuned to achieve the target censoring rate (internal: 0.70; external:
  0.50). The observed time is \\\min(T, C)\\ with event indicator
  \\\mathbf{1}\\T \le C\\\\.

- **External coefficients:** Cox regression models with Breslow ties are
  fitted on the external dataset using `Z1`–`Z6`. The resulting
  estimates are embedded into length-50 coefficient vectors, with
  additional variants constructed to represent different forms of
  coefficient perturbation and distributional shift.

**External coefficients: name present-and-zero vs. name absent.** Every
external coefficient vector bundled here is fully populated and fully
named over the complete covariate space `Z1`–`Z50`. Consequently
[`align_beta`](https://um-kevinhe.github.io/BregSurv/reference/align_beta.md)
never zero-pads them, and
[`align_beta_Q`](https://um-kevinhe.github.io/BregSurv/reference/align_beta_Q.md)
with `Q = NULL` returns the full identity rather than a masked identity.
The distinction is semantic: a covariate whose name is *present* with
value 0 asserts an external estimate of exactly zero and is penalized
toward zero like any other external coefficient, whereas a covariate
whose name is *absent* is treated as carrying no external information –
it is zero-padded and, under the Mahalanobis penalty, left unpenalized.
The structural zeros in these vectors (for example `Z7`–`Z50` in
`beta_external`, which the external model did not fit) are therefore of
the first kind: they are borrowed as genuine external estimates of zero.

## Examples

``` r
data(ExampleData_highdim)
```
