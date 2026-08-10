# Cox KL Divergence: Handling Tied Event Times

When multiple failures occur at the same recorded time point—such as
with daily event recording, grouped clinical visit schedules, or
discretized follow-up times—the underlying risk-set contribution becomes
substantially more complex, and the associated conditional-experiments
structure as well as the stratum-specific probability mass functions
must be modified accordingly. We consider two standard approaches for
handling ties: Cox’s exact method (Cox 1972) and the Breslow
approximation (Breslow 1974). Because these two approaches construct the
probability mass in fundamentally different ways, we discuss them
separately.

## Cox’s Exact Method

In stratum $`s`$, suppose that at time $`t_k^{(s)}`$,
$`d_k^{(s)} = \sum_{i=1}^{n_s}
\delta_i^{(s)}(t_k^{(s)}) \ge 1`$ subjects fail. Let
$`\mathcal{R}_k^{(s)}`$ denote the at-risk set with cardinality
$`n_k^{(s)}`$, and let

``` math
\mathcal{D}_k^{(s)}
= \bigl\{ i \in \mathcal{R}_k^{(s)} : \delta_i^{(s)}(t_k^{(s)}) = 1 \bigr\}
```

denote the observed failure (tie) set of size $`d_k^{(s)}`$. Let
$`\mathcal{R}_k^{(s)}(d_k^{(s)})`$ denote the collection of all subsets
of size $`d_k^{(s)}`$ drawn from $`\mathcal{R}_k^{(s)}`$, with
cardinality $`c_k^{(s)} =
\binom{n_k^{(s)}}{d_k^{(s)}}`$.

### Probabilistic Framework

Under Cox’s exact method, for stratum $`s`$ and event time
$`t_k^{(s)}`$, let $`H
\in \mathcal{R}_k^{(s)}(d_k^{(s)})`$ denote a candidate failure subset
of size $`d_k^{(s)}`$, and define the event $`A_k^{(s)}(H)`$ to indicate
that the subjects in $`H`$ fail in the interval
$`[t_k^{(s)},\, t_k^{(s)} + dt_k^{(s)})`$. Let $`B_k^{(s)}`$ denote all
censoring and failure information up to $`{t_k^{(s)}}^{-}`$, together
with the information that exactly $`d_k^{(s)}`$ failures occur in that
interval. Then

``` math
\bigl\{\, A_k^{(s)}(H) \mid B_k^{(s)} :
H \in \mathcal{R}_k^{(s)}(d_k^{(s)}),\
k=1,\ldots,K^{(s)},\
s=1,\ldots,S
\,\bigr\}
```

remains a well-defined sequence of conditional experiments. At each
event time $`t_k^{(s)}`$, the internal working model specifies the
conditional density as $`\mathrm{Multinomial}(1, \mathbf{q}_k^{(s)})`$.
In contrast to the no-ties case where the support consists of
$`n_k^{(s)}`$ individual subjects, under Cox’s exact method the support
is given by the $`c_k^{(s)}`$ candidate failure subsets of size
$`d_k^{(s)}`$.

### Internal and External Probability Mass Functions

The stratum-specific probability mass at time $`t_k^{(s)}`$ under the
**internal** model is

``` math
\mathbf{q}_k^{(s)}(H)
:= \mathcal{P}\!\left\{ A_k^{(s)}(H) \mid B_k^{(s)} \right\}
=
\frac{
\exp\!\left\{ r_{k}(H;\boldsymbol{\beta}) \right\}
}{
\sum_{H' \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\exp\!\left\{ r_{k}(H';\boldsymbol{\beta}) \right\}
},
```

where

``` math
r_{k}(H;\boldsymbol{\beta})
:=
\sum_{j \in H} r(\mathbf{Z}_j^{(s)},\boldsymbol{\beta})
```

denotes the sum of internal risk scores over subjects in the candidate
failure subset $`H`$.

Replacing the internal risk scores with the external risk scores
$`\tilde{r}(\mathbf{Z}_i^{(s)})`$, the probability mass under the
**external** model is

``` math
\mathbf{p}_k^{(s)}(H)
:= \mathcal{P}_{\mathrm{ext}}\!\left\{ A_k^{(s)}(H) \mid B_k^{(s)} \right\}
=
\frac{
\exp\!\left\{ \tilde{r}_{k}(H) \right\}
}{
\sum_{H' \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\exp\!\left\{ \tilde{r}_{k}(H') \right\}
},
```

where

``` math
\tilde{r}_{k}(H)
:=
\sum_{j \in H}
\tilde{r}(\mathbf{Z}_j^{(s)})
```

denotes the sum of external risk scores over subjects in $`H`$.

### KL Divergence

The KL divergence between the external and internal models at time
$`t_k^{(s)}`$ in stratum $`s`$ is

``` math
\mathbf{d}_{KL}\!\left(\mathbf{p}_k^{(s)} \,\|\, \mathbf{q}_k^{(s)}\right)
= \sum_{H \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\mathbf{p}_k^{(s)}(H)
\log\frac{\mathbf{p}_k^{(s)}(H)}{\mathbf{q}_k^{(s)}(H)}.
```

Substituting the expressions above and accumulating over all strata and
failure times yields

``` math
\mathcal{D}_{\mathrm{KL}}(\mathbf{P} \parallel \mathbf{Q})
\propto
-\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\left(
\sum_{H \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\mathbf{p}_k^{(s)}(H)\, r_k(H;\boldsymbol{\beta})
\right)
+
\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\log
\left\{
\sum_{H' \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\exp\!\left\{
r_k(H';\boldsymbol{\beta})
\right\}
\right\}.
```

### Integrated Objective Function

**Proposition (Exact Ties).** Under the stratified Cox model with exact
ties, the integrated objective
$`Q_{\eta}(\boldsymbol{\beta}) = -\ell(\boldsymbol{\beta})
+ \eta\,\mathcal{D}_{\mathrm{KL}}(\mathbf{P}\parallel\mathbf{Q})`$
admits the representation

``` math
Q_{\eta}(\boldsymbol{\beta})
\propto
-\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\left\{
\frac{
r_k(\mathcal{D}_k^{(s)};\boldsymbol{\beta})
+
\eta
\sum_{H \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\mathbf{p}_k^{(s)}(H)\,r_k(H;\boldsymbol{\beta})
}{1+\eta}
-
\log
\left[
\sum_{H'\in\mathcal{R}_k^{(s)}(d_k^{(s)})}
\exp\!\bigl(r_k(H';\boldsymbol{\beta})\bigr)
\right]
\right\},
```

where
$`r_k(\mathcal{D}_k^{(s)};\boldsymbol{\beta}) = \sum_{j\in\mathcal{D}_k^{(s)}}
r(\mathbf{Z}_j^{(s)},\boldsymbol{\beta})`$.

Furthermore, under the linear specification
$`r(\mathbf{Z}_j^{(s)},\boldsymbol{\beta}) = {\mathbf{Z}_j^{(s)}}^\top\boldsymbol{\beta}`$,
define

``` math
\mathbf{w}_{\mathcal{D}_k}^{(s)}
= \sum_{j\in\mathcal{D}_k^{(s)}} \mathbf{Z}_j^{(s)},
\qquad
\mathbf{w}_H^{(s)}
= \sum_{j\in H} \mathbf{Z}_j^{(s)},
\qquad
\tilde{\mathbf{w}}_{k}^{(s)}
=
\sum_{H\in\mathcal{R}_k^{(s)}(d_k^{(s)})}
\mathbf{p}_k^{(s)}(H)\,\mathbf{w}_H^{(s)}.
```

Then the objective simplifies to

``` math
Q_{\eta}(\boldsymbol{\beta})
\propto
-\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\left\{
\left(
\frac{
\mathbf{w}_{\mathcal{D}_k}^{(s)}
+
\eta\,\tilde{\mathbf{w}}_{k}^{(s)}
}{1+\eta}
\right)^\top
\boldsymbol{\beta}
-
\log
\left[
\sum_{H'\in\mathcal{R}_k^{(s)}(d_k^{(s)})}
\exp\!\bigl( {\mathbf{w}_{H'}^{(s)}}^\top\boldsymbol{\beta} \bigr)
\right]
\right\}.
```

## Breslow Approximation

Although Cox’s exact method provides a precise treatment of tied failure
times, its computational cost grows combinatorially with the number of
ties at each event time: the size of the candidate failure set
$`\binom{n_k^{(s)}}{d_k^{(s)}}`$ becomes prohibitively large whenever
$`d_k^{(s)}`$ is non-negligible relative to $`n_k^{(s)}`$. The Breslow
approximation (Breslow 1974) addresses this limitation by replacing the
exact combinatorial denominator with a computationally tractable
surrogate, while retaining the same support
$`\mathcal{R}_k^{(s)}(d_k^{(s)})`$ of all size-$`d_k^{(s)}`$ subsets of
the risk set.

### Approximation of the Combinatorial Denominator

Under Cox’s exact method, the denominator of $`\mathbf{q}_k^{(s)}(H)`$
involves the elementary symmetric polynomial of degree $`d_k^{(s)}`$ in
the individual exponentiated risk scores,

``` math
\sum_{H' \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\exp\!\left\{ r_k(H'; \boldsymbol{\beta}) \right\}
=
\sum_{H' \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\prod_{j \in H'}
\exp\!\left\{ r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right\},
```

which enumerates all possible subsets of size $`d_k^{(s)}`$ drawn
*without replacement* from $`\mathcal{R}_k^{(s)}`$. The Breslow
approximation replaces this without-replacement enumeration by treating
the $`d_k^{(s)}`$ failures as $`d_k^{(s)}`$ independent draws *with
replacement* from $`\mathcal{R}_k^{(s)}`$, yielding the approximation

``` math
\sum_{H' \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\prod_{j \in H'}
\exp\!\left\{ r(\mathbf{Z}_j^{(s)}, \boldsymbol{\beta}) \right\}
\;\approx\;
\left[
\sum_{l \in \mathcal{R}_k^{(s)}}
\exp\!\left\{ r(\mathbf{Z}_l^{(s)}, \boldsymbol{\beta}) \right\}
\right]^{d_k^{(s)}},
```

which becomes increasingly accurate as $`n_k^{(s)} \gg d_k^{(s)}`$,
since the probability of selecting the same subject twice becomes
negligible. Crucially, the support of the distribution remains
unchanged: both the exact and Breslow formulations are defined over all
$`\binom{n_k^{(s)}}{d_k^{(s)}}`$ candidate failure subsets
$`H \in \mathcal{R}_k^{(s)}(d_k^{(s)})`$. What changes is solely the
denominator used to normalize the probability mass.

### Internal and External Probability Mass Functions

Substituting this approximation, the Breslow approximation to the
**internal** probability mass at time $`t_k^{(s)}`$ in stratum $`s`$ is

``` math
\tilde{\mathbf{q}}_k^{(s)}(H)
:=
\frac{
\exp\!\left\{ r_k(H; \boldsymbol{\beta}) \right\}
}{
\left[
\displaystyle\sum_{l \in \mathcal{R}_k^{(s)}}
\exp\!\left\{ r(\mathbf{Z}_l^{(s)}, \boldsymbol{\beta}) \right\}
\right]^{d_k^{(s)}}
},
```

and correspondingly, the Breslow approximation to the **external**
probability mass is

``` math
\tilde{\mathbf{p}}_k^{(s)}(H)
:=
\frac{
\exp\!\left\{ \tilde{r}_k(H) \right\}
}{
\left[
\displaystyle\sum_{l \in \mathcal{R}_k^{(s)}}
\exp\!\left\{ \tilde{r}(\mathbf{Z}_l^{(s)}) \right\}
\right]^{d_k^{(s)}}
},
```

where $`H \in \mathcal{R}_k^{(s)}(d_k^{(s)})`$ and
$`\tilde{r}_k(H) = \sum_{j \in H} \tilde{r}(\mathbf{Z}_j^{(s)})`$ as
before. Note that $`\tilde{\mathbf{q}}_k^{(s)}`$ and
$`\tilde{\mathbf{p}}_k^{(s)}`$ are not proper probability distributions
over $`\mathcal{R}_k^{(s)}(d_k^{(s)})`$ in general, since the Breslow
denominator does not equal the true normalizing constant and hence the
masses do not sum to one. Nevertheless, they serve as well-defined
surrogates within which the KL-divergence framework can be applied in an
approximate sense.

### KL Divergence and Simplified Weight

The approximate KL divergence follows the same derivation as in the
exact-ties setting. Under the Breslow approximation, the combinatorial
sum over all subsets $`H \in \mathcal{R}_k^{(s)}(d_k^{(s)})`$ collapses
under the with-replacement structure. Specifically, exchanging the order
of summation and noting that the marginal probability of subject $`j`$
appearing in any selected subset equals $`d_k^{(s)}`$ times its
single-draw softmax probability, one obtains

``` math
\sum_{H \in \mathcal{R}_k^{(s)}(d_k^{(s)})}
\tilde{\mathbf{p}}_k^{(s)}(H)\,r_k(H;\boldsymbol{\beta})
=
d_k^{(s)}
\sum_{j \in \mathcal{R}_k^{(s)}}
r(\mathbf{Z}_j^{(s)},\boldsymbol{\beta})\cdot
\frac{
\exp\!\left\{\tilde{r}(\mathbf{Z}_j^{(s)})\right\}
}{
\displaystyle\sum_{l \in \mathcal{R}_k^{(s)}} \exp\!\left\{\tilde{r}(\mathbf{Z}_l^{(s)})\right\}
},
```

with no combinatorial enumeration required.

### Integrated Objective Function

**Proposition (Breslow Approximation).** Under the stratified Cox model
with the Breslow approximation for ties, the integrated objective
$`Q_{\eta}(\boldsymbol{\beta}) = -\ell(\boldsymbol{\beta}) +
\eta\,\mathcal{D}_{\mathrm{KL}}(\mathbf{P}\parallel\mathbf{Q})`$ under
the linear specification $`r(\mathbf{Z}_j^{(s)},\boldsymbol{\beta}) =
{\mathbf{Z}_j^{(s)}}^\top\boldsymbol{\beta}`$ admits the representation

``` math
Q_{\eta}(\boldsymbol{\beta})
\propto
-\sum_{s=1}^{S}
\sum_{k=1}^{K^{(s)}}
\left\{
\left(
\frac{
\mathbf{w}_{\mathcal{D}_k}^{(s)}
+
\eta\,\tilde{\mathbf{w}}_k^{(s)}
}{1+\eta}
\right)^\top \boldsymbol{\beta}
\;-\;
d_k^{(s)}
\log
\left[
\sum_{l \in \mathcal{R}_k^{(s)}}
\exp\!\left\{ {\mathbf{Z}_l^{(s)}}^\top \boldsymbol{\beta} \right\}
\right]
\right\},
```

where
$`\mathbf{w}_{\mathcal{D}_k}^{(s)} = \sum_{j \in \mathcal{D}_k^{(s)}}
\mathbf{Z}_j^{(s)}`$ and

``` math
\tilde{\mathbf{w}}_k^{(s)}
=
d_k^{(s)}
\sum_{j \in \mathcal{R}_k^{(s)}}
\mathbf{Z}_j^{(s)}\cdot
\frac{
\exp\!\left\{\tilde{r}(\mathbf{Z}_j^{(s)})\right\}
}{
\displaystyle\sum_{l \in \mathcal{R}_k^{(s)}} \exp\!\left\{\tilde{r}(\mathbf{Z}_l^{(s)})\right\}
}.
```

As in the exact-ties setting, $`\tilde{\mathbf{w}}_k^{(s)}`$ depends
only on the prior risk score $`\tilde{r}(\cdot)`$ and can be computed
once in a preprocessing step. In contrast to the exact method, however,
$`\tilde{\mathbf{w}}_k^{(s)}`$ under the Breslow approximation requires
no combinatorial enumeration: it reduces to a softmax-weighted average
of covariates over the risk set $`\mathcal{R}_k^{(s)}`$, scaled by
$`d_k^{(s)}`$, with computational cost $`O(n_k^{(s)})`$ per event time.
The resulting objective is structurally identical to the standard
Breslow partial likelihood, with the observed covariate sum
$`\mathbf{w}_{\mathcal{D}_k}^{(s)}`$ replaced by the blended term
$`(\mathbf{w}_{\mathcal{D}_k}^{(s)} + \eta\,\tilde{\mathbf{w}}_k^{(s)})/(1+\eta)`$,
with no additional computational burden introduced by the KL integration
term.

## Comparison of the Two Methods

The Breslow method provides a computationally efficient approximation
and is generally suitable when the number of tied events is moderate.
The exact method yields more accurate inference in the presence of
extensive ties, at the cost of increased computational burden due to the
enumeration of all subsets $`\mathcal{R}_k^{(s)}(d_k^{(s)})`$. In
practice, the two methods produce nearly identical results when ties are
infrequent. Users can select between the two via the `ties` argument in
[`coxkl_ties()`](https://um-kevinhe.github.io/BregSurv/reference/coxkl_ties.md)
and
[`cv.coxkl_ties()`](https://um-kevinhe.github.io/BregSurv/reference/cv.coxkl_ties.md).

## References

Breslow, Norman. 1974. “Covariance Analysis of Censored Survival Data.”
*Biometrics*, 89–99.

Cox, David R. 1972. “Regression Models and Life-Tables.” *Journal of the
Royal Statistical Society: Series B (Methodological)* 34 (2): 187–202.
