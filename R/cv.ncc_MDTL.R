#' Cross-Validated CLR with Mahalanobis Distance Transfer Learning
#'
#' @description
#' Performs K-fold cross-validation (CV) to select the integration parameter
#' \code{eta} for Conditional Logistic Regression with Mahalanobis distance
#' transfer learning, implemented via \code{\link{ncc_MDTL}}.
#'
#' This function is designed for 1:m matched case-control settings where each
#' stratum (matched set) contains exactly one case and \eqn{m} controls.
#'
#' @details
#' Cross-validation is performed at the stratum level: each matched set is
#' treated as an indivisible unit and assigned to a single fold using
#' \code{\link{get_fold_cc}}. This ensures that the conditional likelihood is
#' well-defined within each training and test split.
#'
#' The \code{cv.criteria} argument controls the CV performance metric:
#' \itemize{
#'   \item \code{"loss"}: Average negative conditional log-likelihood on held-out
#'     strata (lower is better).
#'   \item \code{"AUC"}: Matched-set AUC based on within-stratum comparisons
#'     (higher is better).
#'   \item \code{"CIndex"}: Alias for \code{"AUC"} in the 1:m matched setting.
#'   \item \code{"Brier"}: Conditional Brier score based on within-stratum softmax
#'     probabilities (lower is better).
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates.
#' @param stratum Numeric or factor vector defining the matched sets. \strong{Required}.
#' @param beta Numeric vector of external coefficients (length \code{ncol(z)}). \strong{Required}.
#' @param vcov Optional numeric matrix (\code{ncol(z)} x \code{ncol(z)}) as the weighting
#'   matrix \eqn{Q}. Typically the precision matrix of the external estimator. If \code{NULL},
#'   defaults to the identity matrix.
#' @param etas Numeric vector of candidate tuning values for \eqn{\eta}. \strong{Required}.
#' @param tol Convergence tolerance passed to \code{\link{ncc_MDTL}}. Default \code{1e-4}.
#' @param Mstop Maximum Newton-Raphson iterations passed to \code{\link{ncc_MDTL}}.
#'   Default \code{100}.
#' @param nfolds Number of cross-validation folds. Default \code{5}.
#' @param cv.criteria Character string specifying the CV performance criterion.
#'   One of \code{"loss"} (default), \code{"AUC"}, \code{"CIndex"}, or \code{"Brier"}.
#' @param message Logical. If \code{TRUE}, prints progress messages. Default \code{FALSE}.
#' @param seed Optional integer seed for reproducible fold assignment. Default \code{NULL}.
#' @param ... Additional arguments passed to \code{\link{ncc_MDTL}}.
#'
#' @return A list of class \code{"cv.ncc_MDTL"} containing:
#' \describe{
#'   \item{\code{internal_stat}}{A \code{data.frame} with one row per \code{eta} and
#'     the CV metric for the chosen \code{cv.criteria}.}
#'   \item{\code{beta_full}}{Matrix of coefficients from the full-data fit
#'     (columns correspond to \code{etas}).}
#'   \item{\code{best}}{A list with \code{best_eta}, \code{best_beta}, and \code{criteria}.}
#'   \item{\code{criteria}}{The criterion used for selection.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @seealso \code{\link{ncc_MDTL}}, \code{\link{cv.ncckl}}
#'
#' @examples
#' \dontrun{
#' data(ExampleData_cc)
#' train_cc <- ExampleData_cc$train
#'
#' y        <- train_cc$y
#' z        <- train_cc$z
#' sets     <- train_cc$stratum
#' beta_ext <- ExampleData_cc$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#'
#' cv_fit <- cv.ncc_MDTL(
#'   y        = y,
#'   z        = z,
#'   stratum  = sets,
#'   beta     = beta_ext,
#'   vcov     = NULL,
#'   etas     = eta_list,
#'   nfolds   = 5,
#'   cv.criteria = "loss",
#'   seed     = 42
#' )
#' cv_fit$best$best_eta
#' }
#' @export
cv.ncc_MDTL <- function(y, z, stratum,
                            beta, vcov = NULL,
                            etas = NULL,
                            tol = 1.0e-4, Mstop = 100,
                            nfolds = 5,
                            cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
                            message = FALSE,
                            seed = NULL,
                            ...) {

  cv.criteria <- match.arg(cv.criteria, choices = c("loss", "AUC", "CIndex", "Brier"))

  y <- as.numeric(y)
  z <- as.matrix(z)

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas   <- sort(as.numeric(etas))
  n_eta  <- length(etas)

  if (missing(stratum) || is.null(stratum)) {
    stop("stratum must be provided for cv.ncc_MDTL in 1:m matched settings.", call. = FALSE)
  }
  stratum <- as.factor(stratum)

  if (length(beta) != ncol(z)) {
    stop("The dimension of beta does not match the number of columns in z.", call. = FALSE)
  }

  if (is.null(vcov)) {
    Q <- diag(ncol(z))
  } else {
    if (nrow(vcov) != ncol(z) || ncol(vcov) != ncol(z)) {
      stop("The dimension of vcov does not match the number of columns in z.", call. = FALSE)
    }
    Q <- vcov
  }

  events_per_stratum <- tapply(y, stratum, function(x) sum(x == 1))
  if (any(is.na(events_per_stratum)) || any(events_per_stratum != 1)) {
    stop(
      "cv.ncc_MDTL assumes a 1:m matched setting: each stratum must contain exactly ",
      "one case (sum(y==1) == 1 per stratum).",
      call. = FALSE
    )
  }

  n <- length(y)

  full_fit <- ncc_MDTL(
    y       = y,
    z       = z,
    stratum = stratum,
    beta    = beta,
    vcov    = Q,
    etas    = etas,
    tol     = tol,
    Mstop   = Mstop,
    message = FALSE,
    ...
  )
  beta_full <- full_fit$beta

  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold_cc(nfolds = nfolds, delta = y, stratum = stratum)
  if (length(folds) != n) {
    stop("get_fold_cc must return a fold assignment of length equal to length(y).", call. = FALSE)
  }

  result_mat <- matrix(NA_real_, nrow = nfolds, ncol = n_eta)
  if (cv.criteria %in% c("AUC", "CIndex", "Brier")) {
    cv_all_lp <- matrix(NA_real_, nrow = n, ncol = n_eta)
  }

  for (f in seq_len(nfolds)) {
    if (message) message(sprintf("CV fold %d/%d starts...", f, nfolds))

    test_idx  <- which(folds == f)
    train_idx <- which(folds != f)

    y_train       <- y[train_idx]
    z_train       <- z[train_idx, , drop = FALSE]
    stratum_train <- droplevels(stratum[train_idx])

    y_test       <- y[test_idx]
    z_test       <- z[test_idx, , drop = FALSE]
    stratum_test <- droplevels(stratum[test_idx])

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

    fold_fit <- ncc_MDTL(
      y       = y_train,
      z       = z_train,
      stratum = stratum_train,
      beta    = beta,
      vcov    = Q,
      etas    = etas,
      tol     = tol,
      Mstop   = Mstop,
      message = FALSE,
      ...
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
      function(lp) cc_auc(y = y, lp = lp, stratum = stratum)
    )
  } else if (cv.criteria == "Brier") {
    result_vec <- apply(
      cv_all_lp, 2,
      function(lp) cc_brier(y = y, lp = lp, stratum = stratum)
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
    class = "cv.ncc_MDTL"
  )
}
