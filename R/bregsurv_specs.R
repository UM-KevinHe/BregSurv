## The three decisions of the framework, as objects.
##
## bregsurv() and cv.bregsurv() take a target (the model the center fits), a release (what the external
## source released) and a divergence (how the release enters: composite likelihood, Mahalanobis or
## Kullback-Leibler). These constructors validate and hold the data; they fit nothing.

# ---------------------------------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------------------------------

#' Target models
#'
#' The target is the model your center fits to its own data. Every target can borrow from an external
#' release through [cv.bregsurv()]; what changes between targets is the likelihood the integration
#' weight is balanced against.
#'
#' * `target_cox()` is the stratified Cox model, scored by its log-partial likelihood. Tied event times
#'   are handled by `ties`: `"none"` (the default), `"breslow"`, or `"exact"` (Kullback-Leibler divergence
#'   only).
#' * `target_ncc()` is the nested case-control (matched case-control) design: the conditional
#'   likelihood of which member of each matched set is the case.
#' * `target_discrete()` is the grouped-time model of a discrete outcome: subject `i` is at risk in
#'   intervals `1, ..., interval[i]` and the event, if any, happens in `interval[i]`. The interval hazard
#'   is \eqn{h_{k}(z) = g^{-1}(\gamma_{sk} + z^\top\beta)} with a complementary log-log (grouped
#'   proportional hazards, the default) or logit link and one baseline parameter per stratum and interval.
#'
#' With `score = nn_score(...)`, the risk score of the Cox target, or the interval hazards of the
#' discrete target, are given by a neural network instead of a linear predictor (requires the `torch`
#' package).
#'
#' @param time Observed times.
#' @param event Event indicator (1 = event, 0 = censored).
#' @param z Covariate matrix or data frame, one row per subject, with column names.
#' @param stratum Optional stratum labels; each stratum has its own baseline.
#' @param ties Tie handling for `target_cox()`: `"none"`, `"breslow"` or `"exact"`.
#' @param score `"linear"` or an [nn_score()] specification.
#' @param case Case indicator for `target_ncc()` (1 = case, 0 = control).
#' @param set Matched-set identifier for `target_ncc()`.
#' @param interval Integer interval index `1, ..., K` of each subject's last interval at risk.
#' @param link Link of the linear discrete-time model: `"cloglog"` (grouped proportional hazards) or
#'   `"logit"`. The neural discrete-time model always uses the logit (logistic-hazard) link.
#' @param n_intervals Number of intervals `K`; defaults to `max(interval)`.
#'
#' @return An object of class `"bregsurv_target"`.
#' @seealso [release_coef()], [cv.bregsurv()]
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' tg <- target_cox(time = tr$time, event = tr$status, z = tr$z)
#' tg
#' @name targets
NULL

.as_z <- function(z, arg = "z") {
  if (is.null(z)) stop("'", arg, "' is required.", call. = FALSE)
  if (is.data.frame(z)) {
    bad <- !vapply(z, function(v) is.numeric(v) || is.logical(v), logical(1))
    if (any(bad)) stop("'", arg, "' has non-numeric columns: ", paste(names(z)[bad], collapse = ", "),
                       ". Code them as numbers first.", call. = FALSE)
  }
  z <- as.matrix(z)
  storage.mode(z) <- "double"
  if (is.null(colnames(z))) colnames(z) <- paste0("Z", seq_len(ncol(z)))
  if (anyNA(z)) stop("'", arg, "' contains missing values.", call. = FALSE)
  z
}

.check_len <- function(x, n, arg) {
  if (length(x) != n) stop("'", arg, "' has length ", length(x), " but there are ", n, " rows.", call. = FALSE)
  invisible(x)
}

#' @rdname targets
#' @export
target_cox <- function(time, event, z, stratum = NULL, ties = c("none", "breslow", "exact"),
                       score = "linear") {
  ties <- match.arg(ties)
  z <- .as_z(z)
  n <- nrow(z)
  time <- as.numeric(time); .check_len(time, n, "time")
  if (anyNA(time) || any(time <= 0)) stop("'time' must be positive and not missing.", call. = FALSE)
  event <- .check_event(event, "event"); .check_len(event, n, "event")
  if (!is.null(stratum)) .check_len(stratum, n, "stratum")
  score <- .check_score(score)
  if (inherits(score, "nn_score") && ties == "exact")
    stop("ties = \"exact\" is available for the linear Kullback-Leibler divergence only.", call. = FALSE)
  structure(list(type = "cox", time = time, event = event, z = z, stratum = stratum, ties = ties,
                 score = score, n = n), class = "bregsurv_target")
}

#' @rdname targets
#' @export
target_ncc <- function(case, set, z) {
  z <- .as_z(z)
  n <- nrow(z)
  case <- .check_event(case, "case"); .check_len(case, n, "case")
  .check_len(set, n, "set")
  per_set <- tapply(case, set, sum)
  if (any(per_set != 1))
    stop(sum(per_set != 1), " matched set(s) do not contain exactly one case.", call. = FALSE)
  structure(list(type = "ncc", case = case, set = set, z = z, score = "linear", n = n),
            class = "bregsurv_target")
}

#' @rdname targets
#' @export
target_discrete <- function(interval, event, z, stratum = NULL, link = c("cloglog", "logit"),
                            n_intervals = NULL, score = "linear") {
  link <- match.arg(link)
  z <- .as_z(z)
  n <- nrow(z)
  .check_len(interval, n, "interval")
  if (anyNA(interval) || any(interval != round(interval)) || any(interval < 1))
    stop("'interval' must hold whole numbers 1, 2, ..., K.", call. = FALSE)
  interval <- as.integer(interval)
  K <- if (is.null(n_intervals)) max(interval) else as.integer(n_intervals)
  if (max(interval) > K) stop("'interval' exceeds n_intervals = ", K, ".", call. = FALSE)
  event <- .check_event(event, "event"); .check_len(event, n, "event")
  if (!is.null(stratum)) .check_len(stratum, n, "stratum")
  score <- .check_score(score)
  if (inherits(score, "nn_score")) {
    if (!is.null(stratum)) stop("The neural discrete-time model has one set of interval outputs; it takes no strata.",
                                call. = FALSE)
    link <- "logit"
  }
  structure(list(type = "discrete", interval = interval, event = event, z = z, stratum = stratum,
                 link = link, K = K, score = score, n = n), class = "bregsurv_target")
}

.check_score <- function(score) {
  if (identical(score, "linear")) return("linear")
  if (inherits(score, "nn_score")) return(score)
  stop("'score' must be \"linear\" or nn_score(...).", call. = FALSE)
}

#' @export
print.bregsurv_target <- function(x, ...) {
  what <- switch(x$type, cox = "Cox model", ncc = "nested case-control design",
                 discrete = paste0("discrete-time model (", x$K, " intervals, ", x$link, " link)"))
  sc <- if (inherits(x$score, "nn_score")) "neural-network" else "linear"
  ev <- if (x$type == "ncc") sum(x$case) else sum(x$event)
  cat("Target: ", what, ", ", sc, " risk score\n", sep = "")
  cat("  ", x$n, " subjects, ", ncol(x$z), " covariates, ", ev,
      if (x$type == "ncc") " matched sets" else " events", "\n", sep = "")
  if (x$type == "cox" && x$ties != "none") cat("  tied event times: ", x$ties, "\n", sep = "")
  invisible(x)
}

# ---------------------------------------------------------------------------------------------------
# Neural risk score
# ---------------------------------------------------------------------------------------------------

#' A neural-network risk score
#'
#' Pass `nn_score()` as the `score` of [target_cox()] or [target_discrete()] to replace the linear
#' predictor by a feed-forward network. The default network is four residual blocks of width 128
#' (linear layer, layer normalization, ReLU, dropout), trained with Adam and early stopping. For the
#' discrete target the network outputs one logit per interval (a logistic-hazard model); for the Cox
#' target it outputs one risk score, and the partial likelihood of each mini-batch is formed over the
#' risk sets within the batch.
#'
#' Only the Kullback-Leibler divergence is defined for a neural target, because the other two
#' divergences compare coefficients. Fitting requires the `torch` package (`install.packages("torch")`, then
#' `torch::install_torch()` once).
#'
#' @param hidden Widths of the hidden layers. A layer whose width equals the previous one gets a
#'   residual connection.
#' @param dropout Dropout probability after each hidden layer.
#' @param learning_rates Candidate Adam learning rates; one is chosen by cross-validation at
#'   `eta = 0` before the integration weight is chosen.
#' @param batch_size Mini-batch size. `NULL` uses 32 for the discrete target and 64 for the Cox target.
#' @param max_epochs Maximum number of epochs.
#' @param patience,min_delta Early stopping: stop when the held-out objective has not improved by
#'   `min_delta` for `patience` epochs.
#' @param stop_fraction Share of each training set held out for early stopping.
#' @param threads Number of CPU threads torch may use.
#'
#' @return An object of class `"nn_score"`.
#' @examples
#' nn_score(hidden = c(32, 32), dropout = 0.1)
#' @export
nn_score <- function(hidden = c(128, 128, 128, 128), dropout = 0.1,
                     learning_rates = c(5e-4, 1e-3), batch_size = NULL, max_epochs = 512,
                     patience = 5, min_delta = 1e-5, stop_fraction = 0.2, threads = 1) {
  hidden <- as.integer(hidden)
  if (!length(hidden) || any(hidden < 1)) stop("'hidden' must be positive layer widths.", call. = FALSE)
  if (dropout < 0 || dropout >= 1) stop("'dropout' must be in [0, 1).", call. = FALSE)
  if (stop_fraction <= 0 || stop_fraction >= 1) stop("'stop_fraction' must be in (0, 1).", call. = FALSE)
  structure(list(hidden = hidden, dropout = dropout, learning_rates = as.numeric(learning_rates),
                 batch_size = batch_size, max_epochs = as.integer(max_epochs),
                 patience = as.integer(patience), min_delta = min_delta,
                 stop_fraction = stop_fraction, threads = as.integer(threads)),
            class = "nn_score")
}

#' @export
print.nn_score <- function(x, ...) {
  cat("Neural risk score: hidden ", paste(x$hidden, collapse = " x "), ", dropout ", x$dropout,
      ", Adam (learning rate chosen from ", paste(x$learning_rates, collapse = ", "), ")\n", sep = "")
  invisible(x)
}

# ---------------------------------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------------------------------

#' External releases
#'
#' A release is what the external source made available. Its form decides which divergences
#' can use it (the `divergence` argument of [cv.bregsurv()]):
#'
#' | release | divergences it supports |
#' |---|---|
#' | `release_records()`: individual-level records | composite likelihood; on a Cox target also Mahalanobis and Kullback-Leibler, through a Cox model fitted to the records |
#' | `release_coef()`: coefficients, optionally with their precision matrix `Q` | Mahalanobis (Euclidean when `Q = NULL`) and Kullback-Leibler |
#' | `release_score()`: a risk score evaluated on your subjects | Kullback-Leibler |
#' | `release_model()`: coefficients with the baseline hazard, or interval hazards | Kullback-Leibler on the discrete-time target (absolute risk), and everything `release_coef()` supports |
#'
#' @param z Covariates of the external records, with the target's column names.
#' @param time,event,stratum External follow-up, event indicator and strata (cohort records).
#' @param case,set External case indicator and matched sets (nested case-control records).
#' @param interval External interval index (records for a discrete-time target).
#' @param beta Named external coefficient vector. Every name must be one of your covariates; covariates
#'   the release does not cover are set to zero (see [align_beta()]).
#' @param Q Optional precision matrix of `beta` (inverse covariance or information matrix), named like
#'   `beta`.
#' @param score Numeric vector: the external risk score of each target subject.
#' @param baseline Baseline cumulative-hazard increments of the external Cox model over the target's
#'   intervals `1, ..., K`.
#' @param hazard Matrix of external interval hazards, one row per target subject and one column per
#'   interval (an alternative to `beta` + `baseline`).
#'
#' @return An object of class `"bregsurv_release"`.
#' @examples
#' data(ExampleData_lowdim)
#' release_coef(ExampleData_lowdim$beta_external_fair)
#' @name releases
NULL

#' @rdname releases
#' @export
release_records <- function(z, time = NULL, event = NULL, stratum = NULL, case = NULL, set = NULL,
                            interval = NULL) {
  z <- .as_z(z, "z (external)")
  n <- nrow(z)
  if (!is.null(case)) {
    case <- .check_event(case, "case"); .check_len(case, n, "case"); .check_len(set, n, "set")
    kind <- "ncc"
  } else if (!is.null(interval)) {
    event <- .check_event(event, "event"); .check_len(event, n, "event"); .check_len(interval, n, "interval")
    kind <- "discrete"
  } else {
    if (is.null(time) || is.null(event)) stop("Cohort records need 'time' and 'event'.", call. = FALSE)
    time <- as.numeric(time); .check_len(time, n, "time")
    event <- .check_event(event, "event"); .check_len(event, n, "event")
    kind <- "cohort"
  }
  if (!is.null(stratum)) .check_len(stratum, n, "stratum")
  structure(list(form = "records", kind = kind, z = z, time = time, event = event, stratum = stratum,
                 case = case, set = set, interval = if (is.null(interval)) NULL else as.integer(interval)),
            class = "bregsurv_release")
}

#' @rdname releases
#' @export
release_coef <- function(beta, Q = NULL) {
  beta <- .as_beta(beta)
  if (!is.null(Q)) Q <- .as_Q(Q, beta)
  structure(list(form = "coefficients", beta = beta, Q = Q), class = "bregsurv_release")
}

#' @rdname releases
#' @export
release_score <- function(score) {
  score <- as.numeric(score)
  if (anyNA(score) || any(!is.finite(score))) stop("'score' must be finite.", call. = FALSE)
  structure(list(form = "score", score = score), class = "bregsurv_release")
}

#' @rdname releases
#' @export
release_model <- function(beta = NULL, baseline = NULL, hazard = NULL, Q = NULL) {
  if (is.null(hazard) && (is.null(beta) || is.null(baseline)))
    stop("Give 'beta' and 'baseline', or 'hazard'.", call. = FALSE)
  if (!is.null(beta)) beta <- .as_beta(beta)
  if (!is.null(baseline)) {
    baseline <- as.numeric(baseline)
    if (anyNA(baseline) || any(baseline < 0) || !any(baseline > 0))
      stop("'baseline' increments must be non-negative, finite and not all zero.", call. = FALSE)
  }
  if (!is.null(hazard)) {
    hazard <- as.matrix(hazard)
    if (anyNA(hazard) || any(hazard < 0) || any(hazard > 1))
      stop("'hazard' must hold interval hazards in [0, 1].", call. = FALSE)
  }
  if (!is.null(Q)) Q <- .as_Q(Q, beta)
  structure(list(form = "model", beta = beta, baseline = baseline, hazard = hazard, Q = Q),
            class = "bregsurv_release")
}

.as_beta <- function(beta) {
  if (is.matrix(beta) && ncol(beta) == 1) beta <- stats::setNames(beta[, 1], rownames(beta))
  if (!is.numeric(beta) || anyNA(beta)) stop("'beta' must be a numeric vector without missing values.",
                                              call. = FALSE)
  beta
}

.as_Q <- function(Q, beta) {
  Q <- as.matrix(Q)
  if (nrow(Q) != ncol(Q)) stop("'Q' must be square.", call. = FALSE)
  if (!is.null(beta) && nrow(Q) != length(beta)) stop("'Q' must match the length of 'beta'.", call. = FALSE)
  if (is.null(rownames(Q)) && !is.null(names(beta))) dimnames(Q) <- list(names(beta), names(beta))
  Q
}

#' @export
print.bregsurv_release <- function(x, ...) {
  switch(x$form,
         records = cat("Release: individual-level records (", x$kind, "), ", nrow(x$z), " subjects\n", sep = ""),
         coefficients = cat("Release: ", length(x$beta), " coefficients",
                            if (is.null(x$Q)) "" else " with their precision matrix", "\n", sep = ""),
         score = cat("Release: a risk score for ", length(x$score), " subjects\n", sep = ""),
         model = cat("Release: a fitted model",
                     if (!is.null(x$hazard)) paste0(" (interval hazards, ", ncol(x$hazard), " intervals)")
                     else paste0(" (", length(x$beta), " coefficients, baseline over ",
                                 length(x$baseline), " intervals)"), "\n", sep = ""))
  invisible(x)
}

## which divergences a release supports on a target, in the framework's order; the first is the default
.divergences_for <- function(release, target) {
  if (is.null(release)) return("none")
  lin <- identical(target$score, "linear")
  out <- switch(release$form,
    records = {
      if (!lin) character(0)
      else if (target$type == "cox" && release$kind == "cohort") c("composite", "mahalanobis", "kl")
      else if (target$type == "ncc" && release$kind == "ncc") "composite"
      else if (target$type == "discrete" && release$kind == "discrete") "composite"
      else character(0)
    },
    coefficients = {
      if (target$type == "discrete") { if (lin) "mahalanobis" else character(0) }
      else if (!lin) "kl"
      else if (is.null(release$Q)) c("kl", "mahalanobis") else c("mahalanobis", "kl")
    },
    score = if (target$type == "discrete") character(0) else "kl",
    model = {
      if (target$type == "discrete") c("kl", if (lin && !is.null(release$beta)) "mahalanobis")
      else if (is.null(release$beta)) character(0)
      else if (!lin) "kl"
      else if (is.null(release$Q)) c("kl", "mahalanobis") else c("mahalanobis", "kl")
    })
  out
}
