#' Cox Proportional Hazards Model Integrated with External Individual-level Data and Elastic Net Penalty
#'
#' @description
#' Fits a series of penalized stratified Cox models that integrate an external
#' individual-level dataset via a composite likelihood weight \code{eta}, while
#' applying an Elastic Net (Lasso + Ridge) penalty for variable selection and
#' regularization in high-dimensional settings.
#'
#' @details
#' The fitted objective is
#' \deqn{\ell_{\eta,\lambda}(\beta) = \ell_{\text{int}}(\beta) + \eta \, \ell_{\text{ext}}(\beta) - \text{Pen}_{\lambda,\alpha}(\beta),}
#' where \eqn{\text{Pen}_{\lambda,\alpha}} is the Elastic Net penalty. This is equivalent
#' to fitting a penalized stratified Cox model on the stacked data with observation
#' weights 1 (internal) and \code{eta} (external), while keeping internal and external
#' strata separated (no mixing of risk sets across cohorts).
#' \itemize{
#'   \item If \code{alpha = 1}, the penalty is Lasso.
#'   \item If \code{alpha} is close to 0, the penalty approaches Ridge.
#'   \item If \code{eta = 0}, external data is effectively ignored and the model reduces
#'         to a standard Elastic Net Cox model on internal data only.
#' }
#'
#' The function fits one full lambda path per \code{eta} value. Standardization is
#' performed once on the stacked design matrix before the loop, so the lambda sequence
#' is recomputed for each \code{eta} (since \eqn{\lambda_{\max}} depends on the
#' weighted score at \eqn{\beta = 0}).
#'
#' @param z_int Numeric matrix of covariates for the internal dataset (\eqn{n_{\text{int}} \times p}).
#' @param delta_int Numeric vector of event indicators for the internal dataset (1 = event, 0 = censored).
#' @param time_int Numeric vector of survival times for the internal dataset.
#' @param stratum_int Optional stratum identifiers for the internal dataset.
#'   Default \code{NULL} assigns all internal observations to a single stratum.
#' @param z_ext Numeric matrix of covariates for the external dataset (\eqn{n_{\text{ext}} \times p}).
#'   Must have the same number of columns as \code{z_int}.
#' @param delta_ext Numeric vector of event indicators for the external dataset (1 = event, 0 = censored).
#' @param time_ext Numeric vector of survival times for the external dataset.
#' @param stratum_ext Optional stratum identifiers for the external dataset.
#'   Default \code{NULL} assigns all external observations to a single stratum.
#' @param etas Numeric vector of nonnegative external weights. \code{eta = 0} gives
#'   an internal-only penalized fit. The vector is sorted internally in ascending order.
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 < \alpha \le 1}.
#'   \code{alpha = 1} is the lasso penalty, and \code{alpha} close to 0 approaches ridge.
#'   Defaults to 1.
#' @param lambda Optional numeric vector of penalty parameters applied to all \code{eta} values.
#'   If \code{NULL}, a lambda path is generated automatically for each \code{eta}.
#' @param nlambda Integer. The number of lambda values to generate per \code{eta}. Default is 100.
#' @param lambda.min.ratio Numeric. The ratio of the smallest to the largest lambda in the sequence.
#'   Default is 0.05 if \eqn{n_{\text{all}} < p}, and 1e-3 otherwise.
#' @param lambda.early.stop Logical. If \code{TRUE}, stops the lambda path early if the loss
#'   improvement is small. Default \code{FALSE}.
#' @param tol Numeric. Convergence tolerance for the coordinate descent optimization. Default is 1e-4.
#' @param Mstop Integer. Maximum coordinate descent iterations per lambda. Default is 1000.
#' @param max.total.iter Integer. Maximum total iterations across the entire lambda path.
#'   Default is \code{Mstop * nlambda}.
#' @param group Integer vector defining group membership for grouped penalties.
#'   Default treats each variable as its own group (standard Elastic Net / Lasso).
#' @param group.multiplier Numeric vector. Multiplicative factors for penalties applied to each group.
#' @param standardize Logical. If \code{TRUE}, the stacked design matrix \code{z_all} is
#'   standardized internally. Coefficients are returned on the original scale. Default \code{TRUE}.
#' @param nvar.max Integer. Maximum number of active variables allowed. Defaults to \code{p}.
#' @param group.max Integer. Maximum number of active groups allowed. Defaults to the total
#'   number of unique groups.
#' @param stop.loss.ratio Numeric. Threshold for early stopping based on loss ratio. Default is 1e-2.
#' @param actSet Logical. If \code{TRUE}, uses an active-set strategy for coordinate descent. Default \code{TRUE}.
#' @param actIter Integer. Maximum iterations for active set refinement. Default is \code{Mstop}.
#' @param actGroupNum Integer. Limit on active groups in the active set strategy.
#' @param actSetRemove Logical. Whether to allow removal from the active set. Default \code{FALSE}.
#' @param returnX Logical. If \code{TRUE}, the standardized design matrix object \code{std.Z} is
#'   included in the returned result. Default \code{FALSE}.
#' @param trace.lambda Logical. If \code{TRUE}, prints the lambda sequence progress. Default \code{FALSE}.
#' @param message Logical. If \code{TRUE}, shows a progress bar over the \code{etas} loop. Default \code{FALSE}.
#' @param ... Additional arguments (currently unused).
#'
#' @return
#' An object of class \code{"cox_indi_enet"} containing:
#' \describe{
#'   \item{\code{eta}}{Sorted sequence of \eqn{\eta} values used.}
#'   \item{\code{beta}}{Named list of length \code{length(etas)}. Each element is a matrix of
#'     estimated coefficients (\eqn{p \times n_\lambda}) on the original covariate scale,
#'     with columns named by the corresponding \code{lambda} values.}
#'   \item{\code{lambda}}{Unnamed list of length \code{length(etas)}, parallel to
#'     \code{beta}. Each element is the vector of lambda values actually used for
#'     that \code{eta}.}
#'   \item{\code{alpha}}{The Elastic Net mixing parameter used.}
#'   \item{\code{linear.predictors_int}}{List of matrices (\eqn{n_{\text{int}} \times n_\lambda})
#'     of internal linear predictors in the original observation order, one per \code{eta}.}
#'   \item{\code{linear.predictors_ext}}{List of matrices (\eqn{n_{\text{ext}} \times n_\lambda})
#'     of external linear predictors in the original observation order, one per \code{eta}.}
#'   \item{\code{group}}{Factor vector of group assignments for each covariate.}
#'   \item{\code{group.multiplier}}{Numeric vector of group penalty multipliers used.}
#'   \item{\code{data}}{List of the original input data used.}
#' }
#' When \code{returnX = TRUE}, an additional component \code{std.Z} is attached,
#' the standardized design object built from the stacked covariate matrix.
#'
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
#' eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 5)
#'
#' ## Fit the composite-likelihood Elastic Net Cox model path
#' fit.cox_indi_enet <- cox_indi_enet(
#'   z_int       = z_int,
#'   delta_int   = delta_int,
#'   time_int    = time_int,
#'   stratum_int = stratum_int,
#'   z_ext       = z_ext,
#'   delta_ext   = delta_ext,
#'   time_ext    = time_ext,
#'   stratum_ext = stratum_ext,
#'   etas        = eta_list,
#'   alpha       = 1,      # Lasso penalty
#'   nlambda     = 100
#' )
#'
#' ## Coefficient matrix for the first eta value
#' fit.cox_indi_enet$beta[[1]]

#' }
#'
#' @importFrom utils txtProgressBar setTxtProgressBar
#' @export
cox_indi_enet <- function(z_int, delta_int, time_int, stratum_int = NULL,
                           z_ext, delta_ext, time_ext, stratum_ext = NULL,
                           etas, alpha = 1, lambda = NULL, nlambda = 100,
                           lambda.min.ratio = NULL,
                           lambda.early.stop = FALSE, tol = 1.0e-4, Mstop = 1000,
                           max.total.iter = (Mstop * nlambda),
                           group = NULL, group.multiplier = NULL,
                           standardize = TRUE,
                           nvar.max = NULL, group.max = NULL,
                           stop.loss.ratio = 1e-2,
                           actSet = TRUE, actIter = Mstop,
                           actGroupNum = NULL, actSetRemove = FALSE,
                           returnX = FALSE, trace.lambda = FALSE,
                           message = FALSE, ...) {

  z_int   <- as.matrix(z_int)
  z_ext   <- as.matrix(z_ext)
  delta_int <- as.numeric(delta_int)
  delta_ext <- as.numeric(delta_ext)
  time_int  <- as.numeric(time_int)
  time_ext  <- as.numeric(time_ext)

  n_int <- nrow(z_int)
  n_ext <- nrow(z_ext)
  n_all <- n_int + n_ext
  p     <- ncol(z_int)

  if (ncol(z_ext) != p)
    stop("Internal and external datasets must have the same number of covariates.", call. = FALSE)

  if (alpha <= 0 || alpha > 1)
    stop("alpha must be in (0, 1].", call. = FALSE)

  if (is.null(etas))
    stop("etas must be provided.", call. = FALSE)
  etas <- sort(as.numeric(etas))
  check_etas(etas)

  if (is.null(lambda.min.ratio))
    lambda.min.ratio <- ifelse(n_all < p, 0.05, 1e-03)

  if (is.null(group))
    group <- seq_len(p)
  if (is.null(nvar.max))
    nvar.max <- p
  if (is.null(group.max))
    group.max <- length(unique(group))
  if (is.null(actGroupNum))
    actGroupNum <- sum(unique(group) != 0)

  if (is.null(stratum_int)) stratum_int <- rep(1L, n_int)
  if (is.null(stratum_ext)) stratum_ext <- rep(1L, n_ext)

  stratum_int <- as.vector(stratum_int)
  stratum_ext <- as.vector(stratum_ext)

  stratum_int_enc <- as.integer(match(stratum_int, unique(stratum_int)))
  stratum_ext_enc <- as.integer(match(stratum_ext, unique(stratum_ext))) +
    max(stratum_int_enc)

  ord_int <- order(stratum_int_enc, time_int)
  z_int_s       <- z_int[ord_int,  , drop = FALSE]
  delta_int_s   <- delta_int[ord_int]
  time_int_s    <- time_int[ord_int]
  stratum_int_s <- stratum_int_enc[ord_int]

  ord_ext <- order(stratum_ext_enc, time_ext)
  z_ext_s       <- z_ext[ord_ext,  , drop = FALSE]
  delta_ext_s   <- delta_ext[ord_ext]
  time_ext_s    <- time_ext[ord_ext]
  stratum_ext_s <- stratum_ext_enc[ord_ext]


  z_all       <- rbind(z_int_s, z_ext_s)
  delta_all   <- c(delta_int_s, delta_ext_s)
  time_all    <- c(time_int_s,  time_ext_s)
  stratum_all <- c(stratum_int_s, stratum_ext_s)

  n_each_stratum <- as.numeric(table(stratum_all))


  initial_group <- group          # keep original for output
  group.multiplier <- if (is.null(group.multiplier)) {
    rep(1, length(unique(group)))
  } else {
    as.numeric(group.multiplier)
  }

  if (standardize) {
    std.Z <- newZG.Std(z_all, group, group.multiplier)
  } else {
    std.Z <- newZG.Unstd(z_all, group, group.multiplier)
  }

  Z_std        <- std.Z$std.Z          # standardized + orthogonalized matrix
  group_std    <- std.Z$g              # (possibly reordered) group vector
  grp_mult_std <- as.double(std.Z$m)  # group multipliers after orthogonalization

  p_std <- ncol(Z_std)                 # may differ from p if constant cols removed

  K_tab <- as.integer(table(group_std))
  K0    <- as.integer(if (min(group_std) == 0) K_tab[1] else 0)
  K1    <- as.integer(if (min(group_std) == 0) cumsum(K_tab) else c(0L, cumsum(K_tab)))

  initial_active_group <- -1L
  if (actSet) {
    if (K0 == 0)
      initial_active_group <- which(K_tab == min(K_tab))[1] - 1L
  } else {
    actIter <- max.total.iter
  }

  n_eta    <- length(etas)
  beta_list <- vector("list", n_eta)
  names(beta_list) <- round(etas, 6)

  lp_int_list <- vector("list", n_eta)   # linear predictors, internal, original order
  lp_ext_list <- vector("list", n_eta)

  lambda_list <- vector("list", n_eta)   # actual lambda path used per eta

  if (message) {
    pb <- utils::txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }

  for (i in seq_along(etas)) {
    eta_i <- etas[i]
    beta_init <- rep(0.0, p_std)
    weight_all <- c(rep(1.0, n_int), rep(eta_i, n_ext))

    if (is.null(lambda)) {
      if (nlambda < 2)
        stop("nlambda must be at least 2.", call. = FALSE)

      lambda_fit <- set.lambda.cox.enet(
        delta.obs        = delta_all,
        Z                = Z_std,
        time             = time_all,
        ID               = stratum_all,
        beta             = beta_init,
        weight           = weight_all,
        group            = group_std,
        group.multiplier = grp_mult_std,
        n.each_prov      = n_each_stratum,
        alpha            = alpha,
        nlambda          = nlambda,
        lambda.min.ratio = lambda.min.ratio
      )
      lambda_seq  <- lambda_fit$lambda.seq
      beta_start  <- lambda_fit$beta
    } else {
      lambda_seq <- as.numeric(sort(lambda, decreasing = TRUE))
      beta_start <- beta_init
    }

    # ------------------------------------------------------------------
    # 6b. Fit the penalized model on standardized data
    # ------------------------------------------------------------------
    fit <- StratCox_lasso(
      delta_obs        = delta_all,
      Z                = Z_std,
      weight           = weight_all,
      n_each_prov      = n_each_stratum,
      beta             = beta_start,
      K0               = K0,
      K1               = K1,
      lambda_seq       = lambda_seq,
      lambda_early_stop = lambda.early.stop,
      stop_loss_ratio  = stop.loss.ratio,
      group_multiplier = grp_mult_std,
      max_total_iter   = max.total.iter,
      max_each_iter    = Mstop,
      tol              = tol,
      initial_active_group = initial_active_group,
      nvar_max         = nvar.max,
      group_max        = group.max,
      trace_lambda     = trace.lambda,
      actSet           = actSet,
      actIter          = actIter,
      activeGroupNum   = actGroupNum,
      actSetRemove     = actSetRemove
    )

    beta_std  <- fit$beta        # p_std  x nlambda_actual  (standardized space)
    eta_mat   <- fit$Eta         # n_all  x nlambda_actual  (linear predictors, std space)
    iter_vec  <- fit$iter

    # Drop saturated lambdas (iter == NA)
    keep       <- !is.na(iter_vec)
    lambda_seq <- lambda_seq[keep]
    beta_std   <- beta_std[,  keep, drop = FALSE]
    eta_mat    <- eta_mat[,   keep, drop = FALSE]

    beta_orig <- unorthogonalize(beta_std, std.Z$std.Z, group_std)

    if (std.Z$reorder) {
      beta_orig <- beta_orig[std.Z$ord.inv, , drop = FALSE]
    }

    if (standardize) {
      beta_unscaled <- matrix(0.0, nrow = length(std.Z$scale), ncol = ncol(beta_orig))
      beta_unscaled[std.Z$nz, ] <- beta_orig / std.Z$scale[std.Z$nz]
      beta_orig <- beta_unscaled
    }

    rownames(beta_orig) <- colnames(z_all)
    colnames(beta_orig) <- round(lambda_seq, digits = 4)


    lp_int_sorted <- eta_mat[seq_len(n_int),          , drop = FALSE]  # sorted internal LP
    lp_ext_sorted <- eta_mat[n_int + seq_len(n_ext),  , drop = FALSE]  # sorted external LP

    lp_int_orig <- matrix(NA_real_, nrow = n_int, ncol = ncol(eta_mat))
    lp_ext_orig <- matrix(NA_real_, nrow = n_ext, ncol = ncol(eta_mat))
    lp_int_orig[ord_int, ] <- lp_int_sorted
    lp_ext_orig[ord_ext, ] <- lp_ext_sorted

    colnames(lp_int_orig) <- round(lambda_seq, digits = 4)
    colnames(lp_ext_orig) <- round(lambda_seq, digits = 4)

    # Store results
    beta_list[[i]]    <- beta_orig
    lp_int_list[[i]]  <- lp_int_orig
    lp_ext_list[[i]]  <- lp_ext_orig
    lambda_list[[i]]  <- lambda_seq

    if (message) utils::setTxtProgressBar(pb, i)
  }

  if (message) close(pb)

  input_data <- list(
    z_int = z_int, delta_int = delta_int, time_int = time_int, stratum_int = stratum_int,
    z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext, stratum_ext = stratum_ext
  )

  result <- structure(
    list(
      eta              = etas,
      beta             = beta_list,
      lambda           = lambda_list,
      alpha            = alpha,
      linear.predictors_int = lp_int_list,
      linear.predictors_ext = lp_ext_list,
      group            = factor(initial_group),
      group.multiplier = grp_mult_std,
      data             = input_data
    ),
    class = "cox_indi_enet"
  )

  if (returnX) {
    result$std.Z <- std.Z
  }

  return(result)
}


