# NCC KL Divergence-Based Transfer Learning

## Matched-Set Notation and Model Setup

The nested case–control (NCC) design provides an efficient alternative
for fitting Cox proportional hazards models when covariate measurement
for the full cohort is costly. At each observed failure time, the
failing subject (the case) is retained, while a number of controls are
randomly sampled from the corresponding risk set. The resulting sampled
matched sets are then analyzed using conditional likelihood.

We first introduce the matched-set notation. Let $`\mathcal{R}_k^{(s)}`$
denote the at-risk set at time $`t_k^{(s)}`$ in stratum $`s`$. For the
failure at $`t_k^{(s)}`$, we randomly sample $`m`$ controls from
$`\mathcal{R}_k^{(s)}`$, excluding the failing subject and matched by
stratum. The failing subject together with the sampled controls forms a
matched set of size $`m+1`$, which we denote by
$`\tilde{\mathcal{R}}_k^{(s)}`$. Since each stratum contains $`K^{(s)}`$
unique failure times, the NCC design yields a total of
$`M = \sum_{s=1}^{S} K^{(s)}`$ matched sets across all strata.

Under this construction, the matched set $`\tilde{\mathcal{R}}_k^{(s)}`$
forms a subset of the full at-risk set $`\mathcal{R}_k^{(s)}`$.
Following the probabilistic framework introduced in the Cox KL
divergence vignette, we similarly define a sequence of conditional
experiments
$`\{\tilde A_k^{(s)}(i) \mid \tilde B_k^{(s)} : k=1,\ldots,K^{(s)},\, s=1,\ldots,S\}`$.
Here $`\tilde A_k^{(s)}(i)`$ denotes the event that subject
$`i \in \tilde{\mathcal{R}}_k^{(s)}`$ is the failing subject in the
$`(s,k)`$-th matched set, and $`\tilde B_k^{(s)}`$ collects all failure
and censoring information up to time $`{t_k^{(s)}}^{-}`$, together with
the information that the matched set $`\tilde{\mathcal{R}}_k^{(s)}`$ has
been formed by sampling $`m`$ controls from $`\mathcal{R}_k^{(s)}`$ and
that exactly one failure occurs in
$`[t_k^{(s)},\, t_k^{(s)} + dt_k^{(s)})`$.

Consequently, within the $`(s,k)`$-th matched set, the NCC working model
similarly specifies the conditional density within the matched set as a
Multinomial distribution with a single trial, i.e.,

``` math
\mathrm{Multinomial}\!\left(1,\, \tilde{\mathbf{q}}_k^{(s)}\right),
```

where the probability mass assigned to subject
$`i \in \tilde{\mathcal{R}}_k^{(s)}`$ is

``` math
\tilde{\mathbf{q}}_k^{(s)}(i)
:= \mathcal{P}\!\left\{\tilde A_k^{(s)}(i) \,\middle|\, \tilde B_k^{(s)}\right\}
=
\frac{
\exp\!\left\{ r(\mathbf{Z}_i^{(s)}, \boldsymbol{\beta}) \right\}
}{
\sum_{j \in \tilde{\mathcal{R}}_k^{(s)}}
\exp\!\left\{ r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right\}
}.
```

## KL Divergence Formulation

Because the full at-risk set $`\mathcal{R}_k^{(s)}`$ is not used, the
conditional probability $`\tilde{\mathbf{q}}_k^{(s)}(i)`$ generally
differs from the corresponding conditional probability
$`\mathbf{q}_k^{(s)}(i)`$ in the internal Cox working model.
Nevertheless, the probabilities $`\tilde{\mathbf{q}}_k^{(s)}(i)`$ remain
valid conditional probabilities within the matched set, since

``` math
\sum_{i \in \tilde{\mathcal{R}}_k^{(s)}} \tilde{\mathbf{q}}_k^{(s)}(i) = 1.
```

When the matched set is formed by random sampling from
$`\mathcal{R}_k^{(s)}`$, the denominator satisfies

``` math
\mathbb{E}\!\left[
\sum_{j \in \tilde{\mathcal{R}}_k^{(s)}}
\exp\!\left\{ r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right\}
\right]
\approx
\frac{m}{|\mathcal{R}_k^{(s)}|}
\sum_{j \in \mathcal{R}_k^{(s)}}
\exp\!\left\{ r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right\},
```

when the risk-set size $`|\mathcal{R}_k^{(s)}|`$ is large. However, it
is important to note that these two probabilities are defined under
different conditioning events: $`\mathbf{q}_k^{(s)}(i)`$ conditions on
the full at-risk set $`\mathcal{R}_k^{(s)}`$, whereas
$`\tilde{\mathbf{q}}_k^{(s)}(i)`$ conditions on the sampled matched set
$`\tilde{\mathcal{R}}_k^{(s)}`$. Consequently, the two probabilities are
not directly comparable and do not satisfy a simple proportional
relationship. Numerically, the value of
$`\tilde{\mathbf{q}}_k^{(s)}(i)`$ is typically larger than
$`\mathbf{q}_k^{(s)}(i)`$ because the matched set constitutes only a
subsample of the full risk set, resulting in a smaller normalization set
in the denominator. However, such a comparison should be interpreted
with caution, since the two probabilities correspond to different
conditional experiments. In particular, under the NCC construction the
probability $`\tilde{\mathbf{q}}_k^{(s)}(i)`$ is defined only for
subjects included in the sampled matched set, whereas subjects in the
full risk set who are not sampled into the matched set do not have a
corresponding probability defined in this conditional experiment.

To extract information from the external model under the NCC design, we
similarly replace the internal risk score by the external risk score
$`\tilde r(\cdot)`$ obtained from the external coefficient estimates
$`\tilde{\boldsymbol\beta}`$. Analogous to the construction of
$`\tilde{\mathbf q}_k^{(s)}(i)`$, we define the corresponding
probability mass under the **external** model within the matched set as

``` math
\tilde{\mathbf p}_k^{(s)}(i)
:= 
\mathcal P_{\mathrm{ext}}\!\left\{\tilde A_k^{(s)}(i)\mid \tilde B_k^{(s)}\right\},
\qquad i\in\tilde{\mathcal R}_k^{(s)},
```

which takes the same multinomial form as in the Cox construction but
with the denominator restricted to the matched set
$`\tilde{\mathcal R}_k^{(s)}`$.

To quantify the discrepancy between the external and internal
conditional probabilities for the $`(s,k)`$-th matched set, we define
the KL divergence:

``` math
\mathbf d_{KL}\!\left(\tilde{\mathbf p}_k^{(s)}\|\tilde{\mathbf q}_k^{(s)}\right)
=
\sum_{i\in\tilde{\mathcal R}_k^{(s)}}
\tilde{\mathbf p}_k^{(s)}(i)
\log
\frac{\tilde{\mathbf p}_k^{(s)}(i)}
{\tilde{\mathbf q}_k^{(s)}(i)}.
```

Accumulating over all matched sets gives

``` math
\mathcal D_{KL}(\tilde{\mathbf P}\|\tilde{\mathbf Q})
=
\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\mathbf d_{KL}\!\left(\tilde{\mathbf p}_k^{(s)}\|\tilde{\mathbf q}_k^{(s)}\right)
=
-\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\sum_{i\in\tilde{\mathcal R}_k^{(s)}}
\tilde{\mathbf p}_k^{(s)}(i)
\Bigg[
r(\mathbf Z_i^{(s)},\boldsymbol\beta)
-
\log
\Bigg\{
\sum_{j\in\tilde{\mathcal R}_k^{(s)}}
\exp\!\left\{r(\mathbf Z_j^{(s)},\boldsymbol\beta)\right\}
\Bigg\}
\Bigg]
+
\tilde\Psi,
```

where $`\tilde\Psi`$ does not involve $`\boldsymbol\beta`$.

Let $`\xi_{ki}^{(s)}`$ denote the indicator that subject $`i`$ is the
observed failure in the $`(s,k)`$-th matched set, so that the internal
NCC conditional log-likelihood is

``` math
\ell_{\mathrm{NCC}}(\boldsymbol\beta)
=
\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\sum_{i\in\tilde{\mathcal R}_k^{(s)}}
\xi_{ki}^{(s)}
\Bigg[
r(\mathbf Z_i^{(s)},\boldsymbol\beta)
-
\log
\Bigg\{
\sum_{j\in\tilde{\mathcal R}_k^{(s)}}
\exp\!\left\{r(\mathbf Z_j^{(s)},\boldsymbol\beta)\right\}
\Bigg\}
\Bigg].
```

## Integrated Objective Function

**Proposition.** Under the NCC construction, the integrated objective
function satisfies

``` math
Q_{\eta}^{\mathrm{NCC}}(\boldsymbol\beta)
= -\ell_{\mathrm{NCC}}(\boldsymbol\beta)
+ \eta\,\mathcal D_{KL}(\tilde{\mathbf P}\|\tilde{\mathbf Q})
\propto
-\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\sum_{i\in\tilde{\mathcal R}_k^{(s)}}
\left\{
\frac{\xi_{ki}^{(s)}+\eta\,\tilde{\mathbf p}_k^{(s)}(i)}{1+\eta}
\,r(\mathbf Z_i^{(s)},\boldsymbol\beta)
-
\xi_{ki}^{(s)}
\log
\left[
\sum_{j\in\tilde{\mathcal R}_k^{(s)}}
\exp\!\left\{r(\mathbf Z_j^{(s)},\boldsymbol\beta)\right\}
\right]
\right\},
```

where $`\ell_{\mathrm{NCC}}(\boldsymbol\beta)`$ is the internal NCC
conditional log-likelihood, $`\tilde{\mathbf p}_k^{(s)}(i)`$ denotes the
externally induced pseudo-event weight within the $`(s,k)`$-th matched
set that can be fully precomputed before optimization, and $`\eta\ge 0`$
is the integration weight.

It is worth emphasizing that, although the NCC design is commonly used
as a computationally efficient surrogate for the Cox model and yields
consistent estimators of the regression coefficients, the KL divergence
defined under the NCC construction is not a direct surrogate for the
Cox-model KL divergence. This is because the two KL quantities are
defined with respect to different conditional experiments. Consequently,
the corresponding probability models, and hence the associated KL
divergences, are defined on different probability spaces.
