#' Conditional Logistic Regression with KL Integration and a Ridge Penalty
#'
#' @description
#' Fits the 1:m matched case-control model of \code{\link{ncckl}} with a ridge
#' (L2) penalty on the coefficients, over a path of penalty values. The conditional
#' likelihood is computed as a stratified Cox partial likelihood with every row of a
#' matched set at the same time and Breslow risk sets, so the risk set of the case is
#' its whole matched set whatever the row order.
#'
#' @param y Numeric 0/1 case indicator.
#' @param z Numeric covariate matrix.
#' @param stratum Matched-set identifier (required).
#' @param RS Optional external risk score, one per row.
#' @param beta Optional external coefficients (named vectors are aligned by name,
#'   see \code{\link{align_beta}}).
#' @param eta Single non-negative integration weight.
#' @param lambda Optional ridge penalty values; \code{NULL} generates a path ending at 0.
#' @param nlambda,penalty.factor,standardize,tol,Mstop,message,beta_initial As in
#'   \code{\link{coxkl_ridge}}.
#' @return An object of class \code{c("ncckl_ridge", "coxkl_ridge")}.
#' @examples
#' \dontrun{
#' data(ExampleData_cc_highdim)
#' d <- ExampleData_cc_highdim$train
#' fit <- ncckl_ridge(y = d$y, z = d$z, stratum = d$stratum,
#'                    beta = ExampleData_cc_highdim$beta_external, eta = 1)
#' }
#' @export
ncckl_ridge <- function(y, z, stratum, RS = NULL, beta = NULL, eta = NULL,
                        lambda = NULL, nlambda = 100, penalty.factor = 0.999,
                        standardize = TRUE, tol = 1.0e-4, Mstop = 50,
                        message = FALSE, beta_initial = NULL) {
  z <- as.matrix(z)
  y <- .check_event(y, "y")
  if (missing(stratum) || is.null(stratum))
    stop("stratum must be provided for ncckl_ridge in 1:m matched settings.", call. = FALSE)
  if (length(y) != nrow(z)) stop("Length of y must match the number of rows in z.", call. = FALSE)
  fit <- coxkl_ridge(z = z, delta = y, time = rep(1, length(y)), stratum = stratum,
                     RS = RS, beta = beta, eta = eta, lambda = lambda, nlambda = nlambda,
                     penalty.factor = penalty.factor, tol = tol, Mstop = Mstop,
                     message = message, standardize = standardize,
                     beta_initial = beta_initial, ties = "breslow")
  class(fit) <- c("ncckl_ridge", class(fit))
  fit
}

#' Conditional Logistic Regression with Mahalanobis Integration and a Ridge Penalty
#'
#' @description
#' Fits the 1:m matched case-control model of \code{\link{ncc_MDTL}} with a ridge
#' (L2) penalty, over a path of penalty values, with Breslow risk sets on matched
#' sets placed at a common time (exact for one case per set).
#'
#' @param y,z,stratum As in \code{\link{ncckl_ridge}}.
#' @param beta External coefficients (named vectors aligned by name).
#' @param Q Optional penalty metric (precision matrix); \code{NULL} uses the identity on
#'   the covered coordinates, see \code{\link{align_beta_Q}}.
#' @param eta Single non-negative integration weight.
#' @param lambda,nlambda,penalty.factor,standardize,tol,Mstop,message,beta_initial As in
#'   \code{\link{cox_MDTL_ridge}}.
#' @return An object of class \code{c("ncc_MDTL_ridge", "cox_MDTL_ridge")}.
#' @examples
#' \dontrun{
#' data(ExampleData_cc_highdim)
#' d <- ExampleData_cc_highdim$train
#' fit <- ncc_MDTL_ridge(y = d$y, z = d$z, stratum = d$stratum,
#'                       beta = ExampleData_cc_highdim$beta_external, eta = 1)
#' }
#' @export
ncc_MDTL_ridge <- function(y, z, stratum, beta, Q = NULL, eta = NULL,
                           lambda = NULL, nlambda = 100, penalty.factor = 0.999,
                           standardize = TRUE, tol = 1.0e-4, Mstop = 50,
                           message = FALSE, beta_initial = NULL) {
  z <- as.matrix(z)
  y <- .check_event(y, "y")
  if (missing(stratum) || is.null(stratum))
    stop("stratum must be provided for ncc_MDTL_ridge in 1:m matched settings.", call. = FALSE)
  if (length(y) != nrow(z)) stop("Length of y must match the number of rows in z.", call. = FALSE)
  fit <- cox_MDTL_ridge(z = z, delta = y, time = rep(1, length(y)), stratum = stratum,
                        beta = beta, Q = Q, eta = eta, lambda = lambda, nlambda = nlambda,
                        penalty.factor = penalty.factor, tol = tol, Mstop = Mstop,
                        message = message, standardize = standardize,
                        beta_initial = beta_initial, ties = "breslow")
  class(fit) <- c("ncc_MDTL_ridge", class(fit))
  fit
}
