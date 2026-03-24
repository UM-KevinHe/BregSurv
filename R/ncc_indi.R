#' Conditional Logistic Regression with Individual-level External Data (CLR-Indi)
#'
#' @description
#' Fits a series of Conditional Logistic Regression models that integrate external
#' individual-level data via a composite likelihood weight \code{etas},
#' suitable for matched case-control studies.
#'
#' @details
#' This function maps the Conditional Logistic Regression problem to a Cox PH
#' model with fixed event time \eqn{T=1} and event indicator \eqn{\delta=y}
#' for both the internal and external matched case-control datasets, then calls
#' \code{\link{cox_indi}} as the core engine.
#'
#' The fitted objective is
#' \deqn{\ell_\eta(\beta) = \ell_{\text{int}}(\beta) + \eta \, \ell_{\text{ext}}(\beta),}
#' where both likelihoods are the conditional (partial) log-likelihoods of the respective
#' matched datasets, with internal and external risk sets kept separated.
#'
#' @param y_int Numeric vector of binary outcomes for the internal dataset (0 = control, 1 = case).
#' @param z_int Numeric matrix of covariates for the internal dataset.
#' @param stratum_int Numeric or factor vector defining the matched sets (strata) for the
#'   internal dataset. \strong{Required}.
#' @param y_ext Numeric vector of binary outcomes for the external dataset (0 = control, 1 = case).
#' @param z_ext Numeric matrix of covariates for the external dataset. Must have the same
#'   number of columns as \code{z_int}.
#' @param stratum_ext Numeric or factor vector defining the matched sets (strata) for the
#'   external dataset. \strong{Required}.
#' @param etas Numeric vector of nonnegative external weights. \code{eta = 0} gives
#'   an internal-only fit.
#' @param max_iter Maximum number of Newton-Raphson iterations. Default \code{100}.
#' @param tol Convergence tolerance. Default \code{1e-7}.
#' @param message Logical. If \code{TRUE}, shows a progress bar. Default \code{FALSE}.
#'
#' @return An object of class \code{"ncc_indi"} and \code{"cox_indi"} containing
#' the estimation results for each \code{eta} value. See \code{\link{cox_indi}} for
#' a description of the return components.
#'
#' @seealso \code{\link{cox_indi}} for the core function documentation.
#'
#' @export
ncc_indi <- function(y_int, z_int, stratum_int,
                        y_ext, z_ext, stratum_ext,
                        etas, max_iter = 100, tol = 1.0e-7,
                        message = FALSE) {

  z_int <- as.matrix(z_int)
  z_ext <- as.matrix(z_ext)
  y_int <- as.numeric(y_int)
  y_ext <- as.numeric(y_ext)

  if (missing(stratum_int) || is.null(stratum_int)) {
    stop("stratum_int must be provided for ncc_indi in 1:m matched settings.", call. = FALSE)
  }
  if (missing(stratum_ext) || is.null(stratum_ext)) {
    stop("stratum_ext must be provided for ncc_indi in 1:m matched settings.", call. = FALSE)
  }

  # Map CLR problem to Cox PH problem: time = 1, delta = y
  time_int <- rep(1, length(y_int))
  time_ext <- rep(1, length(y_ext))

  res <- cox_indi(
    z_int       = z_int,
    delta_int   = y_int,
    time_int    = time_int,
    stratum_int = stratum_int,
    z_ext       = z_ext,
    delta_ext   = y_ext,
    time_ext    = time_ext,
    stratum_ext = stratum_ext,
    etas        = etas,
    max_iter    = max_iter,
    tol         = tol,
    message     = message
  )

  class(res) <- c("ncc_indi", class(res))
  return(res)
}
