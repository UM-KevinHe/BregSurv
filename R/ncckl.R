#' Conditional Logistic Regression with KL Divergence (CLR-KL)
#'
#' @description
#' Fits a series of Conditional Logistic Regression models that integrate external
#' coefficient information (\code{beta}) using Kullback–Leibler (KL) divergence,
#' suitable for matched case-control studies.
#'
#' @details
#' This function maps the Conditional Logistic Regression problem to the Cox Proportional
#' Hazards model with fixed event time \eqn{T=1} and event indicator \eqn{\delta=y}.
#' It utilizes the \code{\link{coxkl_ties}} core engine to perform the data integration
#' via the KL divergence penalty.
#'
#' \itemize{
#'    \item **Method**: The \code{method} ("breslow" or "exact") specifies which form of
#'    the partial likelihood is used. For 1:M matched case-control studies, "breslow"
#'    and "exact" yield identical results, but "exact" is theoretically preferable.
#'    For \eqn{n:m} matched designs (\eqn{n>1}), the results will differ.
#'    \item **External Information**: Larger values of the tuning parameter \code{eta}
#'    enforce stronger agreement with the external coefficients \code{beta}.
#'    \item **Standard CLR**: Setting \code{etas = 0} (or including 0 in the sequence)
#'    recovers the standard Maximum Likelihood Estimates for Conditional Logistic Regression.
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates.
#' @param stratum Numeric or factor vector defining the matched sets (strata). This is **required** for CLR.
#' @param etas Numeric vector of tuning parameters. Controls the strength of external information integration.
#' @param beta Numeric vector of external coefficients. Used to compute the KL divergence penalty.
#' @param method Character string specifying the tie-handling method ("breslow" or "exact").
#' @param Mstop Integer. Maximum number of Newton-Raphson iterations. Default \code{100}.
#' @param tol Numeric. Convergence tolerance. Default \code{1e-4}.
#' @param message Logical. If \code{TRUE}, prints progress during fitting. Default \code{FALSE}.
#' @param comb_max Integer. Maximum number of combinations for the \code{method = "exact"} calculation. Default \code{1e7}.
#'
#' @return
#' An object of class \code{"coxkl"} (inherited from \code{\link{coxkl_ties}}) containing
#' the estimation results for each \code{eta} value, including estimated coefficients,
#' linear predictors, and log-partial likelihoods.
#'
#' @seealso \code{\link{coxkl_ties}} for the core function documentation.
#'
#' @examples
#' \dontrun{
#' # Load the matched case-control example data
#' data(ExampleData_cc)
#' train_cc <- ExampleData_cc$train
#' 
#' y <- train_cc$y
#' z <- train_cc$z
#' sets <- train_cc$stratum
#' 
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
#' external_beta <- ExampleData_cc$beta_external
#' 
#' # Fit CLR-KL using the Breslow approximation
#' ncckl.fit_breslow <- ncckl(y = y, z = z, stratum = sets, 
#'                                  eta = eta_list, beta = external_beta,
#'                                  method = "breslow")
#' }
#' @export
ncckl <- function(y, z, stratum, etas, beta,
                     method = c("breslow","exact"),
                     Mstop = 100, tol = 1e-4, 
                     message = FALSE,
                     comb_max = 1e7) {
  
  z <- as.matrix(z)
  y <- as.numeric(y)
  
  if (missing(stratum)) {
    warning("Stratum not provided; all data assumed in one stratum", call. = FALSE)
    stratum <- rep(1, length(y))
  }
  
  # Map CLR problem to Cox PH problem: time=1, delta=y
  delta <- y
  time <- rep(1, length(y))
  
  # Call the core CoxKL function
  res <- coxkl_ties(
    z = z,
    delta = delta,
    time = time,
    stratum = stratum,
    beta = beta,
    etas = etas,
    ties = method,
    tol = tol,
    Mstop = Mstop,
    message = message,
    comb_max = comb_max
  )
  return(res)
}