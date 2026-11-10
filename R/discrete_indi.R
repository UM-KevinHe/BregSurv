#' Discrete-Time Model with Individual-Level External Data (Composite Likelihood)
#'
#' @description
#' Fits a series of grouped-time (discrete-time) survival models to the internal data together with
#' an external cohort's records, one fit per value of the integration weight `eta`. It is the
#' discrete-time counterpart of [cox_indi()].
#'
#' @details
#' The objective (minimized) is the composite likelihood
#' \deqn{-\frac{1}{n_{int}}\{\ell_{int}(\gamma, \beta) + \eta\, \ell_{ext}(\gamma^{ext}, \beta)\},}
#' in which the two cohorts share the coefficients \eqn{\beta} and each keeps its own baseline hazard
#' (its own \eqn{\gamma} per stratum and interval). External records carry weight `eta`; `eta = 0` is
#' the internal model alone. The external records must use the internal covariate names and the same
#' intervals.
#'
#' @inheritParams discretekl
#' @param z_int,delta_int,interval_int,stratum_int The internal cohort: covariates, event indicator,
#'   last interval at risk and optional strata (see [discretekl()]).
#' @param z_ext,delta_ext,interval_ext,stratum_ext The external cohort, in the same form, with the
#'   internal covariate names.
#' @param n_intervals Number of intervals \eqn{K}; defaults to the largest interval in either cohort.
#'
#' @return An object of class `"discrete_indi"`: as [discretekl()], with the linear predictors of the
#'   internal subjects in `linear.predictors_int`; `gamma` holds the internal baseline.
#' @seealso [cv.discrete_indi()], [discrete_indi_ridge()], [discrete_indi_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train; ex <- ExampleData_discrete$external
#' fit <- discrete_indi(z_int = tr$z, delta_int = tr$status, interval_int = tr$interval,
#'                      z_ext = ex$z, delta_ext = ex$status, interval_ext = ex$interval,
#'                      etas = c(0, 0.1, 1))
#' fit$beta
#' @export
discrete_indi <- function(z_int, delta_int, interval_int, stratum_int = NULL,
                          z_ext, delta_ext, interval_ext, stratum_ext = NULL, etas,
                          link = c("cloglog", "logit"), n_intervals = NULL,
                          tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  check_etas(etas); etas <- sort(etas)
  s <- .dt_setup("composite", z_int, delta_int, interval_int, stratum_int, link, n_intervals, standardize = TRUE,
                 z_ext = z_ext, delta_ext = delta_ext, interval_ext = interval_ext, stratum_ext = stratum_ext)
  .dt_fit_family(s, "none", etas, 0, NULL, NULL, NULL, tol, Mstop, FALSE, "discrete_indi", message)
}

#' Discrete-Time Composite Likelihood with a Ridge Penalty
#'
#' @description
#' The ridge-penalized version of [discrete_indi()]: one penalty path per integration weight, as
#' [cox_indi_ridge()] does.
#'
#' @inheritParams discrete_indi
#' @inheritParams discretekl_ridge
#' @param etas Numeric vector of non-negative integration weights; a penalty path is fitted at each.
#'
#' @return An object of class `"discrete_indi_ridge"`: `eta`, and lists with one element per `eta` of
#'   `lambda`, `beta` (\eqn{p \times L} matrices), `gamma`, `likelihood`, `linear.predictors_int` and
#'   `converged`.
#' @seealso [cv.discrete_indi_ridge()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train; ex <- ExampleData_discrete$external
#' fit <- discrete_indi_ridge(z_int = tr$z, delta_int = tr$status, interval_int = tr$interval,
#'                            z_ext = ex$z, delta_ext = ex$status, interval_ext = ex$interval,
#'                            etas = c(0, 0.5), nlambda = 10)
#' dim(fit$beta[[1]])
#' @export
discrete_indi_ridge <- function(z_int, delta_int, interval_int, stratum_int = NULL,
                                z_ext, delta_ext, interval_ext, stratum_ext = NULL, etas,
                                lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                                link = c("cloglog", "logit"), n_intervals = NULL, standardize = TRUE,
                                tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  check_etas(etas); etas <- sort(etas)
  s <- .dt_setup("composite", z_int, delta_int, interval_int, stratum_int, link, n_intervals, standardize,
                 z_ext = z_ext, delta_ext = delta_ext, interval_ext = interval_ext, stratum_ext = stratum_ext)
  .dt_fit_family(s, "ridge", etas, 0, lambda, nlambda, lambda.min.ratio, tol, Mstop, TRUE,
                 "discrete_indi_ridge", message)
}

#' Discrete-Time Composite Likelihood with an Elastic-Net Penalty
#'
#' @description
#' The lasso / elastic-net version of [discrete_indi()]: one penalty path per integration weight, as
#' [cox_indi_enet()] does.
#'
#' @inheritParams discrete_indi_ridge
#' @inheritParams discretekl_enet
#'
#' @return An object of class `"discrete_indi_enet"`: as [discrete_indi_ridge()], plus `alpha`.
#' @seealso [cv.discrete_indi_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train; ex <- ExampleData_discrete$external
#' fit <- discrete_indi_enet(z_int = tr$z, delta_int = tr$status, interval_int = tr$interval,
#'                           z_ext = ex$z, delta_ext = ex$status, interval_ext = ex$interval,
#'                           etas = c(0, 0.5), nlambda = 10)
#' colSums(fit$beta[[2]] != 0)
#' @export
discrete_indi_enet <- function(z_int, delta_int, interval_int, stratum_int = NULL,
                               z_ext, delta_ext, interval_ext, stratum_ext = NULL, etas, alpha = 1,
                               lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                               link = c("cloglog", "logit"), n_intervals = NULL, standardize = TRUE,
                               tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  check_etas(etas); etas <- sort(etas); alpha <- .dt_check_alpha(alpha)
  s <- .dt_setup("composite", z_int, delta_int, interval_int, stratum_int, link, n_intervals, standardize,
                 z_ext = z_ext, delta_ext = delta_ext, interval_ext = interval_ext, stratum_ext = stratum_ext)
  .dt_fit_family(s, "enet", etas, alpha, lambda, nlambda, lambda.min.ratio, tol, Mstop, TRUE,
                 "discrete_indi_enet", message)
}

#' Cross-Validated Discrete-Time Composite Likelihood
#'
#' Chooses the integration weight `eta` of [discrete_indi()] by K-fold cross-validation over the
#' internal subjects. The external records enter every training fit and never the held-out score,
#' which is the pooled negative log-likelihood of the held-out internal subjects. It is the
#' discrete-time counterpart of [cv.cox_indi()].
#'
#' @inheritParams discrete_indi
#' @inheritParams cv.discretekl
#'
#' @return An object of class `"cv.discrete_indi"`, with the components of [cv.discretekl()].
#' @seealso [discrete_indi()], [cv.discrete_indi_ridge()], [cv.discrete_indi_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train; ex <- ExampleData_discrete$external
#' cvfit <- cv.discrete_indi(z_int = tr$z, delta_int = tr$status, interval_int = tr$interval,
#'                           z_ext = ex$z, delta_ext = ex$status, interval_ext = ex$interval,
#'                           etas = c(0, 0.1, 0.5, 1), seed = 1)
#' cvfit$internal_stat
#' @export
cv.discrete_indi <- function(z_int, delta_int, interval_int, stratum_int = NULL,
                             z_ext, delta_ext, interval_ext, stratum_ext = NULL, etas,
                             link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                             tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  s <- .dt_setup("composite", z_int, delta_int, interval_int, stratum_int, link, n_intervals, standardize = TRUE,
                 z_ext = z_ext, delta_ext = delta_ext, interval_ext = interval_ext, stratum_ext = stratum_ext)
  .dt_cv_family(s, "none", etas, 0, NULL, NULL, NULL, nfolds, seed, tol, Mstop, "cv.discrete_indi", message)
}

#' Cross-Validated Discrete-Time Composite Likelihood with a Ridge Penalty
#'
#' Chooses `eta` and the ridge penalty `lambda` of [discrete_indi_ridge()] together. It is the
#' discrete-time counterpart of [cv.cox_indi_ridge()].
#'
#' @inheritParams discrete_indi
#' @inheritParams cv.discretekl_ridge
#'
#' @return An object of class `"cv.discrete_indi_ridge"`, with the components of
#'   [cv.discretekl_ridge()].
#' @seealso [discrete_indi_ridge()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train; ex <- ExampleData_discrete$external
#' cvfit <- cv.discrete_indi_ridge(z_int = tr$z, delta_int = tr$status, interval_int = tr$interval,
#'                                 z_ext = ex$z, delta_ext = ex$status, interval_ext = ex$interval,
#'                                 etas = c(0, 0.5), nlambda = 10, seed = 1)
#' cvfit$best[c("best_eta", "best_lambda")]
#' @export
cv.discrete_indi_ridge <- function(z_int, delta_int, interval_int, stratum_int = NULL,
                                   z_ext, delta_ext, interval_ext, stratum_ext = NULL, etas,
                                   lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                                   link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                                   standardize = TRUE, tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  s <- .dt_setup("composite", z_int, delta_int, interval_int, stratum_int, link, n_intervals, standardize,
                 z_ext = z_ext, delta_ext = delta_ext, interval_ext = interval_ext, stratum_ext = stratum_ext)
  .dt_cv_family(s, "ridge", etas, 0, lambda, nlambda, lambda.min.ratio, nfolds, seed, tol, Mstop,
                "cv.discrete_indi_ridge", message)
}

#' Cross-Validated Discrete-Time Composite Likelihood with an Elastic-Net Penalty
#'
#' Chooses `eta` and the lasso / elastic-net penalty `lambda` of [discrete_indi_enet()] together. It
#' is the discrete-time counterpart of [cv.cox_indi_enet()].
#'
#' @inheritParams discrete_indi
#' @inheritParams cv.discretekl_enet
#'
#' @return An object of class `"cv.discrete_indi_enet"`, with the components of
#'   [cv.discretekl_enet()].
#' @seealso [discrete_indi_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train; ex <- ExampleData_discrete$external
#' cvfit <- cv.discrete_indi_enet(z_int = tr$z, delta_int = tr$status, interval_int = tr$interval,
#'                                z_ext = ex$z, delta_ext = ex$status, interval_ext = ex$interval,
#'                                etas = c(0, 0.5), nlambda = 10, seed = 1)
#' cvfit$best$best_beta
#' @export
cv.discrete_indi_enet <- function(z_int, delta_int, interval_int, stratum_int = NULL,
                                  z_ext, delta_ext, interval_ext, stratum_ext = NULL, etas, alpha = 1,
                                  lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                                  link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                                  standardize = TRUE, tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  alpha <- .dt_check_alpha(alpha)
  s <- .dt_setup("composite", z_int, delta_int, interval_int, stratum_int, link, n_intervals, standardize,
                 z_ext = z_ext, delta_ext = delta_ext, interval_ext = interval_ext, stratum_ext = stratum_ext)
  .dt_cv_family(s, "enet", etas, alpha, lambda, nlambda, lambda.min.ratio, nfolds, seed, tol, Mstop,
                "cv.discrete_indi_enet", message)
}
