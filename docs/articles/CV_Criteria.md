# Cross-validation Criteria

## Cross-validation Criterion for Cox Model

Cross-validation is used to select the tuning parameters
$`(\eta, \lambda)`$ for the integrated model.  
For time-to-event outcomes, we consider two broad classes of evaluation
criteria:

1.  **Discrimination-based measures**, represented by Harrell’s
    concordance index (C-index) (Harrell et al. 1982)  
2.  **Partial likelihood–based criteria** that assess goodness of fit

- The **Harrell’s C-index** evaluates a model’s discriminative ability
  to rank individuals by risk.  
  A **stratified C-index** is implemented to align with the stratified
  Cox model, under which baseline hazards differ across strata and risk
  comparisons are valid only within strata.  
  The detailed formula is given in Appendix @ref(cindex_appendix).  
  A higher C-index indicates better ability to distinguish high-risk
  from low-risk individuals.

  In the cross-validation setting, two C-index calculation schemes are
  implemented:

  - **`"CIndex_pooled"` (default)**

    For each validation fold $`i`$ ($`i = 1, 2, \dots, \mathcal{K}`$),
    let  
    $`D_{is}`$ denote the number of comparable pairs and $`N_{is}`$ the
    number of concordant pairs within stratum $`s`$.  
    The pooled C-index aggregates information across all folds and all
    strata:

    ``` math
    \widehat{C}_{\text{pooled}}
    =
    \frac{
      \sum_{i = 1}^{\mathcal{K}} \sum_{s = 1}^{S} N_{is}
    }{
      \sum_{i = 1}^{\mathcal{K}} \sum_{s = 1}^{S} D_{is}
    }.
    ```

    This approach is typically more stable across folds and performs
    well even in settings with limited events.

  - **`"CIndex_foldavg"`**

    In this approach, the C-index is first computed within each
    validation fold and then averaged across folds:

    ``` math
    \widehat{C}_{\text{foldavg}}
    =
    \frac{1}{\mathcal{K}}
    \sum_{i = 1}^{\mathcal{K}}
    \frac{
      \sum_{s = 1}^{S} N_{is}
    }{
      \sum_{s = 1}^{S} D_{is}
    }.
    ```

    Because concordance in a stratified Cox model is only defined within
    strata, each fold may contain a different distribution of strata.  
    When the strata composition varies across folds, the number of
    comparable pairs can differ substantially from fold to fold, which
    may introduce instability or bias in the fold-averaged C-index even
    when each fold has the same total sample size.

- Two partial-likelihood–based criteria are included for
  cross-validation: the Van Houwelingen (V&VH) likelihood method
  (Verweij and Van Houwelingen 1993) and a linear-predictor–based
  predictive deviance criterion (LinPred).

  - **`"LinPred"`**

    The LinPred criterion evaluates out-of-sample performance via
    cross-validated partial likelihood.  
    In each fold, the model is fit on the training subset and the
    estimated coefficients are applied to the held-out subset to obtain
    predicted linear predictors.  
    These cross-validated predictors are then combined and used to
    evaluate the partial likelihood.  
    This procedure yields an out-of-sample analogue of the Cox partial
    likelihood deviance and can therefore be interpreted as a predictive
    deviance, equivalent to a cross-entropy–based measure of goodness of
    fit (Simon et al. 2011).

  - **`"V&VH"`**

    The V&VH criterion averages, across folds, the difference between
    the log-partial likelihood evaluated on each fold-specific training
    set and that of the full dataset.  
    While this approach preserves the full risk-set structure, it is
    computationally more demanding and may be sensitive to high-leverage
    observations.

------------------------------------------------------------------------

## Cross-validation Criterion for (Nested) Case–Control Studies

Predictive performance under matched study designs is evaluated
conditionally within matched sets, reflecting the structure induced by
matching rather than a marginal population-based sampling scheme. We
consider three complementary aspects of predictive accuracy:
discrimination, calibration, and goodness-of-fit. All evaluation metrics
are computed on an independent test set composed of matched sets.

Let $`s = 1,\ldots,S`$ index matched sets, and let $`\mathcal{M}_s`$
denote the subjects in set $`s`$. For subject $`i \in \mathcal{M}_s`$,
we denote the binary outcome by $`Y_i^{(s)} \in \{0,1\}`$ and the
model-based risk score by $`\hat r(\mathbf{Z}_i^{(s)})`$, where larger
values indicate higher predicted risk. When probability-based metrics
are required, the risk score is transformed into a predicted probability
$`\hat p_i^{(s)}`$ using an appropriate link function consistent with
the fitted model.

**Predictive Deviance (`"loss"`)**

Goodness-of-fit assesses how well the fitted working model agrees with
the distribution of the held-out test data at the likelihood level,
conditional on the matched case–control design. Let $`s = 1,\ldots,S`$
index matched sets, and let $`\ell_s(\widehat{\boldsymbol{\beta}})`$
denote the conditional log-likelihood contribution of matched set $`s`$
under the coefficient vector $`\widehat{\boldsymbol{\beta}}`$. Summing
across matched sets yields the total conditional log-likelihood

``` math
\ell(\widehat{\boldsymbol{\beta}})
=
\sum_{s=1}^S \ell_s(\widehat{\boldsymbol{\beta}}).
```

We report a predictive deviance (**reid2014regularization?**) defined as

``` math
\mathrm{Dev}
=
-\frac{2}{n}\,\ell(\widehat{\boldsymbol{\beta}}),
```

where $`n`$ denotes the total number of subjects in the test data.
Smaller values indicate better agreement between the fitted model and
the observed outcomes on held-out matched sets.

**Matched-set AUC (`"AUC"` or `"CIndex"`)**

In matched case–control studies, each case is paired with one or more
controls according to predefined matching criteria, and model
discrimination is evaluated through comparisons restricted within
matched sets. We use matched-set AUC to evaluate the discrimination
ability (Hanley and McNeil 1982). Let $`s = 1,\ldots,S`$ index matched
sets, and let $`\mathcal{M}_s`$ denote the subjects in set $`s`$, which
contains one case ($`Y_i=1`$) and $`m`$ matched controls ($`Y_j=0`$).
For each subject, we compute a risk score $`\hat r(\mathbf{Z}_i)`$ from
the fitted model.

Discrimination is assessed by the probability that the case in a matched
set receives a higher risk score than its matched controls.
Specifically, the matched-set AUC is defined as

``` math
\mathrm{AUC}_s
=
P\!\left(
\hat r(\mathbf{Z}_i) > \hat r(\mathbf{Z}_j)
\,\big|\,
i \text{ is the case in } \mathcal{M}_s,\ 
j \text{ is a control in } \mathcal{M}_s
\right),
```

which can be estimated using a rank-based U-statistic based on all
comparable case–control pairs within $`\mathcal{M}_s`$.

To summarize discrimination across all matched sets, we aggregate
set-specific AUCs using a weighted average,

``` math
\mathrm{AUC}
=
\frac{\sum_{s=1}^S w_s \, \widehat{\mathrm{AUC}}_s}{\sum_{s=1}^S w_s},
```

where $`w_s`$ is proportional to the number of comparable pairs in set
$`s`$. This criterion evaluates the model’s ability to correctly rank
cases above their matched controls and is fully determined by the
matched case–control structure, without reliance on prospective
follow-up times, censoring indicators, or estimation of a baseline
hazard.

Nested case–control (NCC) studies arise as a special case of matched
case–control designs, where controls are sampled from the risk set at
each observed event time in an underlying cohort. Although the matching
mechanism is time-dependent in NCC studies, discrimination can be
evaluated using the same matched-set AUC defined above. In particular,
the resulting AUC is numerically equivalent to the concordance index
(`"CIndex"`) evaluated on the sampled risk sets, since each matched set
corresponds to a valid risk set at the event time and the associated
case–control comparisons coincide with concordance comparisons in the
Cox model.

**Brier Score (`"Brier"`)**

Calibration evaluates the agreement between predicted risks and observed
outcomes at the individual level. Under matched case–control designs,
where the outcome is binary and comparisons are conditioned on matched
sets, calibration can be assessed using the Brier score (Glenn et al.
1950). Let $`Y_i^{(s)} \in \{0,1\}`$ denote the case–control status of
subject $`i`$ in matched set $`s`$, and let $`\hat p_i^{(s)}`$ denote
the model-based predicted probability of being a case, obtained by
transforming the risk score $`\hat r(\mathbf{Z}_i^{(s)})`$ through an
appropriate link function.

The Brier score is defined as the mean squared error between predicted
probabilities and observed outcomes,

``` math
\mathrm{BS}
=
\frac{1}{n}
\sum_{s=1}^S
\sum_{i \in \mathcal{M}_s}
\left(
Y_i^{(s)} - \hat p_i^{(s)}
\right)^2,
```

where $`n`$ denotes the total number of subjects in the test data.
Smaller values of the Brier score indicate better calibration and
overall predictive accuracy.

## Reference

Glenn, W Brier et al. 1950. “Verification of Forecasts Expressed in
Terms of Probability.” *Monthly Weather Review* 78 (1): 1–3.

Hanley, James A, and Barbara J McNeil. 1982. “The Meaning and Use of the
Area Under a Receiver Operating Characteristic (ROC) Curve.” *Radiology*
143 (1): 29–36.

Harrell, Frank E, Robert M Califf, David B Pryor, Kerry L Lee, and
Robert A Rosati. 1982. “Evaluating the Yield of Medical Tests.” *JAMA*
247 (18): 2543–46.

Simon, Noah, Jerome H Friedman, Trevor Hastie, and Rob Tibshirani. 2011.
“Regularization Paths for Cox’s Proportional Hazards Model via
Coordinate Descent.” *Journal of Statistical Software* 39: 1–13.

Verweij, Pierre JM, and Hans C Van Houwelingen. 1993. “Cross-Validation
in Survival Analysis.” *Statistics in Medicine* 12 (24): 2305–14.
