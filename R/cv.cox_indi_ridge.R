#' Cross-Validation for \code{cox_indi_ridge}
#'
#' @description
#' Selects the external weight \eqn{\eta} and the ridge penalty of
#' \code{\link{cox_indi_ridge}} by cross-validation on the internal cohort. Each
#' training fold is fitted together with the whole external cohort; the held-out score
#' uses the internal rows only, exactly as \code{\link{cv.cox_indi_enet}}.
#'
#' @param z_int,delta_int,time_int,stratum_int Internal data, as in \code{\link{cox_indi_ridge}}.
#' @param z_ext,delta_ext,time_ext,stratum_ext External data.
#' @param etas Candidate weights of the external rows.
#' @param lambda Optional common penalty path; \code{NULL} uses the path of the full-data
#'   fit at each \eqn{\eta}.
#' @param nlambda Path length. Default 100.
#' @param nfolds Number of folds. Default 5.
#' @param cv.criteria \code{"V&VH"} (default), \code{"LinPred"}, \code{"CIndex_pooled"} or
#'   \code{"CIndex_foldaverage"}.
#' @param c_index_stratum Optional strata for the C-index criteria (must equal \code{stratum_int}).
#' @param standardize Passed to \code{\link{cox_indi_ridge}}. Default \code{TRUE}.
#' @param message Logical; progress bar.
#' @param seed Optional seed of the fold assignment (Mersenne-Twister).
#' @param ties \code{"none"} or \code{"breslow"}.
#' @param ... Further arguments to \code{\link{cox_indi_ridge}}.
#' @return An object of class \code{"cv.cox_indi_ridge"} with \code{best},
#'   \code{integrated_stat.full_results}, \code{integrated_stat.best_per_eta},
#'   \code{integrated_stat.betahat_best}, \code{criteria}, \code{nfolds}, \code{folds},
#'   \code{seed} and \code{rng_kind}.
#' @examples
#' \dontrun{
#' data(ExampleData_indi)
#' cvfit <- cv.cox_indi_ridge(
#'   z_int = ExampleData_indi$internal$z, delta_int = ExampleData_indi$internal$status,
#'   time_int = ExampleData_indi$internal$time,
#'   z_ext = ExampleData_indi$external$z, delta_ext = ExampleData_indi$external$status,
#'   time_ext = ExampleData_indi$external$time,
#'   etas = c(0, 0.5, 1))
#' }
#' @export
cv.cox_indi_ridge <- function(z_int, delta_int, time_int, stratum_int = NULL,
                             z_ext, delta_ext, time_ext, stratum_ext = NULL,
                             etas,
                             lambda = NULL, nlambda = 100,
                             nfolds = 5,
                             cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                             c_index_stratum = NULL,
                             standardize = TRUE,
                             message = FALSE, seed = NULL, ties = c("none", "breslow"), ...) {
  ties <- .check_ties(match.arg(ties))

  # --------------------------------------------------------------------------
  # 0. Input checks and coercions
  # --------------------------------------------------------------------------
  cv.criteria <- match.arg(cv.criteria,
                           choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas <- sort(as.numeric(etas))
  check_etas(etas)

  z_int     <- as.matrix(z_int)
  z_ext     <- as.matrix(z_ext)
  delta_int <- .check_event(delta_int, "delta_int")
  delta_ext <- .check_event(delta_ext, "delta_ext")
  time_int  <- as.numeric(time_int)
  time_ext  <- as.numeric(time_ext)

  n_int <- nrow(z_int)
  n_ext <- nrow(z_ext)
  n_all <- n_int + n_ext
  p     <- ncol(z_int)

  if (ncol(z_ext) != p)
    stop("Internal and external datasets must have the same number of covariates.", call. = FALSE)

  # Stratum handling for internal data
  if (is.null(stratum_int)) {
    warning("stratum_int not provided. Treating all internal data as one stratum.", call. = FALSE)
    stratum_int <- rep(1L, n_int)
  }

  # c_index_stratum must agree with stratum_int when both are supplied
  if (!is.null(c_index_stratum) && !identical(as.vector(stratum_int), as.vector(c_index_stratum)))
    stop("Provided 'c_index_stratum' is not identical to 'stratum_int'.", call. = FALSE)

  ## 🔴 SORT INTO (STRATUM, TIME) ORDER. Added 2026-08-19; this function was the
  ## only cross-validation driver in the package that did not, and the omission
  ## made its reported loss meaningless rather than merely differently split.
  ##
  ## Two things depended on it. (1) pl_cal_theta forms risk sets with a reverse
  ## cumulative sum over CONTIGUOUS row blocks whose sizes come from
  ## table(stratum_int); table() orders by sorted level while the rows were in
  ## caller order, so the kernel was reading blocks that did not correspond to
  ## the strata it was told about, and computing a partial likelihood against
  ## the wrong risk sets. (2) get_fold does as.factor(stratum) and draws two
  ## sample() calls per stratum, so an unsorted, unencoded stratum consumed the
  ## RNG stream in a different order and produced a DIFFERENT partition from
  ## every sibling estimator -- which breaks the one-partition property the
  ## whole candidate comparison rests on.
  ##
  ## Encoding first (match against first appearance) is what makes table()'s
  ## level order agree with row order for character or non-consecutive strata:
  ## sort() would otherwise put "10" before "2". Mirrors cv.cox_indi.R:108-113.
  stratum_int <- match(as.vector(stratum_int), unique(as.vector(stratum_int)))
  ord0        <- order(stratum_int, time_int)
  z_int       <- z_int[ord0, , drop = FALSE]
  delta_int   <- delta_int[ord0]
  time_int    <- time_int[ord0]
  stratum_int <- stratum_int[ord0]
  # Identical to stratum_int by the check above, so it follows the same permutation.
  if (!is.null(c_index_stratum)) c_index_stratum <- stratum_int

  # --------------------------------------------------------------------------
  # 1. CV fold assignment on internal data (stratified by event & stratum)
  # --------------------------------------------------------------------------
  ## Pin the fold assignment. `set.seed(seed)` on its own is NOT enough: it
  ## inherits the ambient RNG *kind*, and a session left in "L'Ecuyer-CMRG" by
  ## future/future.apply returns a DIFFERENT split from the same seed, hence a
  ## different cross-validated loss. Measured 2026-08-18. The caller's RNG state
  ## is captured and restored on exit, so a parallel worker's stream is left
  ## exactly as it was found.
  if (!is.null(seed)) {
    .rs_old <- if (exists(".Random.seed", envir = globalenv()))
                 get(".Random.seed", envir = globalenv()) else NULL
    on.exit(if (!is.null(.rs_old))
              assign(".Random.seed", .rs_old, envir = globalenv()), add = TRUE)
    set.seed(seed, kind = "Mersenne-Twister")
  }
  .rng_kind <- RNGkind()[1]
  folds <- get_fold(nfolds = nfolds, delta = delta_int, stratum = stratum_int)

  # --------------------------------------------------------------------------
  # 2. Main loop over eta values
  # --------------------------------------------------------------------------
  n_eta        <- length(etas)
  results_list <- vector("list", n_eta)
  fit_beta_list  <- vector("list", n_eta)   # full-data beta matrices, one per eta
  lambda_list    <- vector("list", n_eta)   # lambda path, one per eta

  if (message) {
    cat("Cross-validation over etas sequence:\n")
    pb_eta <- utils::txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }

  for (ei in seq_along(etas)) {
    eta_i <- etas[ei]

    # ---- 2a. Full-data fit to obtain lambda path and full-data betas -------
    fit0 <- cox_indi_ridge(ties = ties, 
      z_int       = z_int,
      delta_int   = delta_int,
      time_int    = time_int,
      stratum_int = stratum_int,
      z_ext       = z_ext,
      delta_ext   = delta_ext,
      time_ext    = time_ext,
      stratum_ext = stratum_ext,
      etas        = eta_i,
      lambda      = lambda,
      nlambda     = nlambda,
      penalty.factor = 1 - 1e-4,
      standardize = standardize,
      message     = FALSE,
      ...
    )

    # cox_indi_ridge returns lists indexed by eta; eta_i is a single value here
    lambda_seq    <- fit0$lambda[[1]]
    beta_full_mat <- fit0$beta[[1]]    # p x L

    fit_beta_list[[ei]] <- beta_full_mat
    lambda_list[[ei]]   <- lambda_seq
    L <- length(lambda_seq)

    # ---- 2b. Allocate fold accumulators ------------------------------------
    if (cv.criteria == "V&VH") {
      vvh_sum <- rep(0.0, L)
    } else if (cv.criteria == "LinPred") {
      LP_oof <- matrix(NA_real_, nrow = n_int, ncol = L)
      colnames(LP_oof) <- round(lambda_seq, 6)
    } else if (cv.criteria == "CIndex_pooled") {
      numer <- rep(0.0, L)
      denom <- rep(0.0, L)
    } else {                                  # CIndex_foldaverage
      csum <- rep(0.0, L)
      cnt  <- rep(0L,  L)
    }

    # ---- 2c. Loop over folds -----------------------------------------------
    for (f in seq_len(nfolds)) {
      train_idx <- which(folds != f)
      test_idx  <- which(folds == f)

      # Fit on training internal + full external, at the shared lambda path
      fit_f <- cox_indi_ridge(ties = ties, 
        z_int       = z_int[train_idx, , drop = FALSE],
        delta_int   = delta_int[train_idx],
        time_int    = time_int[train_idx],
        stratum_int = stratum_int[train_idx],
        z_ext       = z_ext,
        delta_ext   = delta_ext,
        time_ext    = time_ext,
        stratum_ext = stratum_ext,
        etas        = eta_i,
        lambda      = lambda_seq,
        standardize = standardize,
        message     = FALSE,
        ...
      )

      beta_f <- fit_f$beta[[1]]    # p x L  (may have fewer cols if some lambdas dropped)

      # Align columns: if some lambdas were dropped during fold fit, fill with NA columns
      if (ncol(beta_f) < L) {
        lambda_f   <- fit_f$lambda[[1]]
        beta_align <- matrix(NA_real_, nrow = p, ncol = L)
        col_match  <- match(round(lambda_f, 6), round(lambda_seq, 6))
        col_match  <- col_match[!is.na(col_match)]
        beta_align[, col_match] <- beta_f[, seq_along(col_match), drop = FALSE]
        beta_f <- beta_align
      }

      # Linear predictors for all internal obs and for test obs
      LP_train <- z_int[train_idx, , drop = FALSE] %*% beta_f   # n_train x L
      LP_all   <- z_int %*% beta_f                               # n_int   x L
      LP_test  <- z_int[test_idx,  , drop = FALSE] %*% beta_f   # n_test  x L

      # Compute fold contribution
      if (cv.criteria == "V&VH") {
        n_each_train <- as.numeric(table(stratum_int[train_idx]))
        n_each_all   <- as.numeric(table(stratum_int))
        pl_all_vec <- apply(LP_all,   2, function(col)
          .pl_ties(col, delta_int, time_int, n_each_all, ties))
        pl_tr_vec  <- apply(LP_train, 2, function(col)
          .pl_ties(col, delta_int[train_idx], time_int[train_idx], n_each_train, ties))
        vvh_sum <- vvh_sum + (pl_all_vec - pl_tr_vec)

      } else if (cv.criteria == "LinPred") {
        LP_oof[test_idx, ] <- LP_test

      } else {
        # C-index criteria: compute per lambda
        stratum_test <- if (is.null(c_index_stratum)) stratum_int[test_idx] else c_index_stratum[test_idx]
        numer_vec <- denom_vec <- cstat_vec <- rep(NA_real_, L)

        for (j in seq_len(L)) {
          if (anyNA(LP_test[, j])) next
          cstat_j <- c_stat_stratcox(
            time_int[test_idx], LP_test[, j], stratum_test, delta_int[test_idx]
          )
          numer_vec[j] <- cstat_j$numer
          denom_vec[j] <- cstat_j$denom
          cstat_vec[j] <- cstat_j$c_statistic
        }

        if (cv.criteria == "CIndex_pooled") {
          numer <- numer + ifelse(is.na(numer_vec), 0, numer_vec)
          denom <- denom + ifelse(is.na(denom_vec), 0, denom_vec)
        } else {
          csum <- csum + ifelse(is.na(cstat_vec), 0, cstat_vec)
          cnt  <- cnt  + as.integer(!is.na(cstat_vec))
        }
      }
    }   # end fold loop

    # ---- 2d. Aggregate across folds for this eta ---------------------------
    if (cv.criteria == "V&VH") {
      cve_eta <- vvh_sum
    } else if (cv.criteria == "LinPred") {
      n_each_all <- as.numeric(table(stratum_int))
      Lmat    <- loss.coxkl_highdim(delta_int, LP_oof, stratum_int, total = FALSE)
      cve_eta <- colSums(Lmat)
    } else if (cv.criteria == "CIndex_pooled") {
      cve_eta <- numer / pmax(denom, .Machine$double.eps)
    } else {
      cve_eta <- csum / pmax(cnt, 1L)
    }

    results_list[[ei]] <- data.frame(
      eta    = eta_i,
      lambda = lambda_seq,
      score  = cve_eta,
      stringsAsFactors = FALSE
    )

    if (message) utils::setTxtProgressBar(pb_eta, ei)
  }   # end eta loop

  if (message) close(pb_eta)

  # --------------------------------------------------------------------------
  # 3. Identify best (eta, lambda) pair
  # --------------------------------------------------------------------------
  results_df <- do.call(rbind, results_list)
  rownames(results_df) <- NULL

  if (cv.criteria %in% c("V&VH", "LinPred")) {
    results_df$Loss  <- -2 * results_df$score / n_int
    results_df$score <- NULL
    best_per_eta <- do.call(rbind, lapply(
      split(results_df, results_df$eta),
      function(df) df[which.min(df$Loss), , drop = FALSE]
    ))
    best.idx <- which.min(best_per_eta$Loss)

  } else if (cv.criteria == "CIndex_pooled") {
    results_df$CIndex_pooled <- results_df$score
    results_df$score         <- NULL
    best_per_eta <- do.call(rbind, lapply(
      split(results_df, results_df$eta),
      function(df) df[which.max(df$CIndex_pooled), , drop = FALSE]
    ))
    best.idx <- which.max(best_per_eta$CIndex_pooled)

  } else {
    results_df$CIndex_foldaverage <- results_df$score
    results_df$score              <- NULL
    best_per_eta <- do.call(rbind, lapply(
      split(results_df, results_df$eta),
      function(df) df[which.max(df$CIndex_foldaverage), , drop = FALSE]
    ))
    best.idx <- which.max(best_per_eta$CIndex_foldaverage)
  }
  rownames(best_per_eta) <- NULL

  # --------------------------------------------------------------------------
  # 4. Extract best-lambda beta for each eta (from full-data fits)
  # --------------------------------------------------------------------------
  ## An eta whose every lambda gave a non-finite loss (large eta on the lasso
  ## path, seen at eta = 200) has no row in best_per_eta: `split` dropped it.
  ## The old sapply then indexed best_per_eta by position, matched no lambda,
  ## returned a p x 0 matrix and made sapply return a list, which failed at
  ## colnames<- ("attempt to set 'colnames' on an object with less than two
  ## dimensions") on every individual-level fit with such an eta. Rows are
  ## matched by eta value; an eta with no finite loss gets an NA column and is
  ## never selected (2026-09-14).
  beta_best_mat <- matrix(NA_real_, nrow = nrow(fit_beta_list[[1]]),
                          ncol = length(etas))
  rownames(beta_best_mat) <- rownames(fit_beta_list[[1]])
  for (i in seq_along(etas)) {
    j <- match(etas[i], best_per_eta$eta)
    if (is.na(j)) next
    bm  <- fit_beta_list[[i]]
    lam <- lambda_list[[i]]
    idx <- which(abs(lam - best_per_eta$lambda[j]) < 1e-12)
    if (length(idx) != 1) idx <- which.min(abs(lam - best_per_eta$lambda[j]))
    beta_best_mat[, i] <- bm[, idx]
  }
  colnames(beta_best_mat) <- etas
  best_col <- match(best_per_eta$eta[best.idx], etas)

  best_res <- list(
    best_eta    = best_per_eta$eta[best.idx],
    best_lambda = best_per_eta$lambda[best.idx],
    best_beta   = beta_best_mat[, best_col],
    best_value  = .best_value(best_per_eta, best.idx),
    criteria    = cv.criteria
  )

  # --------------------------------------------------------------------------
  # 5. Return
  # --------------------------------------------------------------------------
  structure(
    list(
      best                         = best_res,
      integrated_stat.full_results = results_df,
      integrated_stat.best_per_eta = best_per_eta,
      integrated_stat.betahat_best = beta_best_mat,
      criteria                     = cv.criteria,
      nfolds                       = nfolds,
      ## the split actually used, so a replay can be checked rather than
      ## trusted. Assigned on the internally sorted data, not the caller's
      ## row order. `get_fold` is not exported, so this is the only route to it.
      folds                       = folds,
      seed                       = if (is.null(seed)) NA_integer_ else as.integer(seed),
      rng_kind                       = .rng_kind
    ),
    class = "cv.cox_indi_ridge"
  )
}
