## The framework's single interface: target x release x divergence x penalty.
##
## Linear targets dispatch to the package's estimators, one family per divergence and design:
##
##   divergence    Cox          nested case-control   discrete time
##   kl / none     coxkl*       ncckl*                discretekl*
##   mahalanobis   cox_MDTL*    ncc_MDTL*             discrete_MDTL*
##   composite     cox_indi*    ncc_indi*             discrete_indi*
##
## with the suffix "" / "_ridge" / "_enet" for the penalty, so the numbers are exactly those
## estimators' numbers. Neural risk scores have their own engine (R/neural_engine.R).

`%||%` <- function(a, b) if (is.null(a)) b else a

.log_eta <- function(hi, n, lo = 0.01) c(0, exp(seq(log(lo), log(hi), length.out = n)))

## default integration-weight grids: log spaced from 0.01 to the divergence's upper end, eta = 0 kept
## as the target-only endpoint (the grids the agent uses)
.default_etas <- function(divergence, penalty, target) {
  if (inherits(target$score, "nn_score")) return(c(0, 1, 5, 10, 20, 40, 80))
  if (target$type == "discrete" && divergence == "kl") return(c(0, 1, 5, 10, 20, 50, 100))
  pen <- penalty != "none"
  switch(divergence,
         none = 0,
         kl = , composite = .log_eta(2e2, if (pen) 41 else 81),
         mahalanobis = if (penalty %in% c("lasso", "enet")) .log_eta(1e3, 41) else .log_eta(1e6, if (pen) 41 else 81))
}

#' Fit a time-to-event model that borrows from an external source
#'
#' @description
#' `cv.bregsurv()` is the main function of the package. It fits a model to your data while borrowing
#' from what an external source made available, by minimizing
#' \deqn{Q_\eta(\theta) = -\ell(\theta) + \eta\, B_G(\theta), \qquad \eta \ge 0,}
#' the negative log-likelihood \eqn{\ell} of your data plus an integration weight \eqn{\eta} times a
#' Bregman divergence \eqn{B_G} between your model and the external one. \eqn{\eta = 0} ignores the
#' external source and larger values borrow more; `cv.bregsurv()` chooses \eqn{\eta} (and, under a
#' penalty, the penalty level) by cross-validation on your data.
#'
#' A call is made of four choices, one per argument:
#' 1. `target`: the model you fit to your own data, which fixes \eqn{\ell};
#' 2. `release`: what the external source made available;
#' 3. `divergence`: how the release enters the objective, which fixes \eqn{B_G};
#' 4. `penalty`: an optional ridge, lasso or elastic-net penalty on the coefficients.
#'
#' @param target The model you fit to your data. Build it with one of three constructors; each takes
#'   your data, one row per subject, and checks it:
#'   * [target_cox()]`(time, event, z, stratum = NULL, ties = "none", score = "linear")`: a Cox
#'     proportional-hazards model for follow-up recorded as a time and an event indicator.
#'     - `stratum`: optional strata, each with its own baseline hazard;
#'     - `ties`: how tied event times enter the partial likelihood (`"none"`, `"breslow"` or
#'       `"exact"`).
#'   * [target_ncc()]`(case, set, z)`: a nested case-control (matched case-control) design.
#'     - `case`: 1 for the case and 0 for the controls;
#'     - `set`: the matched set of each row; every set holds exactly one case;
#'     - the likelihood is the conditional likelihood of which member of each set is the case.
#'   * [target_discrete()]`(interval, event, z, stratum = NULL, link = "cloglog", score = "linear")`:
#'     a discrete-time (grouped-time) model for follow-up recorded in intervals \eqn{1, \dots, K}.
#'     - `interval`: the last interval each subject was at risk in;
#'     - `event`: 1 when the event happened in that interval;
#'     - `link`: `"cloglog"` (grouped proportional hazards) or `"logit"`.
#'
#'   In all three, `z` holds the covariates (a numeric matrix or data frame, one column per
#'   covariate, with names). `target_cox()` and `target_discrete()` also take
#'   `score = `[nn_score()] to replace the linear risk score \eqn{z^\top\beta} by a neural network
#'   (requires the `torch` package).
#' @param release What the external source made available, or `NULL` to fit your data alone. Build it
#'   with one of four constructors, by what you received:
#'   * [release_records()]: the external cohort's individual-level records, in the target's design.
#'     - `z`: the external covariates, with the target's column names;
#'     - `time`, `event` (and optionally `stratum`) for a Cox target;
#'     - `case`, `set` for a nested case-control target;
#'     - `interval`, `event` for a discrete-time target.
#'   * [release_coef()]`(beta, Q = NULL)`: published regression coefficients.
#'     - `beta`: a numeric vector named by covariate, every name one of your covariates; covariates
#'       the external model does not include are set to 0;
#'     - `Q`: optionally, their precision matrix (the inverse of their covariance matrix).
#'   * [release_score()]`(score)`: an external risk score evaluated on your subjects, for when only a
#'     risk calculator or its predictions are available.
#'     - `score`: one value per row of your data, in the same order.
#'   * [release_model()]: a fitted model including its baseline hazard, i.e. absolute risks. A
#'     discrete-time target needs this form for the Kullback-Leibler divergence.
#'     - `beta` with `baseline`: the external Cox coefficients and its baseline cumulative-hazard
#'       increments over your intervals \eqn{1, \dots, K};
#'     - or `hazard`: the external interval hazards of your subjects, an \eqn{n \times K} matrix.
#' @param divergence How the release enters the objective, i.e. which Bregman divergence \eqn{B_G}
#'   is used. `NULL` (the default) takes the first one the release supports, in the order listed in
#'   Details.
#'   * `"composite"`: the external records' own log-likelihood is added with weight \eqn{\eta},
#'     giving a composite likelihood in which the two cohorts share the coefficients and keep their
#'     own baselines. Needs [release_records()].
#'   * `"mahalanobis"`: the Mahalanobis distance
#'     \eqn{\frac{1}{2}(\beta - \tilde\beta)^\top Q (\beta - \tilde\beta)} to the external
#'     coefficients \eqn{\tilde\beta}; the Euclidean distance on the covered covariates when the
#'     release has no `Q`. Needs coefficients: [release_coef()] or [release_model()], or on a Cox
#'     target [release_records()], from which a Cox model is fitted.
#'   * `"kl"`: the Kullback-Leibler divergence between the distributions the two models predict for
#'     your subjects (who fails at each event time for a Cox target, which member of a set is the
#'     case for a matched design, the hazard of each interval for a discrete-time target). It needs
#'     only the external model's predictions, so it works with [release_coef()], [release_score()] and
#'     [release_model()]; on a discrete-time target only with [release_model()]. It is the only
#'     divergence defined for a neural target.
#'   * `"none"`: no borrowing, your data alone (\eqn{\eta = 0}); the only choice when
#'     `release = NULL`.
#' @param penalty Penalty on the coefficients of a linear target:
#'   * `"none"` (the default);
#'   * `"ridge"`: \eqn{\frac{\lambda}{2}\|\beta\|_2^2};
#'   * `"lasso"`: \eqn{\lambda\|\beta\|_1}, which sets some coefficients to zero;
#'   * `"enet"`: the elastic net \eqn{\lambda\{\alpha\|\beta\|_1 + \frac{1-\alpha}{2}\|\beta\|_2^2\}}.
#'
#'   A neural target is regularized by early stopping and dropout instead and takes `"none"`.
#' @param alpha Elastic-net mixing parameter for `penalty = "enet"`, in \eqn{(0, 1]}.
#' @param etas Candidate integration weights. `NULL` uses a grid that starts at 0 (your data alone)
#'   and is log spaced from 0.01 to an upper end suited to the divergence.
#' @param lambda,nlambda,lambda.min.ratio The penalty path: given values in `lambda`, or `nlambda`
#'   log-spaced values from the smallest penalty that sets every coefficient to zero down to
#'   `lambda.min.ratio` times it, built for each `eta`.
#' @param nfolds Number of cross-validation folds.
#' @param seed Seed of the fold assignment. The default is fixed, so repeated calls, and calls with
#'   different releases or divergences on the same target, share one partition and their `value`s
#'   can be compared directly.
#' @param criterion Cross-validation criterion. A Cox target uses `"V&VH"` (the partial-likelihood
#'   loss of Verweij and Van Houwelingen) by default and also accepts `"LinPred"`, `"CIndex_pooled"`
#'   and `"CIndex_foldaverage"`; a nested case-control target uses `"loss"` (the conditional
#'   log-likelihood) and also accepts `"AUC"`, `"CIndex"` and `"Brier"`; a discrete-time target uses
#'   the held-out negative log-likelihood per subject. Fits are comparable only under the same
#'   criterion.
#' @param standardize Standardize the covariates before penalizing; coefficients are always returned
#'   on the original scale.
#' @param ... Further arguments passed to the estimator that fits the model (named in the result's
#'   `engine`).
#'
#' @details
#' **Which divergences a release supports.** The first divergence in each cell is the default.
#'
#' | release | Cox | nested case-control | discrete time | neural target |
#' |---|---|---|---|---|
#' | `NULL` | none | none | none | none |
#' | [release_records()] | composite, mahalanobis, kl | composite | composite | -- |
#' | [release_coef()] without `Q` | kl, mahalanobis | kl, mahalanobis | mahalanobis | kl (Cox only) |
#' | [release_coef()] with `Q` | mahalanobis, kl | mahalanobis, kl | mahalanobis | kl (Cox only) |
#' | [release_score()] | kl | kl | -- | kl (Cox only) |
#' | [release_model()] | as [release_coef()] | as [release_coef()] | kl, mahalanobis | kl |
#'
#' **Which estimator fits the model.** A linear target is fitted by one of the package's estimators,
#' named in the result's `engine`; the result is identical to calling that estimator directly.
#'
#' | divergence | Cox | nested case-control | discrete time |
#' |---|---|---|---|
#' | `"kl"`, `"none"` | [cv.coxkl()] | [cv.ncckl()] | [cv.discretekl()] |
#' | `"mahalanobis"` | [cv.cox_MDTL()] | [cv.ncc_MDTL()] | [cv.discrete_MDTL()] |
#' | `"composite"` | [cv.cox_indi()] | [cv.ncc_indi()] | [cv.discrete_indi()] |
#'
#' with the suffix `_ridge` for `penalty = "ridge"` and `_enet` for `"lasso"` and `"enet"`
#' (for example [cv.coxkl_enet()]), and [cv.coxkl_ties()] for `ties = "exact"`. `"none"` is the
#' Kullback-Leibler estimator at \eqn{\eta = 0}. A neural target is trained with `torch`.
#'
#' @return An object of class `"cv.bregsurv"`, a list with
#' \describe{
#'   \item{`eta`, `lambda`}{The selected integration weight and penalty level.}
#'   \item{`value`, `criterion`}{The cross-validated value of the selected fit and its criterion.}
#'   \item{`coefficients`}{The coefficients of the selected fit (linear targets).}
#'   \item{`coefficients_target_only`}{The coefficients at \eqn{\eta = 0}, when 0 is in `etas`.}
#'   \item{`coefficients_external`}{The external coefficients aligned to your covariates, when the
#'     release has coefficients.}
#'   \item{`gamma`}{For a discrete-time target, the baseline parameters of the selected fit (one row
#'     per stratum, one column per interval, on the link scale).}
#'   \item{`path`}{The cross-validated value at each `eta` (at its best `lambda` under a penalty).}
#'   \item{`folds`, `seed`}{The cross-validation partition.}
#'   \item{`engine`, `fit`}{The estimator that was called and its complete result.}
#'   \item{`divergence`, `penalty`, `target`, `release`}{The choices that were made.}
#' }
#' Use [plot()][plot.cv.bregsurv] for the cross-validation curve and the coefficients, [coef()] and
#' [predict()][predict.cv.bregsurv] for the fitted model.
#'
#' @seealso [bregsurv()] to fit at a given `eta`; [targets], [releases], [plot.cv.bregsurv()],
#'   [predict.cv.bregsurv()].
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' target <- target_cox(time = tr$time, event = tr$status, z = tr$z)
#'
#' # a published model, available only as a risk score for each of your subjects
#' score <- as.matrix(tr$z) %*% ExampleData_lowdim$beta_external_fair
#' kl <- cv.bregsurv(target, release_score(score), divergence = "kl")
#' kl
#'
#' # the same model's coefficients, through the Euclidean distance
#' euc <- cv.bregsurv(target, release_coef(ExampleData_lowdim$beta_external_fair),
#'                    divergence = "mahalanobis")
#'
#' # your data alone; all three share one partition, so the values compare directly
#' own <- cv.bregsurv(target)
#' c(target_only = own$value, kl = kl$value, euclidean = euc$value)
#' @export
cv.bregsurv <- function(target, release = NULL, divergence = NULL,
                        penalty = c("none", "ridge", "lasso", "enet"), alpha = 0.5,
                        etas = NULL, lambda = NULL, nlambda = 50, lambda.min.ratio = NULL,
                        nfolds = 5, seed = 20260818L, criterion = NULL, standardize = TRUE, ...) {
  penalty <- match.arg(penalty)
  divergence <- .resolve(target, release, divergence, penalty)
  if (is.null(etas)) etas <- .default_etas(divergence, penalty, target)
  if (divergence == "none") etas <- 0
  neural <- inherits(target$score, "nn_score")

  if (neural) {
    if (penalty != "none") stop("A neural target is regularized by early stopping and dropout; use penalty = \"none\".",
                                call. = FALSE)
    ext <- .ext_for_neural(target, release, divergence)
    r <- .nn_cv(target, ext, etas, nfolds, NULL, seed)
    out <- list(eta = r$eta, lambda = NULL, value = r$value, criterion = r$criterion, coefficients = NULL,
                folds = r$folds, seed = r$seed, path = data.frame(eta = r$pooled$eta, value = r$pooled$loss),
                engine = "neural network (torch)", fit = r)
  } else {
    call <- .engine_call(target, release, divergence, penalty, alpha, etas, lambda, nlambda, lambda.min.ratio,
                         nfolds, seed, criterion, standardize, cv = TRUE, ...)
    obj <- .call_engine(call)
    best <- obj$best
    b <- best$best_beta
    if (is.matrix(b)) b <- b[, 1]
    b <- as.numeric(b); names(b) <- colnames(target$z)
    out <- list(eta = if (divergence == "none") 0 else best$best_eta, lambda = best$best_lambda,
                value = best$best_value, criterion = best$criteria, coefficients = b,
                coefficients_target_only = .eta0_coef(obj, colnames(target$z)),
                coefficients_external = .external_coef(target, release, divergence),
                folds = obj$folds, seed = obj$seed, path = .engine_path(obj), engine = call$fun, fit = obj)
    if (target$type == "discrete") {
      out$gamma <- best$best_gamma
      out$link <- obj$link; out$strata_levels <- obj$strata_levels
    }
  }
  out$divergence <- divergence; out$penalty <- penalty; out$alpha <- if (penalty == "enet") alpha else NULL
  out$target <- .target_summary(target); out$release <- if (is.null(release)) "none" else release$form
  out$training <- target
  out$call <- match.call()
  structure(out, class = "cv.bregsurv")
}

#' Fit a time-to-event model that borrows from an external source, at a given weight
#'
#' `bregsurv()` fits the model at a fixed integration weight `eta` (and penalty level `lambda` under a
#' penalty), without cross-validation. It takes the same `target`, `release`, `divergence` and
#' `penalty` as [cv.bregsurv()], which explains them, and which chooses `eta` from the data.
#'
#' @inheritParams cv.bregsurv
#' @param eta The integration weight; `0` fits your data alone.
#' @param lambda Penalty level, one value, required when `penalty` is not `"none"`.
#' @return An object of class `"bregsurv"` with the `coefficients` (and, for a discrete-time target,
#'   the baseline parameters `gamma`), the `engine` called and its result in `fit`.
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' fit <- bregsurv(target_cox(tr$time, tr$status, tr$z),
#'                 release_coef(ExampleData_lowdim$beta_external_good), divergence = "kl", eta = 1)
#' coef(fit)
#' @export
bregsurv <- function(target, release = NULL, divergence = NULL, eta = 0,
                     penalty = c("none", "ridge", "lasso", "enet"), alpha = 0.5, lambda = NULL,
                     standardize = TRUE, ...) {
  penalty <- match.arg(penalty)
  divergence <- .resolve(target, release, divergence, penalty)
  if (divergence == "none") eta <- 0
  if (length(eta) != 1 || eta < 0) stop("'eta' must be one non-negative number.", call. = FALSE)
  if (penalty != "none" && (is.null(lambda) || length(lambda) != 1))
    stop("A penalized fit at a given weight needs one 'lambda'; use cv.bregsurv() to choose it.", call. = FALSE)
  if (inherits(target$score, "nn_score"))
    stop("A neural target is fitted by cv.bregsurv(), which chooses its training length; ",
         "pass etas = <your eta> there to fix the weight.", call. = FALSE)
  call <- .engine_call(target, release, divergence, penalty, alpha, eta, lambda, NULL, NULL, NULL, NULL, NULL,
                       standardize, cv = FALSE, ...)
  obj <- .call_engine(call)
  b <- obj$beta
  while (is.list(b)) b <- b[[1]]
  if (is.matrix(b)) b <- b[, 1]
  b <- as.numeric(b); names(b) <- colnames(target$z)
  out <- list(coefficients = b, eta = eta, lambda = lambda, engine = call$fun, fit = obj)
  if (target$type == "discrete") {
    g <- obj$gamma
    while (is.list(g)) g <- g[[1]]
    out$gamma <- matrix(g[, , 1], dim(g)[1], dim(g)[2], dimnames = dimnames(g)[1:2])
    out$link <- obj$link; out$strata_levels <- obj$strata_levels
  }
  out$divergence <- divergence; out$penalty <- penalty; out$target <- .target_summary(target)
  out$release <- if (is.null(release)) "none" else release$form
  out$training <- target
  out$call <- match.call()
  structure(out, class = "bregsurv")
}

# ---------------------------------------------------------------------------------------------------
# Resolution and dispatch
# ---------------------------------------------------------------------------------------------------
.resolve <- function(target, release, divergence, penalty) {
  if (!inherits(target, "bregsurv_target")) stop("'target' must come from target_cox(), target_ncc() or target_discrete().",
                                                 call. = FALSE)
  if (!is.null(release) && !inherits(release, "bregsurv_release"))
    stop("'release' must come from release_records(), release_coef(), release_score() or release_model().", call. = FALSE)
  allowed <- .divergences_for(release, target)
  if (!length(allowed)) stop("This release cannot inform this target: ", .why_not(release, target), call. = FALSE)
  if (is.null(divergence)) divergence <- allowed[1]
  divergence <- match.arg(divergence, c("composite", "mahalanobis", "kl", "none"))
  if (divergence == "none" && !is.null(release)) stop("divergence = \"none\" fits the target alone; drop the release.", call. = FALSE)
  if (!divergence %in% allowed)
    stop("A ", release$form, " release supports the divergence(s) ", paste(allowed, collapse = ", "),
         " on this target, not \"", divergence, "\".", call. = FALSE)
  if (target$type == "cox" && target$ties == "exact" && !(divergence %in% c("kl", "none") && penalty == "none"))
    stop("ties = \"exact\" is available for the unpenalized Kullback-Leibler divergence only; use \"breslow\".", call. = FALSE)
  if (target$type == "ncc" && divergence == "composite" && penalty == "ridge")
    stop("The matched design has no ridge composite-likelihood estimator; use \"lasso\" or \"enet\".", call. = FALSE)
  if (target$type == "discrete" && divergence == "mahalanobis" && target$link != "cloglog")
    stop("The Mahalanobis divergence compares the coefficients with a Cox model's, which only the cloglog link shares.",
         call. = FALSE)
  divergence
}

.why_not <- function(release, target) {
  if (inherits(target$score, "nn_score")) return("a neural target can borrow only through the Kullback-Leibler divergence.")
  if (release$form == "score" && target$type == "discrete")
    return("the discrete-time target needs interval hazards: use release_model() with the baseline hazard.")
  if (release$form == "records") return("the records must have the target's design (cohort, matched or discrete).")
  "no divergence of the framework applies."
}

.target_summary <- function(t) list(type = t$type, score = if (inherits(t$score, "nn_score")) "neural" else "linear",
                                    n = t$n, p = ncol(t$z), ties = t$ties, link = t$link, K = t$K)

## external coefficients (and precision) from cohort records, by a Cox fit with Breslow ties
.records_to_coef <- function(rel, znames) {
  ze <- .match_cols(rel$z, znames)
  fm <- if (is.null(rel$stratum))
    survival::coxph(survival::Surv(rel$time, rel$event) ~ ze, ties = "breslow")
  else survival::coxph(survival::Surv(rel$time, rel$event) ~ ze + survival::strata(rel$stratum), ties = "breslow")
  b <- stats::coef(fm); V <- stats::vcov(fm)
  if (any(!is.finite(b)) || any(!is.finite(V))) stop("The Cox fit on the external records did not converge.", call. = FALSE)
  names(b) <- znames
  Q <- solve(V); Q <- (Q + t(Q)) / 2; dimnames(Q) <- list(znames, znames)
  list(beta = b, Q = Q)
}

.match_cols <- function(ze, znames) {
  miss <- setdiff(znames, colnames(ze))
  if (length(miss)) stop("The external records lack the target covariate(s): ", paste(miss, collapse = ", "), call. = FALSE)
  ze[, znames, drop = FALSE]
}

.engine_call <- function(target, release, divergence, penalty, alpha, etas, lambda, nlambda, lambda.min.ratio,
                         nfolds, seed, criterion, standardize, cv, ...) {
  z <- target$z; p <- ncol(z)
  zero <- stats::setNames(numeric(p), colnames(z))
  pfx <- if (cv) "cv." else ""
  suffix <- switch(penalty, none = "", ridge = "_ridge", lasso = "_enet", enet = "_enet")
  if (target$type == "discrete")
    return(.engine_call_discrete(target, release, divergence, penalty, alpha, etas, lambda, nlambda,
                                 lambda.min.ratio, nfolds, seed, standardize, cv, pfx, suffix, zero, ...))
  is_ncc <- target$type == "ncc"
  ## the external information in the form the estimator takes
  info <- list()
  if (divergence %in% c("kl", "mahalanobis")) {
    if (release$form == "records") info <- .records_to_coef(release, colnames(z))
    else if (release$form == "score") info$RS <- release$score
    else { info$beta <- release$beta; info$Q <- release$Q }
  }
  if (divergence == "kl" && !is.null(info$RS)) .check_len(info$RS, target$n, "score")
  if (divergence == "none") info$beta <- zero

  ## the estimator's name
  fam <- switch(divergence, none = if (is_ncc) "ncckl" else "coxkl", kl = if (is_ncc) "ncckl" else "coxkl",
                mahalanobis = if (is_ncc) "ncc_MDTL" else "cox_MDTL", composite = if (is_ncc) "ncc_indi" else "cox_indi")
  fun <- paste0(pfx, fam, suffix)
  exact <- !is_ncc && identical(target$ties, "exact")
  if (exact) fun <- paste0(pfx, "coxkl_ties")

  ## the data
  if (divergence == "composite") {
    ze <- .match_cols(release$z, colnames(z))
    args <- if (is_ncc) list(y_int = target$case, z_int = z, stratum_int = target$set,
                             y_ext = release$case, z_ext = ze, stratum_ext = release$set)
            else list(z_int = z, delta_int = target$event, time_int = target$time, stratum_int = target$stratum,
                      z_ext = ze, delta_ext = release$event, time_ext = release$time, stratum_ext = release$stratum)
  } else {
    args <- if (is_ncc) list(y = target$case, z = z, stratum = target$set)
            else list(z = z, delta = target$event, time = target$time, stratum = target$stratum)
  }
  if (!is.null(info$RS)) {
    if (is_ncc && penalty == "none") stop("The unpenalized matched Kullback-Leibler estimator takes coefficients; ",
                                         "release_coef() or a penalty.", call. = FALSE)
    if (exact) stop("ties = \"exact\" takes coefficients, not a risk score.", call. = FALSE)
    args$RS <- info$RS
  } else if (divergence != "composite") args$beta <- info$beta
  if (divergence == "mahalanobis") args$Q <- info$Q

  ## the weights and the penalty
  single_eta <- !cv && penalty != "none" && divergence != "composite"
  if (single_eta) args$eta <- etas else args$etas <- etas
  if (penalty != "none") {
    args$lambda <- lambda
    if (cv || is.null(lambda)) args$nlambda <- nlambda %||% 50
    if (penalty %in% c("lasso", "enet")) {
      args$alpha <- if (penalty == "lasso") 1 else alpha
      if (!is.null(lambda.min.ratio)) args$lambda.min.ratio <- lambda.min.ratio
    } else args$standardize <- standardize
  }
  if (!is_ncc && !exact) args$ties <- target$ties
  if (exact) args$ties <- "exact"
  if (cv) {
    args$nfolds <- nfolds; args$seed <- seed
    args$cv.criteria <- criterion %||% if (is_ncc) "loss" else "V&VH"
  }
  args$message <- FALSE
  args <- c(args, list(...))
  args <- args[!vapply(args, is.null, logical(1)) | names(args) %in% c("stratum", "stratum_int", "stratum_ext")]
  list(fun = fun, args = args)
}

## the discrete-time estimators take the same arguments as their Cox counterparts, with `interval` for
## `time`, and the external model's absolute risk (`hazard`, or `beta` with `baseline`) for the
## Kullback-Leibler family
.engine_call_discrete <- function(target, release, divergence, penalty, alpha, etas, lambda, nlambda,
                                  lambda.min.ratio, nfolds, seed, standardize, cv, pfx, suffix, zero, ...) {
  fam <- switch(divergence, none = , kl = "discretekl", mahalanobis = "discrete_MDTL", composite = "discrete_indi")
  fun <- paste0(pfx, fam, suffix)
  z <- target$z
  if (divergence == "composite") {
    ze <- .match_cols(release$z, colnames(z))
    args <- list(z_int = z, delta_int = target$event, interval_int = target$interval, stratum_int = target$stratum,
                 z_ext = ze, delta_ext = release$event, interval_ext = release$interval, stratum_ext = release$stratum)
  } else {
    args <- list(z = z, delta = target$event, interval = target$interval, stratum = target$stratum)
  }
  if (divergence == "kl") {
    if (!is.null(release$hazard)) args$hazard <- release$hazard
    else { args$beta <- release$beta; args$baseline <- release$baseline }
  }
  if (divergence == "none") { args$beta <- zero; args$baseline <- rep(1, target$K) }
  if (divergence == "mahalanobis") { args$beta <- release$beta; args$Q <- release$Q }
  args$link <- target$link; args$n_intervals <- target$K

  single_eta <- !cv && penalty != "none" && divergence != "composite"
  if (single_eta) args$eta <- etas else args$etas <- etas
  if (penalty != "none") {
    args$lambda <- lambda
    if (cv || is.null(lambda)) args$nlambda <- nlambda %||% 50
    if (penalty %in% c("lasso", "enet")) {
      args$alpha <- if (penalty == "lasso") 1 else alpha
      if (!is.null(lambda.min.ratio)) args$lambda.min.ratio <- lambda.min.ratio
    }
    args$standardize <- standardize
  }
  if (cv) { args$nfolds <- nfolds; args$seed <- seed }
  args$message <- FALSE
  args <- c(args, list(...))
  args <- args[!vapply(args, is.null, logical(1)) | names(args) %in% c("stratum", "stratum_int", "stratum_ext")]
  list(fun = fun, args = args)
}

## call the estimator. A target without strata is a choice made in target_cox(), so the estimators'
## reminder that all subjects share one stratum is not repeated to the user.
.call_engine <- function(call) {
  withCallingHandlers(do.call(call$fun, call$args), warning = function(w) {
    if (startsWith(conditionMessage(w), "Stratum not provided")) invokeRestart("muffleWarning")
  })
}

## a uniform cross-validation table from any of the cv.* estimators
.engine_path <- function(obj) {
  tab <- obj$internal_stat %||% obj$integrated_stat.best_per_eta
  if (is.null(tab)) return(NULL)
  tab <- as.data.frame(tab)
  val <- setdiff(names(tab)[vapply(tab, is.numeric, logical(1))], c("eta", "lambda", "alpha"))
  out <- data.frame(eta = tab$eta)
  if (!is.null(tab$lambda)) out$lambda <- tab$lambda
  out$value <- tab[[val[1]]]
  out
}

## the coefficients at eta = 0 (the target alone), from an estimator's full-data fits
.eta0_coef <- function(obj, znames) {
  pick <- function(B, etas) {
    j <- which(etas == 0)
    if (!length(j) || is.null(B)) return(NULL)
    stats::setNames(as.numeric(as.matrix(B)[, j[1]]), znames)
  }
  if (!is.null(obj$beta_full) && !is.null(obj$internal_stat$eta)) return(pick(obj$beta_full, obj$internal_stat$eta))
  if (!is.null(obj$integrated_stat.betahat_best) && !is.null(obj$integrated_stat.best_per_eta$eta))
    return(pick(obj$integrated_stat.betahat_best, obj$integrated_stat.best_per_eta$eta))
  NULL
}

## the external coefficients aligned to the target's covariates, when the release carries them
.external_coef <- function(target, release, divergence) {
  if (is.null(release)) return(NULL)
  b <- if (release$form %in% c("coefficients", "model")) release$beta
       else if (release$form == "records" && target$type == "cox" && divergence %in% c("kl", "mahalanobis"))
         .records_to_coef(release, colnames(target$z))$beta
       else NULL
  if (is.null(b)) return(NULL)
  b <- suppressMessages(align_beta(target$z, b))
  stats::setNames(as.numeric(b), colnames(target$z))
}

.ext_for_discrete <- function(target, release, divergence) {
  if (divergence == "none") return(NULL)
  if (divergence == "kl") {
    H <- release$hazard
    if (is.null(H)) {
      b <- align_beta(target$z, release$beta)
      if (length(release$baseline) != target$K)
        stop("'baseline' has ", length(release$baseline), " increments; the target has ", target$K, " intervals.", call. = FALSE)
      H <- -expm1(-outer(exp(drop(target$z %*% b)), release$baseline))
    }
    if (nrow(H) != target$n || ncol(H) != target$K)
      stop("'hazard' must be ", target$n, " x ", target$K, ".", call. = FALSE)
    return(list(teacher = H))
  }
  if (divergence == "mahalanobis") {
    aq <- align_beta_Q(target$z, release$beta, release$Q)
    Q <- aq$Q %||% aq[[2]]
    return(list(beta = aq$beta %||% aq[[1]], Q = unclass(as.matrix(Q)), manufactured = isTRUE(attr(Q, "manufactured"))))
  }
  if (divergence == "composite") {
    ze <- .match_cols(release$z, colnames(target$z))
    if (max(release$interval) > target$K) stop("The external records reach beyond the target's intervals.", call. = FALSE)
    return(list(z = ze, interval = release$interval, event = release$event, stratum = release$stratum))
  }
}

.ext_for_neural <- function(target, release, divergence) {
  if (divergence == "none") return(NULL)
  if (target$type == "discrete") return(.ext_for_discrete(target, release, "kl"))
  RS <- if (release$form == "score") release$score else drop(target$z %*% align_beta(target$z, release$beta))
  .check_len(RS, target$n, "score")
  list(score = RS)
}

# ---------------------------------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------------------------------
.divergence_label <- function(m) switch(m, composite = "composite likelihood (external records)",
                                        mahalanobis = "Mahalanobis distance", kl = "Kullback-Leibler",
                                        none = "none (your data alone)")

#' @export
print.cv.bregsurv <- function(x, ...) {
  tt <- x$target
  cat("Target:     ", switch(tt$type, cox = "Cox", ncc = "nested case-control", discrete = "discrete-time"),
      " (", tt$score, ")", if (!is.null(tt$ties) && tt$ties != "none") paste0(", ties ", tt$ties), "\n", sep = "")
  cat("Divergence: ", .divergence_label(x$divergence),
      if (x$penalty != "none") paste0(", ", x$penalty, " penalty"), "\n", sep = "")
  cat("Selected:   eta = ", format(x$eta, digits = 4),
      if (!is.null(x$lambda)) paste0(", lambda = ", format(x$lambda, digits = 4)), "\n", sep = "")
  cat("CV ", x$criterion, ": ", format(x$value, digits = 6), "  (", length(unique(x$folds)), " folds, seed ",
      x$seed, ")\n", sep = "")
  cat("Engine:     ", x$engine, "\n", sep = "")
  if (!is.null(x$coefficients)) { cat("\nCoefficients:\n"); print(round(x$coefficients, 4)) }
  invisible(x)
}

#' @export
print.bregsurv <- function(x, ...) {
  cat("Divergence: ", .divergence_label(x$divergence), " at eta = ", x$eta,
      if (!is.null(x$lambda)) paste0(", lambda = ", x$lambda), "  [", x$engine, "]\n", sep = "")
  if (!is.null(x$coefficients)) print(round(x$coefficients, 4))
  invisible(x)
}

#' @export
coef.cv.bregsurv <- function(object, ...) {
  if (is.null(object$coefficients)) stop("A neural target has no coefficients.", call. = FALSE)
  object$coefficients
}

#' @export
coef.bregsurv <- function(object, ...) object$coefficients

#' Predictions from a fitted model
#'
#' @param object A `cv.bregsurv` or `bregsurv` fit.
#' @param newz Covariates of new subjects, with the target's column names.
#' @param stratum Strata of the new subjects, when the target was stratified.
#' @param type What to predict:
#'   * `"lp"`: the risk score (the linear predictor \eqn{z^\top\beta}, or the network output) of a
#'     Cox or nested case-control target;
#'   * `"hazard"`: the interval hazards of a discrete-time target, one column per interval;
#'   * `"survival"`: survival probabilities: at the end of each interval for a discrete-time target,
#'     or at `times` for a Cox target (with the Breslow baseline hazard of the training data).
#' @param times Times at which to evaluate survival for a Cox target.
#' @param ... Unused.
#' @return A vector (`"lp"`) or a matrix with one row per new subject.
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train; te <- ExampleData_lowdim$test
#' fit <- cv.bregsurv(target_cox(tr$time, tr$status, tr$z),
#'                    release_coef(ExampleData_lowdim$beta_external_fair), divergence = "kl")
#' head(predict(fit, te$z))
#' predict(fit, te$z[1:3, ], type = "survival", times = c(1, 2, 3))
#' @export
predict.cv.bregsurv <- function(object, newz, stratum = NULL, type = c("lp", "hazard", "survival"),
                                times = NULL, ...) {
  type <- match.arg(type)
  tg <- object$training; tt <- object$target
  if (tt$type == "discrete") {
    H <- if (tt$score == "neural") .nn_predict(object$fit, newz, stratum) else
      .dt_predict(list(beta = object$coefficients, gamma = object$gamma, link = object$link,
                       strata_levels = object$strata_levels), newz, stratum)
    if (type == "hazard") return(H)
    if (type == "survival") { S <- t(apply(1 - H, 1, cumprod)); colnames(S) <- colnames(H); return(S) }
    stop("A discrete target predicts \"hazard\" or \"survival\".", call. = FALSE)
  }
  lp_new <- if (tt$score == "neural") .nn_predict(object$fit, newz) else
    drop(.as_z(newz)[, names(object$coefficients), drop = FALSE] %*% object$coefficients)
  if (type == "lp") return(lp_new)
  if (tt$type != "cox" || type != "survival") stop("This target predicts \"lp\"", if (tt$type == "cox") " or \"survival\"", ".", call. = FALSE)
  if (is.null(times)) stop("'times' is required for survival.", call. = FALSE)
  lp_tr <- if (tt$score == "neural") .nn_predict(object$fit, tg$z) else drop(tg$z %*% object$coefficients)
  st_tr <- if (is.null(tg$stratum)) rep(1, tg$n) else tg$stratum
  base <- .breslow_table(lp_tr, tg$time, tg$event, st_tr)
  st_new <- if (is.null(stratum)) rep(names(base)[1], length(lp_new)) else as.character(stratum)
  out <- t(vapply(seq_along(lp_new), function(i) {
    b <- base[[st_new[i]]]
    H0 <- vapply(times, function(t) { k <- which(b$time <= t); if (length(k)) b$cumhaz[max(k)] else 0 }, numeric(1))
    exp(-H0 * exp(lp_new[i]))
  }, numeric(length(times))))
  if (length(times) == 1) out <- t(out)
  colnames(out) <- paste0("t=", times)
  out
}

#' @rdname predict.cv.bregsurv
#' @export
predict.bregsurv <- function(object, newz, stratum = NULL, type = c("lp", "hazard", "survival"), times = NULL, ...) {
  predict.cv.bregsurv(object, newz, stratum, type, times, ...)
}
