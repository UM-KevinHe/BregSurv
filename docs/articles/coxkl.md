# KL Divergence-Based Transfer Learning for Cox Model

## Notations and Model Setup

Suppose the time-to-event data arise from $`S`$ distinct strata,
representing heterogeneous sources or sampling blocks, where stratum
$`s`$ contains $`n_s`$ subjects and the total sample size is
$`N = \sum_{s=1}^S n_s`$. For subject $`i`$ in stratum $`s`$, let
$`T_i^{(s)}`$ and $`C_i^{(s)}`$ denote the event and censoring times,
respectively. Each subject is associated with $`p`$-dimensional
covariates $`\mathbf{Z}_i^{(s)} \in \mathbb{R}^p`$. We assume that
$`T_i^{(s)}`$ and $`C_i^{(s)}`$ are independent conditional on
$`\mathbf{Z}_i^{(s)}`$. We define the observed time
$`X_i^{(s)} = \min\{T_i^{(s)}, C_i^{(s)}\}`$ and the event indicator
$`\delta_i^{(s)} = \mathbb{I}(T_i^{(s)} \le C_i^{(s)})`$.

Consider the following stratified Cox proportional hazards model:

``` math
\lambda^{(s)}\!\left(t \mid \mathbf{Z}_i^{(s)}\right)
= \lambda_0^{(s)}(t)\exp\!\left\{ r(\mathbf{Z}_i^{(s)}, \boldsymbol{\beta}) \right\},
```

where $`\lambda_0^{(s)}(t)`$ is an unspecified stratum-specific baseline
hazard function, treated as an infinite-dimensional nuisance parameter
that absorbs between-stratum heterogeneity arising from differences in
source populations, clinical practice, or unmeasured confounding, and
$`\boldsymbol{\beta} \in
\mathbb{R}^p`$ is a common regression parameter shared across all
strata. $`r(\mathbf{Z}_i^{(s)}, \boldsymbol{\beta})`$ denotes the
internal risk score; under the standard linear specification,
$`r(\mathbf{Z}_i^{(s)}, \boldsymbol{\beta}) = {\mathbf{Z}_i^{(s)}}^\top
\boldsymbol{\beta}`$.

Assume that, in stratum $`s`$, the observed cohort has $`K^{(s)}`$
unique failure times
$`t_1^{(s)} < t_2^{(s)} < \cdots < t_{K^{(s)}}^{(s)}`$. The stratified
Cox log-partial likelihood is given by

``` math
\ell(\boldsymbol{\beta})
= \sum_{s=1}^{S} \sum_{k=1}^{K^{(s)}} \sum_{i=1}^{n_s}
\delta_i^{(s)}\!\left(t_k^{(s)}\right)
\left[
r(\mathbf{Z}_i^{(s)}, \boldsymbol{\beta})
- \log \left\{
\sum_{j=1}^{n_s} Y_j^{(s)}\!\left(t_k^{(s)}\right)
\exp\!\left\{ r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right\}
\right\}
\right],
```

where $`Y_j^{(s)}(t) = \mathbb{I}\!\left(X_j^{(s)} \ge t\right)`$ is the
at-risk indicator in stratum $`s`$, and $`\delta_i^{(s)}(t) =
\mathbb{I}\!\left(X_i^{(s)} = t,\, \delta_i^{(s)} = 1\right)`$ indicates
whether subject $`i`$ in stratum $`s`$ fails at time $`t`$.

## KL Divergence Formulation

Let $`G`$ be chosen as the negative entropy so that the resulting
Bregman divergence reduces to the Kullback–Leibler divergence. To
construct the probabilistic framework, let $`\mathcal{R}_k^{(s)}`$
denote the at-risk set at $`t_k^{(s)}`$ in stratum $`s`$, let
$`A_k^{(s)}(i)`$ denote the event that subject
$`i \in \mathcal{R}_k^{(s)}`$ fails in the interval
$`[t_k^{(s)},\, t_k^{(s)} +
dt_k^{(s)})`$, and let $`B_k^{(s)}`$ collect all failure and censoring
information up to time $`{t_k^{(s)}}^{-}`$, together with the
information that exactly one failure occurs in
$`[t_k^{(s)},\, t_k^{(s)} + dt_k^{(s)})`$.

Then
$`\{A_k^{(s)}(i) \mid B_k^{(s)} : k=1,\ldots,K^{(s)},\, s=1,\ldots,S\}`$
defines a sequence of conditional experiments. At each event time
$`t_k^{(s)}`$ in stratum $`s`$, the internal working model specifies the
conditional density as

``` math
\mathrm{Multinomial}\!\left(1,\, \mathbf{q}_k^{(s)}\right).
```

The stratum-specific probability mass assigned to subject $`i \in
\mathcal{R}_k^{(s)}`$ under the **internal** model is

``` math
\mathbf{q}_k^{(s)}(i)
:= \mathcal{P}\!\left\{A_k^{(s)}(i) \,\middle|\, B_k^{(s)}\right\}
=
\frac{
\exp\!\left\{ r(\mathbf{Z}_i^{(s)}, \boldsymbol{\beta}) \right\}
}{
\sum_{j=1}^{n_s}
Y_j^{(s)}(t_k^{(s)})
\exp\!\left\{ r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right\}
},
```

where $`\lambda_0^{(s)}(t_k^{(s)})`$ is the stratum-specific baseline
hazard that cancels in the ratio.

To extract information from the external model, we replace the internal
risk score with the external risk score $`\tilde{r}(\cdot)`$, obtained
by applying the external coefficient estimates
$`\tilde{\boldsymbol{\beta}}`$ to the internal cohort. The corresponding
probability mass under the **external** model is

``` math
\mathbf{p}_k^{(s)}(i)
:= \mathcal{P}_{\mathrm{ext}}\!\left\{A_k^{(s)}(i) \,\middle|\, B_k^{(s)}\right\}
=
\frac{
\exp\!\left\{\tilde{r}(\mathbf{Z}_i^{(s)})\right\}
}{
\sum_{j=1}^{n_s}
Y_j^{(s)}(t_k^{(s)})
\exp\!\left\{\tilde{r}(\mathbf{Z}_j^{(s)})\right\}
}.
```

The KL divergence between the external and internal conditional
experiments at time $`t_k^{(s)}`$ is

``` math
\mathbf{d}_{KL}\!\left(\mathbf{p}_k^{(s)} \,\|\, \mathbf{q}_k^{(s)}\right)
= \sum_{i \in \mathcal{R}_k^{(s)}}
\mathbf{p}_k^{(s)}(i)
\log\frac{\mathbf{p}_k^{(s)}(i)}{\mathbf{q}_k^{(s)}(i)}.
```

Accumulating over all strata and failure times yields the total
divergence:

``` math
\mathcal{D}_{\mathrm{KL}}(\mathbf{P} \parallel \mathbf{Q})
=
\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\mathbf{d}_{KL}\!\left(\mathbf{p}_k^{(s)} \,\|\, \mathbf{q}_k^{(s)}\right),
```

which, after substituting the Cox-model expressions, simplifies to

``` math
\mathcal{D}_{\mathrm{KL}}(\mathbf{P} \parallel \mathbf{Q})
=
-\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\sum_{i=1}^{n_s}
\frac{
Y_i^{(s)}(t_k^{(s)})
\exp\!\left\{\tilde{r}(\mathbf{Z}_i^{(s)})\right\}
}{
\sum_{j=1}^{n_s}
Y_j^{(s)}(t_k^{(s)})
\exp\!\left\{\tilde{r}(\mathbf{Z}_j^{(s)})\right\}
}
\left[
r(\mathbf{Z}_i^{(s)},\boldsymbol{\beta})
- \log
\left\{
\sum_{j=1}^{n_s}
Y_j^{(s)}(t_k^{(s)})
\exp\!\left\{r(\mathbf{Z}_j^{(s)},\boldsymbol{\beta})\right\}
\right\}
\right]
+ \Psi,
```

where $`\Psi = \sum_{s,k} \Psi_k^{(s)}`$ does not involve
$`\boldsymbol{\beta}`$.

## Integrated Objective Function

**Proposition.** Under the above construction, the integrated objective
function in the stratified Cox model satisfies

``` math
Q_{\eta}(\boldsymbol{\beta})
= -\ell(\boldsymbol{\beta})
+ \eta \, \mathcal{D}_{\mathrm{KL}}(\mathbf{P} \parallel \mathbf{Q})
\propto
-\sum_{s=1}^{S} \sum_{i=1}^{n_s} \left\{
\frac{\delta_i^{(s)} + \eta \tilde{\delta}_i^{(s)}}{1 + \eta}
\cdot r(\mathbf{Z}_i^{(s)}, \boldsymbol{\beta})
- \delta_i^{(s)} \log \left[\sum_{j=1}^{n_s} Y_j(X_i^{(s)})
\exp\left(r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right) \right]
\right\},
```

where the externally induced pseudo-event weight is defined as

``` math
\tilde{\delta}_i^{(s)}
= \sum_{k=1}^{K^{(s)}}
\frac{
Y_{i}(t_k^{(s)}) \exp\{ \tilde{r}(\mathbf{Z}_{i}^{(s)}) \}
}{
\sum_{j=1}^{n_s} Y_{j}(t_k^{(s)}) \exp\{ \tilde{r}(\mathbf{Z}_{j}^{(s)}) \}
},
```

$`\ell(\boldsymbol{\beta})`$ is the internal stratified Cox log-partial
likelihood defined above, and $`\eta \ge 0`$ is the integration weight.
