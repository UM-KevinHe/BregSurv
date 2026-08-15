#' Cox Proportional Hazards Model with Mahalanobis Distance Transfer Learning
#'
#' @description
#' Fits a Cox proportional hazards model incorporating external information via a
#' Mahalanobis distance penalty. This approach penalizes the deviation of the
#' estimated coefficients from external reference coefficients (\code{beta}),
#' weighted by a specified matrix (typically the inverse covariance matrix).
#'
#' @details
#' The objective function minimizes the negative log-partial likelihood plus a penalty term:
#' \deqn{P(\beta) = \frac{\eta}{2} (\beta - \beta_{ext})^T Q (\beta - \beta_{ext})}
#' where:
#' \itemize{
#'   \item \eqn{\beta_{ext}} is the vector of external coefficients.
#'   \item \eqn{Q} is the weighting (precision) matrix.
#'   \item \eqn{\eta} is the tuning parameter controlling the strength of the external information.
#' }
#' If \code{Q} is \code{NULL}, it defaults to a masked identity (the identity on the
#' covariates supplied by \code{beta}, and 0 on covariates the external source does not
#' cover), reducing the penalty to a Ridge-type shrinkage towards \code{beta}.
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
#' @param etas A numeric vector of non-negative tuning parameters (scalars) to evaluate.
#' @param tol Convergence tolerance for the Newton-Raphson algorithm. Default is 1e-4.
#' @param Mstop Maximum number of iterations for Newton-Raphson. Default is 50.
#' @param backtrack Logical. If \code{TRUE}, uses backtracking line search. Default is \code{FALSE}.
#' @param message Logical. If \code{TRUE}, progress messages are printed.
#' @param data_sorted Logical. If \code{TRUE}, assumes input data is already sorted by stratum and time.
#' @param beta_initial Optional initial coefficient vector for warm start.
#'
#' @return An object of class \code{"cox_MDTL"} containing:
#' \describe{
#'   \item{\code{eta}}{The vector of eta values evaluated.}
#'   \item{\code{beta}}{A matrix of estimated coefficients (p x n_eta).}
#'   \item{\code{linear.predictors}}{A matrix of linear predictors (n x n_eta).}
#'   \item{\code{likelihood}}{A vector of log-partial likelihoods for each eta.}
#'   \item{\code{data}}{A list containing the input data used.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' beta_external_lowdim <- ExampleData_lowdim$beta_external_fair
#' 
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 5)
#' 
#' cox_MDTL_est <- cox_MDTL(
#'   z = train_dat_lowdim$z,
#'   delta = train_dat_lowdim$status,
#'   time = train_dat_lowdim$time,
#'   beta = beta_external_lowdim,
#'   Q = NULL,
#'   etas = eta_list
#' )
#' }
#'
#' @export
cox_MDTL <- function(z, delta, time, stratum = NULL,
                     beta, Q = NULL, etas,
                     tol = 1.0e-4, Mstop = 50,
                     backtrack = FALSE,
                     message = FALSE,
                     data_sorted = FALSE,
                     beta_initial = NULL) {

  ## ---- Input Checks ----
  if (missing(beta)) stop("External beta must be provided.", call. = FALSE)
  if (missing(etas) || is.null(etas)) stop("etas must be provided.", call. = FALSE)
  check_etas(etas)

  ## Align external beta and Q to the covariates of z: a named beta/Q is matched
  ## to colnames(z) and zero-padded where the external source is silent; Q is
  ## validated (symmetric, positive-semidefinite) and defaults to a masked
  ## identity when NULL so padded coefficients are left unpenalized.
  aligned <- align_beta_Q(z, beta, Q)
  beta <- aligned$beta
  Q <- aligned$Q

  ## ---- Data Preparation ----
  z <- as.matrix(z)
  delta <- as.numeric(delta)
  time <- as.numeric(time)
  etas <- sort(etas)
  
  input_data <- list(z = z, time = time, delta = delta, stratum = stratum)
  
  if (!data_sorted) {
    if (is.null(stratum)) {
      if (message) warning("Stratum information not provided. All data is assumed to originate from a single stratum!", call. = FALSE)
      stratum <- rep(1, nrow(z))
      time_order <- order(time)
    } else {
      stratum <- match(stratum, unique(stratum))
      time_order <- order(stratum, time)
    }
    
    z_mat <- z[time_order, , drop = FALSE]
    time <- time[time_order]
    delta <- delta[time_order]
    stratum <- stratum[time_order]
  } else {
    if (is.null(stratum)) stratum <- rep(1, nrow(z))
    z_mat <- z
  }
  
  n.each_stratum <- table(stratum)
  N <- nrow(z_mat)
  n_eta <- length(etas)
  
  ## ---- Initialization ----
  LP_mat <- matrix(NA, nrow = N, ncol = n_eta)
  beta_mat <- matrix(NA, nrow = ncol(z_mat), ncol = n_eta)
  likelihood_mat <- rep(NA, n_eta)
  
  eta_names <- round(etas, 4)
  colnames(LP_mat) <- eta_names
  colnames(beta_mat) <- eta_names
  names(likelihood_mat) <- eta_names
  
  if (is.null(beta_initial)) {
    beta_initial <- rep(0, ncol(z_mat))
  }
  
  if (message) {
    cat("Fitting Cox MDTL over eta sequence:\n")
    pb <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }
  
  ## ---- Main Loop ----
  for (i in seq_along(etas)) {
    eta <- etas[i]
    
    beta_train <- Cox_MDTL_cpp(
      N = N, Z = z_mat, delta = delta, n_each_stratum = n.each_stratum,
      eta = eta, external_beta = beta, Q = Q, beta_initial = beta_initial,
      lambda = 0, tol = tol, max_iter = Mstop, backtrack = backtrack, message = FALSE
    )
    
    LP_train <- z_mat %*% as.matrix(beta_train)
    LP_mat[, i] <- LP_train
    beta_mat[, i] <- beta_train
    likelihood_mat[i] <- pl_cal_theta(LP_train, delta, n.each_stratum)
    
    beta_initial <- beta_train  # "warm start"
    if (message) setTxtProgressBar(pb, i)
  }
  
  if (message) close(pb)
  
  ## ---- Formatting Output ----
  if (!data_sorted) {
    LinPred_original <- matrix(NA_real_, nrow = length(time_order), ncol = n_eta)
    LinPred_original[time_order, ] <- LP_mat
  } else {
    LinPred_original <- LP_mat
  }
  
  structure(
    list(
      eta = etas,
      beta = beta_mat,
      linear.predictors = LinPred_original,
      likelihood = likelihood_mat,
      data = list(
        z = z, # Return original z
        time = time, # Return sorted time if sorted, or original logic depends on usage
        delta = delta,
        stratum = input_data$stratum
      )
    ),
    class = "cox_MDTL"
  )
}





















