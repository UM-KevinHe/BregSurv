#' Cross-Validated CLR with Individual-Level External Data
#'
#' @description
#' Performs K-fold cross-validation (CV) to select the integration parameter
#' \code{eta} for Conditional Logistic Regression with individual-level external
#' data integration, implemented via \code{\link{ncc_indi}}.
#'
#' This function is designed for 1:m matched case-control settings where each
#' stratum (matched set) contains exactly one case and \eqn{m} controls.
#'
#' @details
#' Cross-validation is performed at the stratum level on the \emph{internal} dataset:
#' each matched set is treated as an indivisible unit and assigned to a single fold
#' using \code{\link{get_fold_cc}}. The external dataset is used in full during every
#' training fold.
#'
#' The \code{cv.criteria} argument controls the CV performance metric:
#' \itemize{
#'   \item \code{"loss"}: Average negative conditional log-likelihood on held-out strata.
#'   \item \code{"AUC"}: Matched-set AUC based on within-stratum comparisons.
#'   \item \code{"CIndex"}: Alias for \code{"AUC"} in the 1:m matched setting.
#'   \item \code{"Brier"}: Conditional Brier score based on within-stratum softmax probabilities.
#' }
#'
#' @param y_int Numeric vector of binary outcomes for the internal dataset (0 = control, 1 = case).
#' @param z_int Numeric matrix of covariates for the internal dataset.
#' @param stratum_int Numeric or factor vector defining the internal matched sets. \strong{Required}.
#' @param y_ext Numeric vector of binary outcomes for the external dataset (0 = control, 1 = case).
#' @param z_ext Numeric matrix of covariates for the external dataset.
#' @param stratum_ext Numeric or factor vector defining the external matched sets. \strong{Required}.
#' @param etas Numeric vector of candidate tuning values for \eqn{\eta}. \strong{Required}.
#' @param nfolds Number of cross-validation folds. Default \code{5}.
#' @param cv.criteria Character string specifying the CV performance criterion.
#'   One of \code{"loss"} (default), \code{"AUC"}, \code{"CIndex"}, or \code{"Brier"}.
#' @param max_iter Maximum number of Newton-Raphson iterations passed to \code{\link{ncc_indi}}.
#'   Default \code{100}.
#' @param tol Convergence tolerance passed to \code{\link{ncc_indi}}. Default \code{1e-7}.
#' @param message Logical. If \code{TRUE}, prints progress messages. Default \code{FALSE}.
#' @param seed Optional integer seed for reproducible fold assignment. Default \code{NULL}.
#'
#' @return A list of class \code{"cv.ncc_indi"} containing:
#' \describe{
#'   \item{\code{internal_stat}}{A \code{data.frame} with one row per \code{eta} and the
#'     CV metric for the chosen \code{cv.criteria}.}
#'   \item{\code{beta_full}}{Matrix of coefficients from the full-data fit
#'     (columns correspond to \code{etas}).}
#'   \item{\code{best}}{A list with \code{best_eta}, \code{best_beta}, and \code{criteria}.}
#'   \item{\code{criteria}}{The criterion used for selection.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @seealso \code{\link{ncc_indi}}, \code{\link{cv.ncckl}}
#' @export
cv.ncc_indi <- function(y_int, z_int, stratum_int,
                           y_ext, z_ext, stratum_ext,
                           etas = NULL,
                           nfolds = 5,
                           cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
                           max_iter = 100, tol = 1.0e-7,
                           message = FALSE,
                           seed = NULL) {

  cv.criteria <- match.arg(cv.criteria, choices = c("loss", "AUC", "CIndex", "Brier"))

  y_int <- as.numeric(y_int)
  z_int <- as.matrix(z_int)
  y_ext <- as.numeric(y_ext)
  z_ext <- as.matrix(z_ext)

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas   <- sort(as.numeric(etas))
  n_eta  <- length(etas)

  if (missing(stratum_int) || is.null(stratum_int)) {
    stop("stratum_int must be provided for cv.ncc_indi.", call. = FALSE)
  }
  if (missing(stratum_ext) || is.null(stratum_ext)) {
    stop("stratum_ext must be provided for cv.ncc_indi.", call. = FALSE)
  }
  stratum_int <- as.factor(stratum_int)

  events_per_stratum <- tapply(y_int, stratum_int, function(x) sum(x == 1))
  if (any(is.na(events_per_stratum)) || any(events_per_stratum != 1)) {
    stop(
      "cv.ncc_indi assumes a 1:m matched setting: each stratum in the internal ",
      "dataset must contain exactly one case (sum(y==1) == 1 per stratum).",
      call. = FALSE
    )
  }

  n <- length(y_int)

  full_fit <- ncc_indi(
    y_int       = y_int,
    z_int       = z_int,
    stratum_int = stratum_int,
    y_ext       = y_ext,
    z_ext       = z_ext,
    stratum_ext = stratum_ext,
    etas        = etas,
    max_iter    = max_iter,
    tol         = tol,
    message     = FALSE
  )
  beta_full <- full_fit$beta

  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold_cc(nfolds = nfolds, delta = y_int, stratum = stratum_int)
  if (length(folds) != n) {
    stop("get_fold_cc must return a fold assignment of length equal to length(y_int).", call. = FALSE)
  }

  result_mat <- matrix(NA_real_, nrow = nfolds, ncol = n_eta)
  if (cv.criteria %in% c("AUC", "CIndex", "Brier")) {
    cv_all_lp <- matrix(NA_real_, nrow = n, ncol = n_eta)
  }

  for (f in seq_len(nfolds)) {
    if (message) message(sprintf("CV fold %d/%d starts...", f, nfolds))

    test_idx  <- which(folds == f)
    train_idx <- which(folds != f)

    y_train       <- y_int[train_idx]
    z_train       <- z_int[train_idx, , drop = FALSE]
    stratum_train <- droplevels(stratum_int[train_idx])

    y_test       <- y_int[test_idx]
    z_test       <- z_int[test_idx, , drop = FALSE]
    stratum_test <- droplevels(stratum_int[test_idx])

    ev_train <- tapply(y_train, stratum_train, function(x) sum(x == 1))
    ev_test  <- tapply(y_test,  stratum_test,  function(x) sum(x == 1))
    if (any(is.na(ev_train)) || any(ev_train != 1) ||
        any(is.na(ev_test))  || any(ev_test  != 1)) {
      stop(
        "Each training and test fold must preserve the 1:m matched structure ",
        "(exactly one case per stratum).",
        call. = FALSE
      )
    }

    fold_fit <- ncc_indi(
      y_int       = y_train,
      z_int       = z_train,
      stratum_int = stratum_train,
      y_ext       = y_ext,
      z_ext       = z_ext,
      stratum_ext = stratum_ext,
      etas        = etas,
      max_iter    = max_iter,
      tol         = tol,
      message     = FALSE
    )
    beta_mat_fold <- fold_fit$beta

    for (i in seq_len(n_eta)) {
      beta_hat <- as.numeric(beta_mat_fold[, i])
      lp_test  <- as.numeric(z_test %*% beta_hat)

      if (cv.criteria == "loss") {
        loglik_test <- cc_loglik(y = y_test, lp = lp_test, stratum = stratum_test)
        result_mat[f, i] <- -loglik_test / length(y_test)
      } else {
        cv_all_lp[test_idx, i] <- lp_test
      }
    }
  }

  if (cv.criteria == "loss") {
    result_vec <- colMeans(result_mat, na.rm = TRUE)
  } else if (cv.criteria %in% c("AUC", "CIndex")) {
    result_vec <- apply(
      cv_all_lp, 2,
      function(lp) cc_auc(y = y_int, lp = lp, stratum = stratum_int)
    )
  } else if (cv.criteria == "Brier") {
    result_vec <- apply(
      cv_all_lp, 2,
      function(lp) cc_brier(y = y_int, lp = lp, stratum = stratum_int)
    )
  }

  results <- data.frame(eta = etas)

  if (cv.criteria == "loss") {
    results$loss <- result_vec
    best_eta_idx <- which.min(results$loss)
  } else if (cv.criteria == "AUC") {
    results$AUC <- result_vec
    best_eta_idx <- which.max(results$AUC)
  } else if (cv.criteria == "CIndex") {
    results$CIndex <- result_vec
    best_eta_idx <- which.max(results$CIndex)
  } else if (cv.criteria == "Brier") {
    results$Brier <- result_vec
    best_eta_idx <- which.min(results$Brier)
  }

  best_res <- list(
    best_eta  = etas[best_eta_idx],
    best_beta = beta_full[, best_eta_idx],
    criteria  = cv.criteria
  )

  structure(
    list(
      internal_stat = results,
      beta_full     = beta_full,
      best          = best_res,
      criteria      = cv.criteria,
      nfolds        = nfolds
    ),
    class = "cv.ncc_indi"
  )
}
