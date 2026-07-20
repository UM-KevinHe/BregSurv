<div id="main" class="col-md-9" role="main">

# KL Divergence-Based Transfer Learning for Cox Model

<div class="section level2">

## Notations and Model Setup

Suppose the time-to-event data arise from *S* distinct strata,
representing heterogeneous sources or sampling blocks, where stratum *s*
contains *n*_(*s*) subjects and the total sample size is
$N = \\sum\_{s = 1}^{S}n\_{s}$. For subject *i* in stratum *s*, let
*T*_(*i*)^((*s*)) and *C*_(*i*)^((*s*)) denote the event and censoring
times, respectively. Each subject is associated with *p*-dimensional
covariates **Z**_(*i*)^((*s*)) ∈ ℝ^(*p*). We assume that
*T*_(*i*)^((*s*)) and *C*_(*i*)^((*s*)) are independent conditional on
**Z**_(*i*)^((*s*)). We define the observed time
*X*_(*i*)^((*s*)) = min {*T*_(*i*)^((*s*)), *C*_(*i*)^((*s*))} and the
event indicator
*δ*_(*i*)^((*s*)) = 𝕀(*T*_(*i*)^((*s*)) ≤ *C*_(*i*)^((*s*))).

Consider the following stratified Cox proportional hazards model:

*λ*^((*s*)) (*t*∣**Z**_(*i*)^((*s*))) = *λ*₀^((*s*))(*t*)exp  {*r*(**Z**_(*i*)^((*s*)),**β**)},

where *λ*₀^((*s*))(*t*) is an unspecified stratum-specific baseline
hazard function, treated as an infinite-dimensional nuisance parameter
that absorbs between-stratum heterogeneity arising from differences in
source populations, clinical practice, or unmeasured confounding, and
**β** ∈ ℝ^(*p*) is a common regression parameter shared across all
strata. *r*(**Z**_(*i*)^((*s*)), **β**) denotes the internal risk score;
under the standard linear specification,
*r*(**Z**_(*i*)^((*s*)), **β**) = **Z**_(*i*)^((*s*))^(⊤)**β**.

Assume that, in stratum *s*, the observed cohort has *K*^((*s*)) unique
failure times
*t*₁^((*s*)) &lt; *t*₂^((*s*)) &lt; ⋯ &lt; *t*_(*K*^((*s*)))^((*s*)).
The stratified Cox log-partial likelihood is given by

$$\\ell(\\mathbf{\\beta}) = \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\sum\\limits\_{i = 1}^{n\_{s}}\\delta\_{i}^{(s)}\\!\\left( t\_{k}^{(s)} \\right)\\left\\lbrack r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) - \\log\\left\\{ \\sum\\limits\_{j = 1}^{n\_{s}}Y\_{j}^{(s)}\\!\\left( t\_{k}^{(s)} \\right)\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\} \\right\\} \\right\\rbrack,$$

where *Y*_(*j*)^((*s*))(*t*) = 𝕀 (*X*_(*j*)^((*s*))≥*t*) is the at-risk
indicator in stratum *s*, and
*δ*_(*i*)^((*s*))(*t*) = 𝕀 (*X*_(*i*)^((*s*))=*t*, *δ*_(*i*)^((*s*))=1)
indicates whether subject *i* in stratum *s* fails at time *t*.

</div>

<div class="section level2">

## KL Divergence Formulation

Let *G* be chosen as the negative entropy so that the resulting Bregman
divergence reduces to the Kullback–Leibler divergence. To construct the
probabilistic framework, let ℛ_(*k*)^((*s*)) denote the at-risk set at
*t*_(*k*)^((*s*)) in stratum *s*, let *A*_(*k*)^((*s*))(*i*) denote the
event that subject *i* ∈ ℛ_(*k*)^((*s*)) fails in the interval
\[*t*_(*k*)^((*s*)), *t*_(*k*)^((*s*)) + *d**t*_(*k*)^((*s*))), and let
*B*_(*k*)^((*s*)) collect all failure and censoring information up to
time *t*_(*k*)^((*s*))^(−), together with the information that exactly
one failure occurs in
\[*t*_(*k*)^((*s*)), *t*_(*k*)^((*s*)) + *d**t*_(*k*)^((*s*))).

Then
{*A*_(*k*)^((*s*))(*i*) ∣ *B*_(*k*)^((*s*)) : *k* = 1, …, *K*^((*s*)), *s* = 1, …, *S*}
defines a sequence of conditional experiments. At each event time
*t*_(*k*)^((*s*)) in stratum *s*, the internal working model specifies
the conditional density as

*M**u**l**t**i**n**o**m**i**a**l* (1, **q**_(*k*)^((*s*))).

The stratum-specific probability mass assigned to subject
*i* ∈ ℛ_(*k*)^((*s*)) under the **internal** model is

$$\\mathbf{q}\_{k}^{(s)}(i):=\\mathcal{P}\\!\\left\\{ A\_{k}^{(s)}(i)\\, \\middle\| \\, B\_{k}^{(s)} \\right\\} = \\frac{\\exp\\!\\left\\{ r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) \\right\\}}{\\sum\\limits\_{j = 1}^{n\_{s}}Y\_{j}^{(s)}(t\_{k}^{(s)})\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\}},$$

where *λ*₀^((*s*))(*t*_(*k*)^((*s*))) is the stratum-specific baseline
hazard that cancels in the ratio.

To extract information from the external model, we replace the internal
risk score with the external risk score *r̃*( ⋅ ), obtained by applying
the external coefficient estimates $\\widetilde{\\mathbf{\\beta}}$ to
the internal cohort. The corresponding probability mass under the
**external** model is

$$\\mathbf{p}\_{k}^{(s)}(i):=\\mathcal{P}\_{ext}\\!\\left\\{ A\_{k}^{(s)}(i)\\, \\middle\| \\, B\_{k}^{(s)} \\right\\} = \\frac{\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{i}^{(s)}) \\right\\}}{\\sum\\limits\_{j = 1}^{n\_{s}}Y\_{j}^{(s)}(t\_{k}^{(s)})\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{j}^{(s)}) \\right\\}}.$$

The KL divergence between the external and internal conditional
experiments at time *t*_(*k*)^((*s*)) is

$$\\mathbf{d}\_{KL}\\!\\left( \\mathbf{p}\_{k}^{(s)}\\, \\parallel \\,\\mathbf{q}\_{k}^{(s)} \\right) = \\sum\\limits\_{i \\in \\mathcal{R}\_{k}^{(s)}}\\mathbf{p}\_{k}^{(s)}(i)\\log\\frac{\\mathbf{p}\_{k}^{(s)}(i)}{\\mathbf{q}\_{k}^{(s)}(i)}.$$

Accumulating over all strata and failure times yields the total
divergence:

$$\\mathcal{D}\_{KL}(\\mathbf{P} \\parallel \\mathbf{Q}) = \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\mathbf{d}\_{KL}\\!\\left( \\mathbf{p}\_{k}^{(s)}\\, \\parallel \\,\\mathbf{q}\_{k}^{(s)} \\right),$$

which, after substituting the Cox-model expressions, simplifies to

$$\\mathcal{D}\_{KL}(\\mathbf{P} \\parallel \\mathbf{Q}) = - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\sum\\limits\_{i = 1}^{n\_{s}}\\frac{Y\_{i}^{(s)}(t\_{k}^{(s)})\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{i}^{(s)}) \\right\\}}{\\sum\\limits\_{j = 1}^{n\_{s}}Y\_{j}^{(s)}(t\_{k}^{(s)})\\exp\\!\\left\\{ \\widetilde{r}(\\mathbf{Z}\_{j}^{(s)}) \\right\\}}\\left\\lbrack r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) - \\log\\left\\{ \\sum\\limits\_{j = 1}^{n\_{s}}Y\_{j}^{(s)}(t\_{k}^{(s)})\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\} \\right\\} \\right\\rbrack + \\Psi,$$

where *Ψ* = ∑_(*s*, *k*)*Ψ*_(*k*)^((*s*)) does not involve **β**.

</div>

<div class="section level2">

## Integrated Objective Function

<div class="callout callout-note">

</div>

<div style="border-left: 4px solid #6c757d; background-color: #f8f9fa; 
            padding: 1rem 1.5rem; margin: 1.5rem 0; border-radius: 0 4px 4px 0;">

**Proposition.** Under the above construction, the integrated objective
function in the stratified Cox model satisfies

$$Q\_{\\eta}(\\mathbf{\\beta}) = - \\ell(\\mathbf{\\beta}) + \\eta\\,\\mathcal{D}\_{KL}(\\mathbf{P} \\parallel \\mathbf{Q}) \\propto - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{i = 1}^{n\_{s}}\\left\\{ \\frac{\\delta\_{i}^{(s)} + \\eta{\\widetilde{\\delta}}\_{i}^{(s)}}{1 + \\eta} \\cdot r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) - \\delta\_{i}^{(s)}\\log\\left\\lbrack \\sum\\limits\_{j = 1}^{n\_{s}}Y\_{j}(X\_{i}^{(s)})\\exp\\left( r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right) \\right\\rbrack \\right\\},$$

where the externally induced pseudo-event weight is defined as

$${\\widetilde{\\delta}}\_{i}^{(s)} = \\sum\\limits\_{k = 1}^{K^{(s)}}\\frac{Y\_{i}(t\_{k}^{(s)})\\exp\\{\\widetilde{r}(\\mathbf{Z}\_{i}^{(s)})\\}}{\\sum\\limits\_{j = 1}^{n\_{s}}Y\_{j}(t\_{k}^{(s)})\\exp\\{\\widetilde{r}(\\mathbf{Z}\_{j}^{(s)})\\}},$$

ℓ(**β**) is the internal stratified Cox log-partial likelihood defined
above, and *η* ≥ 0 is the integration weight.

</div>

</div>

</div>
