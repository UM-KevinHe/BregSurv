## The framework's single interface: target x release x member x penalty.
##
## Linear Cox and nested case-control targets dispatch to the estimators the package has always had
## (coxkl*, cox_MDTL*, cox_indi*, ncckl*, ncc_MDTL*, ncc_indi*), so their numbers are exactly those
## estimators' numbers. The discrete-time target and the neural risk scores have their own engines.

`%||%` <- function(a, b) if (is.null(a)) b else a

.log_eta <- function(hi, n, lo = 0.01) c(0, exp(seq(log(lo), log(hi), length.out = n)))

## default integration-weight grids: log spaced from 0.01 to the member's upper end, eta = 0 kept as the
## target-only endpoint (the grids the agent uses)
.default_etas <- function(member, penalty, target) {
  if (inherits(target$score, "nn_score")) return(c(0, 1, 5, 10, 20, 40, 80))
  if (target$type == "discrete" && member == "kl") return(c(0, 1, 5, 10, 20, 50, 100))
  pen <- penalty != "none"
  switch(member,
         none = 0,
         kl = , composite = .log_eta(2e2, if (pen) 41 else 81),
         mahalanobis = if (penalty %in% c("lasso", "enet")) .log_eta(1e3, 41) else .log_eta(1e6, if (pen) 41 else 81))
}

#' Fit a member of the Bregman-divergence framework, choosing the integration weight by cross-validation
#'
#' `cv.bregsurv()` is the package's main interface. It takes the three decisions the framework separates:
#' the **target** model your data call for ([target_cox()], [target_ncc()], [target_discrete()], linear or
#' neural), the **release** the external source made ([release_records()], [release_coef()],
#' [release_score()], [release_model()]), and the **member** through which the release enters, which
#' fixes the Bregman generator:
#'
#' * `"composite"`: the negative external log-likelihood, giving the composite likelihood (records);
#' * `"mahalanobis"`: a quadratic form, giving the Mahalanobis distance to the external coefficients
#'   (Euclidean when the release has no precision matrix);
#' * `"kl"`: the negative entropy on the model's conditional distributions (risk sets, or interval
#'   hazards for the discrete target), giving the Kullback-Leibler divergence;
#' * `"none"`: no release, the target model alone (the `eta = 0` endpoint).
#'
#' The integration weight `eta` (and, under a penalty, `lambda`) is chosen by `nfolds`-fold
#' cross-validation on the target data. Every member fitted with the same `seed` on the same target is
#' scored on the same partition by the same criterion, so their `value`s can be compared directly:
#' the cross-validated partial-likelihood loss of Verweij and Van Houwelingen for a Cox target, the
#' conditional-likelihood loss for a matched design, and the held-out negative log-likelihood per
#' subject for a discrete target.
#'
#' Linear Cox and matched targets are fitted by the package's existing estimators (`cv.coxkl`,
#' `cv.cox_MDTL_enet`, `cv.ncc_indi`, ...), named in the result's `engine` field; the result is
#' identical to calling that estimator directly. The discrete-time target is fitted by Fisher scoring
#' (proximal Newton under a lasso or elastic net), and neural targets by `torch`.
#'
#' @param target A target from [target_cox()], [target_ncc()] or [target_discrete()].
#' @param release A release, or `NULL` for the target model alone.
#' @param member `"composite"`, `"mahalanobis"`, `"kl"` or `"none"`. `NULL` takes the first member the
#'   release supports: composite for records, Mahalanobis for coefficients with a precision matrix,
#'   Kullback-Leibler otherwise.
#' @param penalty `"none"`, `"ridge"`, `"lasso"` or `"enet"` (elastic net with mixing `alpha`).
#' @param alpha Elastic-net mixing parameter for `penalty = "enet"`.
#' @param etas Integration weights to search. `NULL` uses a log-spaced grid from 0.01 to the member's
#'   upper end, with 0 included.
#' @param lambda,nlambda,lambda.min.ratio The penalty path; `NULL` builds a path for each `eta`.
#' @param nfolds Number of folds.
#' @param seed Seed of the fold assignment. The default is fixed, so repeated calls, and different
#'   members, share one partition.
#' @param criterion Cross-validation criterion of the Cox (`"V&VH"`, `"LinPred"`, `"CIndex_pooled"`,
#'   `"CIndex_foldaverage"`) or matched (`"loss"`, `"AUC"`, `"CIndex"`, `"Brier"`) estimators. Members
#'   are comparable only under the same criterion; the discrete and neural targets use their own.
#' @param standardize Standardize covariates for the penalized fits.
#' @param ... Further arguments passed to the underlying estimator.
#'
#' @return An object of class `"cv.bregsurv"` with the selected `eta` and `lambda`, the cross-validated
#'   `value` and its `criterion`, the `coefficients` of a linear target, the `folds`, the `engine` used
#'   and its full result in `fit`.
#' @seealso [bregsurv()] for a fit at a given weight; [targets], [releases].
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' tg <- target_cox(tr$time, tr$status, tr$z)
#' rl <- release_coef(ExampleData_lowdim$beta_external_fair)
#' kl  <- cv.bregsurv(tg, rl, member = "kl")
#' euc <- cv.bregsurv(tg, rl, member = "mahalanobis")
#' own <- cv.bregsurv(tg)                       # the target alone
#' c(kl = kl$value, euclidean = euc$value, target_only = own$value)
#' @export
cv.bregsurv <- function(target, release = NULL, member = NULL,
                        penalty = c("none", "ridge", "lasso", "enet"), alpha = 0.5,
                        etas = NULL, lambda = NULL, nlambda = 50, lambda.min.ratio = NULL,
                        nfolds = 5, seed = 20260818L, criterion = NULL, standardize = TRUE, ...) {
  penalty <- match.arg(penalty)
  sp <- .resolve(target, release, member, penalty)
  member <- sp$member
  if (is.null(etas)) etas <- .default_etas(member, penalty, target)
  if (member == "none") etas <- 0
  neural <- inherits(target$score, "nn_score")

  if (neural) {
    if (penalty != "none") stop("A neural target is regularized by early stopping and dropout; use penalty = \"none\".",
                                call. = FALSE)
    ext <- .ext_for_neural(target, release, member)
    r <- .nn_cv(target, ext, etas, nfolds, NULL, seed)
    out <- list(eta = r$eta, lambda = NULL, value = r$value, criterion = r$criterion, coefficients = NULL,
                folds = r$folds, seed = r$seed, path = r$pooled, engine = "neural network (torch)", fit = r)
  } else if (target$type == "discrete") {
    ext <- .ext_for_discrete(target, release, member)
    r <- .dt_cv(target, member, ext, penalty, alpha, etas, lambda, nlambda, lambda.min.ratio, nfolds,
                NULL, seed, standardize, tol = 1e-9, max_iter = 200)
    out <- list(eta = r$eta, lambda = r$lambda, value = r$value, criterion = r$criterion,
                coefficients = r$beta, folds = r$folds, seed = r$seed,
                path = r$pooled, engine = "grouped-time model (Fisher scoring)", fit = r)
  } else {
    call <- .engine_call(target, release, member, penalty, alpha, etas, lambda, nlambda, lambda.min.ratio,
                         nfolds, seed, criterion, standardize, cv = TRUE, ...)
    obj <- do.call(call$fun, call$args)
    best <- obj$best
    b <- best$best_beta
    if (is.matrix(b)) b <- b[, 1]
    b <- as.numeric(b); names(b) <- colnames(target$z)
    out <- list(eta = if (member == "none") 0 else best$best_eta, lambda = best$best_lambda,
                value = best$best_value, criterion = best$criteria, coefficients = b,
                folds = obj$folds, seed = obj$seed, path = .engine_path(obj), engine = call$fun, fit = obj)
  }
  out$member <- member; out$penalty <- penalty; out$alpha <- if (penalty == "enet") alpha else NULL
  out$target <- .target_summary(target); out$release <- if (is.null(release)) "none" else release$form
  out$training <- target
  out$call <- match.call()
  structure(out, class = "cv.bregsurv")
}

#' Fit a member of the framework at a given integration weight
#'
#' `bregsurv()` fits one member at a fixed `eta` (and `lambda` under a penalty), without
#' cross-validation. See [cv.bregsurv()] for the arguments and for choosing `eta` from the data.
#'
#' @inheritParams cv.bregsurv
#' @param eta The integration weight (`0` is the target model alone).
#' @param lambda Penalty level, required when `penalty` is not `"none"`.
#' @return An object of class `"bregsurv"` with the `coefficients` (linear targets), the `engine` used
#'   and its result in `fit`.
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' fit <- bregsurv(target_cox(tr$time, tr$status, tr$z),
#'                 release_coef(ExampleData_lowdim$beta_external_good), member = "kl", eta = 1)
#' coef(fit)
#' @export
bregsurv <- function(target, release = NULL, member = NULL, eta = 0,
                     penalty = c("none", "ridge", "lasso", "enet"), alpha = 0.5, lambda = NULL,
                     standardize = TRUE, ...) {
  penalty <- match.arg(penalty)
  sp <- .resolve(target, release, member, penalty)
  member <- sp$member
  if (member == "none") eta <- 0
  if (length(eta) != 1 || eta < 0) stop("'eta' must be one non-negative number.", call. = FALSE)
  if (penalty != "none" && (is.null(lambda) || length(lambda) != 1))
    stop("A penalized fit at a given weight needs one 'lambda'; use cv.bregsurv() to choose it.", call. = FALSE)
  if (inherits(target$score, "nn_score"))
    stop("A neural target is fitted by cv.bregsurv(), which chooses its training length; ",
         "pass etas = <your eta> there to fix the weight.", call. = FALSE)
  if (target$type == "discrete") {
    ext <- .ext_for_discrete(target, release, member)
    a <- switch(penalty, none = 0, ridge = 0, lasso = 1, enet = alpha)
    r <- .dt_fit(target, member, ext, eta, if (penalty == "none") NULL else lambda, a, standardize,
                 tol = 1e-9, max_iter = 200)
    out <- list(coefficients = r$beta, eta = eta, lambda = lambda, engine = "grouped-time model (Fisher scoring)", fit = r)
  } else {
    call <- .engine_call(target, release, member, penalty, alpha, eta, lambda, NULL, NULL, NULL, NULL, NULL,
                         standardize, cv = FALSE, ...)
    obj <- do.call(call$fun, call$args)
    b <- obj$beta
    while (is.list(b)) b <- b[[1]]
    if (is.matrix(b)) b <- b[, 1]
    b <- as.numeric(b); names(b) <- colnames(target$z)
    out <- list(coefficients = b, eta = eta, lambda = lambda, engine = call$fun, fit = obj)
  }
  out$member <- member; out$penalty <- penalty; out$target <- .target_summary(target)
  out$release <- if (is.null(release)) "none" else release$form
  out$training <- target
  out$call <- match.call()
  structure(out, class = "bregsurv")
}

# ---------------------------------------------------------------------------------------------------
# Resolution and dispatch
# ---------------------------------------------------------------------------------------------------
.resolve <- function(target, release, member, penalty) {
  if (!inherits(target, "bregsurv_target")) stop("'target' must come from target_cox(), target_ncc() or target_discrete().",
                                                 call. = FALSE)
  if (!is.null(release) && !inherits(release, "bregsurv_release"))
    stop("'release' must come from release_records(), release_coef(), release_score() or release_model().", call. = FALSE)
  allowed <- .members_for(release, target)
  if (!length(allowed)) stop("This release cannot inform this target: ", .why_not(release, target), call. = FALSE)
  if (is.null(member)) member <- allowed[1]
  member <- match.arg(member, c("composite", "mahalanobis", "kl", "none"))
  if (member == "none" && !is.null(release)) stop("member = \"none\" fits the target alone; drop the release.", call. = FALSE)
  if (!member %in% allowed)
    stop("A ", release$form, " release supports the member(s) ", paste(allowed, collapse = ", "),
         " on this target, not \"", member, "\".", call. = FALSE)
  if (target$type == "cox" && target$ties == "exact" && !(member %in% c("kl", "none") && penalty == "none"))
    stop("ties = \"exact\" is available for the unpenalized Kullback-Leibler member only; use \"breslow\".", call. = FALSE)
  if (target$type == "ncc" && member == "composite" && penalty == "ridge")
    stop("The matched design has no ridge composite-likelihood estimator; use \"lasso\" or \"enet\".", call. = FALSE)
  if (target$type == "discrete" && member == "mahalanobis" && target$link != "cloglog")
    stop("The Mahalanobis member compares the coefficients with a Cox model's, which only the cloglog link shares.",
         call. = FALSE)
  list(member = member)
}

.why_not <- function(release, target) {
  if (inherits(target$score, "nn_score")) return("a neural target can borrow only through the Kullback-Leibler member.")
  if (release$form == "score" && target$type == "discrete")
    return("the discrete-time target needs interval hazards: use release_model() with the baseline hazard.")
  if (release$form == "records") return("the records must have the target's design (cohort, matched or discrete).")
  "no member of the framework applies."
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

.engine_call <- function(target, release, member, penalty, alpha, etas, lambda, nlambda, lambda.min.ratio,
                         nfolds, seed, criterion, standardize, cv, ...) {
  z <- target$z; p <- ncol(z)
  zero <- stats::setNames(numeric(p), colnames(z))
  is_ncc <- target$type == "ncc"
  pfx <- if (cv) "cv." else ""
  ## the external information in the form the estimator takes
  info <- list()
  if (member %in% c("kl", "mahalanobis")) {
    if (release$form == "records") info <- .records_to_coef(release, colnames(z))
    else if (release$form == "score") info$RS <- release$score
    else { info$beta <- release$beta; info$Q <- release$Q }
  }
  if (member == "kl" && !is.null(info$RS)) .check_len(info$RS, target$n, "score")
  if (member == "none") info$beta <- zero

  ## the estimator's name
  fam <- switch(member, none = if (is_ncc) "ncckl" else "coxkl", kl = if (is_ncc) "ncckl" else "coxkl",
                mahalanobis = if (is_ncc) "ncc_MDTL" else "cox_MDTL", composite = if (is_ncc) "ncc_indi" else "cox_indi")
  suffix <- switch(penalty, none = "", ridge = "_ridge", lasso = "_enet", enet = "_enet")
  fun <- paste0(pfx, fam, suffix)
  exact <- !is_ncc && identical(target$ties, "exact")
  if (exact) fun <- paste0(pfx, "coxkl_ties")

  ## the data
  if (member == "composite") {
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
  } else if (member != "composite") args$beta <- info$beta
  if (member == "mahalanobis") args$Q <- info$Q

  ## the weights and the penalty
  single_eta <- !cv && penalty != "none" && member != "composite"
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

.ext_for_discrete <- function(target, release, member) {
  if (member == "none") return(NULL)
  if (member == "kl") {
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
  if (member == "mahalanobis") {
    aq <- align_beta_Q(target$z, release$beta, release$Q)
    Q <- aq$Q %||% aq[[2]]
    return(list(beta = aq$beta %||% aq[[1]], Q = unclass(as.matrix(Q)), manufactured = isTRUE(attr(Q, "manufactured"))))
  }
  if (member == "composite") {
    ze <- .match_cols(release$z, colnames(target$z))
    if (max(release$interval) > target$K) stop("The external records reach beyond the target's intervals.", call. = FALSE)
    return(list(z = ze, interval = release$interval, event = release$event, stratum = release$stratum))
  }
}

.ext_for_neural <- function(target, release, member) {
  if (member == "none") return(NULL)
  if (target$type == "discrete") return(.ext_for_discrete(target, release, "kl"))
  RS <- if (release$form == "score") release$score else drop(target$z %*% align_beta(target$z, release$beta))
  .check_len(RS, target$n, "score")
  list(score = RS)
}

# ---------------------------------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------------------------------
.member_label <- function(m) switch(m, composite = "composite likelihood (records)", mahalanobis = "Mahalanobis",
                                    kl = "Kullback-Leibler", none = "none (target model alone)")

#' @export
print.cv.bregsurv <- function(x, ...) {
  tt <- x$target
  cat("Target:   ", switch(tt$type, cox = "Cox", ncc = "nested case-control", discrete = "discrete-time"),
      " (", tt$score, ")", if (!is.null(tt$ties) && tt$ties != "none") paste0(", ties ", tt$ties), "\n", sep = "")
  cat("Member:   ", .member_label(x$member), if (x$penalty != "none") paste0(", ", x$penalty, " penalty"), "\n", sep = "")
  cat("Selected: eta = ", format(x$eta, digits = 4),
      if (!is.null(x$lambda)) paste0(", lambda = ", format(x$lambda, digits = 4)), "\n", sep = "")
  cat("CV ", x$criterion, ": ", format(x$value, digits = 6), "  (", length(unique(x$folds)), " folds, seed ",
      x$seed, ")\n", sep = "")
  cat("Engine:   ", x$engine, "\n", sep = "")
  if (!is.null(x$coefficients)) { cat("\nCoefficients:\n"); print(round(x$coefficients, 4)) }
  invisible(x)
}

#' @export
print.bregsurv <- function(x, ...) {
  cat("Member: ", .member_label(x$member), " at eta = ", x$eta,
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

#' Predictions from a fitted member
#'
#' @param object A `cv.bregsurv` or `bregsurv` fit.
#' @param newz Covariates of new subjects (columns named like the target's).
#' @param stratum Strata of the new subjects, when the target was stratified.
#' @param type `"lp"`: the risk score (linear predictor, or network output) of a Cox or matched target;
#'   `"hazard"`: interval hazards of a discrete target; `"survival"`: survival at the end of each
#'   interval (discrete) or at `times` (Cox, Breslow baseline from the training data).
#' @param times Times at which to evaluate survival for a Cox target.
#' @param ... Unused.
#' @return A vector or a matrix with one row per new subject.
#' @export
predict.cv.bregsurv <- function(object, newz, stratum = NULL, type = c("lp", "hazard", "survival"),
                                times = NULL, ...) {
  type <- match.arg(type)
  tg <- object$training; tt <- object$target
  if (tt$type == "discrete") {
    H <- if (tt$score == "neural") .nn_predict(object$fit, newz, stratum) else .dt_predict(object$fit, newz, stratum)
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
