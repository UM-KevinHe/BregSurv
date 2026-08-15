#' Bagging for MDTL-Integrated Cox Elastic-Net Models
#'
#' Performs bootstrap aggregation (bagging) for the Mahalanobis-distance–based
#' transfer-learning Cox elastic-net model (\code{cv.cox_MDTL_enet}) by repeatedly
#' refitting the model on bootstrap resamples of the internal dataset and
#' averaging the resulting fitted coefficient vectors. This procedure reduces
#' sampling variability and improves robustness relative to a single data split.
#'
#' External information is supplied via a fixed coefficient vector (\code{beta})
#' and, optionally, a weighting matrix (\code{Q}). Both represent external
#' prior information and are \strong{not} resampled across replicates.
#'
#' @param z Matrix of predictors of dimension \code{n x p}.
#' @param delta Event indicator vector.
#' @param time Survival time vector.
#' @param stratum Optional stratum indicator vector for stratified Cox modeling.
#' @param beta Numeric vector of external coefficients. If \code{beta} is named,
#'   names are matched against \code{colnames(z)}: covariates absent from
#'   \code{beta} are set to 0 (with a message) and the vector is reordered, so an
#'   external source covering only a subset of the internal covariates may be
#'   supplied directly. An unnamed \code{beta} is aligned positionally and must
#'   have length \code{ncol(z)}. See \code{\link{align_beta_Q}}. Treated as fixed
#'   prior information and not resampled across bootstrap replicates.
#' @param Q Optional weighting (precision) matrix for the Mahalanobis penalty.
#'   Must be symmetric and positive semi-definite (both checked to a tolerance of
#'   1e-8). If named, it is reordered and zero-padded to \code{colnames(z)}; only
#'   an unnamed \code{Q} must be exactly \code{ncol(z)} by \code{ncol(z)}. If
#'   \code{NULL}, a \emph{masked identity} is used: 1 on covariates actually
#'   supplied by \code{beta} and 0 on zero-padded positions, so padded
#'   coefficients are left unpenalized. See \code{\link{align_beta_Q}}.
#' @param etas Numeric vector of non-negative integration weights. Must be finite
#'   and \eqn{\ge 0}.
#' @param alpha Elastic-net mixing parameter, with \eqn{0 < \alpha \le 1}.
#'   \code{alpha = 1} corresponds to lasso; values close to 0 approach ridge.
#'   Default is \code{1.0}.
#' @param B Number of bootstrap replicates. Default is \code{100}.
#' @param lambda Optional user-specified \code{lambda} sequence.
#' @param nlambda Number of \code{lambda} values to generate if \code{lambda} is not supplied.
#'   Default is \code{100}.
#' @param lambda.min.ratio Ratio of the smallest to the largest \code{lambda} when generating a sequence.
#'   Default is \code{ifelse(nrow(z) < ncol(z), 0.01, 1e-04)}.
#' @param nfolds Number of folds for inner cross-validation via \code{cv.cox_MDTL_enet}.
#'   Default is \code{5}.
#' @param cv.criteria Cross-validation criterion used for selecting the optimal
#'   \code{(eta, lambda)} pair. One of \code{"V&VH"}, \code{"LinPred"},
#'   \code{"CIndex_pooled"} or \code{"CIndex_foldaverage"}; the default is
#'   \code{"V&VH"}.
#' @param c_index_stratum Optional stratum assignment for stratified C-index
#'   evaluation (may differ from model stratification).
#' @param message Logical indicating whether to print progress. Default is \code{FALSE}.
#' @param seed Optional integer seed for reproducibility. Default is \code{NULL}.
#' @param ncores Integer. Number of parallel cores. Default 1 (sequential execution).
#' @param ... Additional arguments passed to \code{cv.cox_MDTL_enet}.
#'
#' @return
#' An object of class \code{"cox_MDTL_bagging"} containing:
#' \itemize{
#'   \item \code{best_beta} — aggregated coefficient estimate obtained by averaging
#'     across valid bootstrap replicates.
#'   \item \code{all_betas} — matrix of dimension \code{p x B_valid} containing
#'     coefficient vectors from each successful bootstrap fit.
#'   \item \code{B} — total number of requested bootstrap replicates.
#'   \item \code{valid_replicates} — number of successful (non-error) fits contributing to aggregation.
#'   \item \code{seed} — seed used for reproducibility (if supplied).
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim     <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' etas <- generate_eta(method = "exponential", n = 10, max_eta = 10)
#'
#' bag.out <- cox_MDTL_enet_bagging(
#'   z            = train_dat_highdim$z,
#'   delta        = train_dat_highdim$status,
#'   time         = train_dat_highdim$time,
#'   stratum      = train_dat_highdim$stratum,
#'   beta         = beta_external_highdim,
#'   Q            = NULL,
#'   etas         = etas,
#'   alpha        = 0.5,
#'   B            = 5,
#'   cv.criteria  = "CIndex_pooled",
#'   message      = TRUE,
#'   seed         = 123
#' )
#' }
#'
#' @export
cox_MDTL_enet_bagging <- function(z, delta, time, stratum = NULL, beta = NULL, Q = NULL,
                                  etas, alpha = 1.0, B = 100, lambda = NULL, nlambda = 100,
                                  lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.01, 1e-04),
                                  nfolds = 5,
                                  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                                  c_index_stratum = NULL,
                                  message = FALSE, seed = NULL, ncores = 1, ...) {

  cv.criteria <- match.arg(cv.criteria)

  z <- as.matrix(z)
  n <- nrow(z)
  p <- ncol(z)

  # Input checks specific to MDTL. The length/name reconciliation of 'beta' (and
  # 'Q') is delegated to align_beta_Q() inside cv.cox_MDTL_enet(), so a named
  # partial external vector is accepted here exactly as it is there.
  if (is.null(beta)) {
    stop("External beta must be provided for Cox MDTL.")
  }

  if (missing(etas) || is.null(etas)) stop("etas must be provided.", call. = FALSE)
  check_etas(etas)

  if (is.null(stratum)) {
    stratum_full <- rep(1, n)
  } else {
    stratum_full <- stratum
  }

  ncores <- max(1L, as.integer(ncores))

  # Capture ... for passing to workers
  dots <- list(...)

  # Define worker function
  boot_one <- function(i, z, delta, time, stratum_full, beta, Q, etas, alpha,
                       lambda, nlambda, lambda.min.ratio, nfolds, cv.criteria,
                       c_index_stratum, p, seed, dots) {
    if (!is.null(seed)) set.seed(seed + i)
    n <- nrow(z)
    boot_idx <- sort(sample(seq_len(n), size = n, replace = TRUE))

    z_b       <- z[boot_idx, , drop = FALSE]
    delta_b   <- delta[boot_idx]
    time_b    <- time[boot_idx]
    stratum_b <- stratum_full[boot_idx]

    # Note: 'beta' and 'Q' are EXTERNAL information, so they are fixed and NOT resampled.

    c_idx_strat_b <- NULL
    if (!is.null(c_index_stratum)) {
      c_idx_strat_b <- c_index_stratum[boot_idx]
    }

    fit_res <- tryCatch({
      do.call(cv.cox_MDTL_enet, c(
        list(
          z = z_b,
          delta = delta_b,
          time = time_b,
          stratum = stratum_b,
          beta = beta,
          Q = Q,
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
      # Carry the message out so a systematic failure is reported rather than
      # collapsing into the opaque "All bootstrap replicates failed."
      structure(conditionMessage(e), class = "bagging_replicate_error")
    })

    if (inherits(fit_res, "bagging_replicate_error")) {
      failed <- rep(NA_real_, p)
      attr(failed, "boot_error") <- as.character(fit_res)
      return(failed)
    }

    if (!is.null(fit_res)) {
      return(as.vector(fit_res$best$best_beta))
    } else {
      return(rep(NA, p))
    }
  }

  if (message) cat("Starting Bagging (B =", B, ") for cv.cox_MDTL_enet on", ncores, "core(s)...\n")

  if (ncores == 1L) {
    # Sequential execution with progress bar
    if (message) pb <- txtProgressBar(min = 0, max = B, style = 3)
    res_list <- vector("list", B)
    for (i in seq_len(B)) {
      if (!is.null(seed)) set.seed(seed + i)
      res_list[[i]] <- boot_one(i, z, delta, time, stratum_full, beta, Q, etas, alpha,
                                lambda, nlambda, lambda.min.ratio, nfolds, cv.criteria,
                                c_index_stratum, p, seed, dots)
      if (message) setTxtProgressBar(pb, i)
    }
    if (message) close(pb)
  } else {
    # Parallel execution
    cl <- parallel::makeCluster(ncores)
    on.exit(parallel::stopCluster(cl), add = TRUE)

    # Set up parallel RNG. Switching the generator is a global side effect, so
    # the caller's RNG kind is captured first and restored on exit (including on
    # error) rather than left mutated.
    if (!is.null(seed)) {
      old_kind <- RNGkind()
      on.exit(RNGkind(old_kind[1]), add = TRUE)
      RNGkind("L'Ecuyer-CMRG")
      set.seed(seed)
      parallel::clusterSetRNGStream(cl, seed)
    }

    res_list <- parallel::parLapply(
      cl, seq_len(B), boot_one,
      z = z, delta = delta, time = time, stratum_full = stratum_full,
      beta = beta, Q = Q, etas = etas, alpha = alpha,
      lambda = lambda, nlambda = nlambda, lambda.min.ratio = lambda.min.ratio,
      nfolds = nfolds, cv.criteria = cv.criteria,
      c_index_stratum = c_index_stratum, p = p, seed = seed, dots = dots
    )
  }

  if (message) cat("Done.\n")

  # First error raised by any replicate (attached by boot_one); cbind() drops
  # attributes, so it must be read off res_list before aggregation.
  first_err <- NA_character_
  for (res_i in res_list) {
    err_i <- attr(res_i, "boot_error")
    if (!is.null(err_i)) {
      first_err <- err_i
      break
    }
  }

  # Aggregate results
  res_mat <- do.call(cbind, res_list)

  # Check for failed runs (NA columns)
  valid_cols <- !apply(res_mat, 2, function(x) any(is.na(x)))
  n_valid <- sum(valid_cols)

  if (n_valid < B) {
    warning(sprintf("Only %d out of %d bootstrap replicates converged.", n_valid, B))
    res_mat <- res_mat[, valid_cols, drop = FALSE]
  }

  if (n_valid == 0) {
    if (is.na(first_err)) {
      stop("All bootstrap replicates failed.")
    } else {
      stop(sprintf("All bootstrap replicates failed. First error: %s", first_err))
    }
  }

  bagged_beta <- rowMeans(res_mat)

  structure(
    list(
      best_beta = bagged_beta,
      all_betas = res_mat,
      B = B,
      seed = seed,
      valid_replicates = n_valid
    ),
    class = "cox_MDTL_bagging"
  )
}





