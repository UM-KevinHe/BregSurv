#' Discrete-Time Model with Mahalanobis-Distance Transfer Learning
#'
#' @description
#' Fits a series of grouped-time (discrete-time) survival models whose coefficients are shrunk toward
#' external coefficients by a Mahalanobis distance, one fit per value of the integration weight `eta`.
#' It is the discrete-time counterpart of [cox_MDTL()].
#'
#' @details
#' The objective (minimized) is
#' \deqn{-\frac{1}{n}\ell(\gamma, \beta) + \frac{\eta}{2}(\beta - \tilde\beta)^\top Q (\beta - \tilde\beta),}
#' with \eqn{\ell} the grouped-time log-likelihood (see [discretekl()]), \eqn{\tilde\beta} the external
#' coefficients and \eqn{Q} their precision matrix: the scale of [cox_MDTL()]. With `Q = NULL` the
#' distance is Euclidean on the covariates the external model covers. The external coefficients must
#' be on the scale of the link: a Cox model's coefficients are on the scale of the default
#' complementary log-log link (the grouped proportional-hazards model).
#'
#' @inheritParams discretekl
#' @param beta Named vector of external coefficients, aligned to `colnames(z)` by name (see
#'   [align_beta_Q()]).
#' @param Q Optional precision matrix of `beta` (the inverse of its covariance matrix), named like
#'   `beta`. `NULL` gives the Euclidean distance on the covered covariates.
#'
#' @return An object of class `"discrete_MDTL"`, with the components of [discretekl()].
#' @seealso [cv.discrete_MDTL()], [discrete_MDTL_ridge()], [discrete_MDTL_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' fit <- discrete_MDTL(z = tr$z, delta = tr$status, interval = tr$interval,
#'                      beta = ExampleData_discrete$beta_external, etas = c(0, 1, 10))
#' fit$beta
#' @export
discrete_MDTL <- function(z, delta, interval, stratum = NULL, beta, Q = NULL, etas,
                          link = c("cloglog", "logit"), n_intervals = NULL,
                          tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  check_etas(etas); etas <- sort(etas)
  s <- .dt_setup("mahalanobis", z, delta, interval, stratum, link, n_intervals, standardize = TRUE,
                 beta = beta, Q = Q)
  .dt_fit_family(s, "none", etas, 0, NULL, NULL, NULL, tol, Mstop, FALSE, "discrete_MDTL", message)
}

#' Discrete-Time Mahalanobis-Distance Transfer Learning with a Ridge Penalty
#'
#' @description
#' The ridge-penalized version of [discrete_MDTL()] at one integration weight. It is the
#' discrete-time counterpart of [cox_MDTL_ridge()].
#'
#' @inheritParams discrete_MDTL
#' @inheritParams discretekl_ridge
#'
#' @return An object of class `"discrete_MDTL_ridge"`, with the components of [discretekl_ridge()].
#' @seealso [cv.discrete_MDTL_ridge()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' fit <- discrete_MDTL_ridge(z = tr$z, delta = tr$status, interval = tr$interval,
#'                            beta = ExampleData_discrete$beta_external, eta = 1, nlambda = 20)
#' dim(fit$beta)
#' @export
discrete_MDTL_ridge <- function(z, delta, interval, stratum = NULL, beta, Q = NULL, eta = NULL,
                                lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                                link = c("cloglog", "logit"), n_intervals = NULL, standardize = TRUE,
                                tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  eta <- .dt_check_eta1(eta)
  s <- .dt_setup("mahalanobis", z, delta, interval, stratum, link, n_intervals, standardize, beta = beta, Q = Q)
  .dt_fit_family(s, "ridge", eta, 0, lambda, nlambda, lambda.min.ratio, tol, Mstop, FALSE,
                 "discrete_MDTL_ridge", message)
}

#' Discrete-Time Mahalanobis-Distance Transfer Learning with an Elastic-Net Penalty
#'
#' @description
#' The lasso / elastic-net version of [discrete_MDTL()] at one integration weight. It is the
#' discrete-time counterpart of [cox_MDTL_enet()].
#'
#' @inheritParams discrete_MDTL
#' @inheritParams discretekl_enet
#'
#' @return An object of class `"discrete_MDTL_enet"`, with the components of [discretekl_enet()].
#' @seealso [cv.discrete_MDTL_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' fit <- discrete_MDTL_enet(z = tr$z, delta = tr$status, interval = tr$interval,
#'                           beta = ExampleData_discrete$beta_external, eta = 1, nlambda = 20)
#' fit$df
#' @export
discrete_MDTL_enet <- function(z, delta, interval, stratum = NULL, beta, Q = NULL, eta = NULL, alpha = 1,
                               lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                               link = c("cloglog", "logit"), n_intervals = NULL, standardize = TRUE,
                               tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  eta <- .dt_check_eta1(eta); alpha <- .dt_check_alpha(alpha)
  s <- .dt_setup("mahalanobis", z, delta, interval, stratum, link, n_intervals, standardize, beta = beta, Q = Q)
  .dt_fit_family(s, "enet", eta, alpha, lambda, nlambda, lambda.min.ratio, tol, Mstop, FALSE,
                 "discrete_MDTL_enet", message)
}

#' Cross-Validated Discrete-Time Mahalanobis-Distance Transfer Learning
#'
#' Chooses the integration weight `eta` of [discrete_MDTL()] by K-fold cross-validation of the
#' pooled held-out negative log-likelihood. It is the discrete-time counterpart of [cv.cox_MDTL()].
#'
#' @inheritParams discrete_MDTL
#' @inheritParams cv.discretekl
#'
#' @return An object of class `"cv.discrete_MDTL"`, with the components of [cv.discretekl()].
#' @seealso [discrete_MDTL()], [cv.discrete_MDTL_ridge()], [cv.discrete_MDTL_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' cvfit <- cv.discrete_MDTL(z = tr$z, delta = tr$status, interval = tr$interval,
#'                           beta = ExampleData_discrete$beta_external,
#'                           etas = c(0, 1, 10, 100), seed = 1)
#' cvfit$internal_stat
#' @export
cv.discrete_MDTL <- function(z, delta, interval, stratum = NULL, beta, Q = NULL, etas,
                             link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                             tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  s <- .dt_setup("mahalanobis", z, delta, interval, stratum, link, n_intervals, standardize = TRUE,
                 beta = beta, Q = Q)
  .dt_cv_family(s, "none", etas, 0, NULL, NULL, NULL, nfolds, seed, tol, Mstop, "cv.discrete_MDTL", message)
}

#' Cross-Validated Discrete-Time Mahalanobis-Distance Transfer Learning with a Ridge Penalty
#'
#' Chooses `eta` and the ridge penalty `lambda` of [discrete_MDTL_ridge()] together. It is the
#' discrete-time counterpart of [cv.cox_MDTL_ridge()].
#'
#' @inheritParams discrete_MDTL
#' @inheritParams cv.discretekl_ridge
#'
#' @return An object of class `"cv.discrete_MDTL_ridge"`, with the components of
#'   [cv.discretekl_ridge()].
#' @seealso [discrete_MDTL_ridge()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' cvfit <- cv.discrete_MDTL_ridge(z = tr$z, delta = tr$status, interval = tr$interval,
#'                                 beta = ExampleData_discrete$beta_external,
#'                                 etas = c(0, 1, 10), nlambda = 10, seed = 1)
#' cvfit$best[c("best_eta", "best_lambda")]
#' @export
cv.discrete_MDTL_ridge <- function(z, delta, interval, stratum = NULL, beta, Q = NULL, etas,
                                   lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                                   link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                                   standardize = TRUE, tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  s <- .dt_setup("mahalanobis", z, delta, interval, stratum, link, n_intervals, standardize, beta = beta, Q = Q)
  .dt_cv_family(s, "ridge", etas, 0, lambda, nlambda, lambda.min.ratio, nfolds, seed, tol, Mstop,
                "cv.discrete_MDTL_ridge", message)
}

#' Cross-Validated Discrete-Time Mahalanobis-Distance Transfer Learning with an Elastic-Net Penalty
#'
#' Chooses `eta` and the lasso / elastic-net penalty `lambda` of [discrete_MDTL_enet()] together. It
#' is the discrete-time counterpart of [cv.cox_MDTL_enet()].
#'
#' @inheritParams discrete_MDTL
#' @inheritParams cv.discretekl_enet
#'
#' @return An object of class `"cv.discrete_MDTL_enet"`, with the components of
#'   [cv.discretekl_enet()].
#' @seealso [discrete_MDTL_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' cvfit <- cv.discrete_MDTL_enet(z = tr$z, delta = tr$status, interval = tr$interval,
#'                                beta = ExampleData_discrete$beta_external,
#'                                etas = c(0, 1, 10), nlambda = 10, seed = 1)
#' cvfit$best$best_beta
#' @export
cv.discrete_MDTL_enet <- function(z, delta, interval, stratum = NULL, beta, Q = NULL, etas, alpha = 1,
                                  lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                                  link = c("cloglog", "logit"), n_intervals = NULL, nfolds = 5, seed = NULL,
                                  standardize = TRUE, tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  alpha <- .dt_check_alpha(alpha)
  s <- .dt_setup("mahalanobis", z, delta, interval, stratum, link, n_intervals, standardize, beta = beta, Q = Q)
  .dt_cv_family(s, "enet", etas, alpha, lambda, nlambda, lambda.min.ratio, nfolds, seed, tol, Mstop,
                "cv.discrete_MDTL_enet", message)
}
