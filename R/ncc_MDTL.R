#' Conditional Logistic Regression with Mahalanobis Distance Transfer Learning (CLR-MDTL)
#'
#' @description
#' Fits a series of Conditional Logistic Regression models that incorporate external
#' coefficient information via a Mahalanobis distance penalty, suitable for matched
#' case-control studies.
#'
#' @details
#' This function maps the Conditional Logistic Regression problem to a Cox PH
#' model with fixed event time \eqn{T=1} and event indicator \eqn{\delta=y},
#' then calls \code{\link{cox_MDTL}} as the core engine.
#'
#' The objective function minimizes the negative conditional log-likelihood plus
#' a Mahalanobis distance penalty:
#' \deqn{P(\beta) = \frac{\eta}{2} (\beta - \beta_{ext})^T Q (\beta - \beta_{ext})}
#' where \eqn{Q} is the weighting matrix (identity if \code{vcov} is \code{NULL}).
#'
#' \itemize{
#'   \item Setting \code{etas = 0} recovers the standard CLR (no external information).
#'   \item Larger \code{eta} enforces stronger agreement with \code{beta}.
#'   \item If \code{vcov = NULL}, \eqn{Q = I} (Euclidean/Ridge-type shrinkage towards \code{beta}).
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates.
#' @param stratum Numeric or factor vector defining the matched sets (strata). \strong{Required}.
#' @param beta Numeric vector of external coefficients (length \code{ncol(z)}). \strong{Required}.
#' @param vcov Optional numeric matrix (\code{ncol(z)} x \code{ncol(z)}) acting as the
#'   weighting matrix \eqn{Q} in the Mahalanobis penalty. Typically the inverse of the
#'   external covariance (precision matrix). If \code{NULL}, defaults to the identity matrix.
#' @param etas Numeric vector of tuning parameters to evaluate. \strong{Required}.
#' @param tol Convergence tolerance for the Newton-Raphson algorithm. Default \code{1e-4}.
#' @param Mstop Maximum number of Newton-Raphson iterations. Default \code{50}.
#' @param backtrack Logical. If \code{TRUE}, uses backtracking line search. Default \code{FALSE}.
#' @param message Logical. If \code{TRUE}, progress messages are printed. Default \code{FALSE}.
#' @param beta_initial Optional initial coefficient vector for warm start.
#'
#' @return An object of class \code{"ncc_MDTL"} and \code{"cox_MDTL"} containing
#' the estimation results for each \code{eta} value. See \code{\link{cox_MDTL}} for
#' a description of the return components.
#'
#' @seealso \code{\link{cox_MDTL}}, \code{\link{ncckl}}
#'
#' @examples
#' \dontrun{
#' data(ExampleData_cc)
#' train_cc <- ExampleData_cc$train
#'
#' y       <- train_cc$y
#' z       <- train_cc$z
#' sets    <- train_cc$stratum
#' beta_ext <- ExampleData_cc$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
#'
#' fit <- ncc_MDTL(
#'   y      = y,
#'   z      = z,
#'   stratum = sets,
#'   beta   = beta_ext,
#'   vcov   = NULL,
#'   etas   = eta_list
#' )
#' }
#' @export
ncc_MDTL <- function(y, z, stratum,
                         beta, vcov = NULL, etas,
                         tol = 1.0e-4, Mstop = 50,
                         backtrack = FALSE,
                         message = FALSE,
                         beta_initial = NULL) {

  z <- as.matrix(z)
  y <- as.numeric(y)

  if (missing(stratum) || is.null(stratum)) {
    stop("stratum must be provided for ncc_MDTL in 1:m matched settings.", call. = FALSE)
  }

  # Map CLR problem to Cox PH problem: time = 1, delta = y
  delta <- y
  time  <- rep(1, length(y))

  res <- cox_MDTL(
    z            = z,
    delta        = delta,
    time         = time,
    stratum      = stratum,
    beta         = beta,
    vcov         = vcov,
    etas         = etas,
    tol          = tol,
    Mstop        = Mstop,
    backtrack    = backtrack,
    message      = message,
    data_sorted  = FALSE,
    beta_initial = beta_initial
  )

  class(res) <- c("ncc_MDTL", class(res))
  return(res)
}
