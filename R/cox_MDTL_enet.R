#' Fit Cox Model with Mahalanobis Distance Transfer Learning and Elastic Net Penalty
#'
#' @description
#' Fits a Cox Proportional Hazards model that integrates external information (Transfer Learning)
#' using an Elastic Net regularization path. The method incorporates prior knowledge from
#' external coefficients (\code{beta}) and an optional weight matrix (\code{Q}), controlled
#' by the transfer learning parameter \code{eta}.
#'
#' The objective function minimizes the negative partial likelihood plus a transfer learning
#' penalty term \eqn{\frac{\eta}{2} (\beta - \beta_{ext})^T Q (\beta - \beta_{ext})} and the
#' Elastic Net penalty.
#'
#' @param z Matrix of predictors (n x p).
#' @param delta Vector of event indicators (1 for event, 0 for censored).
#' @param time Vector of observed survival times.
#' @param stratum Vector indicating the stratum membership. If NULL, all observations are assumed to be in the same stratum.
#' @param beta Vector of external coefficients representing the prior knowledge or "source" model coefficients. If named, the names are matched against \code{colnames(z)} and covariates absent from \code{beta} are zero-padded; if unnamed, \code{beta} must have length \code{ncol(z)}.
#' @param Q Optional weighting (precision) matrix for the Mahalanobis penalty.
#'   Must be symmetric and positive semi-definite (both checked to a tolerance of
#'   1e-8). If named, it is reordered and zero-padded to \code{colnames(z)}; only
#'   an unnamed \code{Q} must be exactly \code{ncol(z)} by \code{ncol(z)}. If
#'   \code{NULL}, a \emph{masked identity} is used: 1 on covariates actually
#'   supplied by \code{beta} and 0 on zero-padded positions, so padded
#'   coefficients are left unpenalized. See \code{\link{align_beta_Q}}.
#' @param eta Scalar. The transfer learning parameter (>= 0). Controls the strength of the external information. \code{eta = 0} ignores external info. The formal default is \code{NULL}, which resolves to \code{eta = 0} with the warning "eta is not provided. Setting eta = 0 (no external information used)."
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 < \alpha \le 1}. \code{alpha=1} is the lasso penalty, and values close to 0 approach ridge. The formal default is \code{NULL}, which resolves to \code{alpha = 1} with the warning "alpha is not provided. Setting alpha = 1 (lasso penalty)."
#' @param lambda Optional user-supplied lambda sequence. If NULL, the algorithm generates its own sequence.
#' @param nlambda The number of lambda values. Default is 100.
#' @param lambda.min.ratio Smallest value for lambda, as a fraction of lambda.max. Default is \code{ifelse(n < p, 0.05, 1e-03)}.
#' @param lambda.early.stop Logical. Whether to stop early if the deviance changes minimally.
#' @param tol Convergence threshold for coordinate descent.
#' @param Mstop Maximum number of iterations per lambda step. Default is 1000.
#' @param max.total.iter Maximum total iterations across all lambda values. Default is \code{Mstop * nlambda}.
#' @param group Vector describing the grouping of the coefficients. Default is \code{1:ncol(z)} (no grouping).
#' @param group.multiplier Vector of multipliers for each group size. Default is \code{NULL}.
#' @param standardize Logical. Should the predictors be standardized before fitting?
#'   Default is TRUE. A \code{Q} you supply carries its own units and the Mahalanobis part
#'   of the penalty is left exactly unchanged; with \code{Q = NULL} the implicit identity
#'   metric is taken on the standardized scale, one standard deviation per covariate, so
#'   that the member does not depend on the units the covariates happen to be recorded in
#'   and agrees with \code{\link{cox_MDTL_ridge}}. Changed in 1.2.0; before that both
#'   cases used a metric of \eqn{\mathrm{diag}(\mathrm{sd}^4)} on the original coefficients.
#' @param nvar.max Maximum number of variables allowed in the model. Default is \code{ncol(z)}.
#' @param group.max Maximum number of groups allowed in the model. Default is \code{length(unique(group))}.
#' @param stop.loss.ratio Ratio of loss change to stop the path early. Default is 1e-2.
#' @param actSet Logical. Whether to use active set convergence strategy.
#' @param actIter Number of iterations for active set. Default is \code{Mstop}.
#' @param actGroupNum Number of active groups. Default is \code{sum(unique(group) != 0)}.
#' @param actSetRemove Logical. Whether to remove inactive groups from the active set. Default is \code{FALSE}.
#' @param returnX Logical. If TRUE, returns the standardized design matrix and other data details. Default is \code{FALSE}.
#' @param trace.lambda Logical. If TRUE, prints the current lambda during fitting. Default is \code{FALSE}.
#' @param message Logical. If TRUE, prints warnings and progress messages.
#' @param data_sorted Logical. Internal flag indicating if data is already sorted by time/stratum. Default is \code{FALSE}.
#'
#' @param ties Tie handling in the partial likelihood. \code{"none"} (the default, and the behaviour of every release before 1.3.0) takes subjects who share an event time in the order the sorted data list them, so each is dropped from the risk sets of the tied rows after it; \code{"breslow"} uses Breslow's approximation, in which the risk set at an event time is everyone whose time is that time or later. The two coincide when no event time is tied.
#' @return An object of class \code{"cox_MDTL_enet"} containing:
#' \itemize{
#'   \item \code{beta}: Matrix of estimated coefficients (p x nlambda).
#'   \item \code{group}: Factor vector of the group assignments supplied for each covariate.
#'   \item \code{lambda}: The sequence of lambda values used.
#'   \item \code{alpha}: The Elastic Net mixing parameter used.
#'   \item \code{likelihood}: Vector of log-partial likelihoods, one per lambda
#'     (larger values indicate better fit; this is \emph{not} a loss). Unlike the
#'     Kullback-Leibler variants, this value is unweighted.
#'   \item \code{n}: Number of observations used in the fit.
#'   \item \code{df}: Degrees of freedom for each lambda.
#'   \item \code{iter}: Number of iterations for each lambda.
#'   \item \code{W}: Matrix of exponential linear predictors.
#'   \item \code{group.multiplier}: Numeric vector of group penalty multipliers used.
#'   \item \code{data}: List of input data.
#' }
#' When \code{returnX = TRUE}, an additional component \code{returnX} is attached, a
#' list with the standardized design object \code{XX} and the sorted \code{time},
#' \code{delta} and \code{stratum} vectors.
#'
#' @examples
#' \donttest{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#' 
#' cox_MDTL_enet_est <- cox_MDTL_enet(
#'   z = train_dat_highdim$z,
#'   delta = train_dat_highdim$status,
#'   time = train_dat_highdim$time,
#'   stratum = train_dat_highdim$stratum,
#'   beta = beta_external_highdim,
#'   Q = NULL,
#'   eta = 0,
#'   alpha = 1
#' )
#' }
#' @export
cox_MDTL_enet <- function(z, delta, time, stratum = NULL, 
                          beta, Q = NULL,
                          eta = NULL, 
                          alpha = NULL, lambda = NULL, nlambda = 100, lambda.min.ratio = ifelse(n < p, 0.05, 1e-03), 
                          lambda.early.stop = FALSE, tol = 1.0e-4, Mstop = 1000, max.total.iter = (Mstop * nlambda), 
                          group = 1:ncol(z), group.multiplier = NULL, standardize = T, 
                          nvar.max = ncol(z), group.max = length(unique(group)), stop.loss.ratio = 1e-2, 
                          actSet = TRUE, actIter = Mstop, actGroupNum = sum(unique(group) != 0), actSetRemove = F,
                          returnX = FALSE, trace.lambda = FALSE, message = FALSE, data_sorted = FALSE,
                          ties = c("none", "breslow")){
  ties <- .check_ties(match.arg(ties))
  
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

  ## Align external beta and Q to the covariates of z (named -> matched to
  ## colnames(z) and zero-padded; Q validated symmetric/PSD; NULL Q -> masked
  ## identity). Must precede z coercion/standardization and the ord reordering.
  aligned <- align_beta_Q(z, beta, Q)
  beta <- aligned$beta
  Q <- aligned$Q
  ## Did the analyst supply the metric, or did align_beta_Q manufacture it?  A supplied
  ## metric carries its own units (an external information matrix does) and the Mahalanobis
  ## penalty is left exactly as specified; a manufactured one is an arbitrary identity, and
  ## under standardize = TRUE it is taken on the standardized scale -- one standard deviation
  ## per covariate -- the same choice the ridge / lasso penalty makes, so the member does not
  ## depend on the units the covariates happen to be recorded in.  The MARK is read here and
  ## not from `is.null(Q)` on entry, because every cv.* wrapper aligns before calling the fit.
  Q_supplied <- !isTRUE(attr(Q, "manufactured"))

  z <- as.matrix(z)
  delta <- .check_event(delta, "delta")
  time <- as.numeric(time)
  
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
    z <- as.matrix(z)[time_order, , drop = FALSE]
    delta <- .check_event(delta[time_order], "delta")
  } else {
    stratum <- as.numeric(stratum)
  }
  
  n.each_stratum <- as.numeric(table(stratum))
  tm <- .tie_maps(as.numeric(time), n.each_stratum, ties)
  
  initial.group <- group
  if (standardize == T){
    std.Z <- newZG.Std(z, group, group.multiplier)
  } else {
    std.Z <- newZG.Unstd(z, group, group.multiplier)
  }
  Z <- std.Z$std.Z[, , drop = F]
  
  #orthogonal transformation for external information
  ord <- if (isTRUE(std.Z$reorder)) std.Z$ord else seq_len(ncol(Z))
  Q    <- Q[ord, ord, drop = FALSE]
  beta <- beta[ord]
  
  ## ---- the metric under standardization --------------------------
  ## beta_std = D beta with D = diag(scale) keeps the linear predictor.  What the
  ## Mahalanobis metric should become depends on where it came from:
  ##   * a Q the caller SUPPLIED carries its own units (an external information matrix
  ##     does), so Q_std = D^{-1} Q D^{-1} leaves
  ##     (beta_std - beta_ext_std)' Q_std (beta_std - beta_ext_std)
  ##       = (beta - beta_ext)' Q (beta - beta_ext)  exactly as specified;
  ##   * with Q = NULL align_beta_Q built a MASKED IDENTITY, and "one unit of whatever
  ##     the column happens to be measured in" is arbitrary and scale dependent.  The
  ##     matrix of ones and zeros is the same on either scale, so leaving it alone puts
  ##     the identity on the STANDARDIZED scale: one standard deviation per covariate,
  ##     free of the covariates' units.  This is the same convention as
  ##     cox_MDTL_ridge, so the two members of the family agree on what "no covariance
  ##     was released" means.
  ## Before 1.2.0 both cases used Q_std = D Q D, which for Q = NULL makes the metric
  ## acting on the original coefficients diag(scale^4).  Measured on the transplant
  ## cohort over 200 splits: 0.6385 then, 0.6423 now, and diag(1) would be 0.6201.
  if (isTRUE(standardize)) {
    D        <- diag(std.Z$scale[ord], ncol(Z))
    Dinv     <- diag(1 / std.Z$scale[ord], ncol(Z))
    Q_std    <- if (Q_supplied) as.matrix(Dinv %*% Q %*% Dinv) else Q
    beta_std <- as.vector(D %*% beta)
  } else {
    Q_std    <- Q
    beta_std <- beta
  }
  
  Tmat <- get_T_from_stdZ(std.Z)
  Tinv <- solve(Tmat)            
  
  Q_prime         <- as.matrix(t(Tinv) %*% Q_std %*% Tinv)
  beta_ext_prime  <- as.vector(Tinv %*% beta_std)
  Qbeta_ext_prime <- as.vector(Q_prime %*% beta_ext_prime)

  
  group <- std.Z$g  
  group.multiplier <- std.Z$m 
  p <- ncol(Z)
  n <- length(delta)
  nvar.max <- as.integer(nvar.max)
  group.max <- as.integer(group.max)
  
  beta.init <- rep(0, ncol(Z))

  
  if (is.null(lambda)) {
    if (nlambda < 2) {
      stop("nlambda must be at least 2", call. = FALSE)
    } else if (nlambda != round(nlambda)){
      stop("nlambda must be a positive integer", call. = FALSE)
    }
    lambda.fit <- setupLambda_MDTL(Z, time, delta, beta.init, stratum,
                                   beta_ext_prime, Q_prime, Qbeta_ext_prime,
                                   group, group.multiplier, n.each_stratum,
                                   alpha, eta, nlambda, lambda.min.ratio, tm = tm)
    
    lambda.seq <- lambda.fit$lambda.seq
    beta <- lambda.fit$beta
  } else {
    nlambda <- length(lambda)  
    lambda.seq <- as.vector(sort(lambda, decreasing = TRUE))
    beta <- beta.init
  }
  
  K <- as.integer(table(group))
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
  
  fit <- cox_MDTL_enet_cpp(delta, Z, n.each_stratum, beta, K0, K1, lambda.seq, lambda.early.stop,
                           stop.loss.ratio, group.multiplier, max.total.iter,Mstop, tol, 
                           initial.active.group, nvar.max, group.max,trace.lambda, actSet, 
                           actIter, actGroupNum, actSetRemove, alpha, eta, Q_prime, Qbeta_ext_prime,
                           tie_first = tm$first, tie_last = tm$last)
  
  
  # fit <- cox_MDTL_enet_cpp(delta, Z, n.each_stratum, beta, K0, K1, lambda.seq, lambda.early.stop,
  #                          stop.loss.ratio, group.multiplier, max.total.iter, Mstop, tol,
  #                          initial.active.group, nvar.max, group.max, trace.lambda, actSet,
  #                          actIter, actGroupNum, actSetRemove, alpha, eta, Q, Qbeta_ext)
  
  
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
  if (std.Z$reorder == TRUE){ # original order of beta
    beta <- beta[std.Z$ord.inv, , drop = F]
  }
  if (standardize == T) {
    original.beta <- matrix(0, nrow = length(std.Z$scale), ncol = ncol(beta))
    original.beta[std.Z$nz, ] <- beta / std.Z$scale[std.Z$nz]
    beta <- original.beta
  }
  
  
  # Names
  rownames(beta) <- colnames(input_data$z)   
  colnames(beta) <- round(lambda, 4)
  colnames(LinPred) <- round(lambda, 4)
  
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
    ties = ties,
    data = input_data
  ), class = "cox_MDTL_enet")
  
  if (returnX == TRUE){
    result$returnX <- list(XX = std.Z,
                           time = time,
                           delta = delta,
                           stratum = stratum)
  }
  return(result)
}
