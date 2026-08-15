#' Cross-Validation for Cox MDTL with Ridge Regularization
#'
#' @description
#' Performs k-fold cross-validation to simultaneously tune the hyperparameter \code{eta}
#' (transfer learning weight) and the regularization parameter \code{lambda} for the
#' Cox MDTL model with a Ridge penalty (L2-norm).
#'
#' This function evaluates the model performance across a grid of \code{eta} and \code{lambda}
#' values. It is efficient for high-dimensional data where an Elastic Net penalty is not required,
#' focusing purely on Ridge regression to handle multicollinearity and overfitting.
#'
#' @details
#' When \code{lambda} is not supplied, the Ridge lambda sequence is generated
#' internally by \code{\link{cox_MDTL_ridge}} and always spans from
#' \code{lambda.max} down to an exact \code{0}, i.e. the last element of the path
#' is the unpenalized solution. This behaviour is fixed for the Ridge path and is
#' therefore \emph{not} configurable through a minimum-ratio argument; only the
#' number of grid points (\code{nlambda}), or an explicit \code{lambda} vector, is
#' under user control.
#'
#' @param z A numeric matrix or data frame of covariates (n x p).
#' @param delta A numeric vector of event indicators (1 = event, 0 = censored).
#' @param time A numeric vector of observed times.
#' @param stratum Optional numeric or factor vector indicating strata. If \code{NULL},
#'   a warning is issued and all subjects are assumed to be in the same stratum.
#' @param beta A numeric vector of external coefficients. If \code{beta} is named,
#'   names are matched against \code{colnames(z)}: covariates absent from
#'   \code{beta} are set to 0 (with a message) and the vector is reordered, so an
#'   external source covering only a subset of the internal covariates may be
#'   supplied directly. An unnamed \code{beta} is aligned positionally and must have
#'   length \code{ncol(z)}. A one-column matrix with row names is accepted as a
#'   named vector. See \code{\link{align_beta_Q}}.
#' @param Q Optional weighting (precision) matrix for the Mahalanobis penalty
#'   (typically the inverse covariance / information matrix of the external
#'   estimator). Must be symmetric and positive semi-definite; both are checked to a
#'   tolerance of 1e-8 and violations are errors. If named, it is reordered and
#'   zero-padded to \code{colnames(z)}; only an unnamed \code{Q} must be exactly
#'   \code{ncol(z)} by \code{ncol(z)}. If \code{NULL}, a \emph{masked identity} is
#'   used: 1 on covariates actually supplied by \code{beta} and 0 on zero-padded
#'   positions, so padded coefficients are left unpenalized. See
#'   \code{\link{align_beta_Q}}.
#' @param etas A numeric vector of non-negative candidate \code{eta} values to be
#'   evaluated. Must be finite and \eqn{\ge 0}. The values are sorted in ascending
#'   order internally, and the rows of \code{integrated_stat.best_per_eta} /
#'   columns of \code{integrated_stat.betahat_best} follow that sorted order.
#' @param lambda Optional user-supplied lambda sequence. If \code{NULL}, the function
#'   computes its own sequence based on \code{nlambda}.
#' @param nlambda The number of \code{lambda} values. Default is 100.
#' @param nfolds Integer. Number of cross-validation folds. Default is 5.
#' @param cv.criteria Character string specifying the cross-validation criterion. Choices are:
#'   \itemize{
#'     \item \code{"V&VH"} (default): Verweij & Van Houwelingen partial likelihood loss.
#'     \item \code{"LinPred"}: Loss based on the prognostic performance of the linear predictor.
#'     \item \code{"CIndex_pooled"}: Harrell's C-index computed by pooling predictions across folds.
#'     \item \code{"CIndex_foldaverage"}: Harrell's C-index computed within each fold and averaged.
#'   }
#' @param c_index_stratum Optional stratum vector. Required only when \code{cv.criteria} involves
#'   stratified C-index calculation but the model itself is unstratified. That use case is
#'   therefore only reachable when \code{stratum = NULL}: if \code{stratum} is supplied and
#'   \code{c_index_stratum} is not identical to it, the function stops with an error.
#' @param message Logical. If \code{TRUE}, progress messages are printed.
#' @param seed Optional integer. Random seed for reproducible fold assignment.
#' @param ... Additional arguments passed to the underlying fitting function.
#'
#' @return An object of class \code{"cv.cox_MDTL_ridge"} containing:
#' \describe{
#'   \item{\code{best}}{A list containing the optimal results:
#'     \itemize{
#'       \item \code{best_eta}: The selected eta value.
#'       \item \code{best_lambda}: The selected lambda value.
#'       \item \code{best_beta}: The coefficient vector corresponding to the optimal parameters.
#'       \item \code{criteria}: The selection criterion used.
#'     }
#'   }
#'   \item{\code{integrated_stat.full_results}}{A data frame of performance metrics for all combinations of eta and lambda.
#'     Besides \code{eta} and \code{lambda} it carries a single metric column named after the
#'     selected criterion: \code{Loss} for \code{"V&VH"} and \code{"LinPred"}, otherwise
#'     \code{CIndex_pooled} or \code{CIndex_foldaverage}.}
#'   \item{\code{integrated_stat.best_per_eta}}{A data frame summarizing the best lambda and performance metric for each eta,
#'     with the same criterion-named metric column.}
#'   \item{\code{integrated_stat.betahat_best}}{A matrix of coefficients for the best lambda at each eta.}
#'   \item{\code{criteria}}{The selection criterion used.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#'
#' cv.cox_MDTL_ridge_est <- cv.cox_MDTL_ridge(
#'   z = train_dat_highdim$z,
#'   delta = train_dat_highdim$status,
#'   time = train_dat_highdim$time,
#'   stratum = train_dat_highdim$stratum,
#'   beta = beta_external_highdim,
#'   Q = NULL,
#'   etas = eta_list,
#'   cv.criteria = "CIndex_pooled"
#' )
#' }
#'
#' @export
cv.cox_MDTL_ridge <- function(z, delta, time, stratum = NULL, beta = NULL, Q = NULL, etas,
                              lambda = NULL, nlambda = 100, nfolds = 5,
                              cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                              c_index_stratum = NULL,
                              message = FALSE, seed = NULL,  ...) {
  
  ## Input checks & data preparation
  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  check_etas(etas)
  etas <- sort(etas)
  cv.criteria <- match.arg(cv.criteria, choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))

  aligned <- align_beta_Q(z, beta, Q)
  beta <- aligned$beta
  Q <- aligned$Q
  
  
  if (is.null(stratum)) {
    warning("Stratum not provided. Treating all data as one stratum.", call. = FALSE)
    stratum <- rep(1, nrow(z))
  } else {
    if (!is.null(c_index_stratum) & !identical(stratum, c_index_stratum)) {
      stop("The provided 'c_index_stratum' is not identical to 'stratum'!")
    }
    stratum <- match(stratum, unique(stratum))
  }
  
  time_order <- order(stratum, time)
  time <- as.numeric(time[time_order])
  stratum <- as.numeric(stratum[time_order])
  z <- as.matrix(z)[time_order, , drop = FALSE]
  delta <- as.numeric(delta[time_order])
  n <- nrow(z)
  
  n.each_stratum_full <- as.numeric(table(stratum))
  
  ## Fixed CV folds
  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold(nfolds = nfolds, delta = delta, stratum = stratum)
  
  n_eta <- length(etas)
  results_list <- list()
  
  n_vars <- ncol(z)
  n_obs <- nrow(z)
  
  beta_ext <- beta
  
  if (message) {
    cat("Cross-validation over eta sequence:\n")
    pb_eta <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }
  
  fit_beta_list <- vector("list", length(etas))
  lambda_list <- vector("list", length(etas))
  
  for (ei in seq_along(etas)) {
    eta <- etas[ei]
    
    if (is.null(lambda)) {
      fit0 <- cox_MDTL_ridge(z = z, delta = delta, time = time, stratum = stratum,
                             beta = beta_ext, Q = Q, eta = eta, lambda = NULL,
                             nlambda = nlambda,
                             data_sorted = TRUE, message = FALSE, ...)
      lambda_seq <- as.vector(fit0$lambda)
    } else {
      lambda_seq <- sort(lambda, decreasing = TRUE)
      fit0 <- cox_MDTL_ridge(z = z, delta = delta, time = time, stratum = stratum,
                             beta = beta_ext, Q = Q, eta = eta, lambda = lambda_seq,
                             nlambda = nlambda,
                             data_sorted = TRUE, message = FALSE, ...)
    }
    beta_initial.fit0 <- fit0$beta[, 1]
    fit_beta_list[[ei]] <- fit0$beta
    lambda_list[[ei]]   <- lambda_seq
    
    L <- length(lambda_seq)
    
    if (cv.criteria == "V&VH") {
      vvh_sum <- rep(0, L)
    } else if (cv.criteria == "LinPred") {
      Y <- matrix(NA_real_, nrow = n, ncol = L)
      colnames(Y) <- round(lambda_seq, 6)
    } else if (cv.criteria == "CIndex_pooled") {
      numer <- rep(0, L); denom <- rep(0, L)
    } else if (cv.criteria == "CIndex_foldaverage") {
      csum <- rep(0, L); cnt <- rep(0, L)
    }
    
    ## Inner loop over folds
    for (f in seq_len(nfolds)) {
      train_idx <- which(folds != f)
      test_idx  <- which(folds == f)
      
      beta_initial <- beta_initial.fit0
      fit_f <- cox_MDTL_ridge(z = z[train_idx, , drop = FALSE],
                              delta = delta[train_idx],
                              time = time[train_idx],
                              stratum = stratum[train_idx],
                              beta = beta_ext, Q = Q,
                              eta = eta, lambda = lambda_seq,
                              data_sorted = TRUE, message = FALSE,
                              beta_initial = beta_initial, ...)
      
      beta_mat <- fit_f$beta
      beta_initial <- beta_mat[, 1]  # warm start for next fold
      
      z_train <- z[train_idx, , drop = FALSE]
      z_test  <- z[test_idx, , drop = FALSE]
      delta_train <- delta[train_idx]
      stratum_train <- stratum[train_idx]
      
      LP_train <- z_train %*% beta_mat
      LP_all   <- z       %*% beta_mat
      LP_test  <- z_test  %*% beta_mat
      
      if (cv.criteria == "V&VH") {
        n.each_stratum_train <- as.numeric(table(stratum_train))
        n.each_stratum_all   <- as.numeric(table(stratum))
        pl_all <- apply(LP_all,  2, function(col) pl_cal_theta(col, delta,        n.each_stratum_all))
        pl_tr  <- apply(LP_train, 2, function(col) pl_cal_theta(col, delta_train, n.each_stratum_train))
        vvh_sum <- vvh_sum + (pl_all - pl_tr)
      } else if (cv.criteria == "LinPred") {
        Y[test_idx, ] <- LP_test
      } else {
        if (is.null(c_index_stratum)) {
          stratum_test <- stratum[test_idx]
        } else {
          stratum_test <- c_index_stratum[test_idx]
        }
        numer_vec <- denom_vec <- cstat_vec <- rep(NA_real_, ncol(LP_test))
        for (j in seq_len(ncol(LP_test))) {
          cstat_j <- c_stat_stratcox(time[test_idx], LP_test[, j], stratum_test, delta[test_idx])
          numer_vec[j] <- cstat_j$numer
          denom_vec[j] <- cstat_j$denom
          cstat_vec[j] <- cstat_j$c_statistic
        }
        if (cv.criteria == "CIndex_pooled") {
          numer <- numer + numer_vec
          denom <- denom + denom_vec
        } else {
          csum <- csum + cstat_vec
          cnt  <- cnt  + 1
        }
      }
    }
    if (cv.criteria == "V&VH") {
      cve_eta <- vvh_sum
    } else if (cv.criteria == "LinPred") {
      Lmat <- loss.coxkl_highdim(delta, Y, stratum, total = FALSE)
      cve_eta <- colSums(Lmat)
    } else if (cv.criteria == "CIndex_pooled") {
      cve_eta <- numer / denom
    } else {
      cve_eta <- csum / pmax(cnt, 1)
    }
    
    results_list[[ei]] <- data.frame(
      eta = eta,
      lambda = lambda_seq,
      score = cve_eta,
      stringsAsFactors = FALSE
    )
    
    if (message) setTxtProgressBar(pb_eta, ei)
  }
  
  if (message) close(pb_eta)
  
  results_df <- do.call(rbind, results_list)
  
  if (cv.criteria %in% c("V&VH", "LinPred")) {
    results_df$Loss <- -2 * results_df$score  / n
    results_df$score <- NULL
    best_per_eta <- do.call(rbind, lapply(split(results_df, results_df$eta), function(df) df[which.min(df$Loss), , drop = FALSE]))
    best.idx <- which.min(best_per_eta$Loss)
  } else if (cv.criteria == "CIndex_pooled") {
    results_df$CIndex_pooled <- results_df$score; results_df$score <- NULL
    best_per_eta <- do.call(rbind, lapply(split(results_df, results_df$eta), function(df) df[which.max(df$CIndex_pooled), , drop = FALSE]))
    best.idx <- which.max(best_per_eta$CIndex_pooled)
  } else {
    results_df$CIndex_foldaverage <- results_df$score; results_df$score <- NULL
    best_per_eta <- do.call(rbind, lapply(split(results_df, results_df$eta), function(df) df[which.max(df$CIndex_foldaverage), , drop = FALSE]))
    best.idx <- which.max(best_per_eta$CIndex_foldaverage)
  }
  rownames(best_per_eta) <- NULL
  
  beta_best_mat <- sapply(seq_along(etas), function(i) {
    beta_mat   <- fit_beta_list[[i]]
    lambda_seq <- lambda_list[[i]]
    
    idx <- which(abs(lambda_seq - best_per_eta$lambda[i]) < 1e-12)
    if (length(idx) != 1) {
      idx <- which.min(abs(lambda_seq - best_per_eta$lambda[i]))
    }
    beta_mat[, idx]
  })
  colnames(beta_best_mat) <- etas
  
  best_res <- list(best_eta = best_per_eta$eta[best.idx],
                   best_lambda = best_per_eta$lambda[best.idx],
                   best_beta = beta_best_mat[, best.idx],
                   criteria = cv.criteria)
  
  
  structure(
    list(
      best = best_res,
      integrated_stat.full_results = results_df,
      integrated_stat.best_per_eta = best_per_eta,
      integrated_stat.betahat_best = beta_best_mat,
      criteria = cv.criteria,
      nfolds = nfolds
    ),
    class = "cv.cox_MDTL_ridge"
  )
}