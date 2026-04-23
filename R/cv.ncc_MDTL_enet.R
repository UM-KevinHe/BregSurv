#' Cross-Validated CLR with Mahalanobis Distance Transfer Learning and Elastic Net Penalty
#'
#' @description
#' Performs K-fold cross-validation (CV) to jointly select the integration
#' parameter \code{eta} and the Elastic Net penalty parameter \code{lambda}
#' for Conditional Logistic Regression with Mahalanobis distance transfer
#' learning and Elastic Net penalty, implemented via \code{\link{ncc_MDTL_enet}}.
#'
#' This function is designed for 1:m matched case-control settings where each
#' stratum (matched set) contains exactly one case and \eqn{m} controls.
#'
#' @details
#' Cross-validation is performed at the stratum level: each matched set is
#' treated as an indivisible unit and assigned to a single fold using
#' \code{\link{get_fold_cc}}.
#'
#' For each candidate \code{eta}, a full \code{lambda} path is fit on the complete
#' data, and then K-fold CV is used to evaluate each \code{lambda} along this path.
#' The function performs a 2D search over \eqn{(\eta, \lambda)}.
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
#'   matrix \eqn{Q}. If \code{NULL}, defaults to the identity matrix.
#' @param etas Numeric vector of candidate tuning values for \eqn{\eta}. \strong{Required}.
#' @param alpha Elastic Net mixing parameter in \eqn{(0,1]}. Default \code{NULL} (set to 1
#'   with a warning if not supplied).
#' @param lambda Optional numeric vector of lambda values. If \code{NULL}, a lambda path
#'   is generated automatically for each \code{eta}.
#' @param nlambda Integer. Number of lambda values. Default \code{100}.
#' @param lambda.min.ratio Smallest lambda as a fraction of \code{lambda.max}. Default
#'   depends on sample size relative to number of covariates.
#' @param nfolds Number of cross-validation folds. Default \code{5}.
#' @param cv.criteria Character string specifying the CV performance criterion.
#'   One of \code{"loss"} (default), \code{"AUC"}, \code{"CIndex"}, or \code{"Brier"}.
#' @param message Logical. If \code{TRUE}, prints progress messages. Default \code{FALSE}.
#' @param seed Optional integer seed for reproducible fold assignment. Default \code{NULL}.
#' @param ... Additional arguments passed to \code{\link{ncc_MDTL_enet}}.
#'
#' @return A list of class \code{"cv.ncc_MDTL_enet"} containing:
#' \describe{
#'   \item{\code{best}}{A list with the global best \eqn{(\eta, \lambda)}:
#'     \code{best_eta}, \code{best_lambda}, \code{best_beta}, \code{cv.criteria}.}
#'   \item{\code{integrated_stat.full_results}}{A \code{data.frame} with the CV score
#'     for every \eqn{(\eta, \lambda)} combination.}
#'   \item{\code{integrated_stat.best_per_eta}}{A \code{data.frame} with the best
#'     \code{lambda} and score for each \code{eta}.}
#'   \item{\code{integrated_stat.betahat_best}}{Matrix of full-data coefficients at the
#'     best \code{lambda} for each \code{eta}.}
#'   \item{\code{criteria}}{The CV criterion used.}
#'   \item{\code{alpha}}{The Elastic Net mixing parameter.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @seealso \code{\link{ncc_MDTL_enet}}, \code{\link{cv.ncckl_enet}}
#'
#' @examples
#' \dontrun{
#' data(ExampleData_cc_highdim)
#' train_cc <- ExampleData_cc_highdim$train
#'
#' y        <- train_cc$y
#' z        <- train_cc$z
#' sets     <- train_cc$stratum
#' beta_ext <- ExampleData_cc_highdim$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 30, max_eta = 20)
#'
#' cv_fit <- cv.ncc_MDTL_enet(
#'   y        = y,
#'   z        = z,
#'   stratum  = sets,
#'   beta     = beta_ext,
#'   vcov     = NULL,
#'   etas     = eta_list,
#'   alpha    = 1,
#'   nfolds   = 5,
#'   cv.criteria = "loss",
#'   seed     = 42
#' )
#' cv_fit$best$best_eta
#' cv_fit$best$best_lambda
#' }
#' @export
cv.ncc_MDTL_enet <- function(y, z, stratum,
                                 beta, vcov = NULL,
                                 etas = NULL,
                                 alpha = NULL,
                                 lambda = NULL,
                                 nlambda = 100,
                                 lambda.min.ratio = ifelse(nrow(z) < ncol(z), 0.05, 1e-03),
                                 nfolds = 5,
                                 cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
                                 message = FALSE,
                                 seed = NULL,
                                 ...) {

  cv.criteria <- match.arg(cv.criteria, choices = c("loss", "AUC", "CIndex", "Brier"))

  y <- as.numeric(y)
  z <- as.matrix(z)

  if (is.null(alpha)) {
    warning("alpha is not provided. Setting alpha = 1 (lasso penalty).", call. = FALSE)
    alpha <- 1
  } else if (alpha > 1 || alpha <= 0) {
    stop("alpha must be in (0, 1].", call. = FALSE)
  }

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas   <- sort(as.numeric(etas))
  n_eta  <- length(etas)

  if (missing(stratum) || is.null(stratum)) {
    stop("stratum must be provided for cv.ncc_MDTL_enet in 1:m matched settings.", call. = FALSE)
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
      "cv.ncc_MDTL_enet assumes a 1:m matched setting: each stratum must contain exactly ",
      "one case (sum(y==1) == 1 per stratum).",
      call. = FALSE
    )
  }

  n <- length(y)

  ## Full-data fit for each eta
  if (message) {
    message("Fitting full CLR-MDTL-ENet model for all etas...")
    pb_full <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }
  full_fit_list  <- vector("list", n_eta)
  lambda_list    <- vector("list", n_eta)
  beta_full_list <- vector("list", n_eta)

  for (i in seq_len(n_eta)) {
    eta_i <- etas[i]

    fit_i <- ncc_MDTL_enet(
      y                = y,
      z                = z,
      stratum          = stratum,
      beta             = beta,
      vcov             = Q,
      eta              = eta_i,
      alpha            = alpha,
      lambda           = lambda,
      nlambda          = nlambda,
      lambda.min.ratio = lambda.min.ratio,
      message          = FALSE,
      ...
    )

    full_fit_list[[i]]  <- fit_i
    lambda_list[[i]]    <- as.vector(fit_i$lambda)
    beta_full_list[[i]] <- fit_i$beta

    if (message) setTxtProgressBar(pb_full, i)
  }
  if (message) close(pb_full)

  ## CV fold assignment at stratum level
  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold_cc(nfolds = nfolds, delta = y, stratum = stratum)
  if (length(folds) != n) {
    stop("get_fold_cc must return a fold assignment of length equal to length(y).", call. = FALSE)
  }

  results_list <- vector("list", n_eta)

  if (message) {
    cat("Cross-validation over eta sequence:\n")
    pb_eta <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }

  for (i in seq_len(n_eta)) {
    eta_i      <- etas[i]
    lambda_seq <- lambda_list[[i]]
    L          <- length(lambda_seq)

    if (cv.criteria == "loss") {
      loss_sum <- numeric(L)
      loss_n   <- numeric(L)
    } else {
      cv_all_lp <- matrix(NA_real_, nrow = n, ncol = L)
    }

    for (f in seq_len(nfolds)) {
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

      fold_fit <- ncc_MDTL_enet(
        y                = y_train,
        z                = z_train,
        stratum          = stratum_train,
        beta             = beta,
        vcov             = Q,
        eta              = eta_i,
        alpha            = alpha,
        lambda           = lambda_seq,
        message          = FALSE,
        ...
      )

      beta_mat_fold <- fold_fit$beta   # p x L

      lp_test_mat <- as.matrix(z_test) %*% beta_mat_fold   # n_test x L

      if (cv.criteria == "loss") {
        for (j in seq_len(L)) {
          lp_test_j   <- lp_test_mat[, j]
          loglik_test <- cc_loglik(y = y_test, lp = lp_test_j, stratum = stratum_test)
          loss_sum[j] <- loss_sum[j] + (-loglik_test)
          loss_n[j]   <- loss_n[j]   + length(y_test)
        }
      } else {
        cv_all_lp[test_idx, ] <- lp_test_mat
      }
    } # end folds

    if (cv.criteria == "loss") {
      score_eta <- loss_sum / pmax(loss_n, 1)
    } else if (cv.criteria %in% c("AUC", "CIndex")) {
      score_eta <- apply(
        cv_all_lp, 2,
        function(lp) cc_auc(y = y, lp = lp, stratum = stratum)
      )
    } else if (cv.criteria == "Brier") {
      score_eta <- apply(
        cv_all_lp, 2,
        function(lp) cc_brier(y = y, lp = lp, stratum = stratum)
      )
    }

    results_list[[i]] <- data.frame(
      eta    = eta_i,
      lambda = lambda_seq,
      score  = score_eta,
      stringsAsFactors = FALSE
    )

    if (message) setTxtProgressBar(pb_eta, i)
  }

  if (message) close(pb_eta)

  results_df <- do.call(rbind, results_list)

  if (cv.criteria %in% c("loss", "Brier")) {
    best_per_eta <- do.call(
      rbind,
      lapply(split(results_df, results_df$eta),
             function(df) df[which.min(df$score), , drop = FALSE])
    )
    best.idx <- which.min(best_per_eta$score)
  } else {
    best_per_eta <- do.call(
      rbind,
      lapply(split(results_df, results_df$eta),
             function(df) df[which.max(df$score), , drop = FALSE])
    )
    best.idx <- which.max(best_per_eta$score)
  }
  rownames(best_per_eta) <- NULL

  beta_best_mat <- sapply(seq_len(n_eta), function(i) {
    beta_mat   <- beta_full_list[[i]]
    lambda_seq <- lambda_list[[i]]

    lambda_target <- best_per_eta$lambda[i]
    idx <- which(abs(lambda_seq - lambda_target) < 1e-12)
    if (length(idx) != 1L) idx <- which.min(abs(lambda_seq - lambda_target))
    beta_mat[, idx]
  })
  colnames(beta_best_mat) <- etas

  best_res <- list(
    best_eta    = best_per_eta$eta[best.idx],
    best_lambda = best_per_eta$lambda[best.idx],
    best_beta   = beta_best_mat[, best.idx],
    criteria    = cv.criteria
  )

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
    class = "cv.ncc_MDTL_enet"
  )
}
