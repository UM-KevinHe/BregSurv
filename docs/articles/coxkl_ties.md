<div id="main" class="col-md-9" role="main">

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

<div class="section level2">

## Cox’s Exact Method

In stratum *s*, suppose that at time *t*_(*k*)^((*s*)),
$d\_{k}^{(s)} = \\sum\_{i = 1}^{n\_{s}}\\delta\_{i}^{(s)}(t\_{k}^{(s)}) \\geq 1$
subjects fail. Let ℛ_(*k*)^((*s*)) denote the at-risk set with
cardinality *n*_(*k*)^((*s*)), and let

𝒟_(*k*)^((*s*)) = {*i* ∈ ℛ_(*k*)^((*s*)) : *δ*_(*i*)^((*s*))(*t*_(*k*)^((*s*))) = 1}

denote the observed failure (tie) set of size *d*_(*k*)^((*s*)). Let
ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))) denote the collection of all subsets
of size *d*_(*k*)^((*s*)) drawn from ℛ_(*k*)^((*s*)), with cardinality
$c\_{k}^{(s)} = \\left( \\frac{n\_{k}^{(s)}}{d\_{k}^{(s)}} \\right)$.

<div class="section level3">

### Probabilistic Framework

Under Cox’s exact method, for stratum *s* and event time
*t*_(*k*)^((*s*)), let *H* ∈ ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))) denote a
candidate failure subset of size *d*_(*k*)^((*s*)), and define the event
*A*_(*k*)^((*s*))(*H*) to indicate that the subjects in *H* fail in the
interval \[*t*_(*k*)^((*s*)), *t*_(*k*)^((*s*)) + *d**t*_(*k*)^((*s*))).
Let *B*_(*k*)^((*s*)) denote all censoring and failure information up to
*t*_(*k*)^((*s*))^(−), together with the information that exactly
*d*_(*k*)^((*s*)) failures occur in that interval. Then

{ *A*_(*k*)^((*s*))(*H*) ∣ *B*_(*k*)^((*s*)) : *H* ∈ ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))), *k* = 1, …, *K*^((*s*)), *s* = 1, …, *S* }

remains a well-defined sequence of conditional experiments. At each
event time *t*_(*k*)^((*s*)), the internal working model specifies the
conditional density as
*M**u**l**t**i**n**o**m**i**a**l*(1, **q**_(*k*)^((*s*))). In contrast
to the no-ties case where the support consists of *n*_(*k*)^((*s*))
individual subjects, under Cox’s exact method the support is given by
the *c*_(*k*)^((*s*)) candidate failure subsets of size
*d*_(*k*)^((*s*)).

</div>

<div class="section level3">

### Internal and External Probability Mass Functions

The stratum-specific probability mass at time *t*_(*k*)^((*s*)) under
the **internal** model is

$$\\mathbf{q}\_{k}^{(s)}(H):=\\mathcal{P}\\!\\left\\{ A\_{k}^{(s)}(H) \\mid B\_{k}^{(s)} \\right\\} = \\frac{\\exp\\!\\left\\{ r\_{k}(H;\\mathbf{\\beta}) \\right\\}}{\\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\exp\\!\\left\\{ r\_{k}(H\\prime;\\mathbf{\\beta}) \\right\\}},$$

where

$$r\_{k}(H;\\mathbf{\\beta}):=\\sum\\limits\_{j \\in H}r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta})$$

denotes the sum of internal risk scores over subjects in the candidate
failure subset *H*.

Replacing the internal risk scores with the external risk scores
*r̃*(**Z**_(*i*)^((*s*))), the probability mass under the **external**
model is

$$\\mathbf{p}\_{k}^{(s)}(H):=\\mathcal{P}\_{ext}\\!\\left\\{ A\_{k}^{(s)}(H) \\mid B\_{k}^{(s)} \\right\\} = \\frac{\\exp\\!\\left\\{ {\\widetilde{r}}\_{k}(H) \\right\\}}{\\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\exp\\!\\left\\{ {\\widetilde{r}}\_{k}(H\\prime) \\right\\}},$$

where

$${\\widetilde{r}}\_{k}(H):=\\sum\\limits\_{j \\in H}\\widetilde{r}(\\mathbf{Z}\_{j}^{(s)})$$

denotes the sum of external risk scores over subjects in *H*.

</div>

<div class="section level3">

### KL Divergence

The KL divergence between the external and internal models at time
*t*_(*k*)^((*s*)) in stratum *s* is

$$\\mathbf{d}\_{KL}\\!\\left( \\mathbf{p}\_{k}^{(s)}\\, \\parallel \\,\\mathbf{q}\_{k}^{(s)} \\right) = \\sum\\limits\_{H \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\mathbf{p}\_{k}^{(s)}(H)\\log\\frac{\\mathbf{p}\_{k}^{(s)}(H)}{\\mathbf{q}\_{k}^{(s)}(H)}.$$

Substituting the expressions above and accumulating over all strata and
failure times yields

$$\\mathcal{D}\_{KL}(\\mathbf{P} \\parallel \\mathbf{Q}) \\propto - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\left( \\sum\\limits\_{H \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\mathbf{p}\_{k}^{(s)}(H)\\, r\_{k}(H;\\mathbf{\\beta}) \\right) + \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\log\\left\\{ \\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\exp\\!\\left\\{ r\_{k}(H\\prime;\\mathbf{\\beta}) \\right\\} \\right\\}.$$

</div>

<div class="section level3">

### Integrated Objective Function

<div style="border-left: 4px solid #158cba; background-color: #f0f8fc;
            padding: 1rem 1.5rem; margin: 1.5rem 0; border-radius: 0 4px 4px 0;">

**Proposition (Exact Ties).** Under the stratified Cox model with exact
ties, the integrated objective
*Q*_(*η*)(**β**) =  − ℓ(**β**) + *η* 𝒟_(*K**L*)(**P** ∥ **Q**) admits
the representation

$$Q\_{\\eta}(\\mathbf{\\beta}) \\propto - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\left\\{ \\frac{r\_{k}(\\mathcal{D}\_{k}^{(s)};\\mathbf{\\beta}) + \\eta\\sum\\limits\_{H \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\mathbf{p}\_{k}^{(s)}(H)\\, r\_{k}(H;\\mathbf{\\beta})}{1 + \\eta} - \\log\\left\\lbrack \\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\exp\\!(r\_{k}(H\\prime;\\mathbf{\\beta})) \\right\\rbrack \\right\\},$$

where
*r*_(*k*)(𝒟_(*k*)^((*s*)); **β**) = ∑_(*j* ∈ 𝒟_(*k*)^((*s*)))*r*(**Z**_(*j*)^((*s*)), **β**).

Furthermore, under the linear specification
*r*(**Z**_(*j*)^((*s*)), **β**) = **Z**_(*j*)^((*s*))^(⊤)**β**, define

$$\\mathbf{w}\_{\\mathcal{D}\_{k}}^{(s)} = \\sum\\limits\_{j \\in \\mathcal{D}\_{k}^{(s)}}\\mathbf{Z}\_{j}^{(s)},\\qquad\\mathbf{w}\_{H}^{(s)} = \\sum\\limits\_{j \\in H}\\mathbf{Z}\_{j}^{(s)},\\qquad{\\widetilde{\\mathbf{w}}}\_{k}^{(s)} = \\sum\\limits\_{H \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\mathbf{p}\_{k}^{(s)}(H)\\,\\mathbf{w}\_{H}^{(s)}.$$

Then the objective simplifies to

$$Q\_{\\eta}(\\mathbf{\\beta}) \\propto - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\left\\{ \\left( \\frac{\\mathbf{w}\_{\\mathcal{D}\_{k}}^{(s)} + \\eta\\,{\\widetilde{\\mathbf{w}}}\_{k}^{(s)}}{1 + \\eta} \\right)^{\\top}\\mathbf{\\beta} - \\log\\left\\lbrack \\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\exp\\!({\\mathbf{w}\_{H\\prime}^{(s)}}^{\\top}\\mathbf{\\beta}) \\right\\rbrack \\right\\}.$$

</div>

</div>

</div>

<div class="section level2">

## Breslow Approximation

Although Cox’s exact method provides a precise treatment of tied failure
times, its computational cost grows combinatorially with the number of
ties at each event time: the size of the candidate failure set
$\\left( \\frac{n\_{k}^{(s)}}{d\_{k}^{(s)}} \\right)$ becomes
prohibitively large whenever *d*_(*k*)^((*s*)) is non-negligible
relative to *n*_(*k*)^((*s*)). The Breslow approximation (Breslow 1974)
addresses this limitation by replacing the exact combinatorial
denominator with a computationally tractable surrogate, while retaining
the same support ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))) of all
size-*d*_(*k*)^((*s*)) subsets of the risk set.

<div class="section level3">

### Approximation of the Combinatorial Denominator

Under Cox’s exact method, the denominator of **q**_(*k*)^((*s*))(*H*)
involves the elementary symmetric polynomial of degree *d*_(*k*)^((*s*))
in the individual exponentiated risk scores,

$$\\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\exp\\!\\left\\{ r\_{k}(H\\prime;\\mathbf{\\beta}) \\right\\} = \\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\prod\\limits\_{j \\in H\\prime}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\},$$

which enumerates all possible subsets of size *d*_(*k*)^((*s*)) drawn
*without replacement* from ℛ_(*k*)^((*s*)). The Breslow approximation
replaces this without-replacement enumeration by treating the
*d*_(*k*)^((*s*)) failures as *d*_(*k*)^((*s*)) independent draws *with
replacement* from ℛ_(*k*)^((*s*)), yielding the approximation

$$\\sum\\limits\_{H\\prime \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}\\prod\\limits\_{j \\in H\\prime}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\}\\; \\approx \\;\\left\\lbrack \\sum\\limits\_{l \\in \\mathcal{R}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{l}^{(s)},\\mathbf{\\beta}) \\right\\} \\right\\rbrack^{d\_{k}^{(s)}},$$

which becomes increasingly accurate as
*n*_(*k*)^((*s*)) ≫ *d*_(*k*)^((*s*)), since the probability of
selecting the same subject twice becomes negligible. Crucially, the
support of the distribution remains unchanged: both the exact and
Breslow formulations are defined over all
$\\left( \\frac{n\_{k}^{(s)}}{d\_{k}^{(s)}} \\right)$ candidate failure
subsets *H* ∈ ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))). What changes is solely
the denominator used to normalize the probability mass.

</div>

<div class="section level3">

### Internal and External Probability Mass Functions

Substituting this approximation, the Breslow approximation to the
**internal** probability mass at time *t*_(*k*)^((*s*)) in stratum *s*
is

$${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(H):=\\frac{\\exp\\!\\left\\{ r\_{k}(H;\\mathbf{\\beta}) \\right\\}}{\\left\\lbrack \\sum\\limits\_{l \\in \\mathcal{R}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{l}^{(s)},\\mathbf{\\beta}) \\right\\} \\right\\rbrack^{d\_{k}^{(s)}}},$$

and correspondingly, the Breslow approximation to the **external**
probability mass is

$${\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(H):=\\frac{\\exp\\!\\left\\{ {\\widetilde{r}}\_{k}(H) \\right\\}}{\\left\\lbrack \\sum\\limits\_{l \\in \\mathcal{R}\_{k}^{(s)}}\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{l}^{(s)}) \\right\\} \\right\\rbrack^{d\_{k}^{(s)}}},$$

where *H* ∈ ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))) and
*r̃*_(*k*)(*H*) = ∑_(*j* ∈ *H*)*r̃*(**Z**_(*j*)^((*s*))) as before. Note
that ${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}$ and
${\\widetilde{\\mathbf{p}}}\_{k}^{(s)}$ are not proper probability
distributions over ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))) in general, since
the Breslow denominator does not equal the true normalizing constant and
hence the masses do not sum to one. Nevertheless, they serve as
well-defined surrogates within which the KL-divergence framework can be
applied in an approximate sense.

</div>

<div class="section level3">

### KL Divergence and Simplified Weight

The approximate KL divergence follows the same derivation as in the
exact-ties setting. Under the Breslow approximation, the combinatorial
sum over all subsets *H* ∈ ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))) collapses
under the with-replacement structure. Specifically, exchanging the order
of summation and noting that the marginal probability of subject *j*
appearing in any selected subset equals *d*_(*k*)^((*s*)) times its
single-draw softmax probability, one obtains

$$\\sum\\limits\_{H \\in \\mathcal{R}\_{k}^{(s)}(d\_{k}^{(s)})}{\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(H)\\, r\_{k}(H;\\mathbf{\\beta}) = d\_{k}^{(s)}\\sum\\limits\_{j \\in \\mathcal{R}\_{k}^{(s)}}r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\cdot \\frac{\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{j}^{(s)}) \\right\\}}{\\sum\\limits\_{l \\in \\mathcal{R}\_{k}^{(s)}}\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{l}^{(s)}) \\right\\}},$$

with no combinatorial enumeration required.

</div>

<div class="section level3">

### Integrated Objective Function

<div style="border-left: 4px solid #158cba; background-color: #f0f8fc;
            padding: 1rem 1.5rem; margin: 1.5rem 0; border-radius: 0 4px 4px 0;">

**Proposition (Breslow Approximation).** Under the stratified Cox model
with the Breslow approximation for ties, the integrated objective
*Q*_(*η*)(**β**) =  − ℓ(**β**) + *η* 𝒟_(*K**L*)(**P** ∥ **Q**) under the
linear specification
*r*(**Z**_(*j*)^((*s*)), **β**) = **Z**_(*j*)^((*s*))^(⊤)**β** admits
the representation

$$Q\_{\\eta}(\\mathbf{\\beta}) \\propto - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\left\\{ \\left( \\frac{\\mathbf{w}\_{\\mathcal{D}\_{k}}^{(s)} + \\eta\\,{\\widetilde{\\mathbf{w}}}\_{k}^{(s)}}{1 + \\eta} \\right)^{\\top}\\mathbf{\\beta}\\; - \\; d\_{k}^{(s)}\\log\\left\\lbrack \\sum\\limits\_{l \\in \\mathcal{R}\_{k}^{(s)}}\\exp\\!\\left\\{ {\\mathbf{Z}\_{l}^{(s)}}^{\\top}\\mathbf{\\beta} \\right\\} \\right\\rbrack \\right\\},$$

where
**w**_(𝒟_(*k*))^((*s*)) = ∑_(*j* ∈ 𝒟_(*k*)^((*s*)))**Z**_(*j*)^((*s*))
and

$${\\widetilde{\\mathbf{w}}}\_{k}^{(s)} = d\_{k}^{(s)}\\sum\\limits\_{j \\in \\mathcal{R}\_{k}^{(s)}}\\mathbf{Z}\_{j}^{(s)} \\cdot \\frac{\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{j}^{(s)}) \\right\\}}{\\sum\\limits\_{l \\in \\mathcal{R}\_{k}^{(s)}}\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{l}^{(s)}) \\right\\}}.$$

</div>

As in the exact-ties setting, ${\\widetilde{\\mathbf{w}}}\_{k}^{(s)}$
depends only on the prior risk score *r̃*( ⋅ ) and can be computed once
in a preprocessing step. In contrast to the exact method, however,
${\\widetilde{\\mathbf{w}}}\_{k}^{(s)}$ under the Breslow approximation
requires no combinatorial enumeration: it reduces to a softmax-weighted
average of covariates over the risk set ℛ_(*k*)^((*s*)), scaled by
*d*_(*k*)^((*s*)), with computational cost *O*(*n*_(*k*)^((*s*))) per
event time. The resulting objective is structurally identical to the
standard Breslow partial likelihood, with the observed covariate sum
**w**_(𝒟_(*k*))^((*s*)) replaced by the blended term
$(\\mathbf{w}\_{\\mathcal{D}\_{k}}^{(s)} + \\eta\\,{\\widetilde{\\mathbf{w}}}\_{k}^{(s)})/(1 + \\eta)$,
with no additional computational burden introduced by the KL integration
term.

</div>

</div>

<div class="section level2">

## Comparison of the Two Methods

The Breslow method provides a computationally efficient approximation
and is generally suitable when the number of tied events is moderate.
The exact method yields more accurate inference in the presence of
extensive ties, at the cost of increased computational burden due to the
enumeration of all subsets ℛ_(*k*)^((*s*))(*d*_(*k*)^((*s*))). In
practice, the two methods produce nearly identical results when ties are
infrequent. Users can select between the two via the `ties` argument in
`coxkl_ties()` and `cv.coxkl_ties()`.

</div>

<div class="section level2 unnumbered">

## References

<div id="refs" class="references csl-bib-body hanging-indent">

<div id="ref-breslow1974covariance" class="csl-entry">

Breslow, Norman. 1974. “Covariance Analysis of Censored Survival Data.”
*Biometrics*, 89–99.

</div>

<div id="ref-cox1972regression" class="csl-entry">

Cox, David R. 1972. “Regression Models and Life-Tables.” *Journal of the
Royal Statistical Society: Series B (Methodological)* 34 (2): 187–202.

</div>

</div>

</div>

</div>
