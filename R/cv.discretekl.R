#' Cross-Validated Discrete-Time KL Model to Tune the Integration Parameter (eta)
#'
#' Performs K-fold cross-validation to select the integration weight `eta` of [discretekl()]. Each
#' fold fits the model on the training subjects and scores it on the held-out subjects by their
#' negative log-likelihood under the grouped-time model; the scores are pooled over folds and divided
#' by the number of subjects. It is the discrete-time counterpart of [cv.coxkl()].
#'
#' @inheritParams discretekl
#' @param etas Numeric vector of non-negative candidate weights (required). Include `0` to compare
#'   with the target model alone.
#' @param nfolds Number of folds. Default `5`.
#' @param seed Optional integer seed of the fold assignment. Folds are assigned at random within the
#'   events and within the censored subjects (within strata when `stratum` is given), so the same seed
#'   gives the same folds to every model fitted on the same data.
#'
#' @return An object of class `"cv.discretekl"`:
#' \describe{
#'   \item{`internal_stat`}{A data frame with one row per `eta`: `eta` and `Loss`, the pooled held-out
#'     negative log-likelihood per subject (lower is better).}
#'   \item{`beta_full`}{Coefficients of the full-data fit, one column per `eta`.}
#'   \item{`best`}{A list with `best_eta`, `best_beta`, `best_gamma` (the baseline parameters, strata
#'     \eqn{\times K}), `best_value` (the selected `Loss`) and `criteria`.}
#'   \item{`criteria`}{`"loss"`.}
#'   \item{`nfolds`, `folds`, `seed`, `rng_kind`}{The folds used and how they were drawn.}
#'   \item{`link`, `K`, `strata_levels`}{The link, the number of intervals and the strata.}
#' }
#' @seealso [discretekl()], [cv.discretekl_ridge()], [cv.discretekl_enet()], [cv.plot()];
#'   [cv.bregsurv()] with [target_discrete()] and [release_model()].
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' cvfit <- cv.discretekl(z = tr$z, delta = tr$status, interval = tr$interval,
#'                        beta = ExampleData_discrete$beta_external,
#'                        baseline = ExampleData_discrete$baseline_external,
#'                        etas = c(0, 1, 5, 20), seed = 1)
#' cvfit$internal_stat
#' cvfit$best$best_eta
#' @export
cv.discretekl <- function(z, delta, interval, stratum = NULL, hazard = NULL, beta = NULL, baseline = NULL,
                          etas, link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                          tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  s <- .dt_setup("kl", z, delta, interval, stratum, link, n_intervals, standardize = TRUE,
                 hazard = hazard, beta = beta, baseline = baseline)
  .dt_cv_family(s, "none", etas, 0, NULL, NULL, NULL, nfolds, seed, tol, Mstop, "cv.discretekl", message)
}

#' Cross-Validated Discrete-Time KL Model with a Ridge Penalty
#'
#' Chooses the integration weight `eta` and the ridge penalty `lambda` of [discretekl_ridge()]
#' together, by K-fold cross-validation of the pooled held-out negative log-likelihood. A penalty path
#' is built for each `eta`. It is the discrete-time counterpart of [cv.coxkl_ridge()].
#'
#' @inheritParams cv.discretekl
#' @inheritParams discretekl_ridge
#' @param lambda Optional penalty values used for every `eta`; `NULL` builds a path for each `eta`.
#'
#' @return An object of class `"cv.discretekl_ridge"`:
#' \describe{
#'   \item{`best`}{A list with `best_eta`, `best_lambda`, `best_beta`, `best_gamma`, `best_value` and
#'     `criteria`.}
#'   \item{`integrated_stat.full_results`}{A data frame with `eta`, `lambda` and `Loss` for every
#'     combination.}
#'   \item{`integrated_stat.best_per_eta`}{The best `lambda` and its `Loss` for each `eta`.}
#'   \item{`integrated_stat.betahat_best`}{Coefficients at the best `lambda`, one column per `eta`.}
#'   \item{`criteria`, `nfolds`, `folds`, `seed`, `rng_kind`, `link`, `K`, `strata_levels`}{As in
#'     [cv.discretekl()].}
#' }
#' @seealso [discretekl_ridge()], [cv.discretekl_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' cvfit <- cv.discretekl_ridge(z = tr$z, delta = tr$status, interval = tr$interval,
#'                              beta = ExampleData_discrete$beta_external,
#'                              baseline = ExampleData_discrete$baseline_external,
#'                              etas = c(0, 1, 10), nlambda = 10, seed = 1)
#' cvfit$best[c("best_eta", "best_lambda", "best_value")]
#' @export
cv.discretekl_ridge <- function(z, delta, interval, stratum = NULL, hazard = NULL, beta = NULL, baseline = NULL,
                                etas, lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                                link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                                standardize = TRUE, tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  s <- .dt_setup("kl", z, delta, interval, stratum, link, n_intervals, standardize,
                 hazard = hazard, beta = beta, baseline = baseline)
  .dt_cv_family(s, "ridge", etas, 0, lambda, nlambda, lambda.min.ratio, nfolds, seed, tol, Mstop,
                "cv.discretekl_ridge", message)
}

#' Cross-Validated Discrete-Time KL Model with an Elastic-Net Penalty
#'
#' Chooses the integration weight `eta` and the lasso / elastic-net penalty `lambda` of
#' [discretekl_enet()] together, by K-fold cross-validation of the pooled held-out negative
#' log-likelihood. It is the discrete-time counterpart of [cv.coxkl_enet()].
#'
#' @inheritParams cv.discretekl_ridge
#' @inheritParams discretekl_enet
#'
#' @return An object of class `"cv.discretekl_enet"`: as [cv.discretekl_ridge()], plus `alpha`.
#' @seealso [discretekl_enet()], [cv.discretekl_ridge()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' cvfit <- cv.discretekl_enet(z = tr$z, delta = tr$status, interval = tr$interval,
#'                             beta = ExampleData_discrete$beta_external,
#'                             baseline = ExampleData_discrete$baseline_external,
#'                             etas = c(0, 1, 10), nlambda = 10, seed = 1)
#' cvfit$best$best_beta
#' @export
cv.discretekl_enet <- function(z, delta, interval, stratum = NULL, hazard = NULL, beta = NULL, baseline = NULL,
                               etas, alpha = 1, lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                               link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                               standardize = TRUE, tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  alpha <- .dt_check_alpha(alpha)
  s <- .dt_setup("kl", z, delta, interval, stratum, link, n_intervals, standardize,
                 hazard = hazard, beta = beta, baseline = baseline)
  .dt_cv_family(s, "enet", etas, alpha, lambda, nlambda, lambda.min.ratio, nfolds, seed, tol, Mstop,
                "cv.discretekl_enet", message)
}
