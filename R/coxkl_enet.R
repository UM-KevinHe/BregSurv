#' Cox Proportional Hazards Model with KL Divergence and Elastic Net Penalty
#'
#' @description
#' Fits a Cox proportional hazards model that integrates external information
#' using Kullback–Leibler (KL) divergence, while applying an Elastic Net
#' (Lasso + Ridge) penalty for variable selection and regularization.
#'
#' External information can be provided as:
#' \itemize{
#'   \item \code{RS}: Precomputed external risk scores.
#'   \item \code{beta}: Externally derived coefficients (which are converted to risk scores internally).
#' }
#' The strength of integration is controlled by the tuning parameter \code{eta}.
#'
#' @details
#' The objective function optimizes the partial likelihood penalized by the KL divergence
#' from the external information and the Elastic Net norm.
#' \itemize{
#'   \item If \code{eta = 0}, the method reduces to a standard Elastic Net Cox model (ignoring external info).
#'   \item If \code{alpha = 1}, the penalty is Lasso.
#'   \item If \code{alpha} is close to 0, the penalty approaches Ridge.
#' }
#'
#' @param z Numeric matrix of covariates (predictors). Rows are observations, columns are variables.
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of follow-up times (observed event or censoring time).
#' @param stratum Optional numeric or factor vector for stratified analysis.
#' @param RS Optional numeric vector of external risk scores. Length must equal \code{nrow(z)}.
#'   If not provided, \code{beta} must be supplied.
#' @param beta Optional numeric vector of external coefficients. If \code{beta} is
#'   named, names are matched against \code{colnames(z)}: covariates absent from
#'   \code{beta} are set to 0 (with a message) and the vector is reordered, so an
#'   external source covering only a subset of the internal covariates may be
#'   supplied directly. An unnamed \code{beta} is aligned positionally and must
#'   have length \code{ncol(z)}. A one-column matrix with row names is accepted
#'   as a named vector. See \code{\link{align_beta}}.
#'   If provided, it is used to calculate risk scores. If not provided, \code{RS} must be supplied.
#' @param eta Single finite non-negative integration weight for the KL divergence
#'   (integration strength). The formal default is \code{NULL}, which resolves to
#'   \code{eta = 0} (no external information used) with the warning
#'   "eta is not provided. Setting eta = 0 (no external information used)."
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 < \alpha \le 1}.
#'   \code{alpha = 1} is the lasso penalty, and \code{alpha} close to 0 approaches ridge.
#'   Defaults to 1.
#' @param lambda Optional numeric vector of penalty parameters. If \code{NULL}, a path is generated automatically.
#' @param nlambda Integer. The number of lambda values to generate. Default is 100.
#' @param lambda.min.ratio Numeric. The ratio of the smallest to the largest lambda in the sequence.
#'   Default depends on sample size relative to features (0.05 if n < p, else 1e-3).
#' @param lambda.early.stop Logical. If \code{TRUE}, stops the lambda path early if the loss improvement is small.
#' @param tol Numeric. Convergence tolerance for the optimization. Default is 1e-4.
#' @param Mstop Integer. Maximum iterations for the inner loop per lambda. Default is 1000.
#' @param max.total.iter Integer. Maximum total iterations across the entire path.
#' @param group Integer vector defining group membership for grouped penalties.
#'   Default treats each variable as its own group.
#' @param group.multiplier Numeric vector. Multiplicative factors for penalties applied to each group.
#' @param standardize Logical. If \code{TRUE}, \code{z} is standardized internally.
#'   Coefficients are returned on the original scale.
#' @param nvar.max Integer. Maximum number of active variables allowed.
#' @param group.max Integer. Maximum number of active groups allowed.
#' @param stop.loss.ratio Numeric. Threshold for early stopping based on loss ratio.
#' @param actSet Logical. If \code{TRUE}, uses an active-set strategy for optimization.
#' @param actIter Integer. Iterations for active set refinement.
#' @param actGroupNum Integer. Limit on active groups in active set strategy.
#' @param actSetRemove Logical. Whether to allow removal from the active set.
#' @param trace.lambda Logical. If \code{TRUE}, prints the lambda sequence progress.
#' @param message Logical. If \code{TRUE}, prints informative messages during fitting.
#' @param data_sorted Logical. Internal use. Indicates if data is already sorted by time/stratum.
#' @param returnX Logical. If \code{TRUE}, returns the standardized design matrix and data in the result.
#' @param ... Additional arguments.
#'
#' @return An object of class \code{"coxkl_enet"}. A list containing:
#' \describe{
#'   \item{\code{beta}}{Matrix of coefficient estimates (p x nlambda).}
#'   \item{\code{group}}{Factor recording the group membership originally supplied in \code{group}.}
#'   \item{\code{lambda}}{The sequence of lambda values used.}
#'   \item{\code{alpha}}{The elastic-net mixing parameter used.}
#'   \item{\code{likelihood}}{Vector of KL-weighted log-partial likelihoods, one per lambda
#'     (larger values indicate better fit; this is \emph{not} a loss). The contribution of each
#'     observation is weighted by \eqn{(\delta + \eta \tilde{\delta}) / (1 + \eta)}, so this is
#'     not the same quantity as the unweighted log-partial likelihood reported by \code{\link{coxkl}}.}
#'   \item{\code{n}}{Number of observations used in the fit.}
#'   \item{\code{df}}{Vector of degrees of freedom (number of non-zero coefficients) for each lambda.}
#'   \item{\code{iter}}{Vector of iteration counts for each lambda.}
#'   \item{\code{W}}{Matrix of exponentiated linear predictors (risk scores) on the original scale.}
#'   \item{\code{group.multiplier}}{Numeric vector of the group-level penalty multipliers actually used.}
#'   \item{\code{data}}{List containing the input data used (\code{z}, \code{time}, \code{delta},
#'     \code{stratum}, \code{RS}), in the original row order supplied by the caller.}
#' }
#' When \code{returnX = TRUE}, the object additionally contains a \code{returnX} component: a list
#' with elements \code{XX} (the standardized design object), \code{time}, \code{delta},
#' \code{stratum} and \code{RS}, all in the internal sorted (\code{stratum}, \code{time}) order
#' rather than the original row order.
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' # Fit the Elastic Net Cox model with KL divergence
#' coxkl_enet_est <- coxkl_enet(
#'   z = train_dat_highdim$z,
#'   delta = train_dat_highdim$status,
#'   time = train_dat_highdim$time,
#'   stratum = train_dat_highdim$stratum,
#'   beta = beta_external_highdim,
#'   eta = 0  # eta=0 implies standard elastic net (ignoring external beta)
#' )
#' }
#'
#' @export
coxkl_enet <- function(z, delta, time, stratum = NULL, RS = NULL, beta = NULL, eta = NULL,
                       alpha = NULL, lambda = NULL, nlambda = 100, lambda.min.ratio = ifelse(n < p, 0.05, 1e-03), 
                       lambda.early.stop = FALSE, tol = 1.0e-4, Mstop = 1000, max.total.iter = (Mstop * nlambda), 
                       group = 1:ncol(z), group.multiplier = NULL, standardize = T, 
                       nvar.max = ncol(z), group.max = length(unique(group)), stop.loss.ratio = 1e-2, 
                       actSet = TRUE, actIter = Mstop, actGroupNum = sum(unique(group) != 0), actSetRemove = F,
                       returnX = FALSE, trace.lambda = FALSE, message = FALSE, data_sorted = FALSE, ...){
  
  if (is.null(alpha)){
    warning("alpha is not provided. Setting alpha = 1 (lasso penalty).", call. = FALSE)
    alpha <- 1
  } else if (alpha > 1 | alpha <= 0) {
    stop("alpha must be in (0, 1]", call.=FALSE)
  }
  
  if (is.null(eta)){
    warning("eta is not provided. Setting eta = 0 (no external information used).", call. = FALSE)
    eta <- 0
  } else {
    check_etas(eta, scalar = TRUE)
  }
  
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
  
  z <- as.matrix(z)
  delta <- as.numeric(delta)
  time <- as.numeric(time)
  
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
    z <- as.matrix(z)[time_order, , drop = FALSE]
    delta <- as.numeric(delta[time_order])
    RS <- as.numeric(RS[time_order, , drop = FALSE])
  } else {
    z <- as.matrix(z)
    time <- as.numeric(time)
    delta <- as.numeric(delta)
    stratum <- as.numeric(stratum)
    RS <- as.numeric(RS)
  }
  
  n.each_stratum <- as.numeric(table(stratum))
  
  initial.group <- group
  if (standardize == T){
    std.Z <- newZG.Std(z, group, group.multiplier)
  } else {
    std.Z <- newZG.Unstd(z, group, group.multiplier)
  }
  Z <- std.Z$std.Z[, , drop = F]
  group <- std.Z$g  
  group.multiplier <- std.Z$m 
  
  p <- ncol(Z)
  n <- length(delta)
  nvar.max <- as.integer(nvar.max)
  group.max <- as.integer(group.max)
  
  beta.init <- rep(0, ncol(Z)) #initial value of beta
  delta_tilde <- calculateDeltaTilde(delta, time, RS, n.each_stratum)
  
  if (is.null(lambda)) {
    if (nlambda < 2) {
      stop("nlambda must be at least 2", call. = FALSE)
    } else if (nlambda != round(nlambda)){
      stop("nlambda must be a positive integer", call. = FALSE)
    }
    lambda.fit <- setupLambdaCoxKL(Z, time, delta, delta_tilde, RS, beta.init, stratum, 
                                   group, group.multiplier, n.each_stratum, alpha,
                                   eta, nlambda, lambda.min.ratio)
    lambda.seq <- lambda.fit$lambda.seq
    beta <- lambda.fit$beta
  } else {
    nlambda <- length(lambda)  # Note: lambda can be a single value
    lambda.seq <- as.vector(sort(lambda, decreasing = TRUE))
    beta <- beta.init
  }
  
  K <- as.integer(table(group)) #number of features in each group
  K0 <- as.integer(if (min(group) == 0) K[1] else 0)
  K1 <- as.integer(if (min(group) == 0) cumsum(K) else c(0, cumsum(K)))
  
  initial.active.group <- -1
  if (actSet == TRUE){
    if (K0 == 0){
      initial.active.group <- which(K == min(K))[1] - 1
    }
  } else {
    actIter <- Mstop
  }
  
  fit <- KL_Cox_highdim(Z, delta, delta_tilde, eta, n.each_stratum, beta, K1, K0, 
                        lambda.seq, alpha, lambda.early.stop, stop.loss.ratio, 
                        group.multiplier, max.total.iter, Mstop, tol, 
                        initial.active.group, nvar.max, group.max, trace.lambda, 
                        actSet, actIter, actGroupNum, actSetRemove)
  # colSums(fit$beta != 0)   #internal check for non-zero coefficients (when at lambda_max, beta should be all zeros)
  
  beta <- fit$beta
  LinPred <- fit$LinPred
  df <- fit$Df
  iter <- fit$iter
  loss <- fit$loss
  
  # Eliminate saturated lambda values
  ind <- !is.na(iter)
  lambda <- lambda.seq[ind]
  beta <- beta[, ind, drop = FALSE]
  loss <- loss[ind]
  LinPred <- LinPred[, ind, drop = FALSE]
  df <- df[ind]
  iter <- iter[ind]
  
  if (iter[1] == max.total.iter){
    stop("Algorithm failed to converge for any values of lambda", call. = FALSE)
  }
  if (sum(iter) == max.total.iter){
    warning("Algorithm failed to converge for all values of lambda", call. = FALSE)
  }
  
  
  # Original scale
  beta <- unorthogonalize(beta, std.Z$std.Z, group)
  rownames(beta) <- colnames(Z)
  if (std.Z$reorder == TRUE){  # original order of beta
    beta <- beta[std.Z$ord.inv, , drop = F]
  }
  if (standardize == T) {
    original.beta <- matrix(0, nrow = length(std.Z$scale), ncol = ncol(beta))
    original.beta[std.Z$nz, ] <- beta / std.Z$scale[std.Z$nz]
    beta <- original.beta
  }
  
  
  # Names
  dimnames(beta) <- list(colnames(Z), round(lambda, digits = 4))
  colnames(LinPred) <- round(lambda, digits = 4)
  
  #recover the original order of linear predictors
  if (data_sorted == FALSE){
    LinPred_original <- matrix(NA_real_, nrow = length(time_order), ncol = ncol(LinPred))
    LinPred_original[time_order, ] <- LinPred
  } else {
    LinPred_original <- LinPred
  }
  
  result <- structure(list(
    beta = beta,
    group = factor(initial.group),
    lambda = lambda,
    alpha = alpha,
    likelihood = loss,
    n = n,
    df = df,
    iter = iter,
    W = exp(LinPred_original),
    group.multiplier = group.multiplier,
    data = input_data
  ), class = "coxkl_enet")
  
  if (returnX == TRUE){
    result$returnX <- list(XX = std.Z,
                           time = time,
                           delta = delta,
                           stratum = stratum,
                           RS = RS)
  }
  return(result)
}