#' Cox Proportional Hazards Model with KL Divergence for Data Integration (Ties Handling)
#'
#' @description
#' Fits a series of Cox proportional hazards models that integrate external information,
#' specified as external coefficients (\code{beta}), using Kullback–Leibler (KL) divergence.
#' This version of the function is designed to **handle tied event times** using either
#' the Breslow or Exact partial likelihood approximation.
#'
#' The strength of integration is controlled by a sequence of tuning parameters (\code{etas}).
#' The function fits a model for each \code{eta} value provided.
#'
#' @details
#' The objective function is a weighted combination of the internal partial likelihood
#' and the KL divergence from the external information derived from \code{beta}.
#'
#' \itemize{
#'    \item **KL Divergence and Weighting**: Larger values of \code{eta} place more weight
#'    on matching the risk set behavior implied by the external coefficients.
#'    \item **Standard Cox**: \code{eta = 0} corresponds to the standard Cox model, relying
#'    solely on the internal partial likelihood.
#'    \item **Ties Handling**: The calculation of the partial likelihood uses the method
#'    specified by the \code{ties} argument ("breslow" or "exact"). The exact method may be
#'    computationally intensive for datasets with many tied events.
#' }
#'
#' The function uses a "warm start" strategy where the solution for the current \code{eta}
#' is used as the initial value for the next \code{eta} in the sorted sequence.
#'
#' @param z Numeric matrix of covariates. Rows represent observations, columns represent predictor variables.
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of observed event or censoring times.
#' @param stratum Optional numeric or factor vector defining strata.
#' @param beta Numeric vector of external coefficients. Length must equal the number of columns in \code{z}.
#'   These are used to compute the external risk scores and the KL divergence term.
#' @param etas Numeric vector of tuning parameters. Controls the reliance on external information.
#'   The function will sort these values and fit a model for each.
#' @param ties Character string specifying the method for handling ties. Must be one of
#'   \code{"breslow"} (default) or \code{"exact"}.
#' @param tol Numeric. Convergence tolerance for the optimization algorithm (Newton-Raphson). Default is \code{1e-4}.
#' @param Mstop Integer. Maximum number of iterations for the optimization. Default is \code{100}.
#' @param message Logical. If \code{TRUE}, prints progress messages (e.g., progress bar) during fitting. Default is \code{FALSE}.
#' @param data_sorted Logical. Internal use. If \code{TRUE}, assumes data is already sorted by stratum and time.
#' @param beta_initial Optional numeric vector. Initial values for the coefficients for the first \code{eta}. Default is zero vector.
#' @param comb_max Integer. Maximum number of combinations to check for the **Exact** partial likelihood calculation,
#'   preventing excessive computation time. Default is \code{1e7}. Only relevant if \code{ties = "exact"}.
#'
#' @return
#' An object of class \code{"coxkl"} containing:
#' \describe{
#'    \item{\code{eta}}{The sorted sequence of \eqn{\eta} values used.}
#'    \item{\code{beta}}{Matrix of estimated coefficients (\eqn{p \times n_{etas}}). Columns correspond to \code{eta} values.}
#'    \item{\code{linear.predictors}}{Matrix of linear predictors (risk scores) for each \code{eta}.}
#'    \item{\code{likelihood}}{Vector of negative log-partial likelihoods for each \code{eta}.}
#'    \item{\code{data}}{List containing the input data used (\code{z}, \code{time}, \code{delta}, \code{stratum}).}
#' }
#'
#' @examples
#' \dontrun{
#' # Load example data
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' # Rounding the event times introduces ties for demonstration purposes
#' train_dat_lowdim$time <- round(train_dat_lowdim$time, 2)
#' 
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
#' 
#' # 1. Fit the model using Breslow's approximation for ties (Default)
#' coxkl_ties.fit_Breslow <- coxkl_ties(
#'     z = train_dat_lowdim$z,
#'     delta = train_dat_lowdim$status,
#'     time = train_dat_lowdim$time,
#'     stratum = train_dat_lowdim$stratum,
#'     beta = ExampleData_lowdim$beta_external_fair,
#'     etas = eta_list,
#'     ties = "breslow"
#' )
#' 
#' # 2. Fit the model using the Exact method for ties
#' coxkl_ties.fit_Exact <- coxkl_ties(
#'     z = train_dat_lowdim$z,
#'     delta = train_dat_lowdim$status,
#'     time = train_dat_lowdim$time,
#'     stratum = train_dat_lowdim$stratum,
#'     beta = ExampleData_lowdim$beta_external_fair,
#'     etas = eta_list,
#'     ties = "exact"
#' )
#' }
#'
#' @export
coxkl_ties <- function(z, delta, time, stratum = NULL, beta,
                       etas, ties = "breslow",
                       tol = 1.0e-4, Mstop = 100,
                       message = FALSE,
                       data_sorted = FALSE,
                       beta_initial = NULL,
                       comb_max = 1e7) {
  
  if (is.null(beta)) {
    stop("No external information is provided.")
  }
  beta <- align_beta(z, beta)
  
  input_data <- list(z = z, time = time, delta = delta, stratum = stratum)
  
  if (!data_sorted) {
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
  } else {
    z_mat <- as.matrix(z)
    time <- as.numeric(time)
    delta <- as.numeric(delta)
    stratum <- as.numeric(stratum)
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

  
  ties <- match.arg(tolower(ties), c("exact","breslow"))
  n.each_stratum <- as.integer(table(stratum))
  
  if (ties == "exact") {
    WTilde <- calculateWTilde_exact(
      Z = z_mat,
      delta = delta,
      time  = time,
      n_each_stratum = n.each_stratum,
      external_beta = as.numeric(beta),
      comb_max = comb_max
    )
  } else {
    risk_score_ext <- as.matrix(z_mat) %*% beta
    WTilde <- calculateWTilde_breslow(
      Z = z_mat,
      delta = delta,
      time  = time,
      risk_score_ext = risk_score_ext,
      n_each_stratum = n.each_stratum
    )
  }
  
  if (is.null(beta_initial)){
    beta_initial <- rep(0, ncol(z_mat))
  }
  
  if (message) {
    cat("Cross-validation over eta sequence:\n")
    pb <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }
  
  for (i in seq_along(etas)){  #"etas" already in ascending order
    eta <- etas[i]
    
    if (ties == "exact") {
      beta_hat <- CoxKL_NR_exact(
        Z = z_mat,
        delta = delta,
        time  = time,
        n_each_stratum = n.each_stratum,
        tildeW = WTilde,
        eta = eta,
        beta = beta_initial,
        tol = tol,
        max_iter = Mstop,
        comb_max = comb_max
      )
      
      LP <- z_mat %*% as.matrix(beta_hat)
      LP_mat[, i] <- LP
      beta_mat[, i] <- beta_hat
      likelihood_mat[i] <- pl_cal_exact(LP, delta, time, n.each_stratum, comb_max)
    } else { # breslow
      beta_hat <- CoxKL_NR_breslow(
        Z = z_mat,
        delta = delta,
        time  = time,
        n_each_stratum = n.each_stratum,
        Wtilde = WTilde,
        eta = eta,
        beta = beta_initial,
        tol = tol,
        max_iter = Mstop
      )
      
      LP <- z_mat %*% as.matrix(beta_hat)
      LP_mat[, i] <- LP
      beta_mat[, i] <- beta_hat
      likelihood_mat[i] <- pl_cal_breslow(LP, delta, time, n.each_stratum)
    }
    
    beta_initial <- beta_hat  # "warm start"
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



