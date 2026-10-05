#!/usr/bin/env Rscript
# run_candidates.R - derive the admissible candidate set, fit all of it, select.
#
# Called by mcp/server.py as:
#   Rscript run_candidates.R <input.json> <output.json>
#
# HARNESS-INVOKED. No LLM-visible schema. This is the step the V3 agent exists
# to perform, and no part of it is a judgement the language model could make.
#
# THE DESIGN, in one paragraph.  Two of the three characteristics that pick an
# estimator are FACTS -- the study design, read off the declared roles, and the
# form the external information arrived in, read off the external object -- and
# together they fix a row of the library. The third, whether a sparsity penalty
# is needed, is NOT observable: it is a judgement about p against the event
# count, not about p. So it is not judged. Every member of the row is fitted and
# cross-validation picks. That is why the agent needs no routing model.
#
# ONE PARTITION.  Every candidate is scored on the SAME folds, or the
# comparison is meaningless. `get_fold` depends only on (delta, stratum), and
# since the package now pins the RNG kind, one seed gives one partition across
# every cv.* function, every beta and every penalty. Verified 2026-08-18 across
# eight variants. The External-only member does not refit at all, so it is scored
# with `vvh_loss_fixed` on the fold vector the first candidate returned.
#
# THE SET CONTAINS THE TWO WAYS OF NOT BORROWING.  Internal-only is the
# external vector replaced by zeros with eta pinned at 0; External-only is the
# published model used unchanged. Both must be able to win. On MIMIC-IV the
# external model beat 8 of the 9 fitted candidates, so an agent whose output
# space held only integration models would have recommended something worse than
# doing nothing.
#
# THE ETA GRIDS ARE NOT INTERCHANGEABLE and must not be thinned. The
# Mahalanobis penalty is on a different scale from the KL divergence: measured on
# the MIUM cohort, unpenalised cox_MDTL has already shrunk 99.7% of the way at
# eta = 1, so the whole trade-off lives below eta = 3 and the grid needs a dense
# low end, while the KL grid is exponential to 200. These defaults are the ones
# tuned against the two real cohorts. Thinning them degrades the very selection
# this tool performs.
#
# input.json:
#   data_path, z_expr, time_expr, delta_expr        cohort designs
#   y_expr, stratum_expr                            NCC designs
#   beta_expr / beta_inline                         the external coefficients
#   Q_expr / Q_inline                               optional weighting matrix
#   seed          the ONE seed every candidate shares (default 20260818)
#   nfolds        default 5
#   nlambda       default 50
#   include       optional character vector, restrict the set (testing only)
#   discrete      {n_intervals, width, time_is_index} -- the analyst's item-7
#                 declaration: the DISCRETE-TIME ROW is fitted instead
#                 of the Cox row (see the block "the discrete-time row" below)
#   baseline_inline {time:[..], cumhaz:[..]} -- the external model's baseline
#                 hazard; read ONLY by the discrete row, where it is what a
#                 Cox model needs to say anything about interval hazards
#   diskd_options optional list overriding the DiSKD training settings
#                 (architecture, eta_grid, learning_rates, max_epochs,
#                 patience) -- TESTING ONLY, like `include`; the product
#                 always runs the released nested CV (ruling 2)
##   test_data     {path?, expr, time_col, event_col, covariates[], stratum_col?}
#                 -- the analyst's OWN test file. Every fitted member is
#                 scored on it once (C-index, loss, IBS, tdAUC via test_eval);
#                 the numbers are REPORTED and never used to select. Cox row only.
#
# output.json:
#   {"status":"ok",
#    "facts":{design, external_form, n, n_events, p, p_covered, p_internal_only},
#    "partition":{seed, nfolds, folds, rng_kind, drawn_by, row_order,
#                 seed_is_effective},
#    "criteria": "...",
#    "candidates":[{key,label,borrowing,penalty,status,loss,eta,lambda,
#                   n_nonzero,seconds,message,
#                   holdout?:{cindex,loss,ibs,tdauc,seconds,baseline_available}}],
#    "selected":{key,label,loss,eta,lambda,beta:{name:value},holdout?},
#    "coefficients":[{variable,beta_external,beta_internal,beta_selected}],
#    "linkage":{...},
#    "test_data"?:{n,n_events,source,criteria,baseline,role}}

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

# 2026-09-30: the candidate set assumes BregSurv >= 1.2.0 -- the ridge family scales the
# design before penalising, and the Mahalanobis metric acts on the scaled design. Under 1.1.0
# every call below still runs and returns numbers (ridge unscaled, the metric in the wrong
# direction), so an older copy earlier on the library path would give a different analysis
# with no error. Refuse instead.
if (utils::packageVersion("BregSurv") < "1.2.0")
  stop(sprintf("run_candidates.R needs BregSurv >= 1.2.0; the copy found at %s is %s.",
               find.package("BregSurv"), as.character(utils::packageVersion("BregSurv"))))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript run_candidates.R <in.json> <out.json>")
input_path <- args[1]; output_path <- args[2]

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

# --- ingestion (requirement R1: the raw data never enters the model's context) -
# The profile and the fitted numbers cross the boundary; the rows never do.
# A tabular file becomes a single data.frame named after the file, so `data_expr`
# can address it the same way as an object inside an .rda.
# 2026-10-03 (V4 trial, H041): two members can reach the same loss to ~1e-9 (a Mahalanobis member at a
# very large weight IS the released model unchanged), and a replay on another thread count then broke the tie
# the other way. Losses within 1e-8 (relative) of the minimum are a tie, settled by the fixed member order,
# so the selection does not depend on the last digits of the arithmetic.
pick_min <- function(losses) {
  m <- min(losses)
  which(losses <= m + 1e-8 * max(1, abs(m)))[1L]
}

load_any <- function(data_path) {
  ext <- tolower(tools::file_ext(data_path))
  e <- new.env()
  nm <- make.names(tools::file_path_sans_ext(basename(data_path)))
  if (ext %in% c("rda", "rdata")) {
    load(data_path, envir = e)
  } else if (ext == "rds") {
    assign(nm, readRDS(data_path), envir = e)
  } else if (ext %in% c("csv", "tsv", "txt")) {
    sep <- if (ext == "csv") "," else "\t"
    assign(nm, utils::read.delim(data_path, sep = sep, stringsAsFactors = FALSE,
                                 check.names = FALSE, na.strings = c("NA", "")),
           envir = e)
  } else if (ext %in% c("xlsx", "xls")) {
    if (!requireNamespace("readxl", quietly = TRUE))
      stop("Reading .xlsx needs the 'readxl' package: install.packages('readxl')")
    assign(nm, as.data.frame(readxl::read_excel(data_path), check.names = FALSE),
           envir = e)
  } else if (ext == "parquet") {
    if (!requireNamespace("arrow", quietly = TRUE))
      stop("Reading .parquet needs the 'arrow' package: install.packages('arrow')")
    assign(nm, as.data.frame(arrow::read_parquet(data_path)), envir = e)
  } else {
    stop(sprintf(paste0("Unsupported file type '.%s'. This tool reads .rda, ",
                        ".rds, .csv, .tsv, .xlsx and .parquet."), ext))
  }
  e
}

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)

  ## ---- V4: a PLAN chosen by the planner ------------------------------------------
  # Absent, the script fits the V3 set exactly as before. Present, `plan` = {row: "cox" | "cox_ties"
  # | "discrete", ties: "breslow" | "exact", members: [{key, etas?, covariates?, mask?, pad_absent?,
  # nlambda?}], diskd_options?}: only the listed members are fitted, each with its own grid and
  # variable sets, all on the one partition, and CV still picks among them. The planner decides
  # what is fitted; nothing here decides anything. The harness checks the plan before it arrives
  # (protected core, admissibility, budget); this script refuses only what it cannot represent.
  plan <- input$plan
  plan_members <- if (!is.null(plan$members)) plan$members else NULL
  plan_of <- function(key) {
    for (m in plan_members) if (identical(as.character(m$key), key)) return(m)
    NULL
  }
  plan_row <- if (!is.null(plan$row)) as.character(plan$row) else "cox"
  if (!is.null(plan_members) && is.null(input$include))
    input$include <- lapply(plan_members, function(m) as.character(m$key))
  if (!is.null(plan$diskd_options) && is.null(input$diskd_options))
    input$diskd_options <- plan$diskd_options
  # V4 item 2: rows fitted by an earlier call of the SAME analysis (same data, declaration, release,
  # seed, folds) under the SAME plan entry -- the harness decides which, by comparing the entries.
  # They are taken as fitted, not refitted, so a planner that refines one member pays for that member
  # only. Their partition must be this call's partition, or nothing is reused (checked after the fits).
  # Cox and matched rows only; the discrete row fits its members together and reuses nothing.
  reuse <- if (!is.null(input$reuse$rows)) input$reuse$rows else list()
  reuse_of <- function(key) {
    for (r in reuse) if (identical(as.character(r$key), key)) return(r)
    NULL
  }

  data_path <- input$data_path
  if (is.null(data_path) || !nzchar(data_path)) stop("data_path is required")
  if (!file.exists(data_path)) stop(sprintf("File not found: %s", data_path))
  e <- load_any(data_path)

  seed    <- if (!is.null(input$seed))    as.integer(input$seed)    else 20260818L
  nfolds  <- if (!is.null(input$nfolds))  as.integer(input$nfolds)  else 5L
  nlambda <- if (!is.null(input$nlambda)) as.integer(input$nlambda) else 50L

  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required")
  z <- as.matrix(z); storage.mode(z) <- "double"
  p <- ncol(z)

  ## ---- fact 1: the study design, read off the declared roles ----------
  is_ncc <- !is.null(input$y_expr) && nzchar(input$y_expr)
  design <- if (is_ncc) "nested case-control" else "full cohort"
  stratum <- eval_in(input$stratum_expr, e)
  ## ---- fact 3: the internal outcome is in DISCRETE INTERVALS ------
  # Declared by the analyst (item 7), never inferred from the data and never
  # read off the release. It chooses a different row of the library, whose
  # members are ranked among themselves only (ruling 4).
  is_discrete <- !is.null(input$discrete)
  if (is_discrete && is_ncc)
    stop("the discrete-time row exists for cohort designs only; a matched design has no follow-up time to cut into intervals")

  if (is_ncc) {
    y <- eval_in(input$y_expr, e); delta <- as.numeric(y); time <- NULL
    if (is.null(stratum)) stop("stratum_expr is required for a nested case-control design")
  } else {
    time  <- as.numeric(eval_in(input$time_expr, e))
    delta <- as.numeric(eval_in(input$delta_expr, e))
    if (is.null(time) || is.null(delta)) stop("time_expr and delta_expr are required")
  }

  ## ---- which value the analyst said means the event -------------------
  # Until 2026-08-19 this script hard-coded 1 as the event and never received
  # `event_value` at all, while the analyst declared it, the consequence card
  # printed it and the approval hash covered it. A declaration of event_value=0
  # on a genuine 0/1 column therefore fitted the exact complement of the
  # declared outcome, silently, with the gate reporting the censoring count as
  # "events". Recoding here is what makes the declared value load-bearing.
  #
  # Absent (a direct caller rather than the V3 pipeline) leaves delta untouched,
  # so existing behaviour is unchanged. Present and equal to 1 on a 0/1 column
  # is the identity, so nothing already recorded moves.
  ev_declared <- input$event_value
  if (!is.null(ev_declared) && nzchar(as.character(ev_declared))) {
    ev_num <- suppressWarnings(as.numeric(as.character(ev_declared)))
    if (is.na(ev_num))
      stop(sprintf("event_value '%s' is not numeric; the event column is numeric here",
                   as.character(ev_declared)))
    if (!any(delta == ev_num, na.rm = TRUE))
      stop(sprintf("event_value %s does not occur in the event column (values: %s)",
                   as.character(ev_declared),
                   paste(sort(unique(delta[!is.na(delta)])), collapse = ", ")))
    delta <- as.numeric(delta == ev_num)
  }

  ## ---- fact 2: the form the external information arrived in ------------
  beta <- NULL
  if (!is.null(input$beta_expr) && nzchar(input$beta_expr))
    beta <- as_named_numeric(eval_in(input$beta_expr, e))
  if (!is.null(input$beta_inline)) beta <- as_named_numeric(input$beta_inline)
  Q <- NULL
  if (!is.null(input$Q_expr) && nzchar(input$Q_expr)) {
    Q <- as.matrix(eval_in(input$Q_expr, e)); storage.mode(Q) <- "double"
  }
  if (!is.null(input$Q_inline)) {
    Q <- as.matrix(do.call(rbind, lapply(input$Q_inline,
                                         function(r) as.numeric(unlist(r)))))
    # Q_inline arrives as bare rows in the ORDER of beta_inline (the harness
    # canonicalises both from the same names); without dimnames the by-name
    # subsetting below never fires and a dropped external term would shift
    # every row of Q onto the wrong variable.
    if (!is.null(beta) && nrow(Q) == length(beta) && ncol(Q) == length(beta))
      dimnames(Q) <- list(names(beta), names(beta))
    else if (!is.null(beta))
      stop(sprintf("Q_inline is %d x %d but beta_inline has %d names",
                   nrow(Q), ncol(Q), length(beta)))
  }
  # NO EXTERNAL INFORMATION IS A SUPPORTED STATE as of 2026-08-19. It used to
  # be `stop("An external coefficient vector is required")`, which is defensible
  # for a transfer-learning library but wrong for an agent: an analyst with no
  # published model to borrow from got an R error, not an analysis and not a
  # reasoned refusal.
  #
  # Removing the stop is NOT sufficient on its own, and that is the whole
  # subtlety. The internal-only member is manufactured FROM the external
  # machinery (`beta = beta_zero, etas = 0`), so with beta absent the KL,
  # Mahalanobis, ridge and lasso borrowing members all degenerate to the same
  # internal fit -- nine rows carrying the same number, and an argmin breaking
  # the tie arbitrarily and then reporting a "borrowing" method as the winner.
  # So the candidate set is restricted below instead, and the Python
  # derive_candidate_keys carries the identical restriction.
  has_external <- !is.null(beta)

  ## ---- external INDIVIDUAL-LEVEL data, the third form -------------------
  # The external cohort may live in the same file or in one of its own. A second
  # file is loaded into its OWN environment and only the `*_ext_expr`
  # expressions are evaluated there, so an external table named `D` cannot
  # shadow the internal one.
  e_ext <- e
  if (!is.null(input$external_data_path) && nzchar(input$external_data_path)) {
    if (!file.exists(input$external_data_path))
      stop(sprintf("External data file not found: %s", input$external_data_path))
    e_ext <- load_any(input$external_data_path)
  }
  z_ext <- eval_in(input$z_ext_expr, e_ext)
  has_indi <- !is.null(z_ext)
  time_ext <- delta_ext <- stratum_ext <- NULL
  if (has_indi) {
    # The three forms of external information are ALTERNATIVES, not a menu to
    # combine. The candidate set is derived from ONE of them; deriving it from
    # two would mean silently choosing which, which is the judgement this whole
    # design exists to remove.
    if (has_external)
      stop(paste("Both individual-level external data and an external",
                 "coefficient vector were supplied. The candidate set is",
                 "derived from one form of external information; supply one."))
    z_ext <- as.matrix(z_ext); storage.mode(z_ext) <- "double"
    if (ncol(z_ext) != p)
      stop(sprintf(paste("The external cohort has %d covariates and the internal",
                         "one has %d. They must be the same variables in the",
                         "same order."), ncol(z_ext), p))
    stratum_ext <- eval_in(input$stratum_ext_expr, e_ext)
    if (is_ncc) {
      delta_ext <- as.numeric(eval_in(input$y_ext_expr, e_ext))
      if (is.null(delta_ext)) stop("y_ext_expr is required for a matched design")
      if (is.null(stratum_ext))
        stop("stratum_ext_expr is required for a matched design")
    } else {
      time_ext  <- as.numeric(eval_in(input$time_ext_expr, e_ext))
      delta_ext <- as.numeric(eval_in(input$delta_ext_expr, e_ext))
      if (is.null(time_ext) || is.null(delta_ext))
        stop("time_ext_expr and delta_ext_expr are required with external data")
    }
    if (!is.null(ev_declared) && nzchar(as.character(ev_declared))) {
      ev_num_e <- suppressWarnings(as.numeric(as.character(ev_declared)))
      # The SAME presence check the internal recode gets. Without it a value
      # that never occurs in the external event column turns that whole column
      # into zeros -- an external cohort with no events at all -- and the fit
      # runs, borrows from nothing, and reports a number. The internal side
      # refuses this; the external side must not be the lax one, especially
      # since it is the half nobody is looking at.
      if (!is.na(ev_num_e) && !any(delta_ext == ev_num_e, na.rm = TRUE))
        stop(sprintf(paste("event_value %s does not occur in the external",
                           "cohort's event column (values: %s)"),
                     as.character(ev_declared),
                     paste(sort(unique(delta_ext[!is.na(delta_ext)])),
                           collapse = ", ")))
      if (!is.na(ev_num_e)) delta_ext <- as.numeric(delta_ext == ev_num_e)
    }
    # NAMES, not just the count. fit_cox_indi.R compares ncol and nothing
    # else, so two tables of the same width in a different column ORDER fit
    # happily and every borrowed coefficient lands on the wrong variable. The
    # coefficient path has matched by name since it existed; the path with the
    # most external data to check had the least checking.
    zne <- colnames(z_ext)
    if (!is.null(zne) && !identical(zne, colnames(z)))
      stop(sprintf(paste("The external cohort covariates are not the internal",
                         "ones in the same order. Internal: %s. External: %s."),
                   paste(colnames(z), collapse = ", "),
                   paste(zne, collapse = ", ")))
  }

  external_form <- if (has_indi) "individual-level data"
                   else if (!has_external) "none"
                   else if (!is.null(Q)) "coefficients and covariance"
                   else "coefficients alone"

  ## ---- linkage: drop external-only names, report the alignment ---------
  zn <- colnames(z)
  if (is.null(zn)) stop("z must have column names")
  bn <- names(beta)
  if (has_indi) {
    # every internal variable is present in the external cohort -- the name and
    # order check above refuses anything else -- so nothing is zero-padded or
    # dropped, and the linkage section has a different story to tell
    linkage <- list(matched_by = "external cohort", n_internal = p,
                    n_external = p, covered = as.list(zn),
                    zero_padded = list(), dropped = list())
  } else if (!has_external) {
    linkage <- list(matched_by = "none", n_internal = p, n_external = 0L,
                    covered = list(), zero_padded = as.list(zn), dropped = list())
  } else if (is.null(bn)) {
    if (length(beta) != p)
      stop(sprintf("An unnamed external beta must have length %d (got %d)", p, length(beta)))
    names(beta) <- zn; bn <- zn
    linkage <- list(matched_by = "position", n_internal = p, n_external = length(bn),
                    covered = as.list(zn), zero_padded = list(), dropped = list())
  } else {
    keep <- bn %in% zn
    dropped <- bn[!keep]
    beta <- beta[keep]
    if (!is.null(Q) && !is.null(rownames(Q))) {
      qk <- rownames(Q) %in% zn
      Q <- Q[qk, qk, drop = FALSE]
    }
    linkage <- list(matched_by = "name", n_internal = p, n_external = length(bn),
                    covered = as.list(intersect(zn, names(beta))),
                    zero_padded = as.list(setdiff(zn, names(beta))),
                    dropped = as.list(dropped))
  }
  beta_full <- rep(0, p); names(beta_full) <- zn
  if (has_external) beta_full[names(beta)] <- beta
  # The Mahalanobis family takes the release as it stands, NOT beta_full.
  # align_beta_Q masks its metric by NAME: every named entry counts as a
  # coordinate the release speaks for. beta_full names every column, with zeros
  # on the ones the release never mentioned, so the "masked identity" became a
  # full identity and every uncovered coefficient was pulled toward 0 with weight
  # eta -- a claim the release never made (settled design, 2026-08-17; found
  # 2026-09-28 on MIUM, where it cost the lasso member 0.03 in concordance). The
  # KL family is unaffected: a zero adds nothing to the risk score it borrows.
  beta_covered <- if (has_external && !has_indi) beta else NULL
  has_Q <- has_external && !has_indi && !is.null(Q)  # the release carried a covariance
  # In the individual-level cell there is no published vector, so beta_full
  # is the all-zero placeholder until the External-cohort-only member fits one
  # and overwrites it. If that member FAILS, the zeros survive and the report's
  # "external model" column renders a column of 0.000 as though the external
  # study had estimated every coefficient to be exactly zero. NA says "not
  # available", which is what is true.
  if (has_indi) beta_full[] <- NA_real_
  beta_zero <- setNames(rep(0, p), zn)

  if (is_discrete) {
  ## =====================================================================
  ## THE DISCRETE-TIME ROW
  ## =====================================================================
  # Members: internal_discrete (DiscreteKL, eta = 0), discretekl (eta by CV),
  # internal_nn (DiSKD, eta = 0), diskd (eta by nested CV), external_discrete
  # (the teacher scored unchanged). The borrowing members need a TEACHER --
  # the external Cox model's coefficients AND its baseline cumulative hazard,
  # evaluated at the interval edges -- so without a baseline the row holds the
  # two internal members only. Every member is scored by the same functional,
  # the pooled held-out negative log-likelihood per subject of the grouped-
  # time model, on ONE event-stratified partition drawn here and handed to
  # both estimators (`folds=`). The Cox row's V&VH loss is a different
  # likelihood; the two rows are never ranked against each other.
  script_dir <- local({
    a <- commandArgs(trailingOnly = FALSE)
    f <- sub("^--file=", "", a[grepl("^--file=", a)])
    if (length(f)) dirname(normalizePath(f[1])) else getwd()
  })
  source(file.path(script_dir, "discretekl_cv.R"), local = TRUE)

  n <- nrow(z)
  K <- as.integer(input$discrete$n_intervals)
  is_index <- isTRUE(input$discrete$time_is_index)
  width <- if (is_index) NA_real_ else as.numeric(input$discrete$width)
  if (is.na(K) || K < 2L) stop("n_intervals must be at least 2")
  if (!is_index && (is.na(width) || width <= 0)) stop("the interval width must be positive")

  ## ---- the grid is part of the model (ruling 1) ----------------------
  # interval k covers [(k-1) w, k w) -- floor, the MIUM grid; a subject
  # observed beyond K w is censored at K (administrative censoring at the
  # horizon). The gate reported the same cut on the consequence card.
  beyond <- rep(FALSE, n)
  if (is_index) {
    if (any(abs(time - round(time)) > 1e-8) || any(time < 1) || any(time > K))
      stop("the time column was declared to be the interval index but holds values outside 1..K")
    time_bin <- as.integer(round(time))
  } else {
    raw_bin <- floor(time / width) + 1
    beyond <- raw_bin > K
    time_bin <- as.integer(pmin(raw_bin, K))
  }
  n_events_beyond <- sum(delta == 1 & beyond)
  delta[beyond] <- 0
  if (max(time_bin) != K)
    stop(sprintf("no subject reaches the last interval %d (last reached: %d); the gate should have refused this", K, max(time_bin)))
  edges <- if (is_index) as.numeric(seq_len(K + 1)) else (0:K) * width

  ## ---- ONE partition, drawn here, handed to every member --------------
  set.seed(seed, kind = "Mersenne-Twister")
  folds <- integer(n)
  for (v in c(0L, 1L)) {
    i <- sample(which(delta == v))
    folds[i] <- 1L + (seq_along(i) - 1L) %% nfolds
  }

  ## ---- the teacher: the external Cox model on the interval grid --------
  bl <- input$baseline_inline
  has_teacher <- has_external && !is.null(bl) && !has_indi
  teacher <- NULL; dH0 <- NULL
  if (has_teacher) {
    bt <- as.numeric(unlist(bl$time)); bc <- as.numeric(unlist(bl$cumhaz))
    if (!length(bt) || length(bt) != length(bc)) stop("baseline_inline must hold time and cumhaz of equal length")
    # the increment of the external cumulative hazard over each interval:
    # H0 at the interval's upper edge minus H0 at its lower edge, the step
    # function RIGHT-continuous as survival::basehaz reports it (H0(7)
    # includes a jump at day 7). A Cox jump exactly at an edge therefore
    # belongs to the preceding increment while an event exactly at an edge
    # belongs to the following interval under floor binning -- the MIUM
    # convention (its code/10_run_discretekl.R audits and retains it), kept
    # here so the agent reproduces that run's teacher exactly.
    # Beyond the last published time point the step function is flat, so a
    # horizon past it adds nothing (the gate refused a baseline that ends
    # before the last interval begins).
    H_at <- function(t) { i <- sum(bt <= t); if (i == 0L) 0 else bc[i] }
    dH0 <- diff(vapply(edges, H_at, numeric(1)))
    if (!any(dH0 > 0)) stop("the external baseline hazard does not increase over the declared horizon; nothing can be borrowed")
    teacher <- dkl_teacher(beta, dH0, zn)      # beta: covered names only
  }
  # inert teacher for the eta = 0 fit when nothing can be borrowed
  teacher0 <- list(beta = beta_zero, gamma = rep(0, K))
  ETAS_DKL <- c(0, 1, 5, 10, 20, 50, 100)
  if (!is.null(plan_of("discretekl")$etas))     # V4: the planner's grid for DiscreteKL
    ETAS_DKL <- sort(unique(c(0, as.numeric(unlist(plan_of("discretekl")$etas)))))
  SCORER_D <- "discrete_nll/pooled"
  rows <- list(); fits <- list(); gammas <- list()
  want <- function(key) is.null(input$include) || key %in% unlist(input$include)
  failed_row <- function(key, label, borrowing, msg, secs = 0, status = "failed")
    list(key = key, label = label, borrowing = borrowing, penalty = "none",
         status = status, loss = NA_real_, eta = NA_real_, lambda = NA_real_,
         n_nonzero = NA_integer_, seconds = secs, message = substr(msg, 1, 300))

  ## ---- DiscreteKL: one CV run gives the eta = 0 fit and the selected one
  t0 <- proc.time()[["elapsed"]]
  dk <- tryCatch(
    dkl_cv(time_bin, z, delta, if (has_teacher) teacher else teacher0,
           etas = if (has_teacher) ETAS_DKL else 0, folds = folds),
    error = function(err) conditionMessage(err))
  secs <- round(proc.time()[["elapsed"]] - t0, 2)
  dkl_settings <- list(etas = if (has_teacher) ETAS_DKL else 0, tol = 1e-20, max_iter = 25L,
                       link = "cloglog", package = "DiscreteKL",
                       package_version = tryCatch(as.character(utils::packageVersion("DiscreteKL")),
                                                  error = function(e) NA_character_))
  if (is.character(dk)) {
    if (want("internal_discrete"))
      rows[[length(rows) + 1L]] <- failed_row("internal_discrete", "Internal only, discrete time", "none", dk, secs)
    if (has_teacher && want("discretekl"))
      rows[[length(rows) + 1L]] <- failed_row("discretekl", "DiscreteKL (Kullback-Leibler, discrete time)", "kl", dk, secs)
  } else {
    pooled <- dk$pooled
    if (want("internal_discrete")) {
      fits[["internal_discrete"]] <- dk$internal$beta; gammas[["internal_discrete"]] <- dk$internal$gamma
      rows[[length(rows) + 1L]] <- list(key = "internal_discrete", label = "Internal only, discrete time",
        borrowing = "none", penalty = "none", status = "ok", scorer = SCORER_D,
        loss = pooled$nll_per_subject[pooled$eta == 0], eta = 0, lambda = NA_real_,
        n_nonzero = sum(abs(dk$internal$beta) > 1e-10), seconds = secs, message = NULL,
        settings = c(dkl_settings, list(score_max_abs = dk$internal$score_max_abs)))
    }
    if (has_teacher && want("discretekl")) {
      fits[["discretekl"]] <- dk$fit$beta; gammas[["discretekl"]] <- dk$fit$gamma
      rows[[length(rows) + 1L]] <- list(key = "discretekl", label = "DiscreteKL (Kullback-Leibler, discrete time)",
        borrowing = "kl", penalty = "none", status = "ok", scorer = SCORER_D,
        loss = pooled$nll_per_subject[pooled$eta == dk$eta], eta = dk$eta, lambda = NA_real_,
        n_nonzero = sum(abs(dk$fit$beta) > 1e-10), seconds = secs, message = NULL,
        settings = c(dkl_settings, list(score_max_abs = dk$fit$score_max_abs,
                                        cv_path = lapply(seq_len(nrow(pooled)), function(i)
                                          list(eta = pooled$eta[i], complete = pooled$complete[i],
                                               nll_per_subject = pooled$nll_per_subject[i])))))
    }
  }

  ## ---- the teacher scored unchanged (external_discrete, ruling 5) ------
  if (has_teacher && want("external_discrete")) {
    t0 <- proc.time()[["elapsed"]]
    ll <- tryCatch(dkl_loglik(time_bin, z, delta, teacher$gamma, teacher$beta, per_subject = TRUE),
                   error = function(err) conditionMessage(err))
    secs <- round(proc.time()[["elapsed"]] - t0, 2)
    if (is.character(ll) || !all(is.finite(ll))) {
      rows[[length(rows) + 1L]] <- failed_row("external_discrete", "External model, unchanged",
        "external", if (is.character(ll)) ll else "the teacher's log-likelihood is not finite on this data", secs)
    } else {
      # no refit, so the pooled held-out value over the folds is the mean
      # over every subject
      fits[["external_discrete"]] <- teacher$beta; gammas[["external_discrete"]] <- teacher$gamma
      rows[[length(rows) + 1L]] <- list(key = "external_discrete", label = "External model, unchanged",
        borrowing = "external", penalty = "none", status = "ok", scorer = SCORER_D,
        loss = -mean(ll), eta = NA_real_, lambda = NA_real_,
        n_nonzero = sum(abs(teacher$beta) > 1e-10), seconds = secs, message = NULL,
        settings = list(scored = "teacher hazards 1 - exp(-dH0_k exp(x'beta_ext)) on every subject"))
    }
  }

  ## ---- the network members, through the Python bridge ------------------
  # DiSKD is Python (ruling 3: the agent is Python; nothing R-only about it).
  # mcp/py_scripts/run_diskd.py takes the same JSON handshake this script
  # takes, fits Internal-NN (eta = 0) and DiSKD on the SAME folds, and
  # returns the pooled held-out NLL of each. BREGSURV_PYTHON names the
  # interpreter (the harness sets it to its own); BREGSURV_SKIP_PYTHON=1
  # records both members as skipped, for a replay without torch.
  nn_keys <- c("internal_nn", if (has_teacher) "diskd")
  if (any(vapply(nn_keys, want, logical(1)))) {
    skip <- tolower(Sys.getenv("BREGSURV_SKIP_PYTHON", "")) %in% c("1", "true", "yes")
    if (skip) {
      for (k in nn_keys) if (want(k))
        rows[[length(rows) + 1L]] <- failed_row(k,
          if (k == "diskd") "DiSKD (distilled network, discrete time)" else "Internal only, network",
          if (k == "diskd") "kl" else "none", "skipped: BREGSURV_SKIP_PYTHON is set", 0, "skipped")
    } else {
      py <- Sys.getenv("BREGSURV_PYTHON", unset = "")
      if (!nzchar(py)) py <- Sys.which("python3")
      if (!nzchar(py)) py <- Sys.which("python")
      bridge <- file.path(dirname(script_dir), "py_scripts", "run_diskd.py")
      threads <- suppressWarnings(as.integer(Sys.getenv("OMP_NUM_THREADS",
                   Sys.getenv("SLURM_CPUS_PER_TASK", "1"))))
      if (is.na(threads) || threads < 1L) threads <- 1L
      payload <- list(x = unname(z), columns = zn, duration_index = time_bin - 1L,
                      event = delta, n_intervals = K, folds = folds, seed = seed,
                      threads = threads,
                      teacher = if (has_teacher) list(beta = as.list(teacher$beta), dH0 = dH0) else NULL,
                      settings = input$diskd_options)
      in_f <- tempfile(fileext = ".json"); out_f <- tempfile(fileext = ".json")
      log_f <- tempfile(fileext = ".log")
      writeLines(toJSON(payload, auto_unbox = TRUE, matrix = "rowmajor", digits = NA, null = "null"), in_f)
      t0 <- proc.time()[["elapsed"]]
      rc <- tryCatch(system2(py, c(shQuote(bridge), shQuote(in_f), shQuote(out_f)),
                             stdout = log_f, stderr = log_f),
                     error = function(err) conditionMessage(err))
      secs <- round(proc.time()[["elapsed"]] - t0, 2)
      tail_log <- function() if (file.exists(log_f)) paste(utils::tail(readLines(log_f, warn = FALSE), 5), collapse = " | ") else ""
      nn <- if (file.exists(out_f)) tryCatch(fromJSON(out_f, simplifyVector = FALSE),
                                             error = function(err) list(status = "error", message = conditionMessage(err)))
            else list(status = "error", message = paste0("the DiSKD bridge produced no output (python: '",
                                                          py, "', exit ", paste(rc, collapse = " "), "): ", tail_log()))
      unlink(log_f)
      if (!identical(nn$status, "ok")) {
        for (k in nn_keys) if (want(k))
          rows[[length(rows) + 1L]] <- failed_row(k,
            if (k == "diskd") "DiSKD (distilled network, discrete time)" else "Internal only, network",
            if (k == "diskd") "kl" else "none", paste0("DiSKD bridge: ", nn$message), secs)
      } else {
        if (want("internal_nn"))
          rows[[length(rows) + 1L]] <- list(key = "internal_nn", label = "Internal only, network",
            borrowing = "none", penalty = "none", status = "ok", scorer = SCORER_D,
            loss = as.numeric(nn$internal$loss), eta = 0, lambda = NA_real_,
            n_nonzero = NA_integer_, seconds = secs, message = NULL,
            settings = c(nn$settings, list(learning_rate_selected = nn$internal$learning_rate,
                                           epochs = nn$internal$epochs)))
        if (has_teacher && want("diskd") && !is.null(nn$diskd))
          rows[[length(rows) + 1L]] <- list(key = "diskd", label = "DiSKD (distilled network, discrete time)",
            borrowing = "kl", penalty = "none", status = "ok", scorer = SCORER_D,
            loss = as.numeric(nn$diskd$loss), eta = as.numeric(nn$diskd$eta), lambda = NA_real_,
            n_nonzero = NA_integer_, seconds = secs, message = NULL,
            settings = c(nn$settings, list(learning_rate_selected = nn$diskd$learning_rate,
                                           epochs = nn$diskd$epochs, cv_path = nn$cv_path)))
      }
      unlink(c(in_f, out_f))
    }
  }

  ## ---- selection inside the row: plain argmin over one scorer ----------
  ok_rows <- Filter(function(r) identical(r$status, "ok") && is.finite(r$loss), rows)
  if (!length(ok_rows)) stop("Every member of the discrete-time row failed; there is nothing to select.")
  scorers <- unique(vapply(ok_rows, function(r) if (is.null(r$scorer)) "unknown" else r$scorer, character(1)))
  if (length(scorers) > 1L)
    stop(sprintf("The discrete row was scored by more than one functional (%s); nothing was selected.",
                 paste(sort(scorers), collapse = " and ")))
  losses <- vapply(ok_rows, function(r) r$loss, numeric(1))
  win <- ok_rows[[pick_min(losses)]]
  b_sel <- fits[[win$key]]                     # NULL for a network member
  b_int <- fits[["internal_discrete"]]
  coefs <- lapply(seq_len(p), function(i) list(
    variable = zn[i],
    beta_external = if (has_teacher) unname(teacher$beta[i]) else NA_real_,
    beta_internal = if (is.null(b_int)) NULL else unname(b_int[i]),
    beta_selected = if (is.null(b_sel)) NULL else unname(b_sel[i]),
    covered_by_external = has_teacher && zn[i] %in% names(beta)))
  g_sel <- gammas[[win$key]]; g_int <- gammas[["internal_discrete"]]
  baseline <- lapply(seq_len(K), function(k) list(
    interval = k, from = edges[k], to = edges[k + 1],
    n_at_risk = sum(time_bin >= k), n_events = sum(delta == 1 & time_bin == k),
    gamma_external = if (has_teacher) unname(teacher$gamma[k]) else NULL,
    gamma_internal = if (is.null(g_int)) NULL else unname(g_int[k]),
    gamma_selected = if (is.null(g_sel)) NULL else unname(g_sel[k])))

  list(
    status = "ok",
    facts = list(design = design, external_form = external_form,
                 outcome_scale = "discrete intervals",
                 n = n, n_events = sum(delta == 1), p = p,
                 p_covered = if (has_teacher) length(linkage$covered) else 0L,
                 p_internal_only = if (has_teacher) length(linkage$zero_padded) else p,
                 tie_handling = "not applicable (grouped time)",
                 has_baseline = has_teacher),
    partition = list(seed = seed, nfolds = nfolds, folds = as.list(folds),
                     rng_kind = "Mersenne-Twister",
                     drawn_by = "harness (event-stratified, shared by every member)",
                     row_order = "caller", seed_is_effective = TRUE),
    criteria = "held-out NLL per subject",
    scorer = scorers,
    candidates = rows,
    selected = list(key = win$key, label = win$label, loss = win$loss,
                    eta = win$eta, lambda = win$lambda, n_nonzero = win$n_nonzero,
                    # a network winner has no coefficients: an empty OBJECT,
                    # not an empty array, so readers that index by name agree
                    beta = if (is.null(b_sel)) setNames(list(), character(0))
                           else as.list(setNames(unname(b_sel), zn)),
                    gamma = if (is.null(g_sel)) list() else as.list(unname(g_sel))),
    coefficients = coefs,
    baseline = baseline,
    linkage = linkage,
    discrete = list(n_intervals = K, width = if (is_index) NULL else width,
                    time_is_index = is_index, edges = edges,
                    n_beyond_horizon = sum(beyond), n_events_beyond_horizon = n_events_beyond,
                    binning = "interval k covers [(k-1) x width, k x width); a subject observed beyond K x width is censored at interval K",
                    teacher = if (has_teacher) list(beta = as.list(teacher$beta), dH0 = dH0) else NULL,
                    etas_discretekl = if (has_teacher) ETAS_DKL else 0)
  )
  } else {
  ## ---- the eta grids ---------------------------------------------------
  # These are the grids the manual EHR analyses used and the product was tuned on. A wider
  # superset (KL to 2000, Mahalanobis to 1e5) was tried on 2026-09-12 and REVERTED the same
  # evening: on MIUM the Mahalanobis CV curve falls monotonically toward the external-only
  # limit, so every finite top is "the top", and the penalised members' lambda paths made a
  # run twice as long (4-5 -> 8-11 min). a design decision: the agent must agree with the hand-run
  # at the same settings; finding the best eta-lambda is not the goal. What stays from that
  # trial is the disclosure: a member whose selected eta is the top of its grid is flagged
  # `eta_at_grid_max` and the report says so. Density is unchanged (never thinned).
  # 2026-09-27: the grids above could not express the amount of borrowing that is often
  # best. `generate_eta(method = "exponential")` is an exponential RAMP, not a log grid, so its
  # smallest positive point was 0.199 for KL, 0.554 for the penalised KL members and 0.909 for
  # every Mahalanobis member -- the whole region below eta = 1 was unreachable -- and the
  # Mahalanobis top was 1e3 where the hand analysis uses 1e6 and selects near that top on
  # 39/204 splits. Measured on MIUM, reps 1..20, same library and same selection rule: the
  # ramp gives a selected member at C-index 0.601, a log grid over the hand analysis's range
  # gives 0.637. The rule below is stated as COVERAGE, not as one cohort's numbers: log spaced
  # from eta = 0.01 (two decades below parity) to the family's upper end, at least five points
  # per decade, with eta = 0 kept as the internal endpoint.
  log_eta <- function(hi, n, lo = 0.01) c(0, exp(seq(log(lo), log(hi), length.out = n)))
  ETAS      <- log_eta(2e2, 81)  # KL, unpenalised
  ETAS_PEN  <- log_eta(2e2, 41)  # KL under a ridge or lasso path
  ETAS_MDTL <- log_eta(1e6, 81)  # Mahalanobis, unpenalised: it shrinks slowly, so it needs the reach
  ETAS_MDTL_RIDGE <- log_eta(1e6, 41)
  ETAS_MDTL_ENET  <- log_eta(1e3, 41)
  ETAS_INDI     <- ETAS
  ETAS_PEN_INDI <- ETAS_PEN
  CRIT <- if (is_ncc) "loss" else "V&VH"

  ## ---- the candidate set, derived from the two facts -------------------
  # NO TIE-CORRECTED ESTIMATOR EVER ENTERS THE CANDIDATE SET, and it is not
  # a question the data gets to answer. Settled with whether a
  # tie correction is wanted is the analyst's decision, the default is none, and
  # nothing here should go looking for a reason to do otherwise.
  #
  # What this replaced, recorded because the failure was subtle: the script used
  # to read `if (ties) "coxkl_ties"`, driven by a threshold the GATE applied to
  # the data. The swap reached only the `internal` and `kl` members, while
  # Mahalanobis, all three ridge, all three lasso and External-only kept
  # pl_cal_theta. cv.coxkl_ties scores with Breslow/exact, so the argmin was
  # comparing two different likelihood functionals and calling the smaller
  # number better. It could not have been made consistent either: cox_MDTL has
  # no `ties` formal, there is no ridge or enet tie variant, and vvh_loss_fixed
  # calls pl_cal_theta unconditionally.
  #
  # The measured tie fraction is still reported by the gate, as information.
  # `coxkl_ties` remains in the library for a caller who wants it directly.
  kl_plain <- if (is_ncc) "ncckl" else "coxkl"

  # The scoring functional each member's reported loss came out of, derived from
  # the function name so no call site can forget to declare it. The NCC split is
  # real too: the unpenalized NCC drivers average per-fold ratios while the enet
  # ones pool, and get_fold_cc assigns whole matched sets so fold sizes differ.
  scorer_of <- function(fn) {
    # kept: the guard must still recognise a tie-corrected scorer if one ever
    # reaches the set through a future edit, and refuse the mixed comparison
    if (grepl("_ties$", fn)) return("vvh/breslow-or-exact")
    if (grepl("^cv\\.ncc", fn))
      # Both NCC families pool as of 2026-08-19. The unpenalized drivers used to
      # average per-fold ratios instead, and this guard is what caught it: the
      # NCC set could not be ranked at all until they were unified.
      return("cc_loglik/pooled")
    "vvh/pl_cal_theta"
  }

  spec <- list()
  add <- function(key, label, borrowing, penalty, fn, args)
    spec[[length(spec) + 1L]] <<- list(key = key, label = label,
                                       borrowing = borrowing, penalty = penalty,
                                       fn = fn, args = args,
                                       scorer = scorer_of(fn))

  base_cohort <- list(z = z, delta = delta, time = time, stratum = stratum,
                      nfolds = nfolds, seed = seed, cv.criteria = CRIT)
  base_ncc    <- list(z = z, y = delta, stratum = stratum,
                      nfolds = nfolds, seed = seed, cv.criteria = CRIT)
  base <- if (is_ncc) base_ncc else base_cohort

  # Internal-only: the external vector replaced by zeros, eta pinned at 0. This
  # is how the two real cohorts computed it, and it reuses the same machinery
  # rather than a second code path that could drift.
  if (has_indi) {
    # ---- individual-level external data ---------------------------------
    # The whole cell was absent: `indi` appeared ZERO times in this script.
    # Every member here comes from the individual-level family so the cell has
    # ONE tolerance, ONE scorer and one partition. cv.cox_indi at eta = 0 is the
    # internal-only fit -- the external rows sit in their own strata carrying
    # weight eta, so at zero they contribute nothing to the score or the
    # information -- which is the same masked-identity trick the coefficient
    # cells use, applied to the estimator this cell is actually about.
    #
    # There is no ridge: the library has no cox_indi_ridge or ncc_indi_ridge, so
    # the penalty axis here has two levels, not three, and the report derives
    # that from the set rather than asserting three.
    base_indi <- if (is_ncc)
      list(z_int = z, y_int = delta, stratum_int = stratum,
           z_ext = z_ext, y_ext = delta_ext, stratum_ext = stratum_ext,
           nfolds = nfolds, seed = seed, cv.criteria = CRIT)
    else
      list(z_int = z, delta_int = delta, time_int = time, stratum_int = stratum,
           z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext,
           stratum_ext = stratum_ext,
           nfolds = nfolds, seed = seed, cv.criteria = CRIT)
    fn_indi  <- if (is_ncc) "cv.ncc_indi" else "cv.cox_indi"
    fn_indiE <- if (is_ncc) "cv.ncc_indi_enet" else "cv.cox_indi_enet"

    add("internal", "Internal only", "none", "none",
        fn_indi, c(base_indi, list(etas = 0)))
    add("indi", "Individual-level borrowing", "individual", "none",
        fn_indi, c(base_indi, list(etas = ETAS_INDI)))
    add("internal_lasso", "Internal only, lasso", "none", "lasso",
        fn_indiE, c(base_indi, list(etas = 0, alpha = 1, nlambda = nlambda)))
    add("indi_lasso", "Individual-level borrowing, lasso", "individual", "lasso",
        fn_indiE, c(base_indi, list(etas = ETAS_PEN_INDI, alpha = 1,
                                    nlambda = nlambda)))
  } else {
    add("internal", "Internal only", "none", "none",
        paste0("cv.", kl_plain), c(base, list(beta = beta_zero, etas = 0)))
    if (has_external) {
      add("kl", "Kullback-Leibler", "kl", "none",
          paste0("cv.", kl_plain), c(base, list(beta = beta_full, etas = ETAS)))
      add("mahalanobis", "Mahalanobis", "mahalanobis", "none",
          if (is_ncc) "cv.ncc_MDTL" else "cv.cox_MDTL",
          c(base, list(beta = beta_covered, Q = Q, etas = ETAS_MDTL)))
      # A released covariance ADDS the Mahalanobis metric; it does not take the
      # Euclidean one away. On MIUM the Euclidean lasso beats the covariance-
      # weighted one (0.643 against 0.620), so a set that swapped one for the other
      # lost its best member exactly when the analyst had more to give.
      if (has_Q)
        add("euclidean", "Euclidean", "euclidean", "none",
            if (is_ncc) "cv.ncc_MDTL" else "cv.cox_MDTL",
            c(base, list(beta = beta_covered, etas = ETAS_MDTL)))
    }

    if (!is_ncc) {
      # Ridge exists for the Cox family only; the NCC side has elastic net alone,
      # by the library's own design.
      add("internal_ridge", "Internal only, ridge", "none", "ridge",
          "cv.coxkl_ridge", c(base, list(beta = beta_zero, etas = 0, nlambda = nlambda)))
      if (has_external) {
        add("kl_ridge", "Kullback-Leibler, ridge", "kl", "ridge",
            "cv.coxkl_ridge", c(base, list(beta = beta_full, etas = ETAS_PEN, nlambda = nlambda)))
        add("mahalanobis_ridge", "Mahalanobis, ridge", "mahalanobis", "ridge",
            "cv.cox_MDTL_ridge",
            c(base, list(beta = beta_covered, Q = Q, etas = ETAS_MDTL_RIDGE, nlambda = nlambda)))
        if (has_Q)
          add("euclidean_ridge", "Euclidean, ridge", "euclidean", "ridge",
              "cv.cox_MDTL_ridge",
              c(base, list(beta = beta_covered, etas = ETAS_MDTL_RIDGE, nlambda = nlambda)))
      }
    }

    enet_kl   <- if (is_ncc) "cv.ncckl_enet" else "cv.coxkl_enet"
    enet_mdtl <- if (is_ncc) "cv.ncc_MDTL_enet" else "cv.cox_MDTL_enet"
    add("internal_lasso", "Internal only, lasso", "none", "lasso",
        enet_kl, c(base, list(beta = beta_zero, etas = 0, alpha = 1, nlambda = nlambda)))
    if (has_external)
      add("kl_lasso", "Kullback-Leibler, lasso", "kl", "lasso",
          enet_kl, c(base, list(beta = beta_full, etas = ETAS_PEN, alpha = 1, nlambda = nlambda)))
    # the Mahalanobis lambda path is strictly proportional to eta, so its floor
    # has to reach far lower than the elastic net default or the path misses the
    # optimum entirely. Measured on the MIUM cohort.
    if (has_external)
      add("mahalanobis_lasso", "Mahalanobis, lasso", "mahalanobis", "lasso",
          enet_mdtl, c(base, list(beta = beta_covered, Q = Q, etas = ETAS_MDTL_ENET, alpha = 1,
                                  nlambda = nlambda, lambda.min.ratio = 1e-9)))
    if (has_external && has_Q)
      add("euclidean_lasso", "Euclidean, lasso", "euclidean", "lasso",
          enet_mdtl, c(base, list(beta = beta_covered, etas = ETAS_MDTL_ENET, alpha = 1,
                                  nlambda = nlambda, lambda.min.ratio = 1e-9)))
  }

  ## ---- V4: the planner's row and its per-member settings --------------------------------------
  # The tie-corrected row: the planner judged from the data that tied event times call for a tie
  # correction (2026-10-02, replacing the 2026-08-19 "only if the analyst asks"). Since BregSurv 1.3.0
  # every Cox-family estimator takes ties = "breslow", so the row is the WHOLE standard
  # set fitted on Breslow's likelihood: each member's key gains "_ties", the released model keeps the
  # key `external` and is scored by vvh_loss_fixed(ties = "breslow") below, and every member reports
  # one scorer, so the guard on mixed functionals still applies.
  TIES_ROW <- plan_row == "cox_ties"
  if (TIES_ROW) {
    if (is_ncc)
      stop("the tie-corrected row exists for a full cohort")
    if (!is.null(plan$ties) && !identical(as.character(plan$ties), "breslow"))
      stop("the tie-corrected row uses Breslow's correction")
    spec <- lapply(spec, function(s) {
      s$key <- paste0(s$key, "_ties"); s$label <- paste0(s$label, ", Breslow ties")
      s$args$ties <- "breslow"; s$scorer <- "vvh/breslow"
      s
    })
  }
  if (!is.null(plan_members)) {
    for (i in seq_along(spec)) {
      s <- spec[[i]]; m <- plan_of(s$key)
      if (is.null(m)) next
      a <- s$args
      internal_member <- startsWith(s$key, "internal")
      # the target-only members stay at eta = 0: a grid there would make them borrowing members
      if (!is.null(m$etas) && !internal_member)
        a$etas <- sort(unique(c(0, as.numeric(unlist(m$etas)))))
      if (!is.null(m$nlambda) && !is.null(a$nlambda)) a$nlambda <- as.integer(m$nlambda)
      vars <- zn
      if (!is.null(m$covariates)) {
        vars <- intersect(zn, as.character(unlist(m$covariates)))
        if (!length(vars)) stop(sprintf("plan member %s keeps no covariate of the cohort", s$key))
      }
      masked <- if (!is.null(m$mask)) intersect(as.character(unlist(m$mask)), zn) else character(0)
      pad <- isTRUE(m$pad_absent)
      # an absent term padded with zero means something only where the metric is the identity
      identity_metric <- s$borrowing == "euclidean" || (s$borrowing == "mahalanobis" && !has_Q)
      if (pad && !identity_metric)
        stop(sprintf("plan member %s: zero-padding applies to an identity-metric member only", s$key))
      if ("z" %in% names(a)) a$z <- z[, vars, drop = FALSE]
      if ("z_int" %in% names(a)) {
        a$z_int <- z[, vars, drop = FALSE]; a$z_ext <- z_ext[, vars, drop = FALSE]
      }
      if (!is.null(a$beta)) {
        if (internal_member) {
          b <- beta_zero[vars]
        } else if (s$borrowing == "kl") {
          # KL borrows the release's risk score: a masked term leaves the score; it is not "free"
          b <- beta_full[vars]; b[intersect(masked, names(b))] <- 0
        } else {
          # Mahalanobis / Euclidean: a masked or uncovered term is free; padding names every term
          b <- if (pad) beta_full else a$beta
          b <- b[names(b) %in% vars & !(names(b) %in% masked)]
          if (!length(b))
            stop(sprintf("plan member %s borrows no term once the mask is applied", s$key))
        }
        a$beta <- b
      }
      if (!is.null(a$Q)) {
        keep <- intersect(rownames(a$Q), names(a$beta))
        a$Q <- a$Q[keep, keep, drop = FALSE]
      }
      s$args <- a; s$vars <- vars; s$masked <- masked; s$padded <- pad
      spec[[i]] <- s
    }
  }

  if (!is.null(input$include)) {
    want <- unlist(input$include)
    spec <- Filter(function(s) s$key %in% want, spec)
  }

  ## ---- fit every member, on one partition ------------------------------
  folds <- NULL
  folds_from <- NA_character_
  folds_rng  <- NA_character_
  rows <- list(); fits <- list()
  n_reused <- 0L
  for (s in spec) {
    ru <- reuse_of(s$key)
    if (!is.null(ru)) {
      # an earlier call fitted this member with this entry: its row and vector, unchanged
      ru$reused <- TRUE
      if (identical(ru$status, "ok")) {
        bv <- unlist(ru$beta)
        if (is.null(bv) || !all(names(bv) %in% zn))
          stop(sprintf("the reused fit of %s does not name the cohort's covariates", s$key))
        fb <- setNames(rep(0, p), zn); fb[names(bv)] <- as.numeric(bv)
        fits[[s$key]] <- fb
      }
      rows[[length(rows) + 1L]] <- ru
      n_reused <- n_reused + 1L
      next
    }
    t0 <- proc.time()[["elapsed"]]
    r <- tryCatch(do.call(s$fn, s$args), error = function(err) conditionMessage(err))
    secs <- round(proc.time()[["elapsed"]] - t0, 2)
    if (is.character(r)) {
      rows[[length(rows) + 1L]] <- list(key = s$key, label = s$label,
        borrowing = s$borrowing, penalty = s$penalty, status = "failed",
        loss = NA_real_, eta = NA_real_, lambda = NA_real_,
        n_nonzero = NA_integer_, seconds = secs, message = substr(r, 1, 300))
      next
    }
    if (is.null(folds) && !is.null(r$folds)) {
      folds <- as.integer(r$folds)
      # Whose RNG kind actually produced it, taken from the estimator that
      # produced the partition rather than asserted. Until 2026-08-19 this was
      # the literal string "Mersenne-Twister" while every cv.* returned its own.
      folds_from  <- s$key
      folds_rng   <- if (!is.null(r$rng_kind)) as.character(r$rng_kind) else NA_character_
    }
    bb <- as.numeric(r$best$best_beta)
    ll <- as.numeric(r$best$best_value)

    # POST-CONDITION. The input checks enumerate the estimator's contract, which
    # is finite; this catches whatever gets past it, and it does not need to have
    # anticipated what. Anything that cannot produce finite coefficients and a
    # finite loss is not a result, whatever the reason, and is recorded as a
    # failure rather than reported as a number.
    bad <- character(0)
    if (!length(bb) || !all(is.finite(bb))) {
      bad <- c(bad, sprintf("%d of %d coefficients are not finite",
                            sum(!is.finite(bb)), length(bb)))
    }
    if (!length(ll) || !is.finite(ll)) bad <- c(bad, "the loss is not finite")
    if (length(bad)) {
      rows[[length(rows) + 1L]] <- list(key = s$key, label = s$label,
        borrowing = s$borrowing, penalty = s$penalty, status = "failed",
        loss = NA_real_, eta = NA_real_, lambda = NA_real_,
        n_nonzero = NA_integer_, seconds = secs,
        message = paste0("the fit returned but did not produce a usable result: ",
                         paste(bad, collapse = "; ")))
      next
    }

    # V4: a member fitted on a subset of the covariates gives a full-length vector with zeros on
    # the terms it left out, so its linear predictor, its held-out scores and the coefficient
    # table are read the same way as everyone else's
    vars_s <- if (!is.null(s$vars)) s$vars else zn
    fb <- setNames(rep(0, p), zn); fb[vars_s] <- bb
    fits[[s$key]] <- fb
    grid <- s$args$etas
    eta_sel <- as.numeric(r$best$best_eta)
    rows[[length(rows) + 1L]] <- list(key = s$key, label = s$label,
      borrowing = s$borrowing, penalty = s$penalty, status = "ok",
      scorer = s$scorer,
      loss = ll,
      eta = eta_sel,
      # the top of the grid was selected: the borrowing weight may be larger than the grid
      # allows, and the report discloses it (never for the eta = 0 internal members)
      eta_at_grid_max = length(grid) > 1L && is.finite(eta_sel) && eta_sel >= max(grid),
      eta_grid_max = if (length(grid) > 1L) max(grid) else NA_real_,
      lambda = if (is.null(r$best$best_lambda)) NA_real_ else as.numeric(r$best$best_lambda),
      n_nonzero = sum(abs(bb) > 1e-10), seconds = secs, message = NULL,
      # V4: what the plan set for this member (absent when the V3 set was fitted)
      covariates_used = length(vars_s),
      masked = if (length(s$masked)) as.list(s$masked) else list(),
      padded = isTRUE(s$padded))
  }

  ## ---- V4: the reused rows' partition must be this one ------------------------------------
  if (n_reused > 0L) {
    rp <- input$reuse$partition
    rf <- if (!is.null(rp$folds)) as.integer(unlist(rp$folds)) else NULL
    if (is.null(rf)) stop("rows were reused without the partition they were scored on")
    if (is.null(folds)) {
      # nothing was fitted in this call: the partition is the one the reused rows were scored on
      folds <- rf
      folds_from <- if (!is.null(rp$drawn_by)) as.character(rp$drawn_by) else NA_character_
      folds_rng  <- if (!is.null(rp$rng_kind)) as.character(rp$rng_kind) else NA_character_
    } else if (!identical(folds, rf)) {
      stop(paste("the members fitted in this call were scored on a different partition from the",
                 "reused ones, so their losses cannot be compared; nothing was selected"))
    }
  }

  ## ---- the External-only member ----------------------------------------
  # It does not refit, so it has no cv.* to run; it is scored at the published
  # vector on the partition the others used.
  if (has_indi && !is_ncc &&
      (is.null(input$include) || "external" %in% unlist(input$include))) {
    # "EXTERNAL COHORT ONLY": fit nothing on the internal data and use a model
    # built entirely on the other one. A published coefficient vector is just
    # somebody elses fitted vector, so this is the SAME row as in the
    # coefficient cells -- it only has to be produced rather than read.
    #
    # It is NOT reachable by turning eta up. In cox_indi the internal rows always
    # carry weight 1, so "ignore my data entirely" is not a point on the path.
    # On both real cohorts the published-vector version of this row BEAT
    # internal-only, which is why it is worth manufacturing here.
    #
    # Unpenalized, matching internal-only. If it will not converge it records
    # `failed` and the report discloses it -- what the MIUM run already did.
    t0 <- proc.time()[["elapsed"]]
    bx <- tryCatch({
      fx <- coxkl(z = z_ext, delta = delta_ext, time = time_ext,
                  stratum = stratum_ext,
                  beta = setNames(rep(0, p), zn), etas = 0,
                  ties = if (TIES_ROW) "breslow" else "none")
      setNames(as.numeric(as.matrix(fx$beta)[, 1]), zn)
    }, error = function(err) conditionMessage(err))
    secs <- round(proc.time()[["elapsed"]] - t0, 2)
    if (is.character(bx) || is.null(folds)) {
      rows[[length(rows) + 1L]] <- list(key = "external",
        label = "External cohort only", borrowing = "external", penalty = "none",
        status = "failed", loss = NA_real_, eta = NA_real_, lambda = NA_real_,
        n_nonzero = NA_integer_, seconds = secs,
        message = if (is.character(bx)) substr(bx, 1, 300)
                  else "No candidate produced a fold assignment to score against.")
    } else {
      ev2 <- tryCatch(vvh_loss_fixed(z = z, delta = delta, time = time,
                                     stratum = stratum, beta = bx, folds = folds,
                                     ties = if (TIES_ROW) "breslow" else "none"),
                      error = function(err) conditionMessage(err))
      if (is.character(ev2)) {
        rows[[length(rows) + 1L]] <- list(key = "external",
          label = "External cohort only", borrowing = "external", penalty = "none",
          status = "failed", loss = NA_real_, eta = NA_real_, lambda = NA_real_,
          n_nonzero = NA_integer_, seconds = secs, message = substr(ev2, 1, 300))
      } else {
        fits[["external"]] <- bx
        # only on success -- see the note where beta_full is initialised
        beta_full <- bx
        rows[[length(rows) + 1L]] <- list(key = "external",
          label = "External cohort only", borrowing = "external", penalty = "none",
          status = "ok", scorer = if (TIES_ROW) "vvh/breslow" else "vvh/pl_cal_theta",
          loss = ev2$VVH_Loss, eta = NA_real_, lambda = NA_real_,
          n_nonzero = sum(abs(bx) > 1e-10), seconds = secs, message = NULL)
      }
    }
  }

  if (has_external &&
      (is.null(input$include) || "external" %in% unlist(input$include))) {
    if (is_ncc) {
      rows[[length(rows) + 1L]] <- list(key = "external",
        label = "External model, unchanged", borrowing = "external", penalty = "none",
        status = "unavailable", loss = NA_real_, eta = NA_real_, lambda = NA_real_,
        n_nonzero = sum(abs(beta_full) > 1e-10), seconds = 0,
        message = paste("The fixed-coefficient cross-validated loss is defined for",
                        "the Cox partial likelihood; there is no nested",
                        "case-control counterpart in this library."))
    } else if (is.null(folds)) {
      rows[[length(rows) + 1L]] <- list(key = "external",
        label = "External model, unchanged", borrowing = "external", penalty = "none",
        status = "failed", loss = NA_real_, eta = NA_real_, lambda = NA_real_,
        n_nonzero = NA_integer_, seconds = 0,
        message = "No candidate produced a fold assignment to score against.")
    } else {
      t0 <- proc.time()[["elapsed"]]
      ev <- tryCatch(vvh_loss_fixed(z = z, delta = delta, time = time,
                                    stratum = stratum, beta = beta_full, folds = folds,
                                    ties = if (TIES_ROW) "breslow" else "none"),
                     error = function(err) conditionMessage(err))
      secs <- round(proc.time()[["elapsed"]] - t0, 2)
      if (is.character(ev)) {
        rows[[length(rows) + 1L]] <- list(key = "external",
          label = "External model, unchanged", borrowing = "external", penalty = "none",
          status = "failed", loss = NA_real_, eta = NA_real_, lambda = NA_real_,
          n_nonzero = NA_integer_, seconds = secs, message = substr(ev, 1, 300))
      } else {
        fits[["external"]] <- beta_full
        rows[[length(rows) + 1L]] <- list(key = "external",
          label = "External model, unchanged", borrowing = "external", penalty = "none",
          status = "ok", scorer = if (TIES_ROW) "vvh/breslow" else "vvh/pl_cal_theta",
          loss = ev$VVH_Loss, eta = NA_real_, lambda = NA_real_,
          n_nonzero = sum(abs(beta_full) > 1e-10), seconds = secs, message = NULL)
      }
    }
  }

  ## ---- the analyst's test data: held-out performance, reported only --
  # An ADDITIONAL file the analyst supplied and named as their test set. It never
  # enters the selection -- eta and lambda inside each member, and the member
  # itself, are chosen by cross-validated loss on the cohort exactly as without
  # it -- and it is never drawn by the harness (the agent
  # splits nothing). Every member with a fitted vector is scored ONCE on it by
  # the library's own `test_eval`, with the Breslow baseline of that member on
  # the cohort (`get_baseline_hazard`) for the Brier score, so the four numbers
  # are the ones a hand-written script gets from the same calls. Cox row only:
  # the matched design has no fixed-coefficient held-out loss in the library
  # and the discrete row's scorer is the grouped-time likelihood.
  test_facts <- NULL
  if (!is.null(input$test_data) && !is_ncc) {
    tspec <- input$test_data
    e_t <- e
    if (!is.null(tspec$path) && nzchar(tspec$path)) {
      if (!file.exists(tspec$path)) stop(sprintf("The test data file was not found: %s", tspec$path))
      e_t <- load_any(tspec$path)
    }
    dt <- eval_in(tspec$expr, e_t)
    if (is.null(dt)) stop("The test data table could not be read.")
    if (is.matrix(dt)) dt <- as.data.frame(dt, stringsAsFactors = FALSE)
    need <- c(tspec$time_col, tspec$event_col, zn,
              if (!is.null(tspec$stratum_col)) tspec$stratum_col)
    miss <- setdiff(need, names(dt))
    if (length(miss))
      stop(sprintf("The test data lacks the declared column(s): %s",
                   paste(utils::head(miss, 8), collapse = ", ")))
    # the covariates in the COHORT's column order, so `betahat` lines up by name
    z_te <- as.matrix(dt[, zn, drop = FALSE]); storage.mode(z_te) <- "double"
    t_te <- as.numeric(dt[[tspec$time_col]])
    d_raw <- dt[[tspec$event_col]]
    d_te <- if (is.factor(d_raw)) as.numeric(as.character(d_raw)) else as.numeric(d_raw)
    if (!is.null(ev_declared) && nzchar(as.character(ev_declared)))
      d_te <- as.numeric(d_te == ev_num)
    s_te <- if (!is.null(tspec$stratum_col)) dt[[tspec$stratum_col]] else NULL
    if (anyNA(z_te) || anyNA(t_te) || anyNA(d_te))
      stop("The test data holds missing values in a declared column; the gate should have refused it.")
    HOLDOUT_CRITERIA <- c(cindex = "CIndex", loss = "loss", ibs = "IBS", tdauc = "tdAUC")
    for (i in seq_along(rows)) {
      r <- rows[[i]]
      b <- fits[[r$key]]
      if (!identical(r$status, "ok") || is.null(b)) next
      if (isTRUE(r$reused) && !is.null(r$holdout)) next  # scored on this test file already
      t0 <- proc.time()[["elapsed"]]
      bh <- tryCatch(get_baseline_hazard(z = z, delta = delta, time = time,
                                         beta = b, stratum = stratum),
                     error = function(err) NULL)
      ho <- lapply(HOLDOUT_CRITERIA, function(crit) tryCatch(
        as.numeric(test_eval(test_z = z_te, test_delta = d_te, test_time = t_te,
                             betahat = b, test_stratum = s_te,
                             train_baseline_obj = if (crit == "IBS") bh else NULL,
                             criteria = crit, ties = if (TIES_ROW) "breslow" else "none")),
        error = function(err) NA_real_))
      ho$seconds <- round(proc.time()[["elapsed"]] - t0, 2)
      ho$baseline_available <- !is.null(bh)
      rows[[i]]$holdout <- ho
    }
    test_facts <- list(n = nrow(dt), n_events = sum(d_te == 1),
                       source = if (!is.null(tspec$path) && nzchar(tspec$path)) basename(tspec$path) else tspec$expr,
                       criteria = unname(HOLDOUT_CRITERIA),
                       baseline = "Breslow baseline of each member on the cohort (get_baseline_hazard); used for the Brier score only",
                       role = "reported only; the selection used the cross-validated loss on the cohort")
  }

  ## ---- every fitted member's coefficients, by name -----------
  # Until now only the selected member's vector left this script, so a member
  # that was NOT selected could not be scored on any data afterwards -- the
  # matched design in particular has no held-out block above. Additive: the
  # report and the benchmark scorers read `holdout` and `selected`, not this.
  for (i in seq_along(rows)) {
    b <- fits[[rows[[i]]$key]]
    if (identical(rows[[i]]$status, "ok") && !is.null(b))
      rows[[i]]$beta <- as.list(setNames(unname(as.numeric(b)), zn))
  }

  ## ---- selection: plain argmin, nothing else ---------------------------
  # No tie judgement, no "difference from the best", no interval. The table lists
  # every candidate's actual number and the reader can see them.
  ok_rows <- Filter(function(r) identical(r$status, "ok") && is.finite(r$loss), rows)
  if (!length(ok_rows)) stop("Every candidate failed; there is nothing to select.")

  # AN ARGMIN IS ONLY MEANINGFUL OVER ONE SCALE. This guard fails closed, in
  # the same shape as the candidate-key drift check on the Python side: if the
  # set was scored by more than one likelihood functional, no ranking exists and
  # refusing is the only honest answer. after the partial
  # tie-variant swap was found to have shipped, and it is the class fix -- the
  # instance fix is at the kl_plain line above. It will also fire the moment the
  # NCC path is wired up, because the unpenalized NCC drivers average per-fold
  # ratios while the enet ones pool; that is a real mismatch and it should stop
  # the run rather than bias the comparison quietly.
  scorers <- unique(vapply(ok_rows,
                           function(r) if (is.null(r$scorer)) "unknown" else r$scorer,
                           character(1)))
  if (length(scorers) > 1L)
    stop(sprintf(paste("The candidate set was scored by more than one likelihood",
                       "functional (%s), so the smallest number is not the best",
                       "model. Nothing was selected."),
                 paste(sort(scorers), collapse = " and ")))

  losses <- vapply(ok_rows, function(r) r$loss, numeric(1))
  win <- ok_rows[[pick_min(losses)]]

  ## ---- what borrowing did, variable by variable ------------------------
  b_sel <- fits[[win$key]]
  b_int <- fits[["internal"]]
  if (is.null(b_int)) b_int <- fits[["internal_ties"]]  # V4: the tie-corrected row's target-only fit
  if (is.null(b_int)) b_int <- fits[["internal_lasso_ties"]]
  coefs <- lapply(seq_len(p), function(i) list(
    variable = zn[i],
    beta_external = unname(beta_full[i]),
    beta_internal = if (is.null(b_int)) NULL else unname(b_int[i]),
    beta_selected = unname(b_sel[i]),
    # "Covered" means the external information says something about this
    # variable. With a published vector that is membership in its names. With an
    # external COHORT it is every variable, because the name-and-order check
    # refused anything else -- and `beta` is NULL there, so the membership test
    # returned FALSE for all p and the report showed an external model that
    # covered nothing while borrowing from all of it.
    # With an external cohort every variable is covered by construction (the
    # name-and-order check refused anything else) -- but only once a vector has
    # actually been fitted from it. If the External-cohort-only member failed
    # there is no external estimate to be covered BY, and beta_external is NA.
    covered_by_external = if (has_indi) !is.null(fits[["external"]])
                          else zn[i] %in% names(beta)))

  list(
    status = "ok",
    facts = list(design = design, external_form = external_form,
                 n = nrow(z), n_events = sum(delta == 1), p = p,
                 p_covered = length(linkage$covered),
                 p_internal_only = length(linkage$zero_padded),
                 # The candidate set NEVER uses a tie-corrected estimator.
                 # that is the analyst's decision, not one
                 # to be inferred from the data, and the default is no
                 # correction. The gate still measures and reports the tie
                 # fraction so the analyst can ask for something else; the
                 # library's coxkl_ties remains available as a direct estimator.
                 tie_handling = "none (the default; not inferred from the data)"),
    partition = list(seed = seed, nfolds = nfolds,
                     folds = if (is.null(folds)) NULL else as.list(folds),
                     # REPORTED, NOT ASSERTED. The kind comes from the
                     # estimator that drew the split. For NCC it is NA on
                     # purpose: get_fold_cc contains no RNG call at all, so the
                     # split is deterministic and `seed` is provenance only --
                     # six NCC bridges still carry comments claiming otherwise.
                     rng_kind = folds_rng,
                     drawn_by = folds_from,
                     # Which row order `folds` indexes. The cohort estimators
                     # sort by (stratum, time) internally and return the split
                     # on THAT order; the NCC ones never reorder and return it
                     # on the caller's. Anything joining folds back to subjects
                     # is right for one design and wrong for the other unless it
                     # reads this.
                     row_order = if (is_ncc) "caller" else "estimator_sorted",
                     seed_is_effective = !is_ncc),
    criteria = CRIT,
    # The one likelihood functional every reported loss came out of. Checked to
    # be single-valued above; published so a reader never has to infer it.
    scorer = scorers,
    candidates = rows,
    selected = list(key = win$key, label = win$label, loss = win$loss,
                    eta = win$eta, lambda = win$lambda,
                    n_nonzero = win$n_nonzero,
                    beta = as.list(setNames(unname(b_sel), zn)),
                    holdout = win$holdout),
    coefficients = coefs,
    linkage = linkage,
    test_data = test_facts
  )
  }  # end of the Cox row
}, error = function(err) {
  list(status = "error", message = conditionMessage(err),
       class = class(err)[1], where = "run_candidates.R")
})

writeLines(toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
                  null = "null", digits = 10, pretty = TRUE),
           con = output_path)
