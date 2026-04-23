#' Bayesian Optimization for the Cox–KL Integration Parameter (eta)
#'
#' @description
#' Employs Bayesian Optimization to find the optimal integration parameter `eta`
#' for the Cox–KL model by maximizing a cross-validated performance criterion.
#' The function wraps \code{\link{cv.coxkl}} and uses the \pkg{rBayesianOptimization}
#' framework to efficiently search the parameter space.
#'
#' @param z Numeric matrix of covariates.
#' @param delta Numeric vector of event indicators (1 = event, 0 = censored).
#' @param time Numeric vector of observed event or censoring times.
#' @param stratum Optional numeric or factor vector defining strata.
#' @param RS Optional numeric vector or matrix of external risk scores.
#' @param beta Optional numeric vector of external coefficients.
#' @param criteria Character string specifying the performance criterion.
#'   Choices are \code{"V&VH"}, \code{"LinPred"}, \code{"CIndex_pooled"},
#'   or \code{"CIndex_foldaverage"}.
#' @param bounds_list A named list defining the search range for \code{eta},
#'   e.g., \code{list(eta = c(0, 10))}.
#' @param init_grid_dt A \code{data.frame} of initial points for the optimization.
#'   Default is \code{0} if \code{init_grid_dt} is provided.
#' @param n_iter Number of iterations for the Bayesian Optimization process.
#' @param acq Acquisition function type. Default is \code{"ucb"}.
#' @param seed Optional integer seed to ensure reproducible CV fold assignments.
#' @param verbose Logical; if \code{TRUE}, progress of the optimization is printed.
#' @param ... Additional arguments passed to \code{\link{cv.coxkl}} and \code{\link{coxkl}}.
#'
#' @return A list containing:
#' \describe{
#'   \item{\code{best_eta}}{The optimal \code{eta} value discovered.}
#'   \item{\code{best_beta}}{The coefficient vector corresponding to \code{best_eta}.}
#'   \item{\code{best_score}}{The raw performance metric value at \code{best_eta}.}
#'   \item{\code{full_stats}}{A \code{data.frame} of all evaluated \code{eta} values and their scores, sorted by \code{eta}.}
#'   \item{\code{beta_matrix}}{A matrix where each column corresponds to the fitted \code{beta} for each \code{eta} in \code{full_stats}.}
#'   \item{\code{bo_object}}{The raw object returned by \code{BayesianOptimization}.}
#'   \item{\code{criteria}}{The criterion used for optimization.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_lowdim)
#' train_dat <- ExampleData_lowdim$train
#' beta_ext <- ExampleData_lowdim$beta_external_fair
#'
#' opt_res <- bopt.coxkl(
#'   z = train_dat$z,
#'   delta = train_dat$status,
#'   time = train_dat$time,
#'   stratum = train_dat$stratum,
#'   beta = beta_ext,
#'   criteria = "CIndex_pooled",
#'   bounds_list = list(eta = c(0, 10)),
#'   init_grid_dt = data.frame(eta = c(0, 1, 5)),
#'   n_iter = 20,
#'   nfolds = 5,
#'   seed = 2024
#' )
#' }
#' @export
bopt.coxkl <- function(z, delta, time, stratum = NULL,
                       RS = NULL, beta = NULL,
                       criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                       bounds_list = list(eta = c(0, 10)),
                       init_grid_dt = data.frame(eta = c(0, 1, 5)),
                       init_points = 0,
                       n_iter = 10,
                       acq = "ucb",
                       kappa = 2.576,
                       seed = NULL,
                       verbose = TRUE, ...) {

  library(rBayesianOptimization)

  target_criteria <- match.arg(criteria)

  if (is.null(seed)) {
    seed <- sample.int(1e6, 1)
  }

  internal_scoring_func <- function(eta) {
    cv_res <- cv.coxkl(
      z = z, delta = delta, time = time, stratum = stratum,
      RS = RS, beta = beta,
      etas = eta,
      cv.criteria = target_criteria,
      seed = seed,
      message = FALSE,
      ...
    )

    raw_val <- as.numeric(cv_res$internal_stat[[2]])

    if (target_criteria %in% c("V&VH", "LinPred")) {
      obj_score <- -raw_val
    } else {
      obj_score <- raw_val
    }

    return(list(
      Score = obj_score,
      Pred = list(
        eta = eta,
        beta = cv_res$beta_full,
        val = raw_val
      )
    ))
  }

  opt_res <- BayesianOptimization(
    FUN = internal_scoring_func,
    bounds = bounds_list,
    init_grid_dt = init_grid_dt,
    init_points = init_points,
    n_iter = n_iter,
    acq = acq,
    kappa = kappa,
    verbose = verbose
  )

  history_dt <- opt_res$Pred

  all_etas <- as.numeric(sapply(history_dt, function(x) x[[1]]))
  all_vals <- as.numeric(sapply(history_dt, function(x) x[[3]]))

  order_idx <- order(all_etas)
  sorted_etas <- all_etas[order_idx]

  sorted_betas <- do.call(cbind, lapply(order_idx, function(i) {
    b_val <- history_dt[[i]][[2]]
    return(as.numeric(b_val))
  }))

  if (!is.null(sorted_betas)) {
    colnames(sorted_betas) <- paste0("eta_", round(sorted_etas, 4))
  }

  stats_df <- data.frame(
    eta = sorted_etas,
    score_raw = all_vals[order_idx]
  )
  colnames(stats_df)[2] <- paste0(target_criteria, "_stat")

  best_eta <- as.numeric(opt_res$Best_Par)
  best_idx <- which.min(abs(sorted_etas - best_eta))

  if (length(best_idx) == 0 || is.na(best_idx)) {
    best_idx <- which.max(stats_df[[2]])
    best_eta <- stats_df$eta[best_idx]
  }

  out <- list(
    best_eta = best_eta,
    best_beta = sorted_betas[, best_idx],
    best_score = stats_df[best_idx, 2],
    full_stats = stats_df,
    beta_matrix = sorted_betas,
    bo_object = opt_res,
    criteria = target_criteria
  )

  return(out)
}

