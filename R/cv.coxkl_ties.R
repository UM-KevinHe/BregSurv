#' Cross-Validated Cox–KL with Ties Handling to Tune the Integration Parameter (eta)
#'
#' @description
#' Performs K-fold cross-validation (CV) to select the optimal integration parameter \code{eta}
#' for the Cox Proportional Hazards model with Kullback–Leibler (KL) divergence data
#' integration, using the Breslow or Exact partial likelihood for tied event times.
#'
#' @details
#' The function returns results in the format of a \code{cv.coxkl} object, allowing
#' downstream processing compatible with non-ties-handling Cox-KL models. The
#' \code{ties} argument controls which form of the partial likelihood (PL) is used
#' for both model fitting and CV criterion calculation.
#'
#' @param z Numeric matrix of covariates (rows = observations, columns = variables).
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of observed event or censoring times.
#' @param stratum Optional numeric or factor vector defining strata.
#' @param beta Numeric vector of external coefficients. **Required**.
#' @param etas Numeric vector of candidate tuning values to be cross-validated.
#' @param ties Character string specifying the method for handling ties. Must be one of
#'   \code{"breslow"} (default) or \code{"exact"}.
#' @param tol Convergence tolerance for the optimizer used inside `coxkl_ties`. Default \code{1e-4}.
#' @param Mstop Maximum number of Newton iterations used inside `coxkl_ties`. Default \code{100}.
#' @param nfolds Number of cross-validation folds. Default \code{5}.
#' @param cv.criteria Character string specifying the performance criterion.
#'   Choices are `"V&VH"`, `"LinPred"`, `"CIndex_pooled"`, or `"CIndex_foldaverage"`.
#'   Default `"CIndex_pooled"`.
#' @param c_index_stratum Optional stratum vector. Used for C-index calculation on test sets.
#' @param message Logical; if \code{TRUE}, prints progress messages. Default \code{FALSE}.
#' @param seed Optional integer seed for reproducible fold assignment. Default \code{NULL}.
#' @param comb_max Integer. Maximum number of combinations for the **Exact** partial likelihood calculation.
#'   Only relevant if \code{ties = "exact"}. Default \code{1e7}.
#' @param ... Additional arguments (currently ignored).
#'
#' @return A \code{list} of class \code{"cv.coxkl"} containing:
#' \describe{
#'    \item{\code{internal_stat}}{A \code{data.frame} with one row per \code{eta} and the CV metric results.}
#'    \item{\code{best}}{A list containing the \code{best_eta}, the corresponding \code{best_beta} from the full model fit, and the \code{criteria} used.}
#'    \item{\code{criteria}}{The criterion used for selection.}
#'    \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' train_dat_lowdim$time <- round(train_dat_lowdim$time, 2)  # Rounding time introduces ties for demonstration
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#' 
#' coxkl_ties.fit_breslow <- cv.coxkl_ties(
#'     z = train_dat_lowdim$z,
#'     delta = train_dat_lowdim$status,
#'     time = train_dat_lowdim$time,
#'     stratum = train_dat_lowdim$stratum,
#'     beta = ExampleData_lowdim$beta_external_fair,
#'     etas = eta_list,
#'     ties = "breslow",
#'     nfolds = 5,
#'     cv.criteria = "V&VH",
#'     seed = 42
#' )
#' }
#' @export
cv.coxkl_ties <- function(z, delta, time, stratum = NULL,
                          beta = NULL,
                          etas = NULL,
                          ties = c("breslow","exact"),
                          tol = 1.0e-4, Mstop = 100,
                          nfolds = 5,
                          cv.criteria = c("CIndex_pooled", "V&VH", "LinPred", "CIndex_foldaverage"),
                          c_index_stratum = NULL,
                          message = FALSE,
                          seed = NULL,
                          comb_max = 1e7, ...) {
  
  cv.criteria <- match.arg(cv.criteria, choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))
  ties <- match.arg(tolower(ties), c("exact","breslow"))
  
  ## --- Internal wrapper function to handle comb_max argument ---
  pl_cal_wrapper <- function(lp, delta, time, n_each_stratum, ties, comb_max) {
    if (ties == "exact") {
      # Pass comb_max only when ties == "exact"
      pl_cal_exact(lp = lp, delta = delta, time = time, n_each_stratum = n_each_stratum, comb_max = comb_max)
    } else {
      # Call pl_cal_breslow without comb_max
      pl_cal_breslow(lp = lp, delta = delta, time = time, n_each_stratum = n_each_stratum)
    }
  }
  
  ## Check and prepare external coefficients
  if (is.null(beta)) stop("The 'beta' (external coefficients) must be provided for cv.coxkl_ties.", call. = FALSE)
  if (length(beta) != ncol(z)) stop("The dimension of beta does not match the number of columns in z.")
  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas <- sort(etas)
  
  ## Process stratum
  if (is.null(stratum)) {
    if (message) warning("Stratum not provided. Treating all data as one stratum.", call. = FALSE)
    stratum <- rep(1, nrow(z))
  } else {
    if (!is.null(c_index_stratum) & !identical(stratum, c_index_stratum)) {
      stratum_orig <- stratum
    }
    stratum <- match(stratum, unique(stratum))
  }
  
  ## Sort data by stratum and time
  time_order <- order(stratum, time)
  time <- as.numeric(time[time_order])
  stratum <- as.numeric(stratum[time_order])
  z <- as.matrix(z)[time_order, , drop = FALSE]
  delta <- as.numeric(delta[time_order])
  
  n <- nrow(z)
  n_eta <- length(etas)
  
  ## Precompute counts per stratum for full data
  n.each_stratum_full <- as.numeric(table(stratum))
  
  # 1. Fit a full model to get beta_full for the final 'best' output
  if (message) message("Fitting full model for all etas...")
  # Assumes coxkl_ties handles data_sorted=TRUE internally
  full_estimate <- coxkl_ties(z = z,
                              delta = delta,
                              time = time,
                              stratum = stratum,
                              beta = beta,
                              etas = etas,
                              ties = ties,
                              tol = tol,
                              Mstop = Mstop,
                              message = FALSE,
                              data_sorted = TRUE,
                              comb_max = comb_max)
  
  beta_full <- full_estimate$beta
  
  ## Fix seed for reproducibility and create folds
  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold(nfolds = nfolds, delta = delta, stratum = stratum)
  
  ## Storage for internal CV results
  result_mat <- matrix(NA_real_, nrow = nfolds, ncol = n_eta)
  if (cv.criteria == "LinPred") {
    cv_all_linpred <- matrix(NA, nrow = n, ncol = n_eta)
  } else if (cv.criteria == "CIndex_pooled") {
    cv_pooled_cindex_array <- array(0, dim = c(nfolds, n_eta, 2))
  }
  
  ## Outer loop over folds
  for (f in seq_len(nfolds)) {
    if (message) message(sprintf("CV fold %d/%d starts...", f, nfolds))
    
    train_idx <- which(folds != f)
    test_idx <- which(folds == f)
    
    z_train <- z[train_idx, , drop = FALSE]
    delta_train <- delta[train_idx]
    time_train <- time[train_idx]
    stratum_train <- stratum[train_idx]
    
    z_test <- z[test_idx, , drop = FALSE]
    delta_test <- delta[test_idx]
    time_test <- time[test_idx]
    
    n.each_stratum_train <- as.numeric(table(stratum_train))
    beta_initial <- rep(0, ncol(z)) # warm start for each fold
    
    if (message) {
      cat("Fitting eta sequence:\n")
      pb <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
    }
    
    # --- Pre-calculate WTilde for the current fold (using external beta) ---
    if (ties == "exact") {
      WTilde_train <- calculateWTilde_exact(
        Z = z_train,
        delta = delta_train,
        time = time_train,
        n_each_stratum = n.each_stratum_train,
        external_beta = as.numeric(beta),
        comb_max = comb_max
      )
    } else { # breslow
      RS_train <- as.numeric(z_train %*% beta)
      WTilde_train <- calculateWTilde_breslow(
        Z = z_train,
        delta = delta_train,
        time = time_train,
        risk_score_ext = RS_train,
        n_each_stratum = n.each_stratum_train
      )
    }
    
    # --- Loop over eta sequence ---
    for (i in seq_along(etas)) {
      eta <- etas[i]
      
      # Fit model on training data (CoxKL_NR_* functions)
      if (ties == "exact") {
        beta_hat <- CoxKL_NR_exact(
          Z = z_train, delta = delta_train, time = time_train,
          n_each_stratum = n.each_stratum_train, tildeW = WTilde_train,
          eta = eta, beta = beta_initial, tol = tol, max_iter = Mstop,
          comb_max = comb_max
        )
      } else { # breslow
        beta_hat <- CoxKL_NR_breslow(
          Z = z_train, delta = delta_train, time = time_train,
          n_each_stratum = n.each_stratum_train, Wtilde = WTilde_train,
          eta = eta, beta = beta_initial, tol = tol, max_iter = Mstop
        )
      }
      
      beta_hat <- as.numeric(beta_hat)
      beta_initial <- beta_hat # warm start
      
      # EVALUATE on TEST
      LP_test <- as.numeric(z_test %*% beta_hat)
      
      # --- Criteria Evaluation ---
      if (cv.criteria == "V&VH") {
        LP_train <- as.numeric(z_train %*% beta_hat)
        LP_internal <- as.numeric(z %*% beta_hat)
        
        # Use pl_cal_wrapper to handle parameter mismatch
        # V&VH = PL(full, beta_hat) - PL(train, beta_hat)
        result_mat[f, i] <-
          pl_cal_wrapper(lp = LP_internal, delta = delta, time = time, 
                         n_each_stratum = n.each_stratum_full, ties = ties, comb_max = comb_max) -
          pl_cal_wrapper(lp = LP_train, delta = delta_train, time = time_train, 
                         n_each_stratum = n.each_stratum_train, ties = ties, comb_max = comb_max)
        
      } else if (cv.criteria == "LinPred") {
        cv_all_linpred[test_idx, i] <- LP_test
        
      } else {
        # C-Index cv.criteria
        if (is.null(c_index_stratum)) {
          stratum_test <- stratum[test_idx]
        } else {
          # Map c_index_stratum using the full data order
          stratum_test_orig <- c_index_stratum[time_order]
          stratum_test <- stratum_test_orig[test_idx]
        }
        
        if (cv.criteria == "CIndex_pooled") {
          cstat <- c_stat_stratcox(time_test, LP_test, stratum_test, delta_test)
          cv_pooled_cindex_array[f, i, ] <- c(cstat$numer, cstat$denom)
          
        } else if (cv.criteria == "CIndex_foldaverage") {
          cstat <- c_stat_stratcox(time_test, LP_test, stratum_test, delta_test)$c_statistic
          result_mat[f, i] <- cstat
        }
      }
      if (message) setTxtProgressBar(pb, i)
    }
    if (message) close(pb)
  } # End fold loop
  
  ## Combine CV results across folds (internal model)
  if (cv.criteria == "V&VH") {
    result_vec <- colSums(result_mat, na.rm = TRUE)
  } else if (cv.criteria == "LinPred") {
    # Use pl_cal_wrapper for LinPred aggregation
    result_vec <- apply(cv_all_linpred, 2,
                        function(lp) pl_cal_wrapper(lp = lp, delta = delta, time = time, 
                                                    n_each_stratum = n.each_stratum_full, 
                                                    ties = ties, comb_max = comb_max))
  } else if (cv.criteria == "CIndex_foldaverage") {
    result_vec <- colMeans(result_mat, na.rm = TRUE)
  } else if (cv.criteria == "CIndex_pooled") {
    numer <- apply(cv_pooled_cindex_array[,,1], 2, sum, na.rm = TRUE)
    denom <- apply(cv_pooled_cindex_array[,,2], 2, sum, na.rm = TRUE)
    result_vec <- numer / denom
  }
  
  ## Assemble internal results by eta
  results <- data.frame(eta = etas)
  if (cv.criteria == "V&VH") {
    results$VVH_Loss <- -2 * result_vec / n
    best_eta.idx <- which.min(results$VVH_Loss)
  } else if (cv.criteria == "LinPred") {
    results$LinPred_Loss <- -2 * result_vec / n
    best_eta.idx <- which.min(results$LinPred_Loss)
  } else if (cv.criteria == "CIndex_pooled") {
    results$CIndex_pooled <- result_vec
    best_eta.idx <- which.max(results$CIndex_pooled)
  } else if (cv.criteria == "CIndex_foldaverage") {
    results$CIndex_foldaverage <- result_vec
    best_eta.idx <- which.max(results$CIndex_foldaverage)
  }
  
  best_res <- list(best_eta = etas[best_eta.idx],
                   best_beta = beta_full[, best_eta.idx],
                   criteria = cv.criteria)
  
  # Final structure matches cv.coxkl
  structure(
    list(
      internal_stat = results,
      beta_full = beta_full,
      best = best_res,
      criteria = cv.criteria,
      nfolds = nfolds
    ),
    class = "cv.coxkl"
  )
}