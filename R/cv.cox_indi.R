#' Cross-Validated cox_indi to Tune etas
#'
#' Performs K-fold cross-validation over candidate \code{etas}. Internal data are split into folds.
#' For each fold, the model is trained on the internal training split plus the full external dataset,
#' then evaluated on the held-out internal fold.
#'
#' @param z_int,delta_int,time_int,stratum_int Internal data.
#' @param z_ext,delta_ext,time_ext,stratum_ext External data (always fully included in training).
#' @param etas Numeric vector of candidate eta values (must be provided).
#' @param nfolds Number of folds (default 5).
#' @param cv.criteria Performance criterion.
#' @param c_index_stratum Optional stratum vector used for C-index evaluation on internal data.
#' @param max_iter,tol Passed to \code{cox_indi}.
#' @param message Logical; print progress (default FALSE).
#' @param seed Optional seed for reproducible folds.
#'
#' @return An object of class \code{"cv.cox_indi"} with components:
#' \itemize{
#' \item \code{internal_stat}: data.frame of CV stats by eta
#' \item \code{beta_full}: matrix of full-data estimates (p x length(etas))
#' \item \code{best}: list with \code{best_eta}, \code{best_beta}, \code{criteria}
#' }
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
#' ## Generate candidate eta values
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 20)
#'
#' ## Cross-validated tuning of eta
#' cv_fit <- cv.cox_indi(
#'   z_int = z_int,
#'   delta_int = delta_int,
#'   time_int = time_int,
#'   stratum_int = stratum_int,
#'   z_ext = z_ext,
#'   delta_ext = delta_ext,
#'   time_ext = time_ext,
#'   stratum_ext = stratum_ext,
#'   etas = eta_list,
#'   nfolds = 5,
#'   cv.criteria = "CIndex_pooled"
#' )
#' }
#' @export

#' @importFrom utils txtProgressBar setTxtProgressBar
#' @export
cv.cox_indi <- function(z_int, delta_int, time_int, stratum_int = NULL,
                        z_ext, delta_ext, time_ext, stratum_ext = NULL,
                        etas,
                        nfolds = 5,
                        cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                        c_index_stratum = NULL,
                        max_iter = 100, tol = 1.0e-7,
                        message = FALSE,
                        seed = NULL) {

  cv.criteria <- match.arg(cv.criteria, choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas <- sort(as.numeric(etas))
  if (any(!is.finite(etas)) || any(etas < 0)) stop("All etas must be finite and nonnegative.", call. = FALSE)

  z_int <- as.matrix(z_int)
  z_ext <- as.matrix(z_ext)
  delta_int <- as.numeric(delta_int)
  delta_ext <- as.numeric(delta_ext)
  time_int <- as.numeric(time_int)
  time_ext <- as.numeric(time_ext)

  n_int <- nrow(z_int)
  p <- ncol(z_int)
  if (ncol(z_ext) != p) stop("Internal and external datasets must have the same number of covariates (columns).", call. = FALSE)

  if (is.null(stratum_int)) stratum_int <- rep(1, n_int)
  stratum_int <- as.vector(stratum_int)

  if (!is.null(c_index_stratum) && length(c_index_stratum) != n_int) {
    stop("c_index_stratum must have the same length as internal data.", call. = FALSE)
  }

  ord0 <- order(match(stratum_int, unique(stratum_int)), time_int)
  z_int <- z_int[ord0, , drop = FALSE]
  delta_int <- delta_int[ord0]
  time_int <- time_int[ord0]
  stratum_int <- stratum_int[ord0]
  if (!is.null(c_index_stratum)) c_index_stratum <- as.vector(c_index_stratum)[ord0]

  n_eta <- length(etas)

  fit_full_path <- cox_indi(
    z_int = z_int, delta_int = delta_int, time_int = time_int, stratum_int = stratum_int,
    z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext, stratum_ext = stratum_ext,
    etas = etas, max_iter = max_iter, tol = tol, message = FALSE
  )
  beta_full <- fit_full_path$beta

  if (!is.null(seed)) set.seed(seed)
  stratum_enc_full <- match(stratum_int, unique(stratum_int))
  folds <- get_fold(nfolds = nfolds, delta = delta_int, stratum = stratum_enc_full)

  result_mat <- matrix(NA_real_, nrow = nfolds, ncol = n_eta)
  if (cv.criteria == "LinPred") {
    cv_all_linpred <- matrix(NA_real_, nrow = n_int, ncol = n_eta)
  } else if (cv.criteria == "CIndex_pooled") {
    cv_pooled_cindex_array <- array(0, dim = c(nfolds, n_eta, 2))
  }

  n_each_stratum_full <- as.numeric(table(stratum_enc_full))

  for (f in seq_len(nfolds)) {
    if (message) message(sprintf("CV fold %d/%d starts...", f, nfolds))

    train_idx <- which(folds != f)
    test_idx  <- which(folds == f)

    z_train <- z_int[train_idx, , drop = FALSE]
    delta_train <- delta_int[train_idx]
    time_train <- time_int[train_idx]
    stratum_train <- stratum_int[train_idx]
    stratum_enc_train <- match(stratum_train, unique(stratum_train))
    n_each_stratum_train <- as.numeric(table(stratum_enc_train))

    z_test <- z_int[test_idx, , drop = FALSE]
    delta_test <- delta_int[test_idx]
    time_test <- time_int[test_idx]

    if (is.null(c_index_stratum)) {
      stratum_test_for_c <- stratum_int[test_idx]
    } else {
      stratum_test_for_c <- c_index_stratum[test_idx]
    }
    stratum_test_for_c <- match(stratum_test_for_c, unique(stratum_test_for_c))

    fit_fold_path <- cox_indi(
      z_int = z_train, delta_int = delta_train, time_int = time_train, stratum_int = stratum_train,
      z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext, stratum_ext = stratum_ext,
      etas = etas, max_iter = max_iter, tol = tol, message = FALSE
    )

    beta_path <- fit_fold_path$beta

    if (message) {
      pb <- utils::txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
    }

    for (i in seq_along(etas)) {
      beta_hat <- as.numeric(beta_path[, i])
      LP_test <- as.vector(z_test %*% beta_hat)

      if (cv.criteria == "V&VH") {
        LP_train <- as.vector(z_train %*% beta_hat)
        LP_full_internal <- as.vector(z_int %*% beta_hat)
        result_mat[f, i] <-
          pl_cal_theta(LP_full_internal, delta_int, n_each_stratum_full) -
          pl_cal_theta(LP_train,         delta_train, n_each_stratum_train)

      } else if (cv.criteria == "LinPred") {
        cv_all_linpred[test_idx, i] <- LP_test

      } else if (cv.criteria == "CIndex_pooled") {
        cstat <- c_stat_stratcox(time_test, LP_test, stratum_test_for_c, delta_test)
        cv_pooled_cindex_array[f, i, ] <- c(cstat$numer, cstat$denom)

      } else if (cv.criteria == "CIndex_foldaverage") {
        result_mat[f, i] <- c_stat_stratcox(time_test, LP_test, stratum_test_for_c, delta_test)$c_statistic
      }

      if (message) utils::setTxtProgressBar(pb, i)
    }

    if (message) close(pb)
  }

  if (cv.criteria == "V&VH") {
    result_vec <- colSums(result_mat, na.rm = TRUE)
  } else if (cv.criteria == "LinPred") {
    result_vec <- apply(cv_all_linpred, 2, function(lp) {
      pl_cal_theta(lp, delta_int, as.numeric(table(stratum_enc_full)))
    })
  } else if (cv.criteria == "CIndex_foldaverage") {
    result_vec <- colMeans(result_mat, na.rm = TRUE)
  } else {
    numer <- apply(cv_pooled_cindex_array[, , 1], 2, sum, na.rm = TRUE)
    denom <- apply(cv_pooled_cindex_array[, , 2], 2, sum, na.rm = TRUE)
    result_vec <- numer / denom
  }

  results <- data.frame(eta = etas)
  n <- n_int

  if (cv.criteria == "V&VH") {
    results$VVH_Loss <- -2 * result_vec / n
    best_eta.idx <- which.min(results$VVH_Loss)
  } else if (cv.criteria == "LinPred") {
    results$LinPred_Loss <- -2 * result_vec / n
    best_eta.idx <- which.min(results$LinPred_Loss)
  } else if (cv.criteria == "CIndex_pooled") {
    results$CIndex_pooled <- result_vec
    best_eta.idx <- which.max(results$CIndex_pooled)
  } else {
    results$CIndex_foldaverage <- result_vec
    best_eta.idx <- which.max(results$CIndex_foldaverage)
  }

  best_res <- list(
    best_eta = etas[best_eta.idx],
    best_beta = beta_full[, best_eta.idx],
    criteria = cv.criteria
  )

  structure(
    list(
      internal_stat = results,
      beta_full = beta_full,
      best = best_res,
      criteria = cv.criteria,
      nfolds = nfolds
    ),
    class = "cv.cox_indi"
  )
}

