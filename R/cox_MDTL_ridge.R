#' Cox MDTL with Ridge Regularization
#'
#' @description
#' Fits a Cox Proportional Hazards model that simultaneously incorporates:
#' 1.  **Transfer Learning**: A Mahalanobis distance penalty that shrinks coefficients towards
#'     external reference coefficients (\code{beta}), controlled by the parameter \code{eta}.
#' 2.  **Ridge Regularization**: An L2-norm penalty on the coefficients to handle high-dimensional
#'     data or multicollinearity, controlled by the sequence of \code{lambda} values.
#'
#' The function computes the solution path over a sequence of \code{lambda} values for a fixed \code{eta}.
#'
#' @param z A numeric matrix or data frame of covariates (n x p).
#' @param delta A numeric vector of event indicators (1 = event, 0 = censored).
#' @param time A numeric vector of observed times.
#' @param stratum Optional numeric or factor vector indicating strata. If \code{NULL},
#'   all subjects are assumed to be in the same stratum.
#' @param beta A numeric vector of external coefficients. If named, the names are
#'   matched against \code{colnames(z)} and covariates absent from \code{beta} are
#'   zero-padded; if unnamed, \code{beta} must have length \code{ncol(z)}.
#' @param Q Optional numeric matrix acting as the weighting matrix \eqn{Q} in the
#'   Mahalanobis penalty. This should be a symmetric positive-semidefinite
#'   \emph{precision} matrix (e.g. the inverse covariance / information matrix of
#'   the external estimator). If named, it is reordered and zero-padded to
#'   \code{colnames(z)}. If \code{NULL}, a masked identity is used.
#' @param eta A single non-negative numeric value controlling the weight of the
#'   external information (Mahalanobis distance penalty). If \code{NULL}, defaults to 0 (no transfer learning).
#' @param lambda Optional numeric vector of regularization parameters. If \code{NULL},
#'   a sequence is generated automatically.
#' @param nlambda Integer. The number of lambda values to generate if \code{lambda} is \code{NULL}.
#'   Default is 100.
#' @param penalty.factor Numeric value used to determine the elastic net mixing parameter \code{alpha}.
#'   The function sets \code{alpha = 1 - penalty.factor}.
#'   A value close to 1 (default 0.999) results in \code{alpha} close to 0, enforcing a Ridge-like penalty.
#' @param tol Convergence tolerance for the optimization algorithm. Default is 1e-4.
#' @param Mstop Maximum number of iterations. Default is 50.
#' @param backtrack Logical. If \code{TRUE}, uses backtracking line search. Default is \code{FALSE}.
#' @param message Logical. If \code{TRUE}, progress messages are printed.
#' @param data_sorted Logical. If \code{TRUE}, assumes input data is already sorted by stratum and time.
#' @param beta_initial Optional initial coefficient vector for warm start.
#' @param ... Additional arguments passed to internal functions.
#'
#' @return An object of class \code{"cox_MDTL_ridge"} containing:
#' \describe{
#'   \item{\code{lambda}}{The sequence of lambda values used.}
#'   \item{\code{beta}}{A matrix of estimated coefficients (p x nlambda).}
#'   \item{\code{linear.predictors}}{A matrix of linear predictors (n x nlambda).}
#'   \item{\code{likelihood}}{A vector of log-partial likelihoods for each lambda.}
#'   \item{\code{data}}{A list containing the input data (z, time, delta, stratum).}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' cox_MDTL_ridge_est <- cox_MDTL_ridge(
#'   z = train_dat_highdim$z,
#'   delta = train_dat_highdim$status,
#'   time = train_dat_highdim$time,
#'   stratum = train_dat_highdim$stratum,
#'   beta = beta_external_highdim,
#'   Q = NULL,
#'   eta = 0.5
#' )
#' }
#'
#' @export
cox_MDTL_ridge <- function(z, delta, time, stratum = NULL, beta = NULL, Q = NULL, eta = NULL,
                           lambda = NULL, nlambda = 100, penalty.factor = 0.999,
                           tol = 1.0e-4, Mstop = 50, backtrack = FALSE, message = FALSE, data_sorted = FALSE,
                           beta_initial = NULL, ...) {
  if (is.null(eta)) {
    warning("eta is not provided. Setting eta = 0 (no external information used).", call. = FALSE)
    eta <- 0
  } else {
    check_etas(eta, scalar = TRUE)
  }

  if (is.null(beta)) stop("External beta must be provided.", call. = FALSE)

  ## Align external beta and Q to the covariates of z (named -> matched to
  ## colnames(z) and zero-padded; Q validated symmetric/PSD; NULL Q -> masked
  ## identity). For a full-length, in-order beta and full Q this is a no-op.
  aligned <- align_beta_Q(z, beta, Q)
  beta <- aligned$beta
  Q <- aligned$Q

  z <- as.matrix(z)
  delta <- as.numeric(delta)
  time <- as.numeric(time)
  
  input_data <- list(z = z, time = time, delta = delta, stratum = stratum)
  
  if (!data_sorted) {
    if (is.null(stratum)) {
      warning("Stratum information not provided. All data is assumed to originate from a single stratum!", call. = FALSE)
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
    stratum <- as.numeric(stratum)
    z_mat <- z
  }
  
  n.each_stratum <- as.numeric(table(stratum))
  beta.init <- rep(0, ncol(z_mat)) # initial value of beta
  
  n_vars <- ncol(z_mat)
  n_obs <- nrow(z_mat)
  
  Qbeta_ext <- as.vector(Q %*% beta)  # a length p vector (fixed term)
  beta_ext <- beta
  
  if (is.null(lambda)) {
    if (nlambda < 2) {
      stop("nlambda must be at least 2", call. = FALSE)
    } else if (nlambda != round(nlambda)) {
      stop("nlambda must be a positive integer", call. = FALSE)
    }
    lambda.fit <- setupLambda_MDTL(z_mat, time, delta, beta.init, stratum,
                                   beta_ext, Q, Qbeta_ext,
                                   group = 1:ncol(z_mat), group.multiplier = rep(1, ncol(z_mat)),
                                   n.each_stratum, alpha = 1 - penalty.factor,
                                   eta, nlambda, lambda.min.ratio = 0)
    
    lambda.seq <- lambda.fit$lambda.seq
  } else {
    nlambda <- length(lambda)
    lambda.seq <- as.vector(sort(lambda, decreasing = TRUE))
  }
  
  LP_mat <- matrix(NA, nrow = nrow(z_mat), ncol = nlambda)
  beta_mat <- matrix(NA, nrow = ncol(z_mat), ncol = nlambda)
  likelihood_mat <- rep(NA, nlambda)
  
  lambda_names <- round(lambda.seq, 4)
  colnames(LP_mat) <- lambda_names
  colnames(beta_mat) <- lambda_names
  names(likelihood_mat) <- lambda_names
  
  
  
  if (is.null(beta_initial)) {
    beta_initial <- rep(0, ncol(z_mat))
  }
  
  if (message) {
    cat("Cross-validation over lambda sequence:\n")
    pb <- txtProgressBar(min = 0, max = nlambda, style = 3, width = 30)
  }
  
  for (i in seq_along(lambda.seq)) {
    lambda <- lambda.seq[i]
    beta_est <- Cox_MDTL_cpp(N = n_obs, Z = z_mat, delta = delta, n_each_stratum = n.each_stratum, eta = eta,
                             external_beta = beta_ext, Q = Q, beta_initial = beta_initial,
                             lambda = lambda, tol = tol, max_iter = Mstop, backtrack = backtrack, message = message)
    LP_train <- z_mat %*% as.matrix(beta_est)
    beta_mat[, i] <- beta_est
    LP_mat[, i] <- LP_train
    likelihood_mat[i] <- pl_cal_theta(LP_train, delta, n.each_stratum)
    
    beta_initial <- beta_est  # "warm start"
    if (message) setTxtProgressBar(pb, i)
  }
  if (message) close(pb)
  
  
  if (data_sorted == FALSE) {
    LinPred_original <- matrix(NA_real_, nrow = length(time_order), ncol = nlambda)
    LinPred_original[time_order, ] <- LP_mat
  } else {
    LinPred_original <- LP_mat
  }
  
  if (is.null(input_data$stratum)) input_data$stratum <- rep(1, nrow(z_mat))
  
  structure(list(
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
  ), class = "cox_MDTL_ridge")
}
