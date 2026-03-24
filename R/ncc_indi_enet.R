#' Conditional Logistic Regression with Individual-level External Data and Elastic Net Penalty (CLR-Indi-ENet)
#'
#' @description
#' Fits a series of penalized Conditional Logistic Regression models for matched
#' case-control data that integrate external individual-level data via a composite
#' likelihood weight \code{etas}, while applying an Elastic Net penalty for
#' variable selection and regularization in high-dimensional settings.
#'
#' @details
#' This function maps the CLR problem to a Cox PH model with fixed event time
#' \eqn{T=1} and \eqn{\delta=y} for both internal and external datasets, then
#' calls \code{\link{cox_indi_enet}} as the core engine.
#'
#' \itemize{
#'   \item If \code{alpha = 1}, the penalty is Lasso.
#'   \item If \code{alpha} is close to 0, the penalty approaches Ridge.
#'   \item If \code{eta = 0}, external data is ignored and the model reduces to
#'         a standard Elastic Net CLR on internal data only.
#' }
#'
#' @param y_int Numeric vector of binary outcomes for the internal dataset (0 = control, 1 = case).
#' @param z_int Numeric matrix of covariates for the internal dataset.
#' @param stratum_int Numeric or factor vector defining the internal matched sets. \strong{Required}.
#' @param y_ext Numeric vector of binary outcomes for the external dataset (0 = control, 1 = case).
#' @param z_ext Numeric matrix of covariates for the external dataset.
#' @param stratum_ext Numeric or factor vector defining the external matched sets. \strong{Required}.
#' @param etas Numeric vector of nonnegative external weights. \code{eta = 0} gives internal-only fit.
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 < \alpha \le 1}.
#'   \code{alpha = 1} is Lasso; \code{alpha} close to 0 approaches Ridge. Default \code{1}.
#' @param lambda Optional numeric vector of penalty parameters. If \code{NULL}, a path is
#'   generated automatically for each \code{eta}.
#' @param nlambda Integer. Number of lambda values to generate. Default \code{100}.
#' @param lambda.min.ratio Numeric. Ratio of smallest to largest lambda. Default \code{NULL}
#'   (determined automatically based on sample size vs. number of covariates).
#' @param lambda.early.stop Logical. If \code{TRUE}, stops the lambda path early if the
#'   loss improvement is small. Default \code{FALSE}.
#' @param tol Convergence tolerance. Default \code{1e-4}.
#' @param Mstop Maximum coordinate descent iterations per lambda. Default \code{1000}.
#' @param max.total.iter Maximum total iterations across the entire lambda path.
#'   Default \code{Mstop * nlambda}.
#' @param group Integer vector defining group membership for grouped penalties.
#'   Default treats each variable as its own group.
#' @param group.multiplier Numeric vector of multiplicative factors for group penalties.
#' @param standardize Logical. If \code{TRUE}, \code{z} is standardized internally.
#'   Coefficients are returned on the original scale. Default \code{TRUE}.
#' @param nvar.max Integer. Maximum number of active variables. Default \code{ncol(z_int)}.
#' @param group.max Integer. Maximum number of active groups.
#' @param stop.loss.ratio Numeric. Threshold for early stopping. Default \code{1e-2}.
#' @param actSet Logical. If \code{TRUE}, uses active-set strategy. Default \code{TRUE}.
#' @param actIter Integer. Iterations for active set refinement. Default \code{Mstop}.
#' @param actGroupNum Integer. Limit on active groups.
#' @param actSetRemove Logical. Whether to allow removal from active set. Default \code{FALSE}.
#' @param returnX Logical. If \code{TRUE}, returns the standardized design matrix. Default \code{FALSE}.
#' @param trace.lambda Logical. If \code{TRUE}, prints the lambda sequence progress. Default \code{FALSE}.
#' @param message Logical. If \code{TRUE}, shows a progress bar. Default \code{FALSE}.
#' @param ... Additional arguments passed to \code{\link{cox_indi_enet}}.
#'
#' @return An object of class \code{"ncc_indi_enet"} and \code{"cox_indi_enet"}.
#'   See \code{\link{cox_indi_enet}} for a description of the return components.
#'
#' @seealso \code{\link{cox_indi_enet}}, \code{\link{ncc_indi}}
#'
#' @export
ncc_indi_enet <- function(y_int, z_int, stratum_int,
                              y_ext, z_ext, stratum_ext,
                              etas,
                              alpha = 1,
                              lambda = NULL,
                              nlambda = 100,
                              lambda.min.ratio = NULL,
                              lambda.early.stop = FALSE,
                              tol = 1.0e-4,
                              Mstop = 1000,
                              max.total.iter = (Mstop * nlambda),
                              group = NULL,
                              group.multiplier = NULL,
                              standardize = TRUE,
                              nvar.max = NULL,
                              group.max = NULL,
                              stop.loss.ratio = 1e-2,
                              actSet = TRUE,
                              actIter = Mstop,
                              actGroupNum = NULL,
                              actSetRemove = FALSE,
                              returnX = FALSE,
                              trace.lambda = FALSE,
                              message = FALSE,
                              ...) {

  z_int <- as.matrix(z_int)
  z_ext <- as.matrix(z_ext)
  y_int <- as.numeric(y_int)
  y_ext <- as.numeric(y_ext)

  if (missing(stratum_int) || is.null(stratum_int)) {
    stop("stratum_int must be provided for ncc_indi_enet in 1:m matched settings.", call. = FALSE)
  }
  if (missing(stratum_ext) || is.null(stratum_ext)) {
    stop("stratum_ext must be provided for ncc_indi_enet in 1:m matched settings.", call. = FALSE)
  }

  if (length(y_int) != nrow(z_int)) {
    stop("Length of y_int must match the number of rows in z_int.", call. = FALSE)
  }
  if (length(y_ext) != nrow(z_ext)) {
    stop("Length of y_ext must match the number of rows in z_ext.", call. = FALSE)
  }

  # Map CLR problem to Cox PH problem: time = 1, delta = y
  time_int <- rep(1, length(y_int))
  time_ext <- rep(1, length(y_ext))

  fit <- cox_indi_enet(
    z_int             = z_int,
    delta_int         = y_int,
    time_int          = time_int,
    stratum_int       = stratum_int,
    z_ext             = z_ext,
    delta_ext         = y_ext,
    time_ext          = time_ext,
    stratum_ext       = stratum_ext,
    etas              = etas,
    alpha             = alpha,
    lambda            = lambda,
    nlambda           = nlambda,
    lambda.min.ratio  = lambda.min.ratio,
    lambda.early.stop = lambda.early.stop,
    tol               = tol,
    Mstop             = Mstop,
    max.total.iter    = max.total.iter,
    group             = group,
    group.multiplier  = group.multiplier,
    standardize       = standardize,
    nvar.max          = nvar.max,
    group.max         = group.max,
    stop.loss.ratio   = stop.loss.ratio,
    actSet            = actSet,
    actIter           = actIter,
    actGroupNum       = actGroupNum,
    actSetRemove      = actSetRemove,
    returnX           = returnX,
    trace.lambda      = trace.lambda,
    message           = message,
    ...
  )

  class(fit) <- c("ncc_indi_enet", class(fit))
  return(fit)
}
