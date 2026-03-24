#' Conditional Logistic Regression (CLR) using Cox PH Core
#'
#' @description
#' Estimates the coefficients for a Conditional Logistic Regression model,
#' particularly suitable for 1:M matched case-control studies, by leveraging the
#' core Cox Proportional Hazards estimation function (\code{\link{cox}}).
#'
#' @details
#' This function implements CLR by mapping it to a specialized Cox PH model:
#' the binary outcome \code{y} is treated as the event indicator (\code{delta}),
#' and all event times (\code{time}) are set to 1, ensuring all "events" are tied.
#' The \code{stratum} argument acts as the matched-set indicator.
#'
#' The three tie-handling methods (Breslow, Efron, and Exact) correspond to different
#' approximations of the Conditional Likelihood. **For mathematically exact CLR results,
#' the \code{method = "exact"} should be used.**
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates (rows = observations, columns = variables).
#' @param stratum Numeric or factor vector defining the matched sets. This is **required**
#'    for CLR; if omitted, a warning is issued and all data is treated as one stratum,
#'    which defeats the purpose of matching.
#' @param method Character string specifying the tie-handling method, which determines
#'    the conditional likelihood approximation. Choices are `"breslow"`, `"exact"`, or `"efron"`.
#'    Default is to use the first match, but typically `"exact"` is preferred for CLR.
#' @param max_iter Maximum number of Newton-Raphson iterations passed to \code{cox}. Default \code{100}.
#' @param tol Convergence tolerance for the Newton-Raphson update passed to \code{cox}. Default \code{1e-7}.
#' @param comb_max Maximum number of combinations allowed for the \code{method = "exact"} calculation. Default \code{1e7}.
#'
#' @return A \code{list} containing:
#' \item{\code{beta}}{Estimated coefficient vector (length p).}
#' \item{\code{loglik}}{The log-conditional likelihood (which is the log-partial likelihood from \code{cox}) at convergence.}
#'
#' @seealso \code{\link{cox}} for the underlying Cox PH estimation function.
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
#' # 1. Fit Conditional Logistic Regression using the Exact method
#' fit_exact <- ncc(y = y, z = z, stratum = sets, method = "exact")
#'
#' # 2. Fit CLR using the Breslow approximation
#' fit_breslow <- ncc(y = y, z = z, stratum = sets, method = "breslow")
#' }
#' @keywords internal
#' @export
ncc <- function(y, z, stratum,
                   method = c("breslow","exact","efron"),
                   max_iter = 100, tol = 1e-7, comb_max = 1e7) {

  method <- match.arg(tolower(method), c("breslow","exact","efron"))

  z <- as.matrix(z)
  y <- as.numeric(y)

  if (missing(stratum)) {
    warning("Stratum not provided; all data assumed in one stratum. This may be inappropriate for matched case-control studies.", call. = FALSE)
    stratum <- rep(1, length(y))
  }

  delta <- y
  time <- rep(1, length(y))

  res <- cox(
    z = z,
    delta = delta,
    time = time,
    stratum = stratum,
    ties = method,
    max_iter = max_iter,
    tol = tol,
    comb_max = comb_max
  )

  list(
    beta = res$beta,
    loglik = res$loglik
  )
}
