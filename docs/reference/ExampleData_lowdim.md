# Example low-dimensional survival data

A simulated survival dataset in a low-dimensional linear setting with 6
covariates (2 correlated continuous, 2 binary, 2 mean-shifted normals),
Weibull baseline hazard, and controlled censoring. Includes internal
train/test sets, and three external-quality coefficient vectors.

## Usage

``` r
data(ExampleData_lowdim)
```

## Format

A list containing the following elements:

- train:

  A list with components:

  z

  :   Data frame of size \\n\_\mathrm{train}\times 6\\ with covariates
      `Z1`–`Z6`.

  status

  :   Vector of event indicators (`1`=event, `0`=censored).

  time

  :   Numeric vector of observed times \\\min(T, C)\\.

  stratum

  :   Vector of stratum labels (here all `1`).

- test:

  A list with the same structure as `train`, with size
  \\n\_\mathrm{test}\times 6\\ for `z`.

- beta_external_good:

  Numeric vector (length 6; named `Z1`–`Z6`) of Cox coefficients
  estimated on a "Good" external dataset using all `Z1`–`Z6`.

- beta_external_fair:

  Numeric vector (length 6; names `Z1`–`Z6`) of Cox coefficients
  estimated on a "Fair" external dataset using a reduced subset `Z1`,
  `Z3`, `Z5`, `Z6`; coefficients for variables not used are `0`.

- beta_external_poor:

  Numeric vector (length 6; names `Z1`–`Z6`) of Cox coefficients
  estimated on a "Poor" external dataset using `Z1` and `Z5` only;
  remaining entries are `0`.

## Details

Data-generating mechanism:

- Covariates: 6 variables `Z1`–`Z6`.

  - `Z1`, `Z2` ~ bivariate normal with AR(1) correlation \\\rho=0.5\\.

  - `Z3`, `Z4` ~ independent Bernoulli(0.5).

  - `Z5` ~ \\N(2,1)\\, `Z6` ~ \\N(-2,1)\\ (group indicator fixed at 1
    for internal train/test).

- True coefficients: \\\beta = (0.3,-0.3,0.3,-0.3,0.3,-0.3)\\ (length
  6).

- Event times: Weibull baseline hazard \\h_0(t)=\lambda\nu \\
  t^{\nu-1}\\ with \\\lambda=1\\, \\\nu=2\\. Given linear predictor
  \\\eta = Z^\top \beta\\, draw \\U\sim\mathrm{Unif}(0,1)\\ and set
  \$\$T = \left(\frac{-\log U}{\lambda \\ e^{\eta}}\right)^{1/\nu}.\$\$

- Censoring: \\C\sim \mathrm{Unif}(0,\text{ub})\\ with `ub` tuned
  iteratively to achieve the target censoring rate (internal: `0.70`;
  external: `0.50`). Observed time is \\\min(T,C)\\, status is
  \\\mathbf{1}\\T \le C\\\\.

- External coefficients: For each quality level ("Good", "Fair",
  "Poor"), fit a Cox model `Surv(time, status) ~ Z1 + ...` on the
  corresponding external data (Breslow ties) using the specified
  covariate subset; place estimates into a length-6 vector named
  `Z1`–`Z6` with zeros for variables not included.

## Examples

``` r
data(ExampleData_lowdim)
```
