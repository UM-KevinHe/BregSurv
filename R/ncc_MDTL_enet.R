#' Conditional Logistic Regression with Mahalanobis Distance Transfer Learning and Elastic Net (CLR-MDTL-ENet)
#'
#' @description
#' Fits a Conditional Logistic Regression model for matched case-control (1:M) data
#' by mapping the problem to a Cox proportional hazards model with fixed event time,
#' while incorporating external coefficient information via a Mahalanobis distance
#' penalty and applying an Elastic Net (Lasso + Ridge) penalty for variable selection.
#'
#' @details
#' This function maps the CLR problem to a Cox model with \eqn{T = 1} and
#' \eqn{\delta = y}, then calls \code{\link{cox_MDTL_enet}} as the core engine.
#'
#' The objective function minimizes the negative conditional log-likelihood plus:
#' \deqn{\frac{\eta}{2}(\beta - \beta_{ext})^T Q (\beta - \beta_{ext}) + \text{Pen}_{\lambda,\alpha}(\beta)}
#' where \eqn{Q} is the weighting matrix and \eqn{\text{Pen}_{\lambda,\alpha}} is the
#' Elastic Net penalty.
#'
#' \itemize{
#'   \item If \code{eta = 0}, the method reduces to a standard Elastic Net CLR.
#'   \item If \code{alpha = 1}, the penalty is Lasso.
#'   \item If \code{alpha} is close to 0, the penalty approaches Ridge.
#'   \item If \code{vcov = NULL}, \eqn{Q = I} (Euclidean distance shrinkage towards \code{beta}).
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates (rows = observations, columns = variables).
#' @param stratum Numeric or factor vector defining the matched sets (strata). \strong{Required}.
#' @param beta Numeric vector of external coefficients (length \code{ncol(z)}). \strong{Required}.
#' @param vcov Optional numeric matrix (\code{ncol(z)} x \code{ncol(z)}) acting as the
#'   weighting matrix \eqn{Q}. Typically the precision matrix of the external estimator.
#'   If \code{NULL}, defaults to the identity matrix.
#' @param eta Numeric scalar. The transfer learning parameter (\eqn{\geq 0}). Controls
#'   the strength of external information. \code{eta = 0} ignores external info.
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 < \alpha \le 1}.
#'   \code{alpha = 1} is Lasso; \code{alpha} close to 0 approaches Ridge. Default \code{NULL}
#'   (set to 1 with a warning if not supplied).
#' @param lambda Optional user-supplied lambda sequence. If \code{NULL}, the algorithm
#'   generates its own sequence based on \code{nlambda} and \code{lambda.min.ratio}.
#' @param nlambda Integer. Number of lambda values. Default \code{100}.
#' @param lambda.min.ratio Smallest value for lambda as a fraction of \code{lambda.max}.
#'   Default depends on sample size relative to number of covariates.
#' @param lambda.early.stop Logical. Whether to stop early if deviance changes minimally.
#'   Default \code{FALSE}.
#' @param tol Convergence tolerance for coordinate descent. Default \code{1e-4}.
#' @param Mstop Maximum iterations per lambda step. Default \code{1000}.
#' @param max.total.iter Maximum total iterations across all lambda values.
#'   Default \code{Mstop * nlambda}.
#' @param group Integer vector describing group membership of coefficients.
#'   Default \code{1:ncol(z)} (no grouping).
#' @param group.multiplier Numeric vector of multipliers for each group.
#' @param standardize Logical. If \code{TRUE}, predictors are standardized before fitting.
#'   Default \code{TRUE}.
#' @param nvar.max Maximum number of variables in the model. Default \code{ncol(z)}.
#' @param group.max Maximum number of groups in the model.
#' @param stop.loss.ratio Ratio of loss change for early path stopping. Default \code{1e-2}.
#' @param actSet Logical. Whether to use active set convergence strategy. Default \code{TRUE}.
#' @param actIter Iterations for active set. Default \code{Mstop}.
#' @param actGroupNum Number of active groups.
#' @param actSetRemove Logical. Whether to remove inactive groups from active set.
#'   Default \code{FALSE}.
#' @param returnX Logical. If \code{TRUE}, returns the standardized design matrix.
#'   Default \code{FALSE}.
#' @param trace.lambda Logical. If \code{TRUE}, prints current lambda during fitting.
#'   Default \code{FALSE}.
#' @param message Logical. If \code{TRUE}, prints warnings and progress messages.
#'   Default \code{FALSE}.
#' @param ... Additional arguments passed to \code{\link{cox_MDTL_enet}}.
#'
#' @return An object of class \code{"ncc_MDTL_enet"} and \code{"cox_MDTL_enet"}.
#'   See \code{\link{cox_MDTL_enet}} for a description of the return components.
#'
#' @seealso \code{\link{cox_MDTL_enet}}, \code{\link{ncckl_enet}}
#'
#' @examples
#' \dontrun{
#' data(ExampleData_cc_highdim)
#' train_cc <- ExampleData_cc_highdim$train
#'
#' y        <- train_cc$y
#' z        <- train_cc$z
#' sets     <- train_cc$stratum
#' beta_ext <- ExampleData_cc_highdim$beta_external
#'
#' fit <- ncc_MDTL_enet(
#'   y       = y,
#'   z       = z,
#'   stratum = sets,
#'   beta    = beta_ext,
#'   vcov    = NULL,
#'   eta     = 0,
#'   alpha   = 1
#' )
#' }
#' @export
ncc_MDTL_enet <- function(y, z, stratum,
                              beta, vcov = NULL,
                              eta = NULL,
                              alpha = NULL,
                              lambda = NULL,
                              nlambda = 100,
                              lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.05, 1e-03),
                              lambda.early.stop = FALSE,
                              tol = 1.0e-4,
                              Mstop = 1000,
                              max.total.iter = (Mstop * nlambda),
                              group = 1:ncol(z),
                              group.multiplier = NULL,
                              standardize = TRUE,
                              nvar.max = ncol(z),
                              group.max = length(unique(group)),
                              stop.loss.ratio = 1e-2,
                              actSet = TRUE,
                              actIter = Mstop,
                              actGroupNum = sum(unique(group) != 0),
                              actSetRemove = FALSE,
                              returnX = FALSE,
                              trace.lambda = FALSE,
                              message = FALSE,
                              ...) {

  z <- as.matrix(z)
  y <- as.numeric(y)

  if (missing(stratum) || is.null(stratum)) {
    stop("stratum must be provided for ncc_MDTL_enet in 1:m matched settings.", call. = FALSE)
  }

  if (length(y) != nrow(z)) {
    stop("Length of y must match the number of rows in z.", call. = FALSE)
  }

  # Map CLR problem to Cox PH problem: time = 1, delta = y
  delta <- y
  time  <- rep(1, length(y))

  fit <- cox_MDTL_enet(
    z                 = z,
    delta             = delta,
    time              = time,
    stratum           = stratum,
    beta              = beta,
    vcov              = vcov,
    eta               = eta,
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
    data_sorted       = FALSE,
    ...
  )

  class(fit) <- c("ncc_MDTL_enet", class(fit))
  return(fit)
}
