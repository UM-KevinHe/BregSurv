#' Cross-Validation for Cox MDTL Model
#'
#' @description
#' Performs k-fold cross-validation to tune the hyperparameter \code{eta} for the
#' Cox Proportional Hazards Model with Mahalanobis Distance Transfer Learning.
#'
#' The function evaluates the model performance across a range of \code{eta} values
#' using specified cv.criteria (e.g., Verweij & Van Houwelingen loss, C-index) to select
#' the optimal weight for the external information.
#'
#' @param z A numeric matrix or data frame of covariates (n x p).
#' @param delta A numeric vector of event indicators (1 = event, 0 = censored).
#' @param time A numeric vector of observed times.
#' @param stratum Optional numeric or factor vector indicating strata. If \code{NULL},
#'   all subjects are assumed to be in the same stratum.
#' @param beta A numeric vector of external coefficients (length p).
#' @param vcov Optional numeric matrix (p x p) representing the weighting matrix \eqn{Q}
#'   for the Mahalanobis penalty. Typically the inverse covariance matrix. If \code{NULL},
#'   defaults to the identity matrix.
#' @param etas A numeric vector of candidate \code{eta} values to be evaluated.
#' @param tol Convergence tolerance for the optimization algorithm. Default is 1e-4.
#' @param Mstop Maximum number of iterations for the optimization. Default is 100.
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
#' @param ... Additional arguments passed to the underlying fitting function \code{\link{cox_MDTL}}.
#'
#' @return An object of class \code{"cv.Cox_MDTL"} containing:
#' \describe{
#'   \item{\code{internal_stat}}{A \code{data.frame} summarizing the performance metric (loss or C-index)
#'     for each candidate \code{eta}.}
#'   \item{\code{best}}{A list containing the optimal results:
#'     \itemize{
#'       \item \code{best_eta}: The selected eta value.
#'       \item \code{best_beta}: The coefficient vector corresponding to the optimal eta (refitted on full data).
#'       \item \code{criteria}: The criterion used for selection.
#'     }
#'   }
#'   \item{\code{criteria}}{The selection criterion used.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' beta_external_lowdim <- ExampleData_lowdim$beta_external_fair
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#'
#' cv.cox_MDTL_est <- cv.cox_MDTL(
#'   z = train_dat_lowdim$z,
#'   delta = train_dat_lowdim$status,
#'   time = train_dat_lowdim$time,
#'   beta = beta_external_lowdim,
#'   vcov = NULL,
#'   etas = eta_list,
#'   cv.criteria = "V&VH"
#' )
#' }
#'
#' @export
cv.cox_MDTL <- function(z, delta, time, stratum = NULL,
                        beta, vcov = NULL,
                        etas = NULL,
                        tol = 1.0e-4, Mstop = 100,
                        nfolds = 5,
                        cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                        c_index_stratum = NULL,
                        message = FALSE,
                        seed = NULL, ...) {

  cv.criteria <- match.arg(cv.criteria, choices = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas <- sort(etas)

  if (length(beta) != ncol(z)) {
    stop("Error: The dimension of external beta does not match the number of columns in z.")
  }

  if (is.null(vcov)) {
    Q <- diag(ncol(z))
  } else {
    if (nrow(vcov) != ncol(z) || ncol(vcov) != ncol(z)) {
      stop("Error: The dimension of external variance-covariance does not match the number of columns in z.")
    }
    Q <- vcov
  }


  ## Process stratum
  if (is.null(stratum)) {
    warning("Stratum not provided. Treating all data as one stratum.", call. = FALSE)
    stratum <- rep(1, nrow(z))
  } else {
    if (!is.null(c_index_stratum) & !identical(stratum, c_index_stratum)) {
      stop("The provided 'c_index_stratum' is not identical to 'stratum'!")
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

  n.each_stratum_full <- as.numeric(table(stratum))


  # fit a full model:
  full_estimate <- cox_MDTL(z = z,
                            delta = delta,
                            time = time,
                            stratum = stratum,
                            beta = beta,
                            vcov = Q,
                            etas = etas,
                            tol = tol,
                            Mstop = Mstop,
                            message = FALSE,
                            data_sorted = TRUE)
  beta_full <- full_estimate$beta


  # do cross-validation
  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold(nfolds = nfolds, delta = delta, stratum = stratum)

  result_mat <- matrix(NA_real_, nrow = nfolds, ncol = n_eta)
  if (cv.criteria == "LinPred") {
    cv_all_linpred <- matrix(NA, nrow = n, ncol = n_eta)
  } else if (cv.criteria == "CIndex_pooled") {
    cv_pooled_cindex_array <- array(0, dim = c(nfolds, n_eta, 2))
  }

  for (f in seq_len(nfolds)) {
    if (message) message(sprintf("CV fold %d/%d starts...", f, nfolds))

    train_idx <- which(folds != f)
    test_idx  <- which(folds == f)

    z_train <- z[train_idx, , drop = FALSE]
    delta_train <- delta[train_idx]
    time_train <- time[train_idx]
    stratum_train <- stratum[train_idx]

    beta_initial <- rep(0, ncol(z))  # warm start for each fold


    ## ----- Cross-validation over eta sequence (internal model) -----
    if (message) {
      cat("Cross-validation over eta sequence:\n")
      pb <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
    }

    for (i in seq_along(etas)) {
      eta <- etas[i]
      cox_estimate <- cox_MDTL(z = z_train,
                               delta = delta_train,
                               time = time_train,
                               stratum = stratum_train,
                               beta = beta,
                               vcov = Q,
                               etas = eta,
                               tol = tol,
                               Mstop = Mstop,
                               message = FALSE,
                               data_sorted = TRUE,
                               beta_initial = beta_initial)

      beta_train <- cox_estimate$beta
      beta_initial <- beta_train  # warm start

      z_test <- z[test_idx, , drop = FALSE]
      delta_test <- delta[test_idx]
      time_test <- time[test_idx]
      LP_test <- as.matrix(z_test) %*% as.matrix(beta_train)

      if (cv.criteria == "V&VH") {
        LP_train <- as.matrix(z_train) %*% as.matrix(beta_train)
        LP_internal <- as.matrix(z) %*% as.matrix(beta_train)
        n.each_stratum_train <- as.numeric(table(stratum_train))

        result_mat[f, i] <- pl_cal_theta(LP_internal, delta, n.each_stratum_full) -
          pl_cal_theta(LP_train, delta_train, n.each_stratum_train)

      } else if (cv.criteria == "LinPred") {
        cv_all_linpred[test_idx, i] <- LP_test
      } else {
        if (is.null(c_index_stratum)) {
          stratum_test <- stratum[test_idx]
        } else {
          stratum_test <- c_index_stratum[test_idx]
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
  }

  if (cv.criteria == "V&VH") {
    result_vec <- colSums(result_mat, na.rm = TRUE)
  } else if (cv.criteria == "LinPred") {
    result_vec <- apply(cv_all_linpred, 2,
                        function(lp) pl_cal_theta(lp, delta, as.numeric(table(stratum))))
  } else if (cv.criteria == "CIndex_foldaverage") {
    result_vec <- colMeans(result_mat, na.rm = TRUE)
  } else if (cv.criteria == "CIndex_pooled") {
    numer <- apply(cv_pooled_cindex_array[, , 1], 2, sum, na.rm = TRUE)
    denom <- apply(cv_pooled_cindex_array[, , 2], 2, sum, na.rm = TRUE)
    result_vec <- numer / denom
  }

  ## Assemble internal results by eta
  results <- data.frame(eta = etas)
  if (cv.criteria == "V&VH") {
    results$VVH_Loss <- -2 * result_vec  / n
    best_eta.idx <- which.min(results$VVH_Loss)
  } else if (cv.criteria == "LinPred") {
    results$LinPred_Loss <- -2 * result_vec  / n
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

  structure(
    list(
      internal_stat = results,
      beta_full = beta_full,
      best = best_res,
      criteria = cv.criteria,
      nfolds = nfolds
    ),
    class = "cv.cox_MDTL"
  )
}
