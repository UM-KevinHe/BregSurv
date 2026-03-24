#' Cross-Validated CLR-KL with Elastic Net Penalty
#'
#' @description
#' Performs K-fold cross-validation (CV) to jointly select the integration
#' parameter \code{eta} and the Elastic Net penalty parameter \code{lambda}
#' for Conditional Logistic Regression with Kullback–Leibler (KL)
#' divergence and Elastic Net penalty, implemented via \code{\link{ncckl_enet}}.
#'
#' This function is designed for 1:m matched case–control settings where each
#' stratum (matched set) contains exactly one case and \eqn{m} controls.
#'
#' @details
#' The matched case–control problem is handled via \code{\link{ncckl_enet}},
#' which maps Conditional Logistic Regression to a Cox model with fixed event
#' time and uses \code{\link{coxkl_enet}} as the core engine.
#'
#' Cross-validation is performed at the stratum level: each matched set is
#' treated as an indivisible unit and assigned to a single fold using
#' \code{\link{get_fold_cc}}. This ensures that the conditional likelihood is
#' well-defined within each training and test split.
#'
#' For each candidate \code{eta}, a full \code{lambda} path is fit on the
#' complete data (via \code{\link{ncckl_enet}}), and then K-fold CV is used
#' to evaluate each \code{lambda} along this path according to the chosen
#' \code{criteria}. The function therefore performs a 2D search over
#' \eqn{(\eta, \lambda)}.
#'
#' The \code{criteria} argument controls the CV performance metric:
#' \itemize{
#'   \item \code{"loss"}: Average negative conditional log-likelihood on held-out
#'     strata (lower is better).
#'   \item \code{"AUC"}: Matched-set AUC based on within-stratum comparisons
#'     (higher is better).
#'   \item \code{"CIndex"}: Alias for \code{"AUC"} in the 1:m matched setting
#'     (higher is better).
#'   \item \code{"Brier"}: Conditional Brier score based on within-stratum
#'     softmax probabilities (lower is better).
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#'   In the 1:m matched case–control setting, each stratum must contain exactly
#'   one case.
#' @param z Numeric matrix of covariates (rows = observations, columns = variables).
#' @param stratum Numeric or factor vector defining the matched sets (strata).
#'   Each unique value identifies one matched set.
#' @param RS Optional numeric vector or matrix of external risk scores.
#'   If not provided, \code{beta} must be supplied.
#' @param beta Optional numeric vector of external coefficients. If provided,
#'   length must equal the number of columns in \code{z}. Either \code{RS} or
#'   \code{beta} must be non-\code{NULL}.
#' @param etas Numeric vector of candidate tuning values for the integration
#'   parameter \eqn{\eta}. The values will be sorted in ascending order.
#' @param alpha Elastic Net mixing parameter in \eqn{(0,1]}. Default is
#'   \code{1} (lasso penalty).
#' @param lambda Optional numeric vector of lambda values. If \code{NULL}, a
#'   lambda path is generated automatically for each \code{eta}.
#' @param nlambda Integer. Number of lambda values to generate when
#'   \code{lambda} is \code{NULL}. Default \code{100}.
#' @param lambda.min.ratio Numeric in \eqn{(0,1)}. Ratio of minimum to maximum
#'   lambda when \code{lambda} is \code{NULL}. If \code{NULL}, it is set
#'   internally to \code{0.05} when \code{n < p}, and \code{1e-3} otherwise.
#' @param nfolds Number of cross-validation folds. Default \code{5}.
#' @param criteria Character string specifying the CV performance criterion.
#'   Choices are:
#'   \itemize{
#'     \item \code{"loss"}: Average negative conditional log-likelihood
#'       (lower is better).
#'     \item \code{"AUC"}: Matched-set AUC based on within-stratum comparisons
#'       (higher is better).
#'     \item \code{"CIndex"}: Concordance index in the matched-set setting,
#'       implemented via the same matched-set AUC calculation as \code{"AUC"}
#'       (higher is better).
#'     \item \code{"Brier"}: Conditional Brier score using within-stratum
#'       softmax probabilities (lower is better).
#'   }
#'   Default is \code{"loss"}.
#' @param message Logical; if \code{TRUE}, prints progress messages. Default
#'   \code{FALSE}.
#' @param seed Optional integer seed for reproducible fold assignment. Default
#'   \code{NULL}.
#' @param ... Additional arguments passed to \code{\link{ncckl_enet}}.
#'
#' @return A \code{list} of class \code{"cv.ncckl_enet"} containing:
#' \describe{
#'   \item{\code{best}}{A list with the global best \eqn{(\eta, \lambda)}:
#'     \itemize{
#'       \item \code{best_eta}: Selected \code{eta}.
#'       \item \code{best_lambda}: Selected \code{lambda}.
#'       \item \code{best_beta}: Coefficient vector from the full-data fit at
#'         \code{(best_eta, best_lambda)}.
#'       \item \code{criteria}: The criterion used.
#'     }
#'   }
#'   \item{\code{integrated_stat.full_results}}{A \code{data.frame} with one row
#'     per \code{(eta, lambda)} combination and the corresponding CV score.}
#'   \item{\code{integrated_stat.best_per_eta}}{A \code{data.frame} with one row
#'     per \code{eta}, containing the best \code{lambda} and its score.}
#'   \item{\code{integrated_stat.betahat_best}}{A matrix of coefficients where
#'     each column is the full-data coefficient vector corresponding to the
#'     best \code{lambda} for a given \code{eta}.}
#'   \item{\code{criteria}}{The CV criterion used.}
#'   \item{\code{alpha}}{The Elastic Net mixing parameter.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
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
#' cv_fit <- cv.ncckl_enet(
#'   y        = y,
#'   z        = z,
#'   stratum  = sets,
#'   beta     = beta_ext,
#'   etas     = eta_list,
#'   alpha    = 1,
#'   nfolds   = 5,
#'   criteria = "loss",
#'   seed     = 42
#' )
#'
#' cv_fit$best$best_eta
#' cv_fit$best$best_lambda
#' }
#'
#' @export
cv.ncckl_enet <- function(y, z, stratum,
                             RS = NULL,
                             beta = NULL,
                             etas = NULL,
                             alpha = 1.0,
                             lambda = NULL,
                             nlambda = 100,
                             lambda.min.ratio = NULL,
                             nfolds = 5,
                             criteria = c("loss", "AUC", "CIndex", "Brier"),
                             message = FALSE,
                             seed = NULL,
                             ...) {

  criteria <- match.arg(criteria, choices = c("loss", "AUC", "CIndex", "Brier"))

  y <- as.numeric(y)
  z <- as.matrix(z)

  if (missing(stratum) || is.null(stratum)) {
    stop("stratum must be provided for cv.ncckl_enet in 1:m matched settings.", call. = FALSE)
  }
  stratum <- as.factor(stratum)

  if (alpha > 1 || alpha <= 0) {
    stop("alpha must be in (0,1].", call. = FALSE)
  }

  ## External information: RS or beta
  if (is.null(RS) && is.null(beta)) {
    stop("Either RS or beta must be provided for cv.ncckl_enet.", call. = FALSE)
  }
  if (!is.null(beta)) {
    if (length(beta) != ncol(z)) {
      stop("The dimension of beta does not match the number of columns in z.", call. = FALSE)
    }
  }

  ## Check 1:m structure: one case per stratum
  events_per_stratum <- tapply(y, stratum, function(x) sum(x == 1))
  if (any(is.na(events_per_stratum)) || any(events_per_stratum != 1)) {
    stop(
      "cv.ncckl_enet assumes a 1:m matched setting: each stratum must contain exactly ",
      "one case (sum(y==1) == 1 per stratum).",
      call. = FALSE
    )
  }

  if (is.null(etas)) {
    stop("etas must be provided.", call. = FALSE)
  }
  etas   <- sort(etas)
  n_eta  <- length(etas)

  n <- nrow(z)
  p <- ncol(z)

  if (is.null(lambda.min.ratio)) {
    lambda.min.ratio <- ifelse(n < p, 0.05, 1e-3)
  }

  if (message) {
    message("Fitting full CLR-KL-ENet model for all etas...")
    pb_full <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }
  full_fit_list  <- vector("list", n_eta)
  lambda_list    <- vector("list", n_eta)
  beta_full_list <- vector("list", n_eta)

  for (i in seq_len(n_eta)) {
    eta_i <- etas[i]

    fit_i <- ncckl_enet(
      y       = y,
      z       = z,
      stratum = stratum,
      RS      = RS,
      beta    = beta,
      eta     = eta_i,
      alpha   = alpha,
      lambda  = lambda,
      nlambda = nlambda,
      lambda.min.ratio = lambda.min.ratio,
      message = FALSE,
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

  ## For criteria that need all CV linear predictors
  store_lp_all <- criteria %in% c("AUC", "CIndex", "Brier")
  if (store_lp_all) {
    ## We will create these per eta below because lambda_seq may vary by eta
  }

  if (message) {
    cat("Cross-validation over eta sequence:\n")
    pb_eta <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }

  for (i in seq_len(n_eta)) {
    eta_i      <- etas[i]
    lambda_seq <- lambda_list[[i]]
    beta_full  <- beta_full_list[[i]]
    L          <- length(lambda_seq)

    if (criteria == "loss") {
      loss_sum <- numeric(L)
      loss_n   <- numeric(L)
    } else {
      cv_all_lp <- matrix(NA_real_, nrow = n, ncol = L)
    }

    ## Loop over folds
    for (f in seq_len(nfolds)) {
      test_idx  <- which(folds == f)
      train_idx <- which(folds != f)

      y_train       <- y[train_idx]
      z_train       <- z[train_idx, , drop = FALSE]
      stratum_train <- droplevels(stratum[train_idx])

      y_test       <- y[test_idx]
      z_test       <- z[test_idx, , drop = FALSE]
      stratum_test <- droplevels(stratum[test_idx])

      ## 1:m structure in each fold
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

      ## External RS for the fold if needed
      RS_train <- NULL
      if (!is.null(RS)) {
        RS_train <- RS[train_idx, , drop = FALSE]
      }

      fold_fit <- ncckl_enet(
        y       = y_train,
        z       = z_train,
        stratum = stratum_train,
        RS      = RS_train,
        beta    = beta,
        eta     = eta_i,
        alpha   = alpha,
        lambda  = lambda_seq,
        message = FALSE,
        ...
      )

      beta_mat_fold <- fold_fit$beta  # p x L

      ## For each lambda, compute test linear predictors
      lp_test_mat <- as.matrix(z_test) %*% beta_mat_fold  # n_test x L

      if (criteria == "loss") {
        for (j in seq_len(L)) {
          lp_test_j <- lp_test_mat[, j]
          loglik_test <- cc_loglik(y = y_test, lp = lp_test_j, stratum = stratum_test)
          loss_sum[j] <- loss_sum[j] + (-loglik_test)
          loss_n[j]   <- loss_n[j]   + length(y_test)
        }
      } else {
        cv_all_lp[test_idx, ] <- lp_test_mat
      }
    } # end folds

    ## Aggregate across folds for this eta
    if (criteria == "loss") {
      score_eta <- loss_sum / pmax(loss_n, 1)
    } else if (criteria %in% c("AUC", "CIndex")) {
      score_eta <- apply(
        cv_all_lp,
        2,
        function(lp) cc_auc(y = y, lp = lp, stratum = stratum)
      )
    } else if (criteria == "Brier") {
      score_eta <- apply(
        cv_all_lp,
        2,
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

  ## Select best lambda per eta, and global best
  if (criteria %in% c("loss", "Brier")) {
    # lower is better
    best_per_eta <- do.call(
      rbind,
      lapply(split(results_df, results_df$eta),
             function(df) df[which.min(df$score), , drop = FALSE])
    )
    best.idx <- which.min(best_per_eta$score)
  } else {
    # AUC / CIndex: higher is better
    best_per_eta <- do.call(
      rbind,
      lapply(split(results_df, results_df$eta),
             function(df) df[which.max(df$score), , drop = FALSE])
    )
    best.idx <- which.max(best_per_eta$score)
  }
  rownames(best_per_eta) <- NULL

  ## Extract full-data betas at best lambda for each eta
  beta_best_mat <- sapply(seq_len(n_eta), function(i) {
    beta_mat   <- beta_full_list[[i]]      # p x L_i
    lambda_seq <- lambda_list[[i]]

    lambda_target <- best_per_eta$lambda[i]
    idx <- which(abs(lambda_seq - lambda_target) < 1e-12)
    if (length(idx) != 1L) {
      idx <- which.min(abs(lambda_seq - lambda_target))
    }
    beta_mat[, idx]
  })
  colnames(beta_best_mat) <- etas

  best_res <- list(
    best_eta    = best_per_eta$eta[best.idx],
    best_lambda = best_per_eta$lambda[best.idx],
    best_beta   = beta_best_mat[, best.idx],
    criteria    = criteria
  )

  structure(
    list(
      best                        = best_res,
      integrated_stat.full_results = results_df,
      integrated_stat.best_per_eta = best_per_eta,
      integrated_stat.betahat_best = beta_best_mat,
      criteria                    = criteria,
      alpha                       = alpha,
      nfolds                      = nfolds
    ),
    class = "cv.ncckl_enet"
  )
}
