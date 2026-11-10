## The three decisions of the framework, as objects.
##
## bregsurv() and cv.bregsurv() take a target (the model the center fits), a release (what the external
## source released) and a divergence (how the release enters: composite likelihood, Mahalanobis or
## Kullback-Leibler). These constructors validate and hold the data; they fit nothing.

# ---------------------------------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------------------------------


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

#' Target: a Cox model
#'
#' @description
#' Builds the target of an analysis whose outcome is a follow-up time with an event indicator: the
#' (stratified) Cox proportional-hazards model
#' \deqn{h(t \mid z) = h_{0s}(t)\, \exp(z^\top\beta),}
#' with a baseline hazard \eqn{h_{0s}} for each stratum \eqn{s} and coefficients \eqn{\beta} shared by
#' all strata. The target sets the likelihood \eqn{\ell(\theta)} in the objective of [cv.bregsurv()]:
#' the log partial likelihood of your data.
#'
#' `target_cox()` checks your data and stores it; it fits nothing. Pass the result to [cv.bregsurv()]
#' (or [bregsurv()]) as `target`.
#'
#' @param time Observed follow-up time of each subject: the event time when `event = 1`, the censoring
#'   time when `event = 0`. Positive numbers, with no missing values.
#' @param event Event indicator of each subject: 1 if the event was observed, 0 if the subject was
#'   censored. Numeric, logical, or the characters `"0"` and `"1"`. A factor, a missing value or any
#'   other code (such as a competing event coded 2) is refused.
#' @param z Covariates: a numeric matrix, or a data frame of numeric columns, with one row per subject
#'   and one named column per covariate. The column names are how an external model's coefficients and
#'   an external cohort's records are matched to your covariates (unnamed columns are called `Z1`,
#'   `Z2`, ...). Code categorical covariates as numbers, for instance as indicator columns, first.
#'   Missing values are refused.
#' @param stratum Optional stratum of each subject, any labels (for instance the centre). Each stratum
#'   has its own baseline hazard and the coefficients are shared. `NULL` puts every subject in one
#'   stratum.
#' @param ties How tied event times enter the partial likelihood:
#'   * `"none"` (the default): subjects who fail at the same time are taken in the order of your data;
#'   * `"breslow"`: Breslow's approximation, in which everyone still at risk at a tied event time is in
#'     its risk set; available with every divergence and penalty;
#'   * `"exact"`: Cox's exact partial likelihood; available with the Kullback-Leibler divergence and no
#'     penalty.
#'
#'   The three coincide when no two events share a time.
#' @param score The form of the risk score: `"linear"` (the default), the linear predictor
#'   \eqn{z^\top\beta}, or a neural network specified by [nn_score()] (requires the `torch` package; the
#'   Kullback-Leibler divergence only).
#'
#' @return An object of class `"bregsurv_target"`, a list with
#' \describe{
#'   \item{`type`}{`"cox"`.}
#'   \item{`time`, `event`, `stratum`}{The checked follow-up times, event indicators and strata.}
#'   \item{`z`}{The covariates as a numeric matrix with column names.}
#'   \item{`ties`, `score`}{The settings.}
#'   \item{`n`}{The number of subjects.}
#' }
#' @seealso [cv.bregsurv()]; the other targets, [target_ncc()] and [target_discrete()]; the releases,
#'   [release_records()], [release_coef()], [release_score()] and [release_model()].
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' target_cox(time = tr$time, event = tr$status, z = tr$z)
#'
#' # with strata: each centre has its own baseline hazard
#' data(ExampleData_indi)
#' int <- ExampleData_indi$internal
#' target_cox(time = int$time, event = int$status, z = int$z, stratum = int$stratum)
#'
#' # follow-up recorded at visits, so many event times are tied
#' data(ExampleData_ties)
#' ti <- ExampleData_ties$train
#' target_cox(time = ti$time, event = ti$status, z = ti$z, ties = "breslow")
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

#' Target: a nested case-control design
#'
#' @description
#' Builds the target of a nested case-control (matched case-control) study, in which each matched set
#' holds one case and the controls sampled for it. The target sets the likelihood \eqn{\ell(\theta)} in
#' the objective of [cv.bregsurv()]: the conditional log-likelihood of which member of each set is the
#' case,
#' \deqn{\ell(\beta) = \sum_{m} \log \frac{\exp(z_{c(m)}^\top\beta)}{\sum_{j \in m} \exp(z_j^\top\beta)},}
#' where \eqn{c(m)} is the case of set \eqn{m}: the likelihood of a Cox model stratified by matched set.
#'
#' `target_ncc()` checks your data and stores it; it fits nothing. Pass the result to [cv.bregsurv()]
#' (or [bregsurv()]) as `target`.
#'
#' @param case Case indicator of each row: 1 for the case, 0 for a control. Coded as the `event` of
#'   [target_cox()].
#' @param set The matched set of each row, any labels. Every set must contain exactly one case.
#' @param z Covariates, one row per member of a set and one named column per covariate, as for
#'   [target_cox()].
#'
#' @details A matched design has no follow-up time, so it takes no `ties` or `stratum` (the matched sets
#'   play the role of strata), and its risk score is always linear.
#'
#' @return An object of class `"bregsurv_target"`, a list with
#' \describe{
#'   \item{`type`}{`"ncc"`.}
#'   \item{`case`, `set`}{The checked case indicators and matched sets.}
#'   \item{`z`}{The covariates as a numeric matrix with column names.}
#'   \item{`score`}{`"linear"`.}
#'   \item{`n`}{The number of rows (members of all sets).}
#' }
#' @seealso [cv.bregsurv()]; the other targets, [target_cox()] and [target_discrete()]; the releases,
#'   [release_records()], [release_coef()], [release_score()] and [release_model()].
#' @examples
#' data(ExampleData_cc_lowdim)
#' cc <- ExampleData_cc_lowdim$train
#' target_ncc(case = cc$y, set = cc$stratum, z = cc$z)
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

#' Target: a discrete-time model
#'
#' @description
#' Builds the target of an analysis whose follow-up is recorded in intervals \eqn{1, \dots, K} (years,
#' visits, treatment cycles): subject \eqn{i} is at risk in intervals \eqn{1, \dots, t_i} and, when its
#' event indicator is 1, has the event in interval \eqn{t_i}. The model is the grouped-time
#' (discrete-time) model of the interval hazards,
#' \deqn{h_k(z) = P(T = k \mid T \ge k, z) = g^{-1}(\gamma_{sk} + z^\top\beta),}
#' with one baseline parameter \eqn{\gamma_{sk}} for each stratum \eqn{s} and interval \eqn{k}, and the
#' link \eqn{g} set by `link`. The target sets the likelihood \eqn{\ell(\theta)} in the objective of
#' [cv.bregsurv()]: the Bernoulli log-likelihood of every subject's intervals at risk.
#'
#' `target_discrete()` checks your data and stores it; it fits nothing. Pass the result to
#' [cv.bregsurv()] (or [bregsurv()]) as `target`.
#'
#' @param interval The last interval each subject was at risk in, a whole number from 1 to \eqn{K}: the
#'   interval of the event for a subject with the event, and the last interval completed without it for
#'   a censored subject.
#' @param event Event indicator of each subject: 1 if the event happened in interval `interval`, 0 if the
#'   subject was censored after it. Coded as the `event` of [target_cox()].
#' @param z Covariates, one row per subject and one named column per covariate, as for [target_cox()].
#' @param stratum Optional stratum of each subject, any labels. Each stratum has its own baseline
#'   parameters \eqn{\gamma_{sk}}; the coefficients are shared.
#' @param link The link \eqn{g}:
#'   * `"cloglog"` (the default), the complementary log-log,
#'     \eqn{h_k(z) = 1 - \exp\{-\exp(\gamma_{sk} + z^\top\beta)\}}: the grouped proportional-hazards
#'     model, whose coefficients are log hazard ratios, as a Cox model's are, so they compare directly
#'     with a Cox model's coefficients;
#'   * `"logit"`, \eqn{\log\{h_k / (1 - h_k)\} = \gamma_{sk} + z^\top\beta}: proportional odds of the
#'     interval hazard.
#' @param n_intervals The number of intervals \eqn{K}; defaults to `max(interval)`. Set it when the
#'   external model covers later intervals that none of your subjects reached.
#' @param score The form of the risk score: `"linear"` (the default), or a neural network specified by
#'   [nn_score()] that outputs one logit per interval (requires the `torch` package; the
#'   Kullback-Leibler divergence only, the logit link, and no strata).
#'
#' @return An object of class `"bregsurv_target"`, a list with
#' \describe{
#'   \item{`type`}{`"discrete"`.}
#'   \item{`interval`, `event`, `stratum`}{The checked intervals, event indicators and strata.}
#'   \item{`z`}{The covariates as a numeric matrix with column names.}
#'   \item{`link`, `K`, `score`}{The link, the number of intervals and the form of the risk score.}
#'   \item{`n`}{The number of subjects.}
#' }
#' @seealso [cv.bregsurv()]; the other targets, [target_cox()] and [target_ncc()]; the releases,
#'   [release_records()], [release_coef()], [release_score()] and [release_model()].
#' @examples
#' data(ExampleData_discrete)
#' dt <- ExampleData_discrete$train
#' table(last_interval = dt$interval, event = dt$status)
#' target_discrete(interval = dt$interval, event = dt$status, z = dt$z)
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
                 discrete = paste0("discrete-time model, ", x$K, " intervals, ", x$link, " link"))
  nn <- if (inherits(x$score, "nn_score")) ", neural-network risk score" else ""
  cat("Target: ", what, nn, "\n", sep = "")
  st <- if (!is.null(x$stratum)) paste0(", ", length(unique(x$stratum)), " strata") else ""
  if (x$type == "ncc") cat("  ", x$n, " subjects in ", length(unique(x$set)), " matched sets, ", ncol(x$z),
                           " covariates\n", sep = "")
  else cat("  ", x$n, " subjects, ", ncol(x$z), " covariates, ", sum(x$event), " events", st, "\n", sep = "")
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


#' Release: individual records
#'
#' @description
#' The external source shared its individual records: another cohort's covariates and outcomes,
#' subject by subject. The records must follow the design of your target and use your covariate names:
#' * for a Cox target ([target_cox()]): `z`, `time` and `event`, and optionally `stratum`;
#' * for a nested case-control target ([target_ncc()]): `z`, `case` and `set`;
#' * for a discrete-time target ([target_discrete()]): `z`, `interval` and `event`, on the target's
#'   intervals, and optionally `stratum`.
#'
#' The design is read off the arguments you give: `case` makes nested case-control records, `interval`
#' discrete-time records, and `time` Cox records.
#'
#' Individual records support the composite-likelihood divergence (`divergence = "composite"` in
#' [cv.bregsurv()]): their log-likelihood is added to yours with weight \eqn{\eta}, the two cohorts share
#' the coefficients, and each keeps its own baseline hazard. On a Cox target they also support the
#' Mahalanobis and Kullback-Leibler divergences, for which [cv.bregsurv()] fits a Cox model to the
#' records and borrows from its coefficients and their precision.
#'
#' @param z The external covariates: a numeric matrix or data frame with one row per external subject and
#'   columns named like your covariates. Columns you do not have are ignored; a covariate of yours that
#'   the records lack is an error.
#' @param time,event Cox records: each external subject's follow-up time (positive) and event indicator
#'   (1 = event, 0 = censored). For discrete-time records, `event` is the event indicator that goes with
#'   `interval`.
#' @param stratum Optional strata of the external subjects (Cox or discrete-time records). The external
#'   baselines are kept apart from yours either way.
#' @param case,set Nested case-control records: the case indicator (1 = case, 0 = control) and the matched
#'   set of each row; every set holds exactly one case. Give these instead of `time`.
#' @param interval Discrete-time records: the last interval each external subject was at risk in, a whole
#'   number on the target's intervals. Give it with `event`, instead of `time`.
#'
#' @return An object of class `"bregsurv_release"`, a list with `form = "records"`, `kind` (`"cohort"`,
#'   `"ncc"` or `"discrete"`), and the checked `z`, `time`, `event`, `stratum`, `case`, `set` and
#'   `interval` (those not given are `NULL`).
#' @seealso [cv.bregsurv()]; the other releases, [release_coef()], [release_score()], [release_model()]; the targets, [target_cox()],
#'   [target_ncc()] and [target_discrete()].
#' @examples
#' # Cox records, with strata
#' data(ExampleData_indi)
#' ext <- ExampleData_indi$external
#' release_records(ext$z, time = ext$time, event = ext$status, stratum = ext$stratum)
#'
#' # nested case-control records
#' data(ExampleData_cc_indi)
#' ecc <- ExampleData_cc_indi$external
#' release_records(ecc$z, case = ecc$y, set = ecc$stratum)
#'
#' # discrete-time records
#' data(ExampleData_discrete)
#' reg <- ExampleData_discrete$external
#' release_records(reg$z, interval = reg$interval, event = reg$status)
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

#' Release: a fitted model, with or without its uncertainty
#'
#' @description
#' The external source published a fitted regression model: its coefficients \eqn{\tilde\beta}, and
#' possibly their uncertainty.
#' * Without its uncertainty (`Q = NULL`), the Mahalanobis divergence is the Euclidean distance
#'   between your coefficients and the published ones, on the covariates the published model includes.
#' * With its uncertainty, the precision matrix `Q` weights the distance, so precisely estimated
#'   coefficients pull harder: \eqn{\frac12(\beta - \tilde\beta)^\top Q (\beta - \tilde\beta)}.
#'
#' A fitted model supports the Kullback-Leibler and Mahalanobis divergences on Cox and nested
#' case-control targets; for the Kullback-Leibler divergence the coefficients define the external risk
#' score \eqn{z^\top\tilde\beta} of each of your subjects. On a discrete-time target it supports the
#' Mahalanobis divergence with the complementary log-log link; the Kullback-Leibler divergence there
#' needs survival probabilities ([release_model()]).
#'
#' @param beta The published coefficients: a numeric vector named by covariate, or a one-column matrix
#'   with row names. Every name must be one of your covariates; covariates the published model does not
#'   include are set to 0 (see [align_beta()]). An unnamed vector must have one value per covariate, in
#'   the order of your columns.
#' @param Q Optional precision matrix of `beta`: square and symmetric, named like `beta`. From a
#'   published covariance matrix `V`, `Q = solve(V)`; from published standard errors alone,
#'   `Q = diag(1 / se^2)`.
#'
#' @return An object of class `"bregsurv_release"`, a list with `form = "coefficients"`, `beta` and `Q`.
#' @seealso [cv.bregsurv()]; the other releases, [release_records()], [release_score()], [release_model()]; the targets, [target_cox()],
#'   [target_ncc()] and [target_discrete()].
#' @examples
#' # without its uncertainty
#' data(ExampleData_lowdim)
#' release_coef(ExampleData_lowdim$beta_external_fair)
#'
#' # with its uncertainty
#' data(ExampleData_discrete)
#' release_coef(ExampleData_discrete$beta_external, Q = ExampleData_discrete$Q_external)
#' @export
release_coef <- function(beta, Q = NULL) {
  beta <- .as_beta(beta)
  if (!is.null(Q)) Q <- .as_Q(Q, beta)
  structure(list(form = "coefficients", beta = beta, Q = Q), class = "bregsurv_release")
}

#' Release: a risk score without survival probabilities
#'
#' @description
#' The external model is available only through its risk score: one number for each of your subjects
#' that ranks them by risk, without survival probabilities (the model's coefficients and baseline
#' hazard are not available). The model may be of any form and may use covariates you do not have; only
#' its scores for your subjects are needed.
#'
#' A risk score supports the Kullback-Leibler divergence on Cox and nested case-control targets, which
#' compares the two models through the probabilities they give each subject of failing first among those
#' at risk (or of being the case of its matched set), and these depend on the score alone. A
#' discrete-time target needs survival probabilities instead ([release_model()]).
#'
#' @param score The external risk score of each subject of your data, in the order of your rows: a
#'   numeric vector on the scale of a linear predictor (a log relative hazard), so that two subjects'
#'   scores differ by the log of their hazard ratio. Missing or infinite values are refused.
#'
#' @return An object of class `"bregsurv_release"`, a list with `form = "score"` and `score`.
#' @seealso [cv.bregsurv()]; the other releases, [release_records()], [release_coef()], [release_model()]; the targets, [target_cox()],
#'   [target_ncc()] and [target_discrete()].
#' @examples
#' data(ExampleData_lowdim)
#' release_score(ExampleData_lowdim$score_external$train)
#' @export
release_score <- function(score) {
  score <- as.numeric(score)
  if (anyNA(score) || any(!is.finite(score))) stop("'score' must be finite.", call. = FALSE)
  structure(list(form = "score", score = score), class = "bregsurv_release")
}

#' Release: survival probabilities
#'
#' @description
#' The external model gives survival probabilities, not only a ranking of subjects: either a Cox model's
#' coefficients together with its baseline cumulative hazard, or the model's interval hazards for each
#' of your subjects directly. Give either
#' * `beta` and `baseline`: the external hazard of a subject with covariates \eqn{z} in interval
#'   \eqn{k} is \eqn{\tilde h_k(z) = 1 - \exp\{-\exp(z^\top\tilde\beta)\, \Delta\Lambda_0(k)\}}; or
#' * `hazard`: the external interval hazards \eqn{\tilde h_{ik}} themselves.
#'
#' Survival probabilities are what a discrete-time target needs for the Kullback-Leibler divergence,
#' which compares the two models' hazards in every interval. With `beta`, the release also supports
#' everything [release_coef()] supports.
#'
#' @param beta Named external coefficients, as in [release_coef()].
#' @param baseline The external baseline cumulative-hazard increments over your intervals
#'   \eqn{1, \dots, K}: \eqn{\Delta\Lambda_0(k) = \Lambda_0(t_k) - \Lambda_0(t_{k-1})}, with \eqn{t_k}
#'   the end of interval \eqn{k}. Non-negative, one value per interval of the target.
#' @param hazard Instead of `beta` and `baseline`: an \eqn{n \times K} matrix whose row \eqn{i}, column
#'   \eqn{k} is the external probability that subject \eqn{i} of your data has the event in interval
#'   \eqn{k} given that it reached the interval. Rows in the order of your data.
#' @param Q Optional precision matrix of `beta`, as in [release_coef()], for the Mahalanobis divergence.
#'
#' @return An object of class `"bregsurv_release"`, a list with `form = "model"`, `beta`, `baseline`,
#'   `hazard` and `Q` (those not given are `NULL`).
#' @seealso [cv.bregsurv()]; the other releases, [release_records()], [release_coef()], [release_score()]; the targets, [target_cox()],
#'   [target_ncc()] and [target_discrete()].
#' @examples
#' data(ExampleData_discrete)
#' release_model(beta = ExampleData_discrete$beta_external,
#'               baseline = ExampleData_discrete$baseline_external)
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
  design <- c(cohort = "Cox design", ncc = "nested case-control design", discrete = "discrete-time design")
  switch(x$form,
         records = cat("Release: individual records (", design[[x$kind]], "), ", nrow(x$z), " subjects",
                       if (!is.null(x$stratum)) paste0(", ", length(unique(x$stratum)), " strata"), "\n", sep = ""),
         coefficients = cat("Release: a fitted model, ", length(x$beta), " coefficients, ",
                            if (is.null(x$Q)) "without its uncertainty" else "with its uncertainty (precision matrix)",
                            "\n", sep = ""),
         score = cat("Release: a risk score for ", length(x$score), " subjects, without survival probabilities\n",
                     sep = ""),
         model = cat("Release: survival probabilities, ",
                     if (!is.null(x$hazard)) paste0("interval hazards for ", nrow(x$hazard), " subjects over ",
                                                    ncol(x$hazard), " intervals")
                     else paste0(length(x$beta), " coefficients with a baseline hazard over ", length(x$baseline),
                                 " intervals"), "\n", sep = ""))
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
