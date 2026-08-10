#' Cross-Validation for CoxKL Model with Elastic Net & Lasso Penalty
#'
#' @description
#' Performs k-fold cross-validation to tune the hyperparameters for the high-dimensional
#' Cox proportional hazards model with Kullback–Leibler (KL) divergence penalty.
#'
#' This function primarily tunes the external information weight \code{eta}.
#' For each candidate \code{eta}, it internally validates the optimal regularization
#' parameter \code{lambda}.
#'
#' @details
#' The function iterates through the provided \code{etas}. For each \code{eta},
#' it performs cross-validation (based on \code{nfolds}) to select the optimal \code{lambda}
#' and computes the corresponding cross-validation score.
#'
#' The available criteria for selection are:
#' \itemize{
#'   \item \code{"V&VH"}: The Verweij & Van Houwelingen partial likelihood loss (default).
#'   \item \code{"LinPred"}: Loss based on the prognostic performance of the linear predictor.
#'   \item \code{"CIndex_pooled"}: Harrell's C-index computed by pooling linear predictors across folds.
#'   \item \code{"CIndex_foldaverage"}: Harrell's C-index computed within each fold and averaged.
#' }
#'
#' @param z Numeric matrix of covariates. Rows represent individuals and columns represent predictors.
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of observed times (event or censoring).
#' @param stratum Optional numeric or factor vector indicating strata. If \code{NULL},
#'   all subjects are assumed to be in the same stratum.
#' @param RS Optional numeric vector or matrix of external risk scores. If not provided,
#'   \code{beta} must be supplied.
#' @param beta Optional numeric vector of external coefficients (length equal to \code{ncol(z)}).
#'   If provided, it is used to compute external risk scores. If not provided, \code{RS} must be supplied.
#' @param etas Numeric vector of candidate \code{eta} values to be evaluated.
#' @param alpha Elastic-net mixing parameter in \eqn{(0,1]}. Default is \code{1} (lasso penalty).
#' @param lambda Optional numeric vector of lambda values. If \code{NULL}, a path is generated automatically.
#' @param nlambda Integer. Number of lambda values to generate if \code{lambda} is NULL. Default is 100.
#' @param lambda.min.ratio Numeric. Ratio of min/max lambda.
#'   Default depends on sample size vs dimension (0.05 if n < p, else 1e-03).
#' @param nfolds Integer. Number of cross-validation folds. Default is \code{5}.
#' @param cv.criteria Character string specifying the cross-validation criterion for selecting
#'   both \code{eta} and \code{lambda}. Choices are:
#'   \itemize{
#'     \item \code{"V&VH"} (default): V&VH loss.
#'     \item \code{"LinPred"}: Loss based on cross-validated linear predictors.
#'     \item \code{"CIndex_pooled"}: Pooled C-Index.
#'     \item \code{"CIndex_foldaverage"}: Average C-Index across folds.
#'   }
#' @param c_index_stratum Optional stratum vector. Required only when \code{cv.criteria} is set
#'   to \code{"CIndex_pooled"} or \code{"CIndex_foldaverage"}, and a stratified C-index needs
#'   to be computed while the fitted model is non-stratified. Default is \code{NULL}.
#' @param message Logical. Whether to print progress messages. Default is \code{FALSE}.
#' @param seed Optional integer. Random seed for reproducible fold assignment.
#' @param ... Additional arguments passed to the underlying fitting function \code{\link{coxkl_enet}}.
#'
#' @return An object of class \code{"cv.coxkl_enet"}. A list containing:
#' \describe{
#'   \item{\code{best}}{A list with the optimal parameters:
#'     \itemize{
#'       \item \code{best_eta}: The selected eta value.
#'       \item \code{best_lambda}: The selected lambda value.
#'       \item \code{best_beta}: The coefficient vector corresponding to the best eta and lambda.
#'       \item \code{criteria}: The criterion used for selection.
#'     }
#'   }
#'   \item{\code{integrated_stat.full_results}}{A \code{data.frame} containing the performance metric
#'     for every combination of \code{eta} and \code{lambda}.}
#'   \item{\code{integrated_stat.best_per_eta}}{A \code{data.frame} containing the best lambda and
#'     corresponding score for each candidate \code{eta}.}
#'   \item{\code{integrated_stat.betahat_best}}{A matrix of coefficients where each column corresponds
#'     to the optimal model for a specific \code{eta}.}
#'   \item{\code{criteria}}{The selection criterion used.}
#'   \item{\code{alpha}}{The elastic net mixing parameter used.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 100)
#'
#' cv.coxkl_enet_est <- cv.coxkl_enet(
#'    z = train_dat_highdim$z,
#'    delta = train_dat_highdim$status,
#'    time = train_dat_highdim$time,
#'    stratum = train_dat_highdim$stratum,
#'    beta = beta_external_highdim,
#'    etas = eta_list,
#'    alpha = 1,
#'    cv.criteria = "CIndex_pooled"
#' )
#' }
#'
#' @export
cv.coxkl_enet <- function(z, delta, time, stratum = NULL, RS = NULL, beta = NULL,
                          etas, alpha = 1.0,
                          lambda = NULL, nlambda = 100, lambda.min.ratio = ifelse(n < p, 0.05, 1e-03),
                          nfolds = 5,
                          cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                          c_index_stratum = NULL,
                          message = FALSE, seed = NULL, ...) {
  
  ## Input check & data preparation
  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  check_etas(etas)
  etas <- sort(etas)
  cv.criteria <- match.arg(cv.criteria, choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))

  if (alpha > 1 | alpha <= 0) stop("alpha must be in (0,1]", call. = FALSE)

  if (is.null(RS) && is.null(beta)) {
    stop("No external information is provided. Either RS or beta must be provided.")
  } else if (is.null(RS) && !is.null(beta)) {
    beta <- align_beta(z, beta)
    RS <- as.matrix(z) %*% as.matrix(beta)
  } else {
    RS <- as.matrix(RS)
  }
  
  if (is.null(stratum)) {
    warning("Stratum not provided. Treating all data as one stratum.", call. = FALSE)
    stratum <- rep(1, nrow(z))
  } else {
    if (!is.null(c_index_stratum) & !identical(stratum, c_index_stratum)) {
      stop("Provided 'c_index_stratum' not identical to 'stratum'!")
    }
    stratum <- match(stratum, unique(stratum))
  }
  
  ## Sort data
  time_order <- order(stratum, time)
  time <- as.numeric(time[time_order])
  stratum <- as.numeric(stratum[time_order])
  z <- as.matrix(z)[time_order, , drop = FALSE]
  delta <- as.numeric(delta[time_order])
  RS <- RS[time_order, , drop = FALSE]
  n <- nrow(z)
  p <- ncol(z)
  n.each_stratum_full <- as.numeric(table(stratum))
  
  ## CV folds
  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold(nfolds = nfolds, delta = delta, stratum = stratum)
  
  results_list <- list()
  n_eta <- length(etas)
  
  ## External baseline accumulators
  if (cv.criteria == "V&VH") {
    pl_full_RS <- pl_cal_theta(as.vector(RS), delta, n.each_stratum_full)
    ext_vvh_per_fold <- numeric(nfolds)
  } else if (cv.criteria == "CIndex_pooled") {
    ext_numer <- numeric(nfolds); ext_denom <- numeric(nfolds)
  } else if (cv.criteria == "CIndex_foldaverage") {
    ext_c_per_fold <- numeric(nfolds)
  }
  
  if (message) {
    cat("Cross-validation over etas sequence:\n")
    pb_eta <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }
  
  fit_beta_list <- vector("list", length(etas))
  lambda_list <- vector("list", length(etas))
  
  for (ei in seq_along(etas)) {
    eta <- etas[ei]
    
    ## Determine lambda path (on full data) & estimation on full data
    if (is.null(lambda)) {
      fit0 <- coxkl_enet(z = z, delta = delta, time = time, stratum = stratum,
                         RS = RS, eta = eta, alpha = alpha,
                         lambda = NULL, nlambda = nlambda, lambda.min.ratio = lambda.min.ratio,
                         data_sorted = TRUE, message = FALSE, ...)
      lambda_seq <- as.vector(fit0$lambda)
    } else {
      lambda_seq <- sort(lambda, decreasing = TRUE)
      fit0 <- coxkl_enet(z = z, delta = delta, time = time, stratum = stratum,
                         RS = RS, eta = eta, alpha = alpha,
                         lambda = lambda_seq, data_sorted = TRUE, message = FALSE, ...)
    }
    
    fit_beta_list[[ei]] <- fit0$beta
    lambda_list[[ei]]   <- lambda_seq
    
    L <- length(lambda_seq)
    
    ## Accumulators
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
    
    ## Loop over folds
    for (f in seq_len(nfolds)) {
      train_idx <- which(folds != f)
      test_idx  <- which(folds == f)
      
      ## Fit full lambda path on training fold
      fit_f <- coxkl_enet(z = z[train_idx, , drop = FALSE],
                          delta = delta[train_idx],
                          time = time[train_idx],
                          stratum = stratum[train_idx],
                          RS = RS[train_idx, , drop = FALSE],
                          eta = eta, alpha = alpha, lambda = lambda_seq,
                          data_sorted = TRUE, message = FALSE, ...)
      
      beta_mat <- fit_f$beta
      LP_train <- z[train_idx, ] %*% beta_mat
      LP_all   <- z %*% beta_mat
      LP_test  <- z[test_idx, ] %*% beta_mat
      
      ## Compute fold-wise CV metric
      if (cv.criteria == "V&VH") {
        n.each_stratum_train <- as.numeric(table(stratum[train_idx]))
        n.each_stratum_all   <- as.numeric(table(stratum))
        pl_all <- apply(LP_all,  2, function(col) pl_cal_theta(col, delta,         n.each_stratum_all))
        pl_tr  <- apply(LP_train,2, function(col) pl_cal_theta(col, delta[train_idx], n.each_stratum_train))
        vvh_sum <- vvh_sum + (pl_all - pl_tr)
      } else if (cv.criteria == "LinPred") {
        Y[test_idx, ] <- LP_test
      } else {
        if (is.null(c_index_stratum)) stratum_test <- stratum[test_idx] else stratum_test <- c_index_stratum[test_idx]
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
    
    ## Aggregate folds for this eta
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
  
  ## Best per eta
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
      alpha = alpha,
      nfolds = nfolds
    ),
    class = "cv.coxkl_enet"
  )
}




