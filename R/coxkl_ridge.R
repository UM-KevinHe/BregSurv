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
#' @param RS Optional numeric vector of external risk scores, one per observation
#'   (a one-column matrix is also accepted). Only a single risk score per observation
#'   is supported. If not provided, \code{beta} must be supplied.
#' @param beta Optional numeric vector of external coefficients. If \code{beta} is
#'   named, names are matched against \code{colnames(z)}: covariates absent from
#'   \code{beta} are set to 0 (with a message) and the vector is reordered, so an
#'   external source covering only a subset of the internal covariates may be
#'   supplied directly. An unnamed \code{beta} is aligned positionally and must
#'   have length \code{ncol(z)}. A one-column matrix with row names is accepted
#'   as a named vector. See \code{\link{align_beta}}.
#'   If provided, used to calculate risk scores. If not provided, \code{RS} must be supplied.
#' @param eta Single finite non-negative integration weight controlling the strength of
#'   external information integration. \code{eta = 0} implies a standard Ridge Cox model.
#'   The formal default is \code{NULL}, which resolves to \code{eta = 0} with the warning
#'   "eta is not provided. Setting eta = 0 (no external information used)."
#' @param lambda Optional numeric scalar or vector of penalty parameters. If \code{NULL}, a sequence is generated automatically.
#' @param nlambda Integer. Number of lambda values to generate if \code{lambda} is \code{NULL}. Default is 100.
#' @param penalty.factor Numeric scalar in \code{[0, 1)}. Controls the internal mixing parameter used to generate
#'   the lambda sequence when \code{lambda = NULL}. A value close to 1 generates a sequence suitable for Ridge-like behavior.
#'   Default is \code{0.999}.
#' @param tol Convergence tolerance for the iterative estimation algorithm. Default is 1e-4.
#' @param Mstop Integer. Maximum number of iterations for estimation. Default is 50.
#' @param backtrack Logical. If \code{TRUE}, uses backtracking line search during optimization.
#' @param message Logical. If \code{TRUE}, progress messages are printed during model fitting.
#' @param data_sorted Logical. Internal optimization. If \code{TRUE}, assumes input data is already sorted by strata and time.
#' @param standardize Logical. If \code{TRUE} (the default since 1.2.0), \code{z} is
#'   scaled to unit standard deviation before the ridge penalty is applied and the
#'   coefficients are returned on the original scale. The ridge penalty is not scale
#'   free, so on covariates of very different magnitudes \code{standardize = FALSE}
#'   penalises large-scale variables almost not at all. Set \code{FALSE} to reproduce
#'   results from version 1.1.0 and earlier.
#' @param beta_initial Optional numeric vector. Initial values for the coefficients. Default is 0.
#'
#' @param ties Tie handling in the partial likelihood. \code{"none"} (the default, and the behaviour of every release before 1.3.0) takes subjects who share an event time in the order the sorted data list them, so each is dropped from the risk sets of the tied rows after it; \code{"breslow"} uses Breslow's approximation, in which the risk set at an event time is everyone whose time is that time or later. The two coincide when no event time is tied.
#' @return
#' An object of class \code{"coxkl_ridge"} containing:
#' \describe{
#'   \item{\code{lambda}}{The sequence of lambda values used for estimation.}
#'   \item{\code{beta}}{A matrix of estimated coefficients (p x nlambda).}
#'   \item{\code{linear.predictors}}{A matrix of linear predictors (n x nlambda), restored to the original data order.}
#'   \item{\code{likelihood}}{Vector of log-partial likelihoods, one per lambda (larger values indicate better fit; this is \emph{not} a loss).}
#'   \item{\code{data}}{A list containing the input data used (\code{z}, \code{time}, \code{delta}, \code{stratum}),
#'     as supplied by the caller (i.e. in the original row order, before the internal sorting by stratum and time).}
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
                        standardize = TRUE, beta_initial = NULL, ties = c("none", "breslow")) {
  ties <- .check_ties(match.arg(ties))
  
  ## ---- Input Checks ----
  if (is.null(eta)) {
    warning("eta is not provided. Setting eta = 0 (no external information used).", call. = FALSE)
    eta <- 0
  } else {
    check_etas(eta, scalar = TRUE)
  }
  
  if (is.null(RS) && is.null(beta)) {
    stop("Error: No external information is provided. Either RS or beta must be provided.")
  } else if (is.null(RS) && !is.null(beta)) {
    beta <- align_beta(z, beta)
    if (message) message("External beta information is used.")
    RS <- as.matrix(z) %*% as.matrix(beta)
  } else if (!is.null(RS)) {
    RS <- as.matrix(RS)
    if (message) message("External Risk Score information is used.")
  }
  
  ## ---- Data Preparation & Sorting ----
  input_data <- list(z = z, time = time, delta = delta, stratum = stratum)
  
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
    delta <- .check_event(delta[time_order], "delta")
    RS <- as.numeric(RS[time_order, , drop = FALSE])
  } else {
    z_mat <- as.matrix(z)
    time <- as.numeric(time)
    delta <- .check_event(delta, "delta")
    stratum <- as.numeric(stratum)
    RS <- as.numeric(RS)
  }
  
  n.each_stratum <- as.numeric(table(stratum))
  tm <- .tie_maps(time, n.each_stratum, ties)
  n_vars <- ncol(z_mat)
  n_obs <- nrow(z_mat)

  ## ---- Standardization of the design matrix ----------------------
  ## The ridge penalty lambda * ||beta||^2 is NOT scale free: with covariates on
  ## different scales a single lambda penalises a variable measured in thousands
  ## essentially not at all and a 0/1 indicator enormously.  Measured on a real
  ## EHR cohort (48 hinge-spline and indicator terms) the unstandardized penalty
  ## cost 0.02-0.09 of test C-index against the standardized one.  The elastic-net
  ## family has standardized by default since it was written; this brings the ridge
  ## family into line.  Scaling only, no centering: centering a Cox design shifts
  ## every linear predictor by the same constant and cannot change the fit, and
  ## leaving it out keeps `linear.predictors` exactly equal to z %*% beta.
  ## The external risk score RS is a fixed vector, so the KL part is untouched.
  std_scale <- rep(1, n_vars)
  if (isTRUE(standardize)) {
    mysd <- function(v) sqrt(sum((v - mean(v))^2) / length(v))
    std_scale <- apply(z_mat, 2, mysd)
    std_scale[!is.finite(std_scale) | std_scale <= 1e-6] <- 1 # constant columns: leave as they are
    z_fit <- sweep(z_mat, 2, std_scale, "/")
  } else {
    z_fit <- z_mat
  }
  
  delta_tilde <- calculateDeltaTilde(delta, time, RS, n.each_stratum, tie_first = tm$first)
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
      z_fit, time, delta, delta_tilde, RS, beta.init, stratum,
      group = 1:n_vars, group.multiplier = rep(1, n_vars),
      n.each_stratum, alpha = 1 - penalty.factor,
      eta, nlambda, lambda.min.ratio = 0, tm = tm
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
  } else {
    ## beta_initial is supplied on the ORIGINAL scale; the fit runs on the scaled one
    beta_initial <- as.numeric(beta_initial) * std_scale
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
      N = n_obs, z_fit, delta, delta_eta, n.each_stratum, eta, beta_initial,
      tol, Mstop, lambda = lambda, backtrack = backtrack, message = FALSE,
      tie_first = tm$first
    )
    
    LP_train <- z_fit %*% as.matrix(beta_est)
    beta_mat[, i] <- beta_est
    LP_mat[, i] <- LP_train
    likelihood_mat[i] <- .pl_ties(LP_train, delta, time, n.each_stratum, ties)
    
    beta_initial <- beta_est # "warm start" for next lambda
    if (message) setTxtProgressBar(pb, i)
  }
  if (message) close(pb)
  
  ## ---- Result Formatting ----
  ## back to the original scale, so that linear.predictors == z %*% beta exactly
  if (isTRUE(standardize)) beta_mat <- beta_mat / std_scale
  rownames(beta_mat) <- colnames(z_mat)
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
      ties = ties,
      data = input_data
    ),
    class = "coxkl_ridge"
  )
}


