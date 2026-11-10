#' Discrete-Time Model with KL Divergence for Data Integration
#'
#' @description
#' Fits a series of grouped-time (discrete-time) survival models that borrow from an external model
#' through the Kullback--Leibler divergence between the two models' interval hazards, one fit per
#' value of the integration weight `eta`. It is the discrete-time counterpart of [coxkl()].
#'
#' Follow-up is recorded in intervals \eqn{1, \dots, K}: subject \eqn{i} is at risk in intervals
#' \eqn{1, \dots, t_i} (`interval`), and `delta = 1` when the event happened in interval \eqn{t_i}.
#' The interval hazard is
#' \deqn{h_k(z) = g^{-1}(\gamma_{sk} + z^\top \beta),}
#' with one baseline parameter \eqn{\gamma_{sk}} per stratum and interval and the link \eqn{g} set by
#' `link`.
#'
#' External information can be supplied either as:
#' * the external model's interval hazards for your subjects (`hazard`), or
#' * an external Cox (grouped proportional hazards) model: its coefficients (`beta`) together with its
#'   baseline cumulative-hazard increments over your intervals (`baseline`).
#'
#' @details
#' The Kullback--Leibler divergence between the external and target interval hazards turns the
#' objective into a binary cross-entropy on the person-intervals with the observed event indicator
#' \eqn{y_{ik}} replaced by the soft target
#' \deqn{\frac{y_{ik} + \eta\, \tilde h_{ik}}{1 + \eta},}
#' where \eqn{\tilde h_{ik}} is the external hazard of subject \eqn{i} in interval \eqn{k}. `eta = 0`
#' is the target model alone; as `eta` grows the fit moves toward the external model. This is the
#' estimator of the `DiscreteKL` package (Wang et al.), computed by Fisher scoring in C++.
#'
#' @param z Numeric matrix (or data frame of numeric columns) of covariates, one row per subject.
#'   Column names are used to align external coefficients by name.
#' @param delta Event indicator: 1 when the event happened in the subject's last interval at risk,
#'   0 when the subject was censored at the end of it.
#' @param interval Whole numbers \eqn{1, \dots, K}: the last interval each subject was at risk in
#'   (the interval of the event when `delta = 1`).
#' @param stratum Optional strata; each stratum has its own baseline hazard over the intervals.
#' @param hazard Optional \eqn{n \times K} matrix of external interval hazards: row \eqn{i}, column
#'   \eqn{k} is the external model's probability that subject \eqn{i} has the event in interval
#'   \eqn{k} given that it reached the interval. If not supplied, `beta` and `baseline` must be.
#' @param beta Optional named vector of external Cox coefficients, aligned to `colnames(z)` by name
#'   (covariates the external model does not cover are set to 0; see [align_beta()]).
#' @param baseline Optional external baseline cumulative-hazard increments over intervals
#'   \eqn{1, \dots, K}, \eqn{\Delta\Lambda_0(k) = \Lambda_0(t_k) - \Lambda_0(t_{k-1})}. With `beta`,
#'   the external interval hazard is \eqn{1 - \exp\{-e^{z^\top\beta}\Delta\Lambda_0(k)\}}.
#' @param etas Numeric vector of non-negative integration weights; sorted in ascending order.
#' @param link `"cloglog"` (complementary log-log: the grouped proportional-hazards model, the
#'   default, on the scale of a Cox model's coefficients) or `"logit"` (proportional odds of the
#'   interval hazard).
#' @param n_intervals Number of intervals \eqn{K}; defaults to `max(interval)`.
#' @param tol Convergence tolerance of the Fisher-scoring iterations. Default `1e-9`.
#' @param Mstop Maximum number of iterations per fit. Default `200`.
#' @param message Logical; if `TRUE`, prints a progress bar.
#'
#' @return An object of class `"discretekl"`:
#' \describe{
#'   \item{`eta`}{The sorted integration weights.}
#'   \item{`beta`}{Matrix of coefficients, \eqn{p \times} `length(etas)`, one column per `eta`.}
#'   \item{`gamma`}{Array of baseline parameters \eqn{\gamma_{sk}}, strata \eqn{\times K \times}
#'     `length(etas)`, on the link scale.}
#'   \item{`likelihood`}{Log-likelihood of the target data at each `eta` (larger is better).}
#'   \item{`linear.predictors`}{Matrix \eqn{z^\top\beta}, one column per `eta`.}
#'   \item{`converged`}{Whether each fit converged.}
#'   \item{`link`, `K`, `strata_levels`}{The link, the number of intervals and the strata.}
#' }
#' @seealso [cv.discretekl()] to choose `eta`; [discretekl_ridge()], [discretekl_enet()];
#'   [cv.bregsurv()] with [target_discrete()] and [release_model()].
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' fit <- discretekl(z = tr$z, delta = tr$status, interval = tr$interval,
#'                   beta = ExampleData_discrete$beta_external,
#'                   baseline = ExampleData_discrete$baseline_external,
#'                   etas = c(0, 1, 10))
#' fit$beta
#' @export
discretekl <- function(z, delta, interval, stratum = NULL, hazard = NULL, beta = NULL, baseline = NULL,
                       etas, link = c("cloglog", "logit"), n_intervals = NULL,
                       tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  check_etas(etas); etas <- sort(etas)
  s <- .dt_setup("kl", z, delta, interval, stratum, link, n_intervals, standardize = TRUE,
                 hazard = hazard, beta = beta, baseline = baseline)
  .dt_fit_family(s, "none", etas, 0, NULL, NULL, NULL, tol, Mstop, FALSE, "discretekl", message)
}

#' Discrete-Time Model with KL Divergence and a Ridge Penalty
#'
#' @description
#' The ridge-penalized version of [discretekl()]: at one integration weight `eta`, fits a path of
#' ridge penalties \eqn{\frac{\lambda}{2}\|\beta\|^2}. It is the discrete-time counterpart of
#' [coxkl_ridge()].
#'
#' @inheritParams discretekl
#' @param eta One non-negative integration weight. `NULL` uses 0 with a warning.
#' @param lambda Optional penalty values; `NULL` builds a log-spaced path of `nlambda` values.
#' @param nlambda Number of penalty values when `lambda` is `NULL`. Default `100`.
#' @param lambda.min.ratio Smallest penalty as a fraction of the largest; `NULL` uses `0.05` when
#'   there are more covariates than subjects and `1e-3` otherwise (a tenth of that for the ridge).
#' @param standardize Standardize the covariates before penalizing; coefficients are returned on the
#'   original scale. Default `TRUE`.
#'
#' @return An object of class `"discretekl_ridge"`: `eta`, `lambda`, and `beta`, `gamma`,
#'   `likelihood`, `linear.predictors`, `converged`, `df` with one entry per penalty value, as in
#'   [discretekl()].
#' @seealso [cv.discretekl_ridge()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' fit <- discretekl_ridge(z = tr$z, delta = tr$status, interval = tr$interval,
#'                         beta = ExampleData_discrete$beta_external,
#'                         baseline = ExampleData_discrete$baseline_external,
#'                         eta = 1, nlambda = 20)
#' dim(fit$beta)
#' @export
discretekl_ridge <- function(z, delta, interval, stratum = NULL, hazard = NULL, beta = NULL, baseline = NULL,
                             eta = NULL, lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                             link = c("cloglog", "logit"), n_intervals = NULL, standardize = TRUE,
                             tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  eta <- .dt_check_eta1(eta)
  s <- .dt_setup("kl", z, delta, interval, stratum, link, n_intervals, standardize,
                 hazard = hazard, beta = beta, baseline = baseline)
  .dt_fit_family(s, "ridge", eta, 0, lambda, nlambda, lambda.min.ratio, tol, Mstop, FALSE, "discretekl_ridge", message)
}

#' Discrete-Time Model with KL Divergence and an Elastic-Net Penalty
#'
#' @description
#' The lasso / elastic-net version of [discretekl()]: at one integration weight `eta`, fits a path of
#' penalties \eqn{\lambda\{\alpha\|\beta\|_1 + \frac{1-\alpha}{2}\|\beta\|^2\}} by proximal Newton with
#' coordinate descent. It is the discrete-time counterpart of [coxkl_enet()].
#'
#' @inheritParams discretekl_ridge
#' @param alpha Elastic-net mixing parameter in \eqn{(0, 1]}; `alpha = 1` (the default) is the lasso.
#'
#' @return An object of class `"discretekl_enet"`: as [discretekl_ridge()], plus `alpha`; `df`
#'   counts the non-zero coefficients at each penalty value.
#' @seealso [cv.discretekl_enet()]
#' @examples
#' data(ExampleData_discrete)
#' tr <- ExampleData_discrete$train
#' fit <- discretekl_enet(z = tr$z, delta = tr$status, interval = tr$interval,
#'                        beta = ExampleData_discrete$beta_external,
#'                        baseline = ExampleData_discrete$baseline_external,
#'                        eta = 1, nlambda = 20)
#' fit$df
#' @export
discretekl_enet <- function(z, delta, interval, stratum = NULL, hazard = NULL, beta = NULL, baseline = NULL,
                            eta = NULL, alpha = 1, lambda = NULL, nlambda = 100, lambda.min.ratio = NULL,
                            link = c("cloglog", "logit"), n_intervals = NULL, standardize = TRUE,
                            tol = 1e-9, Mstop = 200, message = FALSE) {
  link <- match.arg(link)
  eta <- .dt_check_eta1(eta); alpha <- .dt_check_alpha(alpha)
  s <- .dt_setup("kl", z, delta, interval, stratum, link, n_intervals, standardize,
                 hazard = hazard, beta = beta, baseline = baseline)
  .dt_fit_family(s, "enet", eta, alpha, lambda, nlambda, lambda.min.ratio, tol, Mstop, FALSE, "discretekl_enet", message)
}
