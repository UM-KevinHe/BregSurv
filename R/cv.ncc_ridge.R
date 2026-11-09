## Shared cross-validation for the two matched-set ridge members. Folds are whole
## matched sets (get_fold_cc, deterministic); the loss is the pooled held-out
## conditional log-likelihood per row, as in cv.ncckl_enet. `fit_fun(idx, eta, lambda)`
## fits on rows `idx` and returns an object with `$lambda` and `$beta` (p x L).
.cv_ncc_ridge <- function(y, z, stratum, etas, fit_fun, nfolds, cv.criteria, seed,
                          message, cls) {
  n <- nrow(z)
  events_per_stratum <- tapply(y, stratum, function(x) sum(x == 1))
  if (any(is.na(events_per_stratum)) || any(events_per_stratum != 1))
    stop(cls, " assumes a 1:m matched setting: each stratum must contain exactly one case.",
         call. = FALSE)
  if (!is.null(seed)) {
    .rs_old <- if (exists(".Random.seed", envir = globalenv()))
                 get(".Random.seed", envir = globalenv()) else NULL
    on.exit(if (!is.null(.rs_old))
              assign(".Random.seed", .rs_old, envir = globalenv()), add = TRUE)
    set.seed(seed, kind = "Mersenne-Twister")
  }
  .rng_kind <- RNGkind()[1]
  folds <- get_fold_cc(nfolds = nfolds, delta = y, stratum = stratum)

  n_eta <- length(etas)
  results_list <- beta_full_list <- lambda_list <- vector("list", n_eta)
  if (message) pb <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  for (i in seq_len(n_eta)) {
    full <- fit_fun(seq_len(n), etas[i], NULL)
    lam <- as.vector(full$lambda); L <- length(lam)
    beta_full_list[[i]] <- full$beta; lambda_list[[i]] <- lam
    if (cv.criteria == "loss") { loss_sum <- numeric(L); loss_n <- numeric(L) }
    else cv_lp <- matrix(NA_real_, n, L)
    for (f in seq_len(nfolds)) {
      tr <- which(folds != f); te <- which(folds == f)
      bf <- fit_fun(tr, etas[i], lam)$beta
      lp <- z[te, , drop = FALSE] %*% bf
      if (cv.criteria == "loss") {
        st <- droplevels(stratum[te])
        for (j in seq_len(L)) {
          loss_sum[j] <- loss_sum[j] - cc_loglik(y = y[te], lp = lp[, j], stratum = st)
          loss_n[j] <- loss_n[j] + length(te)
        }
      } else cv_lp[te, ] <- lp
    }
    score <- if (cv.criteria == "loss") loss_sum / pmax(loss_n, 1)
             else if (cv.criteria %in% c("AUC", "CIndex"))
               apply(cv_lp, 2, function(l) cc_auc(y = y, lp = l, stratum = stratum))
             else apply(cv_lp, 2, function(l) cc_brier(y = y, lp = l, stratum = stratum))
    results_list[[i]] <- data.frame(eta = etas[i], lambda = lam, score = score)
    if (message) setTxtProgressBar(pb, i)
  }
  if (message) close(pb)
  results_df <- do.call(rbind, results_list)
  lower <- cv.criteria %in% c("loss", "Brier")
  pick <- function(v) if (lower) which.min(v) else which.max(v)
  best_per_eta <- do.call(rbind, lapply(split(results_df, results_df$eta),
                                        function(df) df[pick(df$score), , drop = FALSE]))
  rownames(best_per_eta) <- NULL
  best.idx <- pick(best_per_eta$score)
  beta_best_mat <- matrix(NA_real_, nrow(beta_full_list[[1]]), n_eta,
                          dimnames = list(rownames(beta_full_list[[1]]), etas))
  for (i in seq_len(n_eta)) {
    j <- match(etas[i], best_per_eta$eta); if (is.na(j)) next
    k <- which.min(abs(lambda_list[[i]] - best_per_eta$lambda[j]))
    beta_best_mat[, i] <- beta_full_list[[i]][, k]
  }
  best_col <- match(best_per_eta$eta[best.idx], etas)
  structure(list(
    best = list(best_eta = best_per_eta$eta[best.idx],
                best_lambda = best_per_eta$lambda[best.idx],
                best_beta = beta_best_mat[, best_col],
                best_value = .best_value(best_per_eta, best.idx),
                criteria = cv.criteria),
    integrated_stat.full_results = results_df,
    integrated_stat.best_per_eta = best_per_eta,
    integrated_stat.betahat_best = beta_best_mat,
    criteria = cv.criteria, nfolds = nfolds,
    ## get_fold_cc assigns whole matched sets on the caller's row order and draws no
    ## random number, so `seed` is provenance only
    folds = folds, seed = if (is.null(seed)) NA_integer_ else as.integer(seed),
    rng_kind = .rng_kind
  ), class = cls)
}

#' Cross-Validation for \code{ncckl_ridge}
#'
#' @description Selects \eqn{\eta} and the ridge penalty of \code{\link{ncckl_ridge}}
#' by cross-validation over whole matched sets (\code{get_fold_cc}).
#' @param y,z,stratum,RS,beta As in \code{\link{ncckl_ridge}}.
#' @param etas Candidate integration weights.
#' @param lambda Optional common penalty path; \code{NULL} uses the path of the full-data
#'   fit at each \eqn{\eta}.
#' @param nlambda Path length. Default 100.
#' @param nfolds Number of folds. Default 5.
#' @param cv.criteria \code{"loss"} (pooled held-out conditional log-likelihood per row,
#'   the default), \code{"AUC"}, \code{"CIndex"} or \code{"Brier"}.
#' @param standardize Passed to \code{\link{ncckl_ridge}}.
#' @param message Logical; progress bar.
#' @param seed Recorded for provenance (the folds use no random numbers).
#' @return An object of class \code{"cv.ncckl_ridge"} with \code{best},
#'   \code{integrated_stat.full_results}, \code{integrated_stat.best_per_eta},
#'   \code{integrated_stat.betahat_best}, \code{criteria}, \code{nfolds}, \code{folds},
#'   \code{seed} and \code{rng_kind}.
#' @examples
#' \dontrun{
#' data(ExampleData_cc_highdim)
#' d <- ExampleData_cc_highdim$train
#' cvfit <- cv.ncckl_ridge(y = d$y, z = d$z, stratum = d$stratum,
#'                         beta = ExampleData_cc_highdim$beta_external, etas = c(0, 1, 5))
#' }
#' @export
cv.ncckl_ridge <- function(y, z, stratum, RS = NULL, beta = NULL, etas,
                           lambda = NULL, nlambda = 100, nfolds = 5,
                           cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
                           standardize = TRUE, message = FALSE, seed = NULL) {
  cv.criteria <- match.arg(cv.criteria)
  y <- .check_event(y, "y"); z <- as.matrix(z)
  if (missing(stratum) || is.null(stratum))
    stop("stratum must be provided for cv.ncckl_ridge.", call. = FALSE)
  stratum <- as.factor(stratum)
  if (is.null(RS) && is.null(beta))
    stop("Either RS or beta must be provided for cv.ncckl_ridge.", call. = FALSE)
  if (!is.null(RS)) RS <- as.matrix(RS)
  if (!is.null(beta)) beta <- align_beta(z, beta)
  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  check_etas(etas); etas <- sort(as.numeric(etas))
  fit_fun <- function(idx, eta, lam) {
    ncckl_ridge(y = y[idx], z = z[idx, , drop = FALSE], stratum = droplevels(stratum[idx]),
                RS = if (is.null(RS)) NULL else RS[idx, , drop = FALSE],
                beta = if (is.null(RS)) beta else NULL, eta = eta,
                lambda = if (is.null(lam)) lambda else lam,
                nlambda = nlambda, penalty.factor = 1 - 1e-4, standardize = standardize)
  }
  .cv_ncc_ridge(y, z, stratum, etas, fit_fun, nfolds, cv.criteria, seed, message,
                "cv.ncckl_ridge")
}

#' Cross-Validation for \code{ncc_MDTL_ridge}
#'
#' @description Selects \eqn{\eta} and the ridge penalty of \code{\link{ncc_MDTL_ridge}}
#' by cross-validation over whole matched sets.
#' @param y,z,stratum,beta,Q As in \code{\link{ncc_MDTL_ridge}}.
#' @param etas,lambda,nlambda,nfolds,cv.criteria,standardize,message,seed As in
#'   \code{\link{cv.ncckl_ridge}}.
#' @return An object of class \code{"cv.ncc_MDTL_ridge"}, with the components of
#'   \code{\link{cv.ncckl_ridge}}.
#' @examples
#' \dontrun{
#' data(ExampleData_cc_highdim)
#' d <- ExampleData_cc_highdim$train
#' cvfit <- cv.ncc_MDTL_ridge(y = d$y, z = d$z, stratum = d$stratum,
#'                            beta = ExampleData_cc_highdim$beta_external, etas = c(0, 1, 5))
#' }
#' @export
cv.ncc_MDTL_ridge <- function(y, z, stratum, beta, Q = NULL, etas,
                              lambda = NULL, nlambda = 100, nfolds = 5,
                              cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
                              standardize = TRUE, message = FALSE, seed = NULL) {
  cv.criteria <- match.arg(cv.criteria)
  y <- .check_event(y, "y"); z <- as.matrix(z)
  if (missing(stratum) || is.null(stratum))
    stop("stratum must be provided for cv.ncc_MDTL_ridge.", call. = FALSE)
  stratum <- as.factor(stratum)
  ## aligned once; a manufactured identity keeps its mark through the second alignment
  aligned <- align_beta_Q(z, beta, Q); beta <- aligned$beta; Q <- aligned$Q
  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  check_etas(etas); etas <- sort(as.numeric(etas))
  fit_fun <- function(idx, eta, lam) {
    ncc_MDTL_ridge(y = y[idx], z = z[idx, , drop = FALSE], stratum = droplevels(stratum[idx]),
                   beta = beta, Q = Q, eta = eta, lambda = if (is.null(lam)) lambda else lam,
                   nlambda = nlambda, penalty.factor = 1 - 1e-4, standardize = standardize)
  }
  .cv_ncc_ridge(y, z, stratum, etas, fit_fun, nfolds, cv.criteria, seed, message,
                "cv.ncc_MDTL_ridge")
}
