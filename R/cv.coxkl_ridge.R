#' Cross-Validation for CoxKL Ridge Model (Tuning Eta and Lambda)
#'
#' @description
#' Performs k-fold cross-validation to tune the hyperparameters for the Cox proportional
#' hazards model with Kullback–Leibler (KL) divergence penalty and Ridge (L2) regularization.
#'
#' The function operates in two layers:
#' \enumerate{
#'   \item **Outer Loop (Eta):** Iterates through user-provided \code{etas} to control the weight of external information.
#'   \item **Inner Loop (Lambda):** For each \code{eta}, performs cross-validation to select the optimal Ridge penalty parameter \code{lambda}.
#' }
#'
#' @details
#' When \code{lambda} is not supplied, the Ridge lambda sequence is generated
#' internally by \code{\link{coxkl_ridge}} and always spans from \code{lambda.max}
#' down to an exact \code{0}, i.e. the last element of the path is the unpenalized
#' solution. This behaviour is fixed for the Ridge path and is therefore \emph{not}
#' configurable through a minimum-ratio argument; only the number of grid points
#' (\code{nlambda}), or an explicit \code{lambda} vector, is under user control.
#'
#' @param z Numeric matrix of covariates. Rows represent individuals and columns represent predictors.
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of observed times (event or censoring).
#' @param stratum Optional numeric or factor vector indicating strata. If \code{NULL},
#'   a warning is issued and all subjects are assumed to be in the same stratum.
#' @param RS Optional numeric vector or matrix of external risk scores. If not provided,
#'   \code{beta} must be supplied.
#' @param beta Optional numeric vector of external coefficients. If provided, used to
#'   compute external risk scores; if not provided, \code{RS} must be supplied. If
#'   \code{beta} is named, names are matched against \code{colnames(z)}: covariates
#'   absent from \code{beta} are set to 0 (with a message) and the vector is
#'   reordered, so an external source covering only a subset of the internal
#'   covariates may be supplied directly. An unnamed \code{beta} is aligned
#'   positionally and must have length \code{ncol(z)}. A one-column matrix with row
#'   names is accepted as a named vector. See \code{\link{align_beta}}.
#' @param etas Numeric vector of non-negative candidate \code{eta} values to be
#'   evaluated. Must be finite and \eqn{\ge 0}. The values are sorted in ascending
#'   order internally, and the rows of \code{integrated_stat.best_per_eta} /
#'   columns of \code{integrated_stat.betahat_best} follow that sorted order.
#' @param lambda Optional numeric vector of lambda values. If \code{NULL}, a path is generated automatically.
#' @param nlambda Integer. Number of lambda values to generate if \code{lambda} is \code{NULL}. Default is 100.
#' @param nfolds Integer. Number of cross-validation folds. Default is \code{5}.
#' @param cv.criteria Character string specifying the cross-validation criterion for selecting
#'   parameters. Choices are:
#'   \itemize{
#'     \item \code{"V&VH"} (default): Verweij & Van Houwelingen partial likelihood loss.
#'     \item \code{"LinPred"}: Loss based on the prognostic performance of the linear predictor.
#'     \item \code{"CIndex_pooled"}: Harrell's C-index computed by pooling predictions across folds.
#'     \item \code{"CIndex_foldaverage"}: Harrell's C-index computed within each fold and averaged.
#'   }
#' @param c_index_stratum Optional stratum vector. Required only when \code{cv.criteria} is set
#'   to \code{"CIndex_pooled"} or \code{"CIndex_foldaverage"} and stratification is needed for
#'   evaluation but not for model fitting. That use case is therefore only reachable when
#'   \code{stratum = NULL}: if \code{stratum} is supplied and \code{c_index_stratum} is not
#'   identical to it, the function stops with an error. Default is \code{NULL}.
#' @param message Logical. Whether to print progress messages. Default is \code{FALSE}.
#' @param seed Optional integer. Random seed for reproducible fold assignment.
#' @param ... Additional arguments passed to the underlying fitting function \code{\link{coxkl_ridge}}.
#'
#' @return An object of class \code{"cv.coxkl_ridge"}. A list containing:
#' \describe{
#'   \item{\code{best}}{A list with the optimal parameters:
#'     \itemize{
#'       \item \code{best_eta}: The selected eta value.
#'       \item \code{best_lambda}: The selected lambda value.
#'       \item \code{best_beta}: The coefficient vector corresponding to the best parameters.
#'       \item \code{criteria}: The criterion used for selection.
#'     }
#'   }
#'   \item{\code{integrated_stat.full_results}}{A \code{data.frame} containing the performance score
#'     (and loss if applicable) for every combination of \code{eta} and \code{lambda}.
#'     Besides \code{eta} and \code{lambda} it carries a single metric column named
#'     after the selected criterion: \code{Loss} for \code{"V&VH"} and
#'     \code{"LinPred"}, otherwise \code{CIndex_pooled} or
#'     \code{CIndex_foldaverage}.}
#'   \item{\code{integrated_stat.best_per_eta}}{A \code{data.frame} summarizing the best lambda
#'     and corresponding score for each candidate \code{eta}, with the same
#'     criterion-named metric column.}
#'   \item{\code{integrated_stat.betahat_best}}{A matrix of coefficients where each column corresponds
#'     to the optimal model for a specific \code{eta}.}
#'   \item{\code{criteria}}{The selection criterion used.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' beta_external_highdim <- ExampleData_highdim$beta_external
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#' 
#' cv.coxkl_ridge_est <- cv.coxkl_ridge(
#'    z = train_dat_highdim$z,
#'    delta = train_dat_highdim$status,
#'    time = train_dat_highdim$time,
#'    stratum = train_dat_highdim$stratum,
#'    beta = beta_external_highdim,
#'    etas = eta_list,
#'    cv.criteria = "CIndex_pooled"
#' )
#' }
#'
#' @export
cv.coxkl_ridge <- function(z, delta, time, stratum = NULL, RS = NULL, beta = NULL, etas,
                           lambda = NULL, nlambda = 100,
                           nfolds = 5,
                           cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                           c_index_stratum = NULL,
                           message = FALSE, seed = NULL, ...) {
  
  ## ---- Input Check & Preparation ----
  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  check_etas(etas)
  etas <- sort(etas)
  cv.criteria <- match.arg(cv.criteria, choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))

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
      stop("The provided 'c_index_stratum' is not identical to 'stratum'!")
    }
    stratum <- match(stratum, unique(stratum))
  }
  
  ## ---- Sort Data ----
  time_order <- order(stratum, time)
  time <- as.numeric(time[time_order])
  stratum <- as.numeric(stratum[time_order])
  z <- as.matrix(z)[time_order, , drop = FALSE]
  delta <- as.numeric(delta[time_order])
  RS <- RS[time_order, , drop = FALSE]
  
  n_obs <- nrow(z)
  n_vars <- ncol(z)
  n.each_stratum_full <- as.numeric(table(stratum))

  ## ---- CV Folds ----
  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold(nfolds = nfolds, delta = delta, stratum = stratum)
  
  n_eta <- length(etas)
  results_list <- list()
  
  if (message) {
    cat("Cross-validation over eta sequence:\n")
    pb_eta <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
  }
  
  fit_beta_list <- vector("list", length(etas))
  lambda_list <- vector("list", length(etas))
  
  ## ---- Main Loop over Etas ----
  for (ei in seq_along(etas)) {
    eta <- etas[ei]
    
    ## 1. Fit on Full Data (to get lambda sequence and warm start)
    if (is.null(lambda)) {
      fit0 <- coxkl_ridge(z = z, delta = delta, time = time, stratum = stratum,
                          RS = RS, eta = eta, lambda = NULL,
                          nlambda = nlambda, penalty.factor = 1 - 1e-4, # implicit assumption for ridge gen
                          data_sorted = TRUE, message = FALSE, ...) # coxkl_ridge hard-codes lambda.min.ratio = 0 (path ends at the unpenalized solution)
      lambda_seq <- as.vector(fit0$lambda)
    } else {
      lambda_seq <- sort(lambda, decreasing = TRUE)
      fit0 <- coxkl_ridge(z = z, delta = delta, time = time, stratum = stratum,
                          RS = RS, eta = eta, lambda = lambda_seq,
                          data_sorted = TRUE, message = FALSE, ...)
    }
    
    # Store full fit results
    fit_beta_list[[ei]] <- fit0$beta
    lambda_list[[ei]] <- lambda_seq
    beta_initial.fit0 <- fit0$beta[, 1] # Warm start for first fold
    
    L <- length(lambda_seq)
    
    ## 2. Initialize Accumulators
    if (cv.criteria == "V&VH") {
      vvh_sum <- rep(0, L)
    } else if (cv.criteria == "LinPred") {
      Y <- matrix(NA_real_, nrow = n_obs, ncol = L)
      colnames(Y) <- round(lambda_seq, 6)
    } else if (cv.criteria == "CIndex_pooled") {
      numer <- rep(0, L); denom <- rep(0, L)
    } else if (cv.criteria == "CIndex_foldaverage") {
      csum <- rep(0, L); cnt <- rep(0, L)
    }
    
    ## 3. Loop over Folds
    for (f in seq_len(nfolds)) {
      train_idx <- which(folds != f)
      test_idx  <- which(folds == f)
      
      beta_initial <- beta_initial.fit0
      
      # Fit on training fold
      fit_f <- coxkl_ridge(z = z[train_idx, , drop = FALSE],
                           delta = delta[train_idx],
                           time = time[train_idx],
                           stratum = stratum[train_idx],
                           RS = RS[train_idx, , drop = FALSE],
                           eta = eta, lambda = lambda_seq,
                           data_sorted = TRUE, message = FALSE,
                           beta_initial = beta_initial, ...)
      
      beta_mat <- fit_f$beta
      # Update warm start for next fold (using first lambda of current fold)
      beta_initial <- beta_mat[, 1]
      
      # Predict
      LP_train <- z[train_idx, , drop = FALSE] %*% beta_mat
      LP_all   <- z %*% beta_mat
      LP_test  <- z[test_idx, , drop = FALSE] %*% beta_mat
      
      # Evaluate
      if (cv.criteria == "V&VH") {
        n.each_stratum_train <- as.numeric(table(stratum[train_idx]))
        n.each_stratum_all   <- as.numeric(table(stratum))
        pl_all <- apply(LP_all,  2, function(col) pl_cal_theta(col, delta, n.each_stratum_all))
        pl_tr  <- apply(LP_train,2, function(col) pl_cal_theta(col, delta[train_idx], n.each_stratum_train))
        vvh_sum <- vvh_sum + (pl_all - pl_tr)
      } else if (cv.criteria == "LinPred") {
        Y[test_idx, ] <- LP_test
      } else {
        stratum_test <- if (is.null(c_index_stratum)) stratum[test_idx] else c_index_stratum[test_idx]
        
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
    } # end fold loop
    
    ## 4. Aggregate Scores for this Eta
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
  } # end eta loop
  
  if (message) close(pb_eta)
  
  results_df <- do.call(rbind, results_list)
  
  ## ---- Find Best Parameters ----
  if (cv.criteria %in% c("V&VH", "LinPred")) {
    results_df$Loss <- -2 * results_df$score / n_obs
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
  
  # Extract best beta for each eta
  beta_best_mat <- sapply(seq_along(etas), function(i) {
    beta_mat   <- fit_beta_list[[i]]
    lambda_seq <- lambda_list[[i]]
    target_lambda <- best_per_eta$lambda[i]
    
    idx <- which(abs(lambda_seq - target_lambda) < 1e-12)
    if (length(idx) != 1) {
      idx <- which.min(abs(lambda_seq - target_lambda))
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
    class = "cv.coxkl_ridge"
  )
}
  
