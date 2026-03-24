#' Conditional Logistic Regression with KL Divergence and Elastic Net Penalty (CLR-KL-ENet)
#'
#' @description
#' Fits a Conditional Logistic Regression model for matched case-control (1:M) data
#' by mapping the problem to a Cox proportional hazards model with fixed event time,
#' while integrating external information via Kullback–Leibler (KL) divergence and
#' applying an Elastic Net (Lasso + Ridge) penalty for variable selection
#' and regularization.
#'
#' This function is a thin wrapper around \code{\link{coxkl_enet}}:
#' it maps the CLR problem to a Cox model with \eqn{T = 1} and \eqn{\delta = y}
#' and then calls \code{coxkl_enet} as the core engine.
#'
#' External information can be provided either as:
#' \itemize{
#'   \item \code{RS}: Precomputed external risk scores (aligned with the rows of \code{z}).
#'   \item \code{beta}: Externally derived coefficients (which are converted to risk scores internally).
#' }
#' The strength of integration is controlled by the tuning parameter \code{eta}, while
#' \code{alpha} and \code{lambda} govern the Elastic Net penalty.
#'
#' @details
#' This function assumes a 1:M matched case-control design, where each stratum
#' corresponds to a matched set containing one case (\code{y = 1}) and one or more
#' controls (\code{y = 0}). The CLR likelihood is equivalent to a Cox partial likelihood
#' with a common event time within each matched set. Thus, we define
#' \eqn{\delta_i = y_i} and \eqn{T_i = 1} for all subjects and fit a stratified Cox model
#' with KL divergence and Elastic Net penalty via \code{\link{coxkl_enet}}.
#'
#' \itemize{
#'   \item If \code{eta = 0}, the method reduces to a standard Elastic Net CLR
#'   (ignoring external information).
#'   \item If \code{alpha = 1}, the penalty is Lasso.
#'   \item If \code{alpha} is close to 0, the penalty approaches Ridge.
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates (predictors). Rows are observations, columns are variables.
#' @param stratum Numeric or factor vector defining the matched sets (strata).
#'   This is required for conditional logistic regression.
#' @param RS Optional numeric vector of external risk scores. Length must equal \code{nrow(z)}.
#'   If not provided, \code{beta} must be supplied.
#' @param beta Optional numeric vector of external coefficients. Length must equal \code{ncol(z)}.
#'   If provided, it is used to calculate risk scores. If not provided, \code{RS} must be supplied.
#' @param eta Numeric scalar. The tuning parameter for KL divergence (integration strength).
#'   Defaults to 0 (no external information).
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 < \alpha \le 1}.
#'   \code{alpha = 1} is the Lasso penalty, and \code{alpha} close to 0 approaches Ridge.
#'   If \code{NULL}, it is set to 1 with a warning inside \code{\link{coxkl_enet}}.
#' @param lambda Optional numeric vector of penalty parameters. If \code{NULL},
#'   a path is generated automatically.
#' @param nlambda Integer. Number of lambda values to generate when \code{lambda} is \code{NULL}.
#'   Default is 100.
#' @param lambda.min.ratio Numeric. Ratio of the smallest to the largest lambda in the sequence
#'   when \code{lambda} is \code{NULL}. Default is \code{1e-3}. Users may override this to
#'   mimic the behavior in \code{\link{coxkl_enet}}.
#' @param lambda.early.stop Logical. If \code{TRUE}, stops the lambda path early if the loss
#'   improvement is small.
#' @param tol Numeric. Convergence tolerance for the optimization. Default is \code{1e-4}.
#' @param Mstop Integer. Maximum iterations for the inner loop per lambda. Default is \code{1000}.
#' @param max.total.iter Integer. Maximum total iterations across the entire lambda path.
#'   Default is \code{Mstop * nlambda}.
#' @param group Integer vector defining group membership for grouped penalties.
#'   Default treats each variable as its own group (\code{1:ncol(z)}).
#' @param group.multiplier Numeric vector. Multiplicative factors for penalties applied
#'   to each group.
#' @param standardize Logical. If \code{TRUE}, \code{z} is standardized internally.
#'   Coefficients are returned on the original scale. Default is \code{TRUE}.
#' @param nvar.max Integer. Maximum number of active variables allowed.
#'   Default is \code{ncol(z)}.
#' @param group.max Integer. Maximum number of active groups allowed.
#'   Default is the total number of unique groups.
#' @param stop.loss.ratio Numeric. Threshold for early stopping based on loss ratio.
#'   Default is \code{1e-2}.
#' @param actSet Logical. If \code{TRUE}, uses an active-set strategy for optimization.
#'   Default is \code{TRUE}.
#' @param actIter Integer. Iterations for active set refinement.
#'   Default is \code{Mstop}.
#' @param actGroupNum Integer. Limit on active groups in the active-set strategy.
#'   Default is \code{sum(unique(group) != 0)}.
#' @param actSetRemove Logical. Whether to allow removal of groups from the active set.
#'   Default is \code{FALSE}.
#' @param returnX Logical. If \code{TRUE}, returns the standardized design matrix
#'   and processed data in the result. Default is \code{FALSE}.
#' @param trace.lambda Logical. If \code{TRUE}, prints the lambda sequence progress.
#'   Default is \code{FALSE}.
#' @param message Logical. If \code{TRUE}, prints informative messages during fitting.
#'   Default is \code{FALSE}.
#' @param ... Additional arguments passed to \code{\link{coxkl_enet}}.
#'
#' @return
#' An object of class \code{"ncckl_enet"} and \code{"coxkl_enet"} containing:
#' \describe{
#'   \item{\code{beta}}{Matrix of coefficient estimates (p x nlambda).}
#'   \item{\code{lambda}}{Sequence of lambda values used.}
#'   \item{\code{alpha}}{Elastic Net mixing parameter used.}
#'   \item{\code{likelihood}}{Vector of negative log-partial likelihoods (loss)
#'         for each lambda.}
#'   \item{\code{df}}{Vector of degrees of freedom (number of non-zero coefficients)
#'         for each lambda.}
#'   \item{\code{iter}}{Vector of iteration counts for each lambda.}
#'   \item{\code{W}}{Matrix of exponentiated linear predictors (risk scores)
#'         on the original scale.}
#'   \item{\code{data}}{List containing the input data used (including \code{y},
#'         \code{z}, \code{stratum}, and external information).}
#' }
#'
#' @seealso
#' \code{\link{coxkl_enet}} for the underlying Cox PH engine with KL divergence
#' and Elastic Net regularization.
#'
#' @examples
#' \dontrun{
#' data(ExampleData_cc)
#' train_cc <- ExampleData_cc$train
#'
#' y <- train_cc$y
#' z <- train_cc$z
#' sets <- train_cc$stratum
#'
#' beta_external_cc <- ExampleData_cc$beta_external
#'
#' # Fit CLR-KL-ENet with eta = 0 (standard Elastic Net CLR)
#' ncckl_enet_fit <- ncckl_enet(
#'   y       = y,
#'   z       = z,
#'   stratum = sets,
#'   beta    = beta_external_cc,
#'   eta     = 0
#' )
#' }
#'
#' @export
ncckl_enet <- function(y,
                          z,
                          stratum,
                          RS = NULL,
                          beta = NULL,
                          eta = NULL,
                          alpha = NULL,
                          lambda = NULL,
                          nlambda = 100,
                          lambda.min.ratio = 1e-3,
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

  if (missing(stratum)) {
    warning("Stratum not provided; all data assumed in one stratum", call. = FALSE)
    stratum <- rep(1, length(y))
  }

  if (length(y) != nrow(z)) {
    stop("Length of y must match the number of rows in z.", call. = FALSE)
  }

  # Map CLR problem to Cox PH problem: time = 1, delta = y
  delta <- y
  time  <- rep(1, length(y))

  fit <- coxkl_enet(
    z                 = z,
    delta             = delta,
    time              = time,
    stratum           = stratum,
    RS                = RS,
    beta              = beta,
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

  class(fit) <- c("ncckl_enet", class(fit))
  return(fit)
}
