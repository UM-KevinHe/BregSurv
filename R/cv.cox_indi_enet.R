#' Cross-Validation for Cox Model Integrated with External Individual-level Data and Elastic Net Penalty
#'
#' @description
#' Performs k-fold cross-validation on the \strong{internal} dataset to jointly tune
#' the external weight \code{eta} and the regularisation parameter \code{lambda} for
#' \code{\link{cox_indi_enet}}.
#'
#' @details
#' Cross-validation is applied exclusively to the internal cohort; the external dataset
#' is used in full during every training fold (weighted by \code{eta}), exactly mirroring
#' how \code{\link{cox_indi_enet}} stacks the two cohorts with separate risk sets.
#'
#' The procedure:
#' \enumerate{
#'   \item For each candidate \code{eta}, fit \code{\link{cox_indi_enet}} on the full
#'         internal + external data to obtain the lambda path and the full-data coefficient
#'         matrices.
#'   \item Split the \emph{internal} observations into \code{nfolds} folds (stratified
#'         by event indicator and, optionally, stratum).
#'   \item For each fold and each \code{eta}, refit \code{\link{cox_indi_enet}} on the
#'         training portion of the internal data (+ full external data) at the common
#'         lambda sequence, then evaluate the chosen criterion on the held-out internal
#'         test fold.
#'   \item Aggregate across folds and select the (\code{eta}, \code{lambda}) pair that
#'         optimises the criterion.
#' }
#'
#' Available cross-validation criteria:
#' \itemize{
#'   \item \code{"V&VH"} (default): Verweij & Van Houwelingen partial likelihood loss
#'         (lower is better).
#'   \item \code{"LinPred"}: Cross-validated partial likelihood evaluated at the
#'         out-of-fold linear predictors (lower is better).
#'   \item \code{"CIndex_pooled"}: Harrell's C-index computed by pooling numerators and
#'         denominators across folds (higher is better).
#'   \item \code{"CIndex_foldaverage"}: Harrell's C-index computed within each fold and
#'         averaged (higher is better).
#' }
#'
#' @param z_int Numeric matrix of covariates for the internal dataset
#'   (\eqn{n_{\text{int}} \times p}).
#' @param delta_int Numeric vector of event indicators for the internal dataset
#'   (1 = event, 0 = censored).
#' @param time_int Numeric vector of survival times for the internal dataset.
#' @param stratum_int Optional stratum identifiers for the internal dataset.
#'   Default \code{NULL} assigns all internal observations to a single stratum.
#' @param z_ext Numeric matrix of covariates for the external dataset
#'   (\eqn{n_{\text{ext}} \times p}). Must have the same number of columns as \code{z_int}.
#' @param delta_ext Numeric vector of event indicators for the external dataset
#'   (1 = event, 0 = censored).
#' @param time_ext Numeric vector of survival times for the external dataset.
#' @param stratum_ext Optional stratum identifiers for the external dataset.
#'   Default \code{NULL} assigns all external observations to a single stratum.
#' @param etas Numeric vector of nonnegative candidate external weights.
#'   \code{eta = 0} corresponds to an internal-only penalised fit.
#'   The vector is sorted internally in ascending order.
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 < \alpha \le 1}.
#'   \code{alpha = 1} is the lasso penalty, and \code{alpha} close to 0 approaches ridge.
#'   Defaults to 1.
#' @param lambda Optional numeric vector of penalty parameters shared across all
#'   \code{eta} values and folds. If \code{NULL}, the lambda path is derived from
#'   the full-data fit at each \code{eta}.
#' @param nlambda Integer. Number of lambda values to generate per \code{eta} when
#'   \code{lambda} is \code{NULL}. Default is 100.
#' @param lambda.min.ratio Numeric. Ratio of the smallest to the largest lambda.
#'   Default is 0.05 if \eqn{n_{\text{all}} < p}, and 1e-3 otherwise.
#' @param nfolds Integer. Number of cross-validation folds (applied to internal data only).
#'   Default is 5.
#' @param cv.criteria Character string specifying the cross-validation criterion.
#'   One of \code{"V&VH"} (default), \code{"LinPred"}, \code{"CIndex_pooled"}, or
#'   \code{"CIndex_foldaverage"}.
#' @param c_index_stratum Optional stratum vector for the internal dataset.
#'   Only needed when \code{cv.criteria} is \code{"CIndex_pooled"} or
#'   \code{"CIndex_foldaverage"} and a stratified C-index is desired while the
#'   fitted model uses a different (or no) stratification. Default \code{NULL}.
#' @param message Logical. If \code{TRUE}, shows a progress bar over the \code{etas} loop.
#'   Default \code{FALSE}.
#' @param seed Optional integer. Random seed for reproducible fold assignment.
#' @param ... Additional arguments passed to the underlying fitting function
#'   \code{\link{cox_indi_enet}}.
#'
#' @return An object of class \code{"cv.cox_indi_enet"}. A list containing:
#' \describe{
#'   \item{\code{best}}{A list with the optimal tuning parameters:
#'     \itemize{
#'       \item \code{best_eta}: The selected \eqn{\eta} value.
#'       \item \code{best_lambda}: The selected \eqn{\lambda} value.
#'       \item \code{best_beta}: Coefficient vector at the optimal (\code{eta}, \code{lambda}).
#'       \item \code{criteria}: The criterion used for selection.
#'     }
#'   }
#'   \item{\code{integrated_stat.full_results}}{A \code{data.frame} with the cross-validation
#'     score for every (\code{eta}, \code{lambda}) combination evaluated.}
#'   \item{\code{integrated_stat.best_per_eta}}{A \code{data.frame} with the best
#'     \code{lambda} and corresponding score for each candidate \code{eta}.}
#'   \item{\code{integrated_stat.betahat_best}}{A coefficient matrix
#'     (\eqn{p \times n_{\text{eta}}}) where each column is the optimal-\code{lambda}
#'     coefficient vector for a given \code{eta}, estimated on the full data.}
#'   \item{\code{criteria}}{The selection criterion used.}
#'   \item{\code{alpha}}{The Elastic Net mixing parameter used.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
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
#' eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 3)
#'
#' ## Run cross-validation
#' cv_fit.cox_indi_enet <- cv.cox_indi_enet(
#'   z_int       = z_int,
#'   delta_int   = delta_int,
#'   time_int    = time_int,
#'   stratum_int = stratum_int,
#'   z_ext       = z_ext,
#'   delta_ext   = delta_ext,
#'   time_ext    = time_ext,
#'   stratum_ext = stratum_ext,
#'   etas        = eta_list,
#'   alpha       = 1,
#'   nfolds      = 5,
#'   cv.criteria = "CIndex_pooled",
#'   message = TRUE
#' )
#' }
#'
#' @importFrom utils txtProgressBar setTxtProgressBar
#' @export
cv.cox_indi_enet <- function(z_int, delta_int, time_int, stratum_int = NULL,
                             z_ext, delta_ext, time_ext, stratum_ext = NULL,
                             etas, alpha = 1.0,
                             lambda = NULL, nlambda = 100,
                             lambda.min.ratio = NULL,
                             nfolds = 5,
                             cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                             c_index_stratum = NULL,
                             message = FALSE, seed = NULL, ...) {

  # --------------------------------------------------------------------------
  # 0. Input checks and coercions
  # --------------------------------------------------------------------------
  cv.criteria <- match.arg(cv.criteria,
                           choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas <- sort(as.numeric(etas))
  check_etas(etas)

  if (alpha <= 0 || alpha > 1)
    stop("alpha must be in (0, 1].", call. = FALSE)

  z_int     <- as.matrix(z_int)
  z_ext     <- as.matrix(z_ext)
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

  if (is.null(lambda.min.ratio))
    lambda.min.ratio <- ifelse(n_all < p, 0.05, 1e-03)

  # Stratum handling for internal data
  if (is.null(stratum_int)) {
    warning("stratum_int not provided. Treating all internal data as one stratum.", call. = FALSE)
    stratum_int <- rep(1L, n_int)
  }

  # c_index_stratum must agree with stratum_int when both are supplied
  if (!is.null(c_index_stratum) && !identical(as.vector(stratum_int), as.vector(c_index_stratum)))
    stop("Provided 'c_index_stratum' is not identical to 'stratum_int'.", call. = FALSE)

  # --------------------------------------------------------------------------
  # 1. CV fold assignment on internal data (stratified by event & stratum)
  # --------------------------------------------------------------------------
  if (!is.null(seed)) set.seed(seed)
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
    fit0 <- cox_indi_enet(
      z_int       = z_int,
      delta_int   = delta_int,
      time_int    = time_int,
      stratum_int = stratum_int,
      z_ext       = z_ext,
      delta_ext   = delta_ext,
      time_ext    = time_ext,
      stratum_ext = stratum_ext,
      etas        = eta_i,
      alpha       = alpha,
      lambda      = lambda,
      nlambda     = nlambda,
      lambda.min.ratio = lambda.min.ratio,
      message     = FALSE,
      ...
    )

    # cox_indi_enet returns lists indexed by eta; eta_i is a single value here
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
      fit_f <- cox_indi_enet(
        z_int       = z_int[train_idx, , drop = FALSE],
        delta_int   = delta_int[train_idx],
        time_int    = time_int[train_idx],
        stratum_int = stratum_int[train_idx],
        z_ext       = z_ext,
        delta_ext   = delta_ext,
        time_ext    = time_ext,
        stratum_ext = stratum_ext,
        etas        = eta_i,
        alpha       = alpha,
        lambda      = lambda_seq,
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
          pl_cal_theta(col, delta_int, n_each_all))
        pl_tr_vec  <- apply(LP_train, 2, function(col)
          pl_cal_theta(col, delta_int[train_idx], n_each_train))
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
  beta_best_mat <- sapply(seq_along(etas), function(i) {
    bm  <- fit_beta_list[[i]]
    lam <- lambda_list[[i]]
    idx <- which(abs(lam - best_per_eta$lambda[i]) < 1e-12)
    if (length(idx) != 1) idx <- which.min(abs(lam - best_per_eta$lambda[i]))
    bm[, idx]
  })
  colnames(beta_best_mat) <- etas

  best_res <- list(
    best_eta    = best_per_eta$eta[best.idx],
    best_lambda = best_per_eta$lambda[best.idx],
    best_beta   = beta_best_mat[, best.idx],
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
      alpha                        = alpha,
      nfolds                       = nfolds
    ),
    class = "cv.cox_indi_enet"
  )
}
