#' Bagging for KL-Integrated Cox Elastic-Net Models
#'
#' Performs bootstrap aggregation (bagging) for the KL-integrated Cox
#' elastic-net model by repeatedly applying \code{cv.coxkl_enet} on bootstrap
#' resamples of the data. The procedure aggregates fitted coefficient vectors
#' across replicates to produce a more stable estimate that is less sensitive
#' to sampling variation or a single data split.
#'
#' External information may be supplied either as a fixed coefficient vector
#' (\code{beta}) or as pre-computed external risk scores (\code{RS}). When
#' \code{RS} is provided, it is resampled along with the bootstrap replicates;
#' when \code{beta} is provided, it is treated as fixed across replicates and
#' not resampled.
#'
#' @param z Matrix of predictors of dimension \code{n x p}.
#' @param delta Event indicator vector.
#' @param time Survival time vector.
#' @param stratum Optional stratum indicator vector for stratified Cox models.
#' @param RS Optional matrix or vector of external risk scores. If provided, it
#'   is resampled within each bootstrap replicate. If both \code{RS} and
#'   \code{beta} are supplied, \code{RS} takes precedence and \code{beta} is
#'   silently discarded.
#' @param beta Optional vector of external coefficients. If provided, it is
#'   treated as fixed and not resampled. It is passed through unchanged to
#'   \code{cv.coxkl_enet}, where a named \code{beta} is matched against
#'   \code{colnames(z)} and zero-padded for any covariate it does not cover,
#'   while an unnamed \code{beta} is aligned positionally and must have length
#'   \code{p} (see \code{\link{align_beta}}). Ignored when \code{RS} is supplied.
#' @param etas Numeric vector of non-negative integration weights. Must be finite
#'   and \eqn{\ge 0}.
#' @param alpha Elastic-net mixing parameter, with \eqn{0 < \alpha \le 1}
#'   (\code{alpha = 1} is the lasso penalty; values close to 0 approach ridge).
#'   Default is \code{1.0}. Values outside \code{(0, 1]} are rejected by
#'   \code{cv.coxkl_enet}; because each replicate is wrapped in
#'   \code{tryCatch()}, this surfaces as every replicate failing rather than as
#'   an immediate error.
#' @param B Number of bootstrap replicates. Default is \code{100}.
#' @param lambda Optional user-specified \code{lambda} sequence for the
#'   underlying elastic-net fit.
#' @param nlambda Number of \code{lambda} values to generate if \code{lambda}
#'   is not supplied. Default is \code{100}.
#' @param lambda.min.ratio Ratio of smallest to largest \code{lambda} value
#'   when generating a \code{lambda} sequence. Defaults to \code{0.05} when
#'   \code{nrow(z) < ncol(z)} and \code{1e-03} otherwise.
#' @param nfolds Number of folds for cross-validation in
#'   \code{cv.coxkl_enet}. Default is \code{5}.
#' @param cv.criteria Cross-validation criterion used for selecting
#'   \code{eta}–\code{lambda} pairs. One of \code{"V&VH"} (the default),
#'   \code{"LinPred"}, \code{"CIndex_pooled"} or \code{"CIndex_foldaverage"}.
#' @param c_index_stratum Optional stratum assignment for stratified C-index
#'   evaluation.
#' @param message Logical indicating whether to print progress.
#' @param seed Optional seed for reproducibility.
#' @param ncores Integer. Number of parallel cores. Default 1 (sequential execution).
#' @param ... Additional arguments passed to \code{cv.coxkl_enet}.
#'
#' @return
#' An object of class \code{"bagging"}, which is a list containing:
#' \itemize{
#'   \item \code{best_beta} — aggregated coefficient estimate obtained via
#'     averaging across valid replicates.
#'   \item \code{all_betas} — matrix of dimension \code{p x B_valid}
#'     containing coefficient vectors from each successful bootstrap fit.
#'   \item \code{B} — total number of bootstrap replicates.
#'   \item \code{seed} — seed used (if any).
#'   \item \code{valid_replicates} — number of successful (non-error)
#'     bootstrap fits used in aggregation.
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim     <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#' etas <- generate_eta(method = "exponential", n = 10, max_eta = 100)
#'
#' bag.out <- coxkl_enet_bagging(
#'   z     = train_dat_highdim$z,
#'   delta = train_dat_highdim$status,
#'   time  = train_dat_highdim$time,
#'   stratum = train_dat_highdim$stratum,
#'   beta    = beta_external_highdim,
#'   etas    = etas,
#'   B       = 5,
#'   seed    = 1
#' )
#' }
#'
#' @export
coxkl_enet_bagging <- function(z, delta, time, stratum = NULL, RS = NULL, beta = NULL,
                               etas, alpha = 1.0, B = 100, lambda = NULL, nlambda = 100,
                               lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.05, 1e-03),
                               nfolds = 5, cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                               c_index_stratum = NULL,
                               message = FALSE, seed = NULL, ncores = 1, ...) {

  cv.criteria <- match.arg(cv.criteria)

  z <- as.matrix(z)
  n <- nrow(z)
  p <- ncol(z)

  if (is.null(RS) && is.null(beta)) {
    stop("No external information is provided. Either RS or beta must be provided.")
  }

  check_etas(etas)

  if (!is.null(RS)) RS <- as.matrix(RS)

  if (is.null(stratum)) {
    stratum_full <- rep(1, n)
  } else {
    stratum_full <- stratum
  }

  ncores <- max(1L, as.integer(ncores))

  # Capture ... for passing to workers
  dots <- list(...)

  # Define worker function
  boot_one <- function(i, z, delta, time, stratum_full, RS, beta, etas, alpha,
                       lambda, nlambda, lambda.min.ratio, nfolds, cv.criteria,
                       c_index_stratum, p, seed, dots) {
    if (!is.null(seed)) set.seed(seed + i)
    n <- nrow(z)
    boot_idx <- sort(sample(seq_len(n), size = n, replace = TRUE))

    z_b       <- z[boot_idx, , drop = FALSE]
    delta_b   <- delta[boot_idx]
    time_b    <- time[boot_idx]
    stratum_b <- stratum_full[boot_idx]

    RS_b <- NULL
    beta_in <- NULL

    if (!is.null(RS)) {
      RS_b <- RS[boot_idx, , drop = FALSE]
    } else {
      beta_in <- beta
    }

    c_idx_strat_b <- NULL
    if (!is.null(c_index_stratum)) {
      c_idx_strat_b <- c_index_stratum[boot_idx]
    }

    fit_res <- tryCatch({
      do.call(cv.coxkl_enet, c(
        list(
          z = z_b,
          delta = delta_b,
          time = time_b,
          stratum = stratum_b,
          RS = RS_b,
          beta = beta_in,
          etas = etas,
          alpha = alpha,
          lambda = lambda,
          nlambda = nlambda,
          lambda.min.ratio = lambda.min.ratio,
          nfolds = nfolds,
          cv.criteria = cv.criteria,
          c_index_stratum = c_idx_strat_b,
          message = FALSE
        ),
        dots
      ))
    }, error = function(e) {
      return(NULL)
    })

    if (!is.null(fit_res)) {
      return(as.vector(fit_res$best$best_beta))
    } else {
      return(rep(NA, p))
    }
  }

  if (message) cat("Running", B, "bootstrap replicates on", ncores, "core(s)...\n")

  if (ncores == 1L) {
    # Sequential execution with progress bar
    if (message) pb <- txtProgressBar(min = 0, max = B, style = 3)
    res_list <- vector("list", B)
    for (i in seq_len(B)) {
      if (!is.null(seed)) set.seed(seed + i)
      res_list[[i]] <- boot_one(i, z, delta, time, stratum_full, RS, beta, etas, alpha,
                                lambda, nlambda, lambda.min.ratio, nfolds, cv.criteria,
                                c_index_stratum, p, seed, dots)
      if (message) setTxtProgressBar(pb, i)
    }
    if (message) close(pb)
  } else {
    # Parallel execution
    cl <- parallel::makeCluster(ncores)
    on.exit(parallel::stopCluster(cl), add = TRUE)

    # Set up parallel RNG
    if (!is.null(seed)) {
      RNGkind("L'Ecuyer-CMRG")
      set.seed(seed)
      parallel::clusterSetRNGStream(cl, seed)
    }

    res_list <- parallel::parLapply(
      cl, seq_len(B), boot_one,
      z = z, delta = delta, time = time, stratum_full = stratum_full,
      RS = RS, beta = beta, etas = etas, alpha = alpha,
      lambda = lambda, nlambda = nlambda, lambda.min.ratio = lambda.min.ratio,
      nfolds = nfolds, cv.criteria = cv.criteria,
      c_index_stratum = c_index_stratum, p = p, seed = seed, dots = dots
    )
  }

  if (message) cat("Done.\n")

  res_mat <- do.call(cbind, res_list)
  valid_cols <- !apply(res_mat, 2, function(x) any(is.na(x)))

  if (sum(valid_cols) < B) {
    warning(sprintf("Only %d out of %d bootstrap replicates converged.", sum(valid_cols), B))
    res_mat <- res_mat[, valid_cols, drop = FALSE]
  }

  bagged_beta <- rowMeans(res_mat)

  structure(
    list(
      best_beta = bagged_beta,
      all_betas = res_mat,
      B = B,
      seed = seed,
      valid_replicates = sum(valid_cols)
    ),
    class = "bagging"
  )
}
