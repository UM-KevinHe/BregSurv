#!/usr/bin/env Rscript
# diagnose_transfer.R - V4 work item 3: the transfer-diagnostics card.
#
#   Rscript diagnose_transfer.R <in.json> <out.json>
#
# HARNESS-INVOKED. The card is what the V4 planner reads before it decides what to fit: which likelihood
# row, which members, which grids, which terms to borrow, whether to pad an absent term with zero, whether
# network members are worth fitting. Every number on it is a DESCRIPTION of the training data and the release;
# nothing here is selected for the analyst and nothing here is reported as a result. The test file, if any,
# is never read.
#
# input.json: the payload run_candidates.R takes (data_path, z_expr, time_expr, delta_expr | y_expr,
#   stratum_expr, event_value, beta_inline | beta_expr, Q_inline | Q_expr, external_data_path, z_ext_expr,
#   time_ext_expr, delta_ext_expr | y_ext_expr, stratum_ext_expr, baseline_inline, seed, nfolds). Extra
#   keys are ignored, so the harness can hand it the same object.
#
# output.json: {"status":"ok", "facts":{...}, "outcome":{...}, "external":{...}, "terms":[...],
#   "records"?:{...}, "baseline"?:{...}, "notes":[...]}

suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
  library(BregSurv)
})
if (utils::packageVersion("BregSurv") < "1.2.0")
  stop("diagnose_transfer.R needs BregSurv >= 1.2.0")

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript diagnose_transfer.R <in.json> <out.json>")

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) return(NULL)
  eval(parse(text = expr_str), envir = env)
}
as_named_numeric <- function(x) {
  if (is.null(x)) return(NULL)
  nm <- names(x)
  if (is.null(nm) && is.matrix(x) && ncol(x) == 1L) nm <- rownames(x)
  v <- as.numeric(unlist(x, use.names = FALSE))
  if (!is.null(nm) && length(nm) == length(v)) names(v) <- nm
  v
}
load_any <- function(path) {
  ext <- tolower(tools::file_ext(path)); e <- new.env()
  nm <- make.names(tools::file_path_sans_ext(basename(path)))
  if (ext %in% c("rda", "rdata")) load(path, envir = e)
  else if (ext == "rds") assign(nm, readRDS(path), envir = e)
  else if (ext %in% c("csv", "tsv", "txt"))
    assign(nm, utils::read.delim(path, sep = if (ext == "csv") "," else "\t", stringsAsFactors = FALSE,
                                 check.names = FALSE, na.strings = c("NA", "")), envir = e)
  else stop(sprintf("diagnose_transfer.R reads .rda, .rds, .csv and .tsv; got .%s", ext))
  e
}
`%||%` <- function(a, b) if (is.null(a)) b else a
num <- function(x, d = 6) if (is.null(x) || length(x) != 1L || !is.finite(x)) NULL else round(as.numeric(x), d)

# the follow-up time's grid, by the rule profile_columns.R uses
## whether the exact tie correction can be computed: the library enumerates C(at risk, tied events) at
## every event time and stops above comb_max (1e7 in cv.coxkl_ties). Measured on the whole cohort, an
## upper bound for every cross-validation fold, whose risk sets are smaller.
EXACT_COMB_MAX <- 1e7
exact_ties <- function(time, delta, stratum) {
  s <- if (is.null(stratum)) rep(1L, length(time)) else as.integer(as.factor(stratum))
  worst <- 0
  for (g in unique(s)) {
    tg <- time[s == g]; dg <- delta[s == g]
    for (tk in unique(tg[dg == 1])) {
      d <- sum(tg == tk & dg == 1)
      if (d > 1) worst <- max(worst, choose(sum(tg >= tk), d))
    }
  }
  list(largest_enumeration = num(worst, 0), limit = EXACT_COMB_MAX, feasible = worst <= EXACT_COMB_MAX)
}

time_grid <- function(v) {
  vv <- v[is.finite(v)]; dv <- sort(unique(vv)); step <- NA_real_
  if (length(dv) >= 2L) {
    gaps <- diff(dv); g0 <- min(gaps[gaps > 0])
    if (is.finite(g0) && g0 > 0 && all(abs(dv / g0 - round(dv / g0)) < 1e-8)) step <- g0
  }
  list(integer_valued = all(abs(vv - round(vv)) < 1e-8), step = num(step), n_distinct = length(dv),
       coarse = !is.na(step) && length(dv) <= 100L, min = num(min(vv)), max = num(max(vv)))
}

result <- tryCatch({
  input <- fromJSON(args[1], simplifyVector = FALSE)
  e <- load_any(input$data_path)
  seed <- if (!is.null(input$seed)) as.integer(input$seed) else 20260818L
  nfolds <- if (!is.null(input$nfolds)) as.integer(input$nfolds) else 5L
  notes <- list()

  z <- as.matrix(eval_in(input$z_expr, e)); storage.mode(z) <- "double"
  zn <- colnames(z); p <- ncol(z)
  is_ncc <- !is.null(input$y_expr) && nzchar(input$y_expr)
  stratum <- eval_in(input$stratum_expr, e)
  if (is_ncc) {
    delta <- as.numeric(eval_in(input$y_expr, e)); time <- NULL
  } else {
    time <- as.numeric(eval_in(input$time_expr, e)); delta <- as.numeric(eval_in(input$delta_expr, e))
  }
  ev <- input$event_value
  if (!is.null(ev) && nzchar(as.character(ev))) delta <- as.numeric(delta == as.numeric(as.character(ev)))
  n <- nrow(z); n_events <- sum(delta == 1, na.rm = TRUE)

  ## ---- the outcome: ties and the time grid (cohort designs) ------------------------------------
  outcome <- list()
  if (!is_ncc) {
    et <- time[delta == 1]
    outcome <- list(
      n_distinct_event_times = length(unique(et)),
      tie_fraction = num(if (length(et)) sum(duplicated(et)) / length(et) else 0, 4),
      events_sharing_a_time = sum(et %in% et[duplicated(et)]),
      exact_ties = exact_ties(time, delta, stratum),
      time_grid = time_grid(time),
      administrative_censoring_at_max = sum(time == max(time) & delta == 0))
  } else {
    sets <- table(stratum)
    outcome <- list(n_sets = length(sets), median_set_size = num(stats::median(sets)),
                    sets_with_one_case = sum(tapply(delta, stratum, sum) == 1))
  }

  ## ---- the release ---------------------------------------------------------------------------
  beta <- NULL
  if (!is.null(input$beta_expr) && nzchar(input$beta_expr)) beta <- as_named_numeric(eval_in(input$beta_expr, e))
  if (!is.null(input$beta_inline)) beta <- as_named_numeric(input$beta_inline)
  Q <- NULL
  if (!is.null(input$Q_inline)) {
    Q <- as.matrix(do.call(rbind, lapply(input$Q_inline, function(r) as.numeric(unlist(r)))))
    if (!is.null(beta) && nrow(Q) == length(beta)) dimnames(Q) <- list(names(beta), names(beta))
  } else if (!is.null(input$Q_expr) && nzchar(input$Q_expr)) {
    Q <- as.matrix(eval_in(input$Q_expr, e))
  }
  e_ext <- e
  if (!is.null(input$external_data_path) && nzchar(input$external_data_path)) e_ext <- load_any(input$external_data_path)
  z_ext <- eval_in(input$z_ext_expr, e_ext)
  has_indi <- !is.null(z_ext)

  covered <- if (!is.null(beta)) intersect(names(beta), zn) else if (has_indi) zn else character(0)
  external <- list(
    form = if (has_indi) "individual-level data" else if (is.null(beta)) "none"
           else if (!is.null(Q)) "coefficients and covariance" else "coefficients alone",
    n_terms_released = if (!is.null(beta)) length(beta) else if (has_indi) p else 0L,
    n_covered = length(covered), n_internal_only = p - length(covered),
    internal_only = as.list(setdiff(zn, covered)),
    released_not_in_cohort = as.list(if (!is.null(beta)) setdiff(names(beta), zn) else character(0)))

  facts <- list(design = if (is_ncc) "nested case-control" else "full cohort", n = n, n_events = n_events,
                p = p, events_per_parameter = num(n_events / p, 3),
                events_per_internal_only_term = num(if (p > length(covered)) n_events / (p - length(covered)) else NA, 3))

  sds <- apply(z, 2, stats::sd)

  ## ---- the target-only fit the comparison needs: ridge, lambda by CV (cohort designs) -----------
  b_int <- NULL; loss_int <- NULL; folds <- NULL
  if (!is_ncc) {
    cvr <- tryCatch(cv.coxkl_ridge(z = z, delta = delta, time = time, stratum = stratum, beta = setNames(rep(0, p), zn),
                                   etas = 0, nfolds = nfolds, seed = seed, cv.criteria = "V&VH"),
                    error = function(err) conditionMessage(err))
    if (is.character(cvr)) {
      notes[[length(notes) + 1L]] <- paste("the target-only ridge fit failed:", substr(cvr, 1, 200))
    } else {
      b_int <- setNames(as.numeric(cvr$best$best_beta), zn)
      loss_int <- as.numeric(cvr$best$best_value); folds <- as.integer(cvr$folds)
    }
  } else {
    notes[[length(notes) + 1L]] <- "per-term comparison is not computed for a matched design in this version"
  }

  ## ---- per covered term: the release against the target-only fit, on the per-SD scale ---------
  terms <- list()
  ref <- if (!is.null(beta)) beta else NULL
  if (has_indi && !is_ncc) {
    # another cohort's records: its own ridge fit plays the release's part, and the covariate shift is shown
    time_ext <- as.numeric(eval_in(input$time_ext_expr, e_ext)); delta_ext <- as.numeric(eval_in(input$delta_ext_expr, e_ext))
    if (!is.null(ev) && nzchar(as.character(ev))) delta_ext <- as.numeric(delta_ext == as.numeric(as.character(ev)))
    z_ext <- as.matrix(z_ext); storage.mode(z_ext) <- "double"
    cve <- tryCatch(cv.coxkl_ridge(z = z_ext, delta = delta_ext, time = time_ext, beta = setNames(rep(0, p), zn),
                                   etas = 0, nfolds = nfolds, seed = seed, cv.criteria = "V&VH"),
                    error = function(err) conditionMessage(err))
    if (!is.character(cve)) ref <- setNames(as.numeric(cve$best$best_beta), zn)
    smd <- (colMeans(z) - colMeans(z_ext)) / sqrt((apply(z, 2, stats::var) + apply(z_ext, 2, stats::var)) / 2)
    records <- list(n_external = nrow(z_ext), n_events_external = sum(delta_ext == 1, na.rm = TRUE),
                    max_abs_standardised_mean_difference = num(max(abs(smd), na.rm = TRUE), 3),
                    standardised_mean_difference = as.list(round(smd, 3)))
  }

  ## ---- the release on the internal data: discrimination and calibration of its linear predictor ----
  rel <- if (!is.null(beta)) beta else ref    # for records: the external cohort's own ridge fit
  if (!is.null(rel) && length(covered)) {
    lp <- as.numeric(z[, covered, drop = FALSE] %*% rel[covered])
    if (!is_ncc) {
      f <- if (is.null(stratum)) Surv(time, delta) ~ lp else Surv(time, delta) ~ lp + strata(stratum)
      fit <- tryCatch(coxph(f), error = function(err) NULL)
      cc <- tryCatch(concordance(Surv(time, delta) ~ lp, reverse = TRUE)$concordance, error = function(err) NA)
      external$calibration <- list(
        slope = if (!is.null(fit)) num(unname(coef(fit)["lp"]), 4) else NULL,
        slope_se = if (!is.null(fit)) num(sqrt(vcov(fit)["lp", "lp"]), 4) else NULL,
        cindex_on_internal = num(cc, 4),
        meaning = "slope 1: the release's risk score is on the right scale here; below 1: its effects are too strong for this cohort; near 0: it carries little here")
      if (!is.null(folds)) {
        bx <- setNames(rep(0, p), zn); bx[covered] <- rel[covered]
        le <- tryCatch(vvh_loss_fixed(z = z, delta = delta, time = time, stratum = stratum, beta = bx, folds = folds),
                       error = function(err) NULL)
        external$cv_loss_released_unchanged <- num(if (is.list(le)) le$VVH_Loss else le, 5)
        external$cv_loss_target_only_ridge <- num(loss_int, 5)
      }
    } else {
      fit <- tryCatch(clogit(delta ~ lp + strata(stratum)), error = function(err) NULL)
      external$calibration <- list(slope = if (!is.null(fit)) num(unname(coef(fit)["lp"]), 4) else NULL,
                                   slope_se = if (!is.null(fit)) num(sqrt(vcov(fit)["lp", "lp"]), 4) else NULL)
    }
  }

  if (!is.null(ref) && !is.null(b_int)) {
    for (v in covered) {
      d <- (b_int[[v]] - ref[[v]]) * sds[[v]]
      terms[[length(terms) + 1L]] <- list(term = v, beta_release = num(ref[[v]], 5), beta_target_only = num(b_int[[v]], 5),
                                          sd = num(sds[[v]], 4), difference_per_sd = num(d, 4),
                                          same_sign = sign(b_int[[v]]) == sign(ref[[v]]) || abs(b_int[[v]]) < 1e-8)
    }
    diffs <- vapply(terms, function(t) abs(t$difference_per_sd %||% NA_real_), numeric(1))
    ord <- order(-diffs)
    external$heterogeneity <- list(
      median_abs_difference_per_sd = num(stats::median(diffs, na.rm = TRUE), 4),
      n_sign_disagreements = sum(!vapply(terms, function(t) isTRUE(t$same_sign), logical(1))),
      largest = lapply(head(ord[is.finite(diffs[ord])], 5), function(i) terms[[i]]$term),
      meaning = "difference_per_sd: the target-only (ridge) log hazard ratio minus the release's, per standard deviation of the covariate in this cohort")
  }

  ## the covariates the release does not cover: what the target-only fit says about each, so the planner can
  ## weigh what padding them with zero would assert
  if (!is.null(b_int) && p > length(covered)) {
    external$absent <- lapply(setdiff(zn, covered), function(v)
      list(term = v, beta_target_only = num(b_int[[v]], 5), sd = num(sds[[v]], 4),
           effect_per_sd = num(b_int[[v]] * sds[[v]], 4)))
  }

  ## ---- the matrix and the baseline ---------------------------------------------------------------
  if (!is.null(Q)) {
    ok <- intersect(rownames(Q), covered)
    Qc <- Q[ok, ok, drop = FALSE]
    external$matrix <- list(n = nrow(Qc), condition_number = num(kappa(Qc, exact = TRUE), 1),
                            symmetric = isSymmetric(unname(Qc), tol = 1e-8))
  }
  baseline <- NULL
  if (!is.null(input$baseline_inline)) {
    bt <- as.numeric(unlist(input$baseline_inline$time))
    baseline <- list(available = TRUE, last_time = num(max(bt)),
                     covers_internal_follow_up = if (!is_ncc) max(bt) >= max(time) else NULL)
  }

  out <- list(status = "ok", facts = facts, outcome = outcome, external = external, terms = terms, notes = notes)
  if (exists("records")) out$records <- records
  if (!is.null(baseline)) out$baseline <- baseline
  out
}, error = function(err) list(status = "error", message = conditionMessage(err)))

write_json(result, args[2], auto_unbox = TRUE, null = "null", digits = NA, pretty = TRUE)
