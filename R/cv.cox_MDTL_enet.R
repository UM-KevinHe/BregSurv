#' Cross-Validation for Cox MDTL with Elastic Net Regularization
#'
#' @description
#' Performs k-fold cross-validation to simultaneously tune the hyperparameter \code{eta}
#' (transfer learning weight) and the regularization parameter \code{lambda} for the
#' Cox MDTL model with an Elastic Net penalty.
#'
#' This function evaluates the model performance across a grid of \code{eta} and \code{lambda}
#' values to select the optimal combination that minimizes the chosen loss function or
#' maximizes the C-index.
#'
#' @param z A numeric matrix or data frame of covariates (n x p).
#' @param delta A numeric vector of event indicators (1 = event, 0 = censored).
#' @param time A numeric vector of observed times.
#' @param stratum Optional numeric or factor vector indicating strata. If \code{NULL},
#'   all subjects are assumed to be in the same stratum.
#' @param beta A numeric vector of external coefficients (length p).
#' @param Q Optional numeric matrix (p x p) representing the weighting matrix \eqn{Q}
#'   for the Mahalanobis penalty. This should be a symmetric positive-semidefinite
#'   \emph{precision} matrix (typically the inverse covariance / information matrix of
#'   the external estimator). If named, it is reordered and zero-padded to
#'   \code{colnames(z)}. If \code{NULL}, a masked identity is used.
#' @param etas A numeric vector of candidate \code{eta} values to be evaluated.
#' @param alpha The Elastic Net mixing parameter, with \eqn{0 \le \alpha \le 1}.
#'   \code{alpha = 1} is the Lasso penalty, and \code{alpha = 0} is the Ridge penalty.
#'   If \code{NULL}, defaults to 1 (Lasso).
#' @param lambda Optional user-supplied lambda sequence. If \code{NULL}, typical usage
#'   is to have the program compute its own \code{lambda} sequence based on \code{nlambda}
#'   and \code{lambda.min.ratio}.
#' @param nlambda The number of \code{lambda} values. Default is 100.
#' @param lambda.min.ratio Smallest value for \code{lambda}, as a fraction of \code{lambda.max}.
#'   Default depends on the sample size relative to the number of predictors.
#' @param nfolds Integer. Number of cross-validation folds. Default is 5.
#' @param cv.criteria Character string specifying the cross-validation criterion. Choices are:
#'   \itemize{
#'     \item \code{"V&VH"} (default): Verweij & Van Houwelingen partial likelihood loss.
#'     \item \code{"LinPred"}: Loss based on the prognostic performance of the linear predictor.
#'     \item \code{"CIndex_pooled"}: Harrell's C-index computed by pooling predictions across folds.
#'     \item \code{"CIndex_foldaverage"}: Harrell's C-index computed within each fold and averaged.
#'   }
#' @param c_index_stratum Optional stratum vector. Required only when \code{cv.criteria} involves
#'   stratified C-index calculation but the model itself is unstratified.
#' @param message Logical. If \code{TRUE}, progress messages are printed.
#' @param seed Optional integer. Random seed for reproducible fold assignment.
#' @param ... Additional arguments passed to the underlying fitting function.
#'
#' @return An object of class \code{"cv.cox_MDTL_enet"} containing:
#' \describe{
#'   \item{\code{best}}{A list containing the optimal results:
#'     \itemize{
#'       \item \code{best_eta}: The selected eta value.
#'       \item \code{best_lambda}: The selected lambda value.
#'       \item \code{best_beta}: The coefficient vector corresponding to the optimal parameters.
#'       \item \code{criteria}: The selection criterion used.
#'     }
#'   }
#'   \item{\code{integrated_stat.full_results}}{A data frame of performance metrics for all combinations of eta and lambda.}
#'   \item{\code{integrated_stat.best_per_eta}}{A data frame summarizing the best lambda and performance metric for each eta.}
#'   \item{\code{integrated_stat.betahat_best}}{A matrix of coefficients for the best lambda at each eta.}
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
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#'
#' cv.cox_MDTL_enet_est <- cv.cox_MDTL_enet(
#'   z = train_dat_highdim$z,
#'   delta = train_dat_highdim$status,
#'   time = train_dat_highdim$time,
#'   stratum = train_dat_highdim$stratum,
#'   beta = beta_external_highdim,
#'   Q = NULL,
#'   etas = eta_list,
#'   alpha = 1,
#'   cv.criteria = "CIndex_pooled",
#'   message = TRUE
#' )
#' }
#'
#' @export
cv.cox_MDTL_enet <- function(z, delta, time, stratum = NULL,
                             beta, Q = NULL,
                             etas = NULL, alpha = NULL,
                             lambda = NULL, nlambda = 100, lambda.min.ratio = ifelse(n < p, 0.05, 1e-03),
                             nfolds = 5,
                             cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                             c_index_stratum = NULL,
                             message = FALSE, seed = NULL, ...) {
  
  n <- nrow(z)
  p <- ncol(z)
  
  if (is.null(alpha)) {
    warning("alpha is not provided. Setting alpha = 1 (lasso penalty).", call. = FALSE)
    alpha <- 1
  } else if (alpha > 1 | alpha <= 0) {
    stop("alpha must be in (0, 1]", call. = FALSE)
  }
  
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
  
  n.each_stratum_full <- as.numeric(table(stratum))
  
  ## CV folds
  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold(nfolds = nfolds, delta = delta, stratum = stratum)
  
  results_list <- list()
  n_eta <- length(etas)
  
  
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
      fit0 <- cox_MDTL_enet(
        z = z, delta = delta, time = time, stratum = stratum,
        beta = beta, Q = Q,
        eta = eta, alpha = alpha,
        lambda = NULL, nlambda = nlambda, lambda.min.ratio = lambda.min.ratio,
        message = FALSE, data_sorted = TRUE, ...
      )
      lambda_seq <- as.vector(fit0$lambda)
    } else {
      lambda_seq <- sort(lambda, decreasing = TRUE)
      fit0 <- cox_MDTL_enet(
        z = z, delta = delta, time = time, stratum = stratum,
        beta = beta, Q = Q,
        eta = eta, alpha = alpha,
        lambda = lambda_seq,
        message = FALSE, data_sorted = TRUE, ...
      )
    }
    
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
    
    ## Loop over folds
    for (f in seq_len(nfolds)) {
      train_idx <- which(folds != f)
      test_idx  <- which(folds == f)
      
      ## Fit full lambda path on training fold
      fit_f <- cox_MDTL_enet(
        z = z[train_idx, , drop = FALSE],
        delta = delta[train_idx],
        time = time[train_idx],
        stratum = stratum[train_idx],
        beta = beta, Q = Q,
        eta = eta, alpha = alpha,
        lambda = lambda_seq,
        message = FALSE, data_sorted = TRUE, ...
      )
      
      beta_mat <- fit_f$beta
      LP_train <- z[train_idx, , drop = FALSE] %*% beta_mat
      LP_all   <- z %*% beta_mat
      LP_test  <- z[test_idx, , drop = FALSE] %*% beta_mat
      
      ## Compute fold-wise CV metric
      if (cv.criteria == "V&VH") {
        n.each_stratum_train <- as.numeric(table(stratum[train_idx]))
        n.each_stratum_all   <- as.numeric(table(stratum))
        pl_all <- apply(LP_all, 2, function(col) pl_cal_theta(col, delta, n.each_stratum_all))
        pl_tr  <- apply(LP_train, 2, function(col) pl_cal_theta(col, delta[train_idx], n.each_stratum_train))
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
  
  best_res <- list(
    best_eta = best_per_eta$eta[best.idx],
    best_lambda = best_per_eta$lambda[best.idx],
    best_beta = beta_best_mat[, best.idx],
    criteria = cv.criteria
  )
  
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
    class = "cv.cox_MDTL_enet"
  )
}