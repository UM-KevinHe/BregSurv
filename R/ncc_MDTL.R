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
#' where \eqn{Q} is the weighting matrix (a \emph{masked} identity when \code{Q} is
#' \code{NULL}; see the \code{Q} argument).
#'
#' \itemize{
#'   \item Setting \code{etas = 0} recovers the standard CLR (no external information).
#'   \item Larger \code{eta} enforces stronger agreement with \code{beta}.
#'   \item If \code{Q = NULL}, a \emph{masked identity} is used: 1 on the covariates
#'     actually supplied by \code{beta} and 0 on zero-padded positions. This gives
#'     Euclidean/Ridge-type shrinkage towards \code{beta} on the covariates the external
#'     source covers, while leaving padded coefficients unpenalized.
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates.
#' @param stratum Numeric or factor vector defining the matched sets (strata). \strong{Required}.
#' @param beta Numeric vector of external coefficients. \strong{Required}. If \code{beta}
#'   is named, names are matched against \code{colnames(z)}: covariates absent from
#'   \code{beta} are set to 0 (with a message) and the vector is reordered, so an
#'   external source covering only a subset of the internal covariates may be supplied
#'   directly. An unnamed \code{beta} is aligned positionally and must have length
#'   \code{ncol(z)}. A one-column matrix with row names is accepted as a named vector.
#'   See \code{\link{align_beta_Q}}. The bundled external beta
#'   \code{ExampleData_cc_lowdim$beta_external} is named \code{Z1}--\code{Z6}, so the
#'   examples below already exercise the name-matching path.
#' @param Q Optional weighting (precision) matrix for the Mahalanobis penalty, typically
#'   the inverse of the external covariance. Must be symmetric and positive semi-definite
#'   (both checked to a tolerance of 1e-8). If named, it is reordered and zero-padded to
#'   \code{colnames(z)}; only an unnamed \code{Q} must be exactly \code{ncol(z)} by
#'   \code{ncol(z)}. If \code{NULL}, a \emph{masked identity} is used: 1 on covariates
#'   actually supplied by \code{beta} and 0 on zero-padded positions, so padded
#'   coefficients are left unpenalized. See \code{\link{align_beta_Q}}.
#' @param etas Numeric vector of non-negative tuning parameters to evaluate.
#'   \strong{Required}. Must be finite and \eqn{\ge 0}. The values are sorted in ascending
#'   order internally, and the columns of the returned coefficient matrix follow that
#'   sorted order.
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
#' data(ExampleData_cc_lowdim)
#' train_cc <- ExampleData_cc_lowdim$train
#'
#' y       <- train_cc$y
#' z       <- train_cc$z
#' sets    <- train_cc$stratum
#' beta_ext <- ExampleData_cc_lowdim$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
#'
#' fit <- ncc_MDTL(
#'   y      = y,
#'   z      = z,
#'   stratum = sets,
#'   beta   = beta_ext,
#'   Q      = NULL,
#'   etas   = eta_list
#' )
#' }
#' @export
ncc_MDTL <- function(y, z, stratum,
                         beta, Q = NULL, etas,
                         tol = 1.0e-4, Mstop = 50,
                         backtrack = FALSE,
                         message = FALSE,
                         beta_initial = NULL) {

  z <- as.matrix(z)
  y <- as.numeric(y)

  check_etas(etas)

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
    Q            = Q,
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
