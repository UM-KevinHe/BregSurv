<div id="main" class="col-md-9" role="main">

# NCC KL Divergence-Based Transfer Learning

<div class="section level2">

## Matched-Set Notation and Model Setup

The nested case–control (NCC) design provides an efficient alternative
for fitting Cox proportional hazards models when covariate measurement
for the full cohort is costly. At each observed failure time, the
failing subject (the case) is retained, while a number of controls are
randomly sampled from the corresponding risk set. The resulting sampled
matched sets are then analyzed using conditional likelihood.

We first introduce the matched-set notation. Let ℛ_(*k*)^((*s*)) denote
the at-risk set at time *t*_(*k*)^((*s*)) in stratum *s*. For the
failure at *t*_(*k*)^((*s*)), we randomly sample *m* controls from
ℛ_(*k*)^((*s*)), excluding the failing subject and matched by stratum.
The failing subject together with the sampled controls forms a matched
set of size *m* + 1, which we denote by
${\\widetilde{\\mathcal{R}}}\_{k}^{(s)}$. Since each stratum contains
*K*^((*s*)) unique failure times, the NCC design yields a total of
$M = \\sum\_{s = 1}^{S}K^{(s)}$ matched sets across all strata.

Under this construction, the matched set
${\\widetilde{\\mathcal{R}}}\_{k}^{(s)}$ forms a subset of the full
at-risk set ℛ_(*k*)^((*s*)). Following the probabilistic framework
introduced in the Cox KL divergence vignette, we similarly define a
sequence of conditional experiments
{*Ã*_(*k*)^((*s*))(*i*) ∣ *B̃*_(*k*)^((*s*)) : *k* = 1, …, *K*^((*s*)), *s* = 1, …, *S*}.
Here *Ã*_(*k*)^((*s*))(*i*) denotes the event that subject
$i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}$ is the failing subject
in the (*s*, *k*)-th matched set, and *B̃*_(*k*)^((*s*)) collects all
failure and censoring information up to time *t*_(*k*)^((*s*))^(−),
together with the information that the matched set
${\\widetilde{\\mathcal{R}}}\_{k}^{(s)}$ has been formed by sampling *m*
controls from ℛ_(*k*)^((*s*)) and that exactly one failure occurs in
\[*t*_(*k*)^((*s*)), *t*_(*k*)^((*s*)) + *d**t*_(*k*)^((*s*))).

Consequently, within the (*s*, *k*)-th matched set, the NCC working
model similarly specifies the conditional density within the matched set
as a Multinomial distribution with a single trial, i.e.,

$${Multinomial}\\!\\left( 1,\\,{\\widetilde{\\mathbf{q}}}\_{k}^{(s)} \\right),$$

where the probability mass assigned to subject
$i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}$ is

$${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i):=\\mathcal{P}\\!\\left\\{ {\\widetilde{A}}\_{k}^{(s)}(i)\\, \\middle\| \\,{\\widetilde{B}}\_{k}^{(s)} \\right\\} = \\frac{\\exp\\!\\left\\{ r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) \\right\\}}{\\sum\\limits\_{j \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\}}.$$

</div>

<div class="section level2">

## KL Divergence Formulation

Because the full at-risk set ℛ_(*k*)^((*s*)) is not used, the
conditional probability ${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i)$
generally differs from the corresponding conditional probability
**q**_(*k*)^((*s*))(*i*) in the internal Cox working model.
Nevertheless, the probabilities
${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i)$ remain valid conditional
probabilities within the matched set, since

$$\\sum\\limits\_{i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}{\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i) = 1.$$

When the matched set is formed by random sampling from ℛ_(*k*)^((*s*)),
the denominator satisfies

$$\\mathbb{E}\\!\\left\\lbrack \\sum\\limits\_{j \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\} \\right\\rbrack \\approx \\frac{m}{\|\\mathcal{R}\_{k}^{(s)}\|}\\sum\\limits\_{j \\in \\mathcal{R}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\},$$

when the risk-set size \|ℛ_(*k*)^((*s*))\| is large. However, it is
important to note that these two probabilities are defined under
different conditioning events: **q**_(*k*)^((*s*))(*i*) conditions on
the full at-risk set ℛ_(*k*)^((*s*)), whereas
${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i)$ conditions on the sampled
matched set ${\\widetilde{\\mathcal{R}}}\_{k}^{(s)}$. Consequently, the
two probabilities are not directly comparable and do not satisfy a
simple proportional relationship. Numerically, the value of
${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i)$ is typically larger than
**q**_(*k*)^((*s*))(*i*) because the matched set constitutes only a
subsample of the full risk set, resulting in a smaller normalization set
in the denominator. However, such a comparison should be interpreted
with caution, since the two probabilities correspond to different
conditional experiments. In particular, under the NCC construction the
probability ${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i)$ is defined only
for subjects included in the sampled matched set, whereas subjects in
the full risk set who are not sampled into the matched set do not have a
corresponding probability defined in this conditional experiment.

To extract information from the external model under the NCC design, we
similarly replace the internal risk score by the external risk score
*r̃*( ⋅ ) obtained from the external coefficient estimates
$\\widetilde{\\mathbf{\\beta}}$. Analogous to the construction of
${\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i)$, we define the corresponding
probability mass under the **external** model within the matched set as

$${\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(i):=\\mathcal{P}\_{ext}\\!\\left\\{ {\\widetilde{A}}\_{k}^{(s)}(i) \\mid {\\widetilde{B}}\_{k}^{(s)} \\right\\},\\qquad i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)},$$

which takes the same multinomial form as in the Cox construction but
with the denominator restricted to the matched set
${\\widetilde{\\mathcal{R}}}\_{k}^{(s)}$.

To quantify the discrepancy between the external and internal
conditional probabilities for the (*s*, *k*)-th matched set, we define
the KL divergence:

$$\\mathbf{d}\_{KL}\\!\\left( {\\widetilde{\\mathbf{p}}}\_{k}^{(s)} \\parallel {\\widetilde{\\mathbf{q}}}\_{k}^{(s)} \\right) = \\sum\\limits\_{i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}{\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(i)\\log\\frac{{\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(i)}{{\\widetilde{\\mathbf{q}}}\_{k}^{(s)}(i)}.$$

Accumulating over all matched sets gives

$$\\mathcal{D}\_{KL}(\\widetilde{\\mathbf{P}} \\parallel \\widetilde{\\mathbf{Q}}) = \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\mathbf{d}\_{KL}\\!\\left( {\\widetilde{\\mathbf{p}}}\_{k}^{(s)} \\parallel {\\widetilde{\\mathbf{q}}}\_{k}^{(s)} \\right) = - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\sum\\limits\_{i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}{\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(i)\\lbrack r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) - \\log\\{\\sum\\limits\_{j \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\}\\}\\rbrack + \\widetilde{\\Psi},$$

where *Ψ̃* does not involve **β**.

Let *ξ*_(*k**i*)^((*s*)) denote the indicator that subject *i* is the
observed failure in the (*s*, *k*)-th matched set, so that the internal
NCC conditional log-likelihood is

$$\\ell\_{NCC}(\\mathbf{\\beta}) = \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\sum\\limits\_{i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}\\xi\_{ki}^{(s)}\\lbrack r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) - \\log\\{\\sum\\limits\_{j \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\}\\}\\rbrack.$$

</div>

<div class="section level2">

## Integrated Objective Function

<div class="callout callout-note">

</div>

<div style="border-left: 4px solid #6c757d; background-color: #f8f9fa; 
            padding: 1rem 1.5rem; margin: 1.5rem 0; border-radius: 0 4px 4px 0;">

**Proposition.** Under the NCC construction, the integrated objective
function satisfies

$$Q\_{\\eta}^{NCC}(\\mathbf{\\beta}) = - \\ell\_{NCC}(\\mathbf{\\beta}) + \\eta\\,\\mathcal{D}\_{KL}(\\widetilde{\\mathbf{P}} \\parallel \\widetilde{\\mathbf{Q}}) \\propto - \\sum\\limits\_{s = 1}^{S}\\sum\\limits\_{k = 1}^{K^{(s)}}\\sum\\limits\_{i \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}\\left\\{ \\frac{\\xi\_{ki}^{(s)} + \\eta\\,{\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(i)}{1 + \\eta}\\, r(\\mathbf{Z}\_{i}^{(s)},\\mathbf{\\beta}) - \\xi\_{ki}^{(s)}\\log\\left\\lbrack \\sum\\limits\_{j \\in {\\widetilde{\\mathcal{R}}}\_{k}^{(s)}}\\exp\\!\\left\\{ r(\\mathbf{Z}\_{j}^{(s)},\\mathbf{\\beta}) \\right\\} \\right\\rbrack \\right\\},$$

where ℓ_(*N**C**C*)(**β**) is the internal NCC conditional
log-likelihood, ${\\widetilde{\\mathbf{p}}}\_{k}^{(s)}(i)$ denotes the
externally induced pseudo-event weight within the (*s*, *k*)-th matched
set that can be fully precomputed before optimization, and *η* ≥ 0 is
the integration weight.

</div>

It is worth emphasizing that, although the NCC design is commonly used
as a computationally efficient surrogate for the Cox model and yields
consistent estimators of the regression coefficients, the KL divergence
defined under the NCC construction is not a direct surrogate for the
Cox-model KL divergence. This is because the two KL quantities are
defined with respect to different conditional experiments. Consequently,
the corresponding probability models, and hence the associated KL
divergences, are defined on different probability spaces.

</div>

</div>
