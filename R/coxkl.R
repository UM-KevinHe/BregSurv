#' Cox Proportional Hazards Model with KL Divergence for Data Integration
#'
#' @description
#' Fits a series of Cox proportional hazards models that incorporate external information
#' using Kullback–Leibler (KL) divergence.
#'
#' External information can be supplied either as:
#' \itemize{
#'   \item Precomputed external risk scores (\code{RS}).
#'   \item Externally derived coefficients (\code{beta}).
#' }
#' The strength of integration is controlled by a sequence of tuning parameters (\code{etas}).
#' The function fits a model for each \code{eta} value provided.
#'
#' @details
#' The objective function is a weighted combination of the internal partial likelihood
#' and the KL divergence from the external information.
#' \itemize{
#'   \item Larger values of \code{eta} place more weight on the external information.
#'   \item \code{eta = 0} corresponds to the standard Cox model relying solely on internal data.
#' }
#' The function uses a "warm start" strategy where the solution for the current \code{eta}
#' is used as the initial value for the next \code{eta} in the sorted sequence.
#'
#' @param z Numeric matrix of covariates. Rows represent observations, columns represent predictor variables.
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of observed event or censoring times.
#' @param stratum Optional numeric or factor vector defining strata.
#' @param RS Optional numeric vector or matrix of external risk scores. Length must equal the number of observations.
#'   If not supplied, \code{beta} must be provided.
#' @param beta Optional numeric vector of external coefficients. Length must equal the number of columns in \code{z}.
#'   If provided, these are used to calculate risk scores internally. If not supplied, \code{RS} must be provided.
#' @param etas Numeric vector of tuning parameters. Controls the reliance on external information.
#'   The function will sort these values and fit a model for each.
#' @param tol Numeric. Convergence tolerance for the optimization algorithm. Default is \code{1e-4}.
#' @param Mstop Integer. Maximum number of iterations for the optimization. Default is \code{100}.
#' @param backtrack Logical. If \code{TRUE}, applies backtracking line search during optimization. Default is \code{FALSE}.
#' @param message Logical. If \code{TRUE}, prints progress messages (e.g., progress bar) during fitting. Default is \code{FALSE}.
#' @param data_sorted Logical. Internal use. If \code{TRUE}, assumes data is already sorted by stratum and time.
#' @param beta_initial Optional numeric vector. Initial values for the coefficients for the first \code{eta}.
#'
#' @return
#' An object of class \code{"coxkl"} containing:
#' \describe{
#'   \item{\code{eta}}{The sorted sequence of \eqn{\eta} values used.}
#'   \item{\code{beta}}{Matrix of estimated coefficients (\eqn{p \times n_{etas}}). Columns correspond to \code{eta} values.}
#'   \item{\code{linear.predictors}}{Matrix of linear predictors (risk scores) for each \code{eta}.}
#'   \item{\code{likelihood}}{Vector of negative log-partial likelihoods for each \code{eta}.}
#'   \item{\code{data}}{List containing the input data used (\code{z}, \code{time}, \code{delta}, \code{stratum}, \code{RS}).}
#' }
#'
#' @examples
#' \dontrun{
#' # Load example data
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' beta_external_lowdim <- ExampleData_lowdim$beta_external_fair
#'
#' # Generate a sequence of eta values
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#'
#' # Fit the model
#' coxkl_est <- coxkl(
#'   z = train_dat_lowdim$z,
#'   delta = train_dat_lowdim$status,
#'   time = train_dat_lowdim$time,
#'   stratum = train_dat_lowdim$stratum,
#'   beta = beta_external_lowdim,
#'   etas = eta_list
#' )
#' }
#' @importFrom utils txtProgressBar setTxtProgressBar
#' @importFrom Rcpp evalCpp
#'
#' @export
coxkl <- function(z, delta, time, stratum = NULL,
                  RS = NULL, beta = NULL,
                  etas, tol = 1.0e-4, Mstop = 100,
                  backtrack = FALSE,
                  message = FALSE,
                  data_sorted = FALSE,
                  beta_initial = NULL){

  if (is.null(RS) && is.null(beta)) {
    stop("No external information is provided. Either RS or beta must be provided.")
  } else if (is.null(RS) && !is.null(beta)) {
    beta <- align_beta(z, beta)
    if (message) message("External beta information is used.")
    RS <- as.matrix(z) %*% as.matrix(beta)
  } else if (!is.null(RS)) {
    RS <- as.matrix(RS)
    if (message) message("External Risk Score information is used.")
  }

  input_data <- list(z = z, time = time, delta = delta, stratum = stratum, RS = RS)

  if (!data_sorted) {
    ## ---- Sorting Section ----
    if (is.null(stratum)) {
      if (message) warning("Stratum information not provided. All data is assumed to originate from a single stratum!", call. = FALSE)
      stratum <- rep(1, nrow(z))
    } else {
      stratum <- match(stratum, unique(stratum))
    }
    time_order <- order(stratum, time)
    time <- as.numeric(time[time_order])
    stratum <- as.numeric(stratum[time_order])
    z_mat <- as.matrix(z)[time_order, , drop = FALSE]
    delta <- as.numeric(delta[time_order])
    RS <- as.numeric(RS[time_order, , drop = FALSE])
  } else {
    z_mat <- as.matrix(z)
    time <- as.numeric(time)
    delta <- as.numeric(delta)
    stratum <- as.numeric(stratum)
    RS <- as.numeric(RS)
  }

  check_etas(etas)
  etas <- sort(etas)
  n_eta <- length(etas)
  LP_mat <- matrix(NA, nrow = nrow(z_mat), ncol = n_eta)
  beta_mat <- matrix(NA, nrow = ncol(z_mat), ncol = n_eta)
  likelihood_mat <- rep(NA, n_eta)

  eta_names <- round(etas, 4)
  colnames(LP_mat) <- eta_names
  colnames(beta_mat) <- eta_names
  names(likelihood_mat) <- eta_names

  n.each_stratum <- as.numeric(table(stratum))
  delta_tilde <- calculateDeltaTilde(delta, time, RS, n.each_stratum)

  N <- nrow(z_mat)

  if (is.null(beta_initial)){
    beta_initial <- rep(0, ncol(z_mat))
  }

  if (message) {
    cat("Cross-validation over eta sequence:\n")
    pb <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }

  for (i in seq_along(etas)){  #"etas" already in ascending order
    eta <- etas[i]
    delta_eta <- (eta * delta_tilde + delta)/(1 + eta)

    beta_est <- KL_Cox_Estimate_cpp(N = N, z_mat, delta, delta_eta, n.each_stratum, eta, beta_initial,
                                    tol, Mstop, lambda = 0, backtrack = backtrack, message = message)
    LP <- z_mat %*% as.matrix(beta_est)
    LP_mat[, i] <- LP
    beta_mat[, i] <- beta_est
    likelihood_mat[i] <- pl_cal_theta(LP, delta, n.each_stratum)

    beta_initial <- beta_est  # "warm start"
    if (message) setTxtProgressBar(pb, i)
  }
  if (message) close(pb)

  if (data_sorted == FALSE){
    LinPred_original <- matrix(NA_real_, nrow = length(time_order), ncol = n_eta)
    LinPred_original[time_order, ] <- LP_mat
  } else {
    LinPred_original <- LP_mat
  }

  if (is.null(input_data$stratum)) input_data$stratum <- rep(1, nrow(z))

  structure(list(
    eta = etas,
    beta = beta_mat,
    linear.predictors = LinPred_original,
    likelihood = likelihood_mat,
    data = input_data
  ), class = "coxkl")
}

