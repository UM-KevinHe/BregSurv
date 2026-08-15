#' Estimate Cox Proportional Hazards Model Coefficients
#'
#' @description
#' Estimates the coefficients of a Cox Proportional Hazards model using the Newton-Raphson method
#' implemented in C++ (Rcpp). It supports stratification, observation weights, and different
#' tie-handling methods (Breslow, Efron, Exact).
#'
#' @param z A matrix or data frame of covariates (n x p).
#' @param delta A binary event indicator vector (length n), where 1 = event and 0 = censored.
#' @param time A numeric vector of observed times (length n).
#' @param stratum A vector indicating strata for a stratified Cox model. If missing,
#'   a \code{warning} ("Stratum information not provided...") is issued and all data
#'   is assumed to belong to a single stratum.
#' @param ties A character string specifying the method for tie handling. Options are
#'   "breslow", "efron", or "exact". The formal default is \code{NULL}, which the
#'   function resolves to "breslow", so omitting \code{ties} gives Breslow handling.
#' @param max_iter Maximum number of Newton-Raphson iterations (default = 100).
#' @param tol Convergence tolerance for the Newton-Raphson update (default = 1e-7).
#' @param comb_max Maximum number of combinations allowed for the "exact" method (default = 1e7).
#'
#' @return A list with exactly two components:
#' \item{beta}{Estimated coefficient vector (length p), named with \code{colnames(z)}.}
#' \item{loglik}{The log-partial likelihood at convergence.}
#'
#' @examples
#' \donttest{
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' train_dat_lowdim$time <- round(train_dat_lowdim$time, 2)  #make ties
#'
#' fit <- cox(z = train_dat_lowdim$z,
#'            delta = train_dat_lowdim$status,
#'            time = train_dat_lowdim$time)
#'
#' # Breslow method for tied data
#' fit_Breslow <- cox(z = train_dat_lowdim$z,
#'                    delta = train_dat_lowdim$status,
#'                    time = train_dat_lowdim$time,
#'                    ties = "breslow")
#' }
#' @keywords internal
#' @export
cox <- function(z, delta, time, stratum,
                ties = NULL,
                max_iter = 100, tol = 1.0e-7, comb_max = 1e7) {
  if (missing(stratum)) {
    warning("Stratum information not provided. All data is assumed to originate from a single stratum!", call. = FALSE)
    stratum <- matrix(1, nrow = nrow(z))
    colnames(stratum) <- "stratum"
    ord <- order(time)
  } else {
    stratum <- as.matrix(match(stratum, unique(stratum)))
    ord <- order(stratum, time)
  }

  stratum <- stratum[ord, , drop = FALSE]
  z <- as.matrix(z[ord, , drop = FALSE])
  delta <- delta[ord]
  time <- time[ord]

  p <- ncol(z)
  beta_init <- rep(0, p)
  n.each_stratum <- as.vector(table(stratum))

  if (is.null(ties)) ties <- "breslow"
  ties_method <- match(match.arg(tolower(ties), c("breslow", "efron", "exact")),
                       c("breslow", "efron", "exact")) - 1

  # Mapping: 0 = breslow, 1 = efron, 2 = exact
  res <- Cox_NR(Z = z,
                delta = delta,
                time = time,
                n_each_stratum = n.each_stratum,
                beta = beta_init,
                ties_method = ties_method,
                tol = tol,
                max_iter = max_iter,
                comb_max = comb_max)

  names(res$beta) <- colnames(z)

  return(res)
}

