#' BregSurv: Transfer Learning for Cox Models via Bregman Divergence
#'
#' BregSurv implements a Bregman-divergence framework for transfer learning in
#' survival analysis, allowing an internal cohort to borrow strength from external
#' information while accommodating population heterogeneity. The amount of borrowing
#' is governed by a single non-negative weight \code{eta}, with \code{eta = 0}
#' recovering the standard internal-only fit.
#'
#' Three modes of external information are supported, differing in what the external
#' source is able to share:
#' \itemize{
#'   \item \strong{Individual-level} (\code{\link{cox_indi}}, \code{\link{ncc_indi}}):
#'     the external covariates and outcomes themselves, combined through a weighted
#'     pseudo-likelihood.
#'   \item \strong{Coefficient-level / KL} (\code{\link{coxkl}},
#'     \code{\link{coxkl_ties}}, \code{\link{ncckl}}): only a published external
#'     coefficient vector, integrated through a Kullback--Leibler divergence penalty.
#'   \item \strong{Coefficient plus curvature / Mahalanobis} (\code{\link{cox_MDTL}},
#'     \code{\link{ncc_MDTL}}): an external coefficient vector together with its
#'     information or covariance matrix, integrated through a Mahalanobis-distance
#'     penalty.
#' }
#'
#' Each mode is available for both study-design families -- full-cohort Cox
#' proportional hazards models and nested case-control (NCC) designs -- with
#' stratification, tied event times, high-dimensional ridge and elastic-net variants,
#' and matching \code{cv.*} functions for tuning \code{eta} and \code{lambda}.
#'
#' Because an external source often covers only a subset of the internal covariates,
#' the exported helpers \code{\link{align_beta}} and \code{\link{align_beta_Q}}
#' reconcile a named external coefficient vector (and, for the Mahalanobis setting,
#' its weighting matrix) with \code{colnames(z)}, zero-padding covariates the external
#' source did not estimate. They are called automatically inside the fitting and
#' cross-validation functions, and are exported so the alignment can be inspected
#' directly.
#'
#' @useDynLib BregSurv, .registration = TRUE
#' @importFrom Rcpp sourceCpp
#' @keywords internal
"_PACKAGE"
