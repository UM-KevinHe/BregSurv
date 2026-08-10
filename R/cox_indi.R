#' Cox Proportional Hazards Model Integrated with External Individual-level Information
#'
#' @description
#' Fits a series of composite-likelihood (weighted) stratified Cox models that integrate
#' an external individual-level dataset via an external likelihood weight \code{eta}.
#'
#' @details
#' The fitted objective is
#' \deqn{\ell_\eta(\beta) = \ell_{\text{int}}(\beta) + \eta \, \ell_{\text{ext}}(\beta),}
#' which is equivalent to fitting a stratified Cox model on the stacked data with
#' observation weights 1 (internal) and \code{eta} (external), while keeping internal
#' and external strata separated (no mixing of risk sets across cohorts).
#'
#' The function fits one model per \code{eta} value. It uses a warm-start strategy:
#' the solution at the current \code{eta} is used as the initial value for the next \code{eta}
#' in the sorted sequence.
#'
#' @param z_int Matrix of covariates for the internal dataset (n_int x p).
#' @param delta_int Event indicators for the internal dataset (0/1).
#' @param time_int Survival times for the internal dataset.
#' @param stratum_int Optional stratum identifiers for the internal dataset (default \code{NULL} -> single stratum).
#' @param z_ext Matrix of covariates for the external dataset (n_ext x p).
#' @param delta_ext Event indicators for the external dataset (0/1).
#' @param time_ext Survival times for the external dataset.
#' @param stratum_ext Optional stratum identifiers for the external dataset (default \code{NULL} -> single stratum).
#' @param etas Numeric vector of nonnegative external weights. \code{eta = 0} gives internal-only fit.
#' @param max_iter Maximum Newton-Raphson iterations (default 100).
#' @param tol Convergence tolerance (default 1e-7).
#' @param message Logical; if \code{TRUE}, show a progress bar. Default \code{FALSE}.
#'
#' @return
#' An object of class \code{"cox_indi"} containing:
#' \describe{
#'   \item{\code{eta}}{Sorted sequence of \eqn{\eta} values used.}
#'   \item{\code{beta}}{Matrix of estimated coefficients (\eqn{p \times n_{etas}}). Columns correspond to \code{etas}.}
#'   \item{\code{linear.predictors_int}}{Matrix of internal linear predictors for each \code{eta} (\eqn{n_{int} \times n_{etas}}).}
#'   \item{\code{linear.predictors_ext}}{Matrix of external linear predictors for each \code{eta} (\eqn{n_{ext} \times n_{etas}}).}
#'   \item{\code{data}}{List of inputs used.}
#' }
#' @examples
#' \dontrun{
#' ## Load example individual-level data
#' data(ExampleData_indi)
#'
#' z_int       <- ExampleData_indi$internal$z
#' delta_int   <- ExampleData_indi$internal$status
#' time_int    <- ExampleData_indi$internal$time
#' stratum_int <- ExampleData_indi$internal$stratum
#'
#' z_ext       <- ExampleData_indi$external$z
#' delta_ext   <- ExampleData_indi$external$status
#' time_ext    <- ExampleData_indi$external$time
#' stratum_ext <- ExampleData_indi$external$stratum
#'
#' ## Generate a sequence of eta values
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 100)
#'
#' ## Fit the composite-likelihood Cox model path
#' fit_path <- cox_indi(
#'   z_int = z_int,
#'   delta_int = delta_int,
#'   time_int = time_int,
#'   stratum_int = stratum_int,
#'   z_ext = z_ext,
#'   delta_ext = delta_ext,
#'   time_ext = time_ext,
#'   stratum_ext = stratum_ext,
#'   etas = eta_list
#' )
#'
#' ## Estimated coefficients along the eta path
#' fit_path$beta
#' }
#'
#' @importFrom utils txtProgressBar setTxtProgressBar
#' @export
cox_indi <- function(z_int, delta_int, time_int, stratum_int = NULL,
                     z_ext, delta_ext, time_ext, stratum_ext = NULL,
                     etas, max_iter = 100, tol = 1.0e-7,
                     message = FALSE) {

  z_int <- as.matrix(z_int)
  z_ext <- as.matrix(z_ext)
  delta_int <- as.numeric(delta_int)
  delta_ext <- as.numeric(delta_ext)
  time_int <- as.numeric(time_int)
  time_ext <- as.numeric(time_ext)

  n_int <- nrow(z_int)
  n_ext <- nrow(z_ext)
  p <- ncol(z_int)

  if (ncol(z_ext) != p) stop("Internal and external datasets must have the same number of covariates (columns).", call. = FALSE)

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas <- sort(as.numeric(etas))
  check_etas(etas)

  if (is.null(stratum_int)) stratum_int <- rep(1, n_int)
  if (is.null(stratum_ext)) stratum_ext <- rep(1, n_ext)

  stratum_int <- as.vector(stratum_int)
  stratum_ext <- as.vector(stratum_ext)

  stratum_int_encoded <- as.numeric(match(stratum_int, unique(stratum_int)))
  stratum_ext_encoded <- as.numeric(match(stratum_ext, unique(stratum_ext))) + max(stratum_int_encoded)

  ord_int <- order(stratum_int_encoded, time_int)
  z_int_s <- z_int[ord_int, , drop = FALSE]
  delta_int_s <- delta_int[ord_int]
  time_int_s <- time_int[ord_int]
  stratum_int_s <- stratum_int_encoded[ord_int]

  ord_ext <- order(stratum_ext_encoded, time_ext)
  z_ext_s <- z_ext[ord_ext, , drop = FALSE]
  delta_ext_s <- delta_ext[ord_ext]
  time_ext_s <- time_ext[ord_ext]
  stratum_ext_s <- stratum_ext_encoded[ord_ext]

  z_all <- rbind(z_int_s, z_ext_s)
  delta_all <- c(delta_int_s, delta_ext_s)
  stratum_all <- c(stratum_int_s, stratum_ext_s)

  n_each_stratum <- as.numeric(table(stratum_all))

  n_eta <- length(etas)
  beta_mat <- matrix(NA_real_, nrow = p, ncol = n_eta)
  lp_int_mat_sorted <- matrix(NA_real_, nrow = n_int, ncol = n_eta)
  lp_ext_mat_sorted <- matrix(NA_real_, nrow = n_ext, ncol = n_eta)

  eta_names <- round(etas, 6)
  colnames(beta_mat) <- eta_names
  colnames(lp_int_mat_sorted) <- eta_names
  colnames(lp_ext_mat_sorted) <- eta_names

  beta_init <- rep(0, p)

  if (message) {
    pb <- utils::txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }

  for (i in seq_along(etas)) {
    eta <- etas[i]

    weight_all <- c(rep(1, n_int), rep(eta, n_ext))

    fit <- Cox_indi(
      Z = z_all,
      delta = delta_all,
      weight = weight_all,
      n_each_stratum = n_each_stratum,
      beta = beta_init,
      tol = tol,
      max_iter = max_iter
    )

    beta_hat <- as.numeric(fit$beta)
    beta_mat[, i] <- beta_hat

    lp_int_mat_sorted[, i] <- as.vector(z_int_s %*% beta_hat)
    lp_ext_mat_sorted[, i] <- as.vector(z_ext_s %*% beta_hat)

    beta_init <- beta_hat

    if (message) utils::setTxtProgressBar(pb, i)
  }
  if (message) close(pb)

  lp_int_original <- matrix(NA_real_, nrow = n_int, ncol = n_eta)
  lp_int_original[ord_int, ] <- lp_int_mat_sorted

  lp_ext_original <- matrix(NA_real_, nrow = n_ext, ncol = n_eta)
  lp_ext_original[ord_ext, ] <- lp_ext_mat_sorted

  input_data <- list(
    z_int = z_int, delta_int = delta_int, time_int = time_int, stratum_int = stratum_int,
    z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext, stratum_ext = stratum_ext
  )

  structure(
    list(
      eta = etas,
      beta = beta_mat,
      linear.predictors_int = lp_int_original,
      linear.predictors_ext = lp_ext_original,
      data = input_data
    ),
    class = "cox_indi"
  )
}

