<div id="main" class="col-md-9" role="main">

# Package index

<div class="section level2">

## Low-Dimensional Individual-Level Internal–External Integration

<div class="section-desc">

Models that integrate individual-level external data via composite
likelihood weighting, for both full-cohort Cox and nested case-control
(NCC) designs.

</div>

</div>

<div class="section level2">

-   `cox_indi()` : Cox Proportional Hazards Model Integrated with
    External Individual-level Information
-   `cv.cox_indi()` : Cross-Validated cox\_indi to Tune etas
-   `ncc_indi()` : Conditional Logistic Regression with Individual-level
    External Data (CLR-Indi)
-   `cv.ncc_indi()` : Cross-Validated CLR with Individual-Level External
    Data

</div>

<div class="section level2">

## Low-Dimensional KL Divergence-Based Integration

<div class="section-desc">

Models that integrate external coefficient summaries via
Kullback–Leibler divergence penalization, for both full-cohort Cox and
nested case-control (NCC) designs.

</div>

</div>

<div class="section level2">

-   `coxkl()` : Cox Proportional Hazards Model with KL Divergence for
    Data Integration
-   `cv.coxkl()` : Cross-Validated Cox–KL to Tune the Integration
    Parameter (eta)
-   `bopt.coxkl()` : Bayesian Optimization for the Cox–KL Integration
    Parameter (eta)
-   `coxkl_ties()` : Cox Proportional Hazards Model with KL Divergence
    for Data Integration (Ties Handling)
-   `cv.coxkl_ties()` : Cross-Validated Cox–KL with Ties Handling to
    Tune the Integration Parameter (eta)
-   `ncckl()` : Conditional Logistic Regression with KL Divergence
    (CLR-KL)
-   `cv.ncckl()` : Cross-Validated Conditional Logistic Regression with
    KL Integration

</div>

<div class="section level2">

## Low-Dimensional Mahalanobis Distance-Based Integration

<div class="section-desc">

Models that integrate external coefficient and curvature summaries via
Mahalanobis distance penalization, for both full-cohort Cox and matched
case-control (NCC) designs.

</div>

</div>

<div class="section level2">

-   `cox_MDTL()` : Cox Proportional Hazards Model with Mahalanobis
    Distance Transfer Learning
-   `cv.cox_MDTL()` : Cross-Validation for Cox MDTL Model
-   `ncc_MDTL()` : Conditional Logistic Regression with Mahalanobis
    Distance Transfer Learning (CLR-MDTL)
-   `cv.ncc_MDTL()` : Cross-Validated CLR with Mahalanobis Distance
    Transfer Learning

</div>

<div class="section level2">

## High-Dimensional Individual-Level Internal–External Integration

<div class="section-desc">

Penalized models with Elastic Net regularization that integrate
individual-level external data, for both full-cohort Cox and nested
case-control (NCC) designs.

</div>

</div>

<div class="section level2">

-   `cox_indi_enet()` : Cox Proportional Hazards Model Integrated with
    External Individual-level Data and Elastic Net Penalty
-   `cv.cox_indi_enet()` : Cross-Validation for Cox Model Integrated
    with External Individual-level Data and Elastic Net Penalty
-   `ncc_indi_enet()` : Conditional Logistic Regression with
    Individual-level External Data and Elastic Net Penalty
    (CLR-Indi-ENet)
-   `cv.ncc_indi_enet()` : Cross-Validated CLR with Individual-Level
    External Data and Elastic Net Penalty

</div>

<div class="section level2">

## High-Dimensional KL Divergence-Based Integration

<div class="section-desc">

Penalized models with Ridge, Lasso, or Elastic Net regularization that
integrate external coefficient summaries via KL divergence, for both
full-cohort Cox and nested case-control (NCC) designs.

</div>

</div>

<div class="section level2">

-   `coxkl_ridge()` : Cox Proportional Hazards Model with Ridge Penalty
    and External Information
-   `coxkl_enet()` : Cox Proportional Hazards Model with KL Divergence
    and Elastic Net Penalty
-   `cv.coxkl_ridge()` : Cross-Validation for CoxKL Ridge Model (Tuning
    Eta and Lambda)
-   `cv.coxkl_enet()` : Cross-Validation for CoxKL Model with Elastic
    Net & Lasso Penalty
-   `ncckl_enet()` : Conditional Logistic Regression with KL Divergence
    and Elastic Net Penalty (CLR-KL-ENet)
-   `cv.ncckl_enet()` : Cross-Validated CLR-KL with Elastic Net Penalty

</div>

<div class="section level2">

## High-Dimensional Mahalanobis Distance-Based Integration

<div class="section-desc">

Penalized models with Ridge, Lasso, or Elastic Net regularization that
integrate external coefficient and curvature summaries via Mahalanobis
distance, for both full-cohort Cox and nested case-control (NCC)
designs.

</div>

</div>

<div class="section level2">

-   `cox_MDTL_ridge()` : Cox MDTL with Ridge Regularization
-   `cox_MDTL_enet()` : Fit Cox Model with Multi-Domain Transfer
    Learning and Elastic Net Penalty
-   `cv.cox_MDTL_ridge()` : Cross-Validation for Cox MDTL with Ridge
    Regularization
-   `cv.cox_MDTL_enet()` : Cross-Validation for Cox MDTL with Elastic
    Net Regularization
-   `ncc_MDTL_enet()` : Conditional Logistic Regression with Mahalanobis
    Distance Transfer Learning and Elastic Net (CLR-MDTL-ENet)
-   `cv.ncc_MDTL_enet()` : Cross-Validated CLR with Mahalanobis Distance
    Transfer Learning and Elastic Net Penalty

</div>

<div class="section level2">

## Variable Selection and Stability for High-Dimensional Models

</div>

<div class="section level2">

-   `variable_importance()` : Bootstrap Variable Importance via
    Selection Frequency
-   `coxkl_enet.StabSelect()` : Stability Selection for KL-Integrated
    Cox Elastic-Net Models
-   `cox_MDTL_enet.StabSelect()` : Stability Selection for
    MDTL-Integrated Cox Elastic-Net Models

</div>

<div class="section level2">

## Bagging for High-Dimensional Models

</div>

<div class="section level2">

-   `coxkl_enet_bagging()` : Bagging for KL-Integrated Cox Elastic-Net
    Models
-   `cox_MDTL_enet_bagging()` : Bagging for MDTL-Integrated Cox
    Elastic-Net Models

</div>

<div class="section level2">

## Multi-Source Integration

</div>

<div class="section level2">

-   `coxkl_enet.multi()` : Multi-Source Integration for KL-Integrated
    Cox Elastic-Net Models

</div>

<div class="section level2">

## Plotting Functions

</div>

<div class="section level2">

-   `cv.plot()` : Plot Cross-Validation Results vs Eta
-   `plot(<coxkl>)` : Plot Validation Results for coxkl Object
-   `plot(<coxkl_ridge>)` : Plot Validation Results for coxkl\_ridge
    Object
-   `plot(<coxkl_enet>)` : Plot Validation Results for coxkl\_enet
    Object
-   `plot(<cox_MDTL>)` : Plot Validation Results for Cox\_MDTL Object
-   `plot(<cox_MDTL_enet>)` : Plot Validation Results for
    cox\_MDTL\_enet Object
-   `plot(<cox_MDTL_ridge>)` : Plot Validation Results for
    cox\_MDTL\_ridge Object
-   `plot(<StabSelect>)` : Plot Stability Selection Path
-   `plot(<variable_importance>)` : Plot Variable Importance (Selection
    Frequency)
-   `plot(<coxkl_enet.multi>)` : Plot Method for Multi-Source
    KL-Integrated Cox Elastic-Net Models

</div>

<div class="section level2">

## Utilities

</div>

<div class="section level2">

-   `generate_eta()` : Generate a Sequence of Tuning Parameters (eta)

</div>

<div class="section level2">

## Datasets

</div>

<div class="section level2">

-   `ExampleData_lowdim` : Example low-dimensional survival data
-   `ExampleData_highdim` : Example high-dimensional survival data
-   `ExampleData_cc_lowdim` : Example Data for Conditional Logistic
    Regression
-   `ExampleData_cc_highdim` : Example high-dimensional matched
    case-control data
-   `ExampleData_indi` : Example internal/external Cox individual-level
    data
-   `ExampleData_cc_indi` : Example internal/external matched
    case-control individual-level data

</div>

</div>
