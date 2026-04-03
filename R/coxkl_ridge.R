#' Cox Proportional Hazards Model with Ridge Penalty and External Information
#'
#' @description
#' Fits a Cox proportional hazards model using a Ridge (L2) penalty on all covariates,
#' while integrating external information via Kullback–Leibler (KL) divergence.
#'
#' This function is useful for high-dimensional data or situations with collinearity,
#' allowing the incorporation of prior knowledge (external coefficients or risk scores)
#' to improve estimation.
#'
#' @details
#' The objective function optimizes the partial likelihood penalized by two terms:
#' \enumerate{
#'   \item The KL divergence between the current model's predictions and the external information (weighted by \code{eta}).
#'   \item The Ridge (L2) norm of the coefficients (weighted by \code{lambda}).
#' }
#' Unlike Lasso, Ridge regression does not perform variable selection (coefficients are shrunk towards zero but not set to exactly zero),
#' making it suitable for retaining all features while controlling overfitting.
#'
#' @param z Numeric matrix of covariates. Rows represent individuals and columns represent predictors.
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of observed times (event or censoring).
#' @param stratum Optional numeric or factor vector specifying strata. If \code{NULL}, all observations are in the same stratum.
#' @param RS Optional numeric vector or matrix of external risk scores. If not provided, \code{beta} must be supplied.
#' @param beta Optional numeric vector of externally derived coefficients (length equal to \code{ncol(z)}).
#'   If provided, used to calculate risk scores. If not provided, \code{RS} must be supplied.
#' @param eta Non-negative scalar controlling the strength of external information integration.
#'   \code{eta = 0} implies a standard Ridge Cox model.
#' @param lambda Optional numeric scalar or vector of penalty parameters. If \code{NULL}, a sequence is generated automatically.
#' @param nlambda Integer. Number of lambda values to generate if \code{lambda} is \code{NULL}. Default is 100.
#' @param penalty.factor Numeric scalar in \code{[0, 1)}. Controls the internal mixing parameter used to generate
#'   the lambda sequence when \code{lambda = NULL}. A value close to 1 generates a sequence suitable for Ridge-like behavior.
#' @param tol Convergence tolerance for the iterative estimation algorithm. Default is 1e-4.
#' @param Mstop Integer. Maximum number of iterations for estimation. Default is 50.
#' @param backtrack Logical. If \code{TRUE}, uses backtracking line search during optimization.
#' @param message Logical. If \code{TRUE}, progress messages are printed during model fitting.
#' @param data_sorted Logical. Internal optimization. If \code{TRUE}, assumes input data is already sorted by strata and time.
#' @param beta_initial Optional numeric vector. Initial values for the coefficients. Default is 0.
#' @param ... Additional arguments.
#'
#' @return
#' An object of class \code{"coxkl_ridge"} containing:
#' \describe{
#'   \item{\code{lambda}}{The sequence of lambda values used for estimation.}
#'   \item{\code{beta}}{A matrix of estimated coefficients (p x nlambda).}
#'   \item{\code{linear.predictors}}{A matrix of linear predictors (n x nlambda), restored to the original data order.}
#'   \item{\code{likelihood}}{A vector of negative log-partial likelihoods for each lambda.}
#'   \item{\code{data}}{A list containing the input data used (\code{z}, \code{time}, \code{delta}, \code{stratum}).}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' coxkl_ridge_est <- coxkl_ridge(
#'   z = train_dat_highdim$z,
#'   delta = train_dat_highdim$status,
#'   time = train_dat_highdim$time,
#'   stratum = train_dat_highdim$stratum,
#'   beta = beta_external_highdim,
#'   eta = 0
#' )
#' }
#'
#' @export
coxkl_ridge <- function(z, delta, time, stratum = NULL, RS = NULL, beta = NULL, eta = NULL,
                        lambda = NULL, nlambda = 100, penalty.factor = 0.999,
                        tol = 1.0e-4, Mstop = 50, backtrack = FALSE, message = FALSE, data_sorted = FALSE,
                        beta_initial = NULL, ...) {
  
  ## ---- Input Checks ----
  if (is.null(eta)) {
    warning("eta is not provided. Setting eta = 0 (no external information used).", call. = FALSE)
    eta <- 0
  } else {
    if (!is.finite(eta) || eta < 0 || length(eta) != 1) {
      stop("eta must be a non-negative scalar.", call. = FALSE)
    }
  }
  
  if (is.null(RS) && is.null(beta)) {
    stop("Error: No external information is provided. Either RS or beta must be provided.")
  } else if (is.null(RS) && !is.null(beta)) {
    if (length(beta) == ncol(z)) {
      if (message) message("External beta information is used.")
      RS <- as.matrix(z) %*% as.matrix(beta)
    } else {
      stop("Error: The dimension of beta does not match the number of columns in z.")
    }
  } else if (!is.null(RS)) {
    RS <- as.matrix(RS)
    if (message) message("External Risk Score information is used.")
  }
  
  ## ---- Data Preparation & Sorting ----
  input_data <- list(z = z, time = time, delta = delta, stratum = stratum, RS = RS)
  
  if (!data_sorted) {
    if (is.null(stratum)) {
      warning("Stratum information not provided. All data is assumed to originate from a single stratum!", call. = FALSE)
      stratum <- rep(1, nrow(z))
      time_order <- order(time)
    } else {
      stratum <- match(stratum, unique(stratum))
      time_order <- order(stratum, time)
    }
    
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
  
  n.each_stratum <- as.numeric(table(stratum))
  n_vars <- ncol(z_mat)
  n_obs <- nrow(z_mat)
  
  delta_tilde <- calculateDeltaTilde(delta, time, RS, n.each_stratum)
  beta.init <- rep(0, n_vars)
  
  ## ---- Lambda Generation ----
  if (is.null(lambda)) {
    if (nlambda < 2) {
      stop("nlambda must be at least 2", call. = FALSE)
    } else if (nlambda != round(nlambda)) {
      stop("nlambda must be a positive integer", call. = FALSE)
    }
    # Use internal setup to approximate ridge-like lambda sequence
    lambda.fit <- setupLambdaCoxKL(
      z_mat, time, delta, delta_tilde, RS, beta.init, stratum,
      group = 1:n_vars, group.multiplier = rep(1, n_vars),
      n.each_stratum, alpha = 1 - penalty.factor,
      eta, nlambda, lambda.min.ratio = 0
    )
    lambda.seq <- lambda.fit$lambda.seq
  } else {
    nlambda <- length(lambda) # Note: lambda can be a single value
    lambda.seq <- as.vector(sort(lambda, decreasing = TRUE))
  }
  
  ## ---- Initialization ----
  LP_mat <- matrix(NA, nrow = n_obs, ncol = nlambda)
  beta_mat <- matrix(NA, nrow = n_vars, ncol = nlambda)
  likelihood_mat <- rep(NA, nlambda)
  
  lambda_names <- round(lambda.seq, 4)
  colnames(LP_mat) <- lambda_names
  colnames(beta_mat) <- lambda_names
  names(likelihood_mat) <- lambda_names
  
  if (is.null(beta_initial)) {
    beta_initial <- rep(0, n_vars)
  }
  
  if (message) {
    cat("Fitting Ridge path over lambda sequence:\n")
    pb <- txtProgressBar(min = 0, max = nlambda, style = 3, width = 30)
  }
  
  delta_eta <- (eta * delta_tilde + delta) / (1 + eta)

  ## ---- Estimation Loop ----
  for (i in seq_along(lambda.seq)) {
    lambda <- lambda.seq[i]
    # Assumes KL_Cox_Estimate_cpp is available in the package namespace
    beta_est <- KL_Cox_Estimate_cpp(
      N = n_obs, z_mat, delta, delta_eta, n.each_stratum, eta, beta_initial,
      tol, Mstop, lambda = lambda, backtrack = backtrack, message = FALSE
    )
    
    LP_train <- z_mat %*% as.matrix(beta_est)
    beta_mat[, i] <- beta_est
    LP_mat[, i] <- LP_train
    likelihood_mat[i] <- pl_cal_theta(LP_train, delta, n.each_stratum)
    
    beta_initial <- beta_est # "warm start" for next lambda
    if (message) setTxtProgressBar(pb, i)
  }
  if (message) close(pb)
  
  ## ---- Result Formatting ----
  # Restore original order if data was sorted
  if (!data_sorted) {
    LinPred_original <- matrix(NA_real_, nrow = length(time_order), ncol = nlambda)
    LinPred_original[time_order, ] <- LP_mat
  } else {
    LinPred_original <- LP_mat
  }
  
  if (is.null(input_data$stratum)) input_data$stratum <- rep(1, nrow(z_mat))
  
  structure(
    list(
      lambda = lambda.seq,
      beta = beta_mat,
      linear.predictors = LinPred_original,
      likelihood = likelihood_mat,
      data = list(
        z = z,
        time = time,
        delta = delta,
        stratum = input_data$stratum
      )
    ),
    class = "coxkl_ridge"
  )
}


