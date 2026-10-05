#!/usr/bin/env Rscript
# check_admissibility.R - the admissibility gate.
#
# Called by mcp/server.py as:
#   Rscript check_admissibility.R <input.json> <output.json>
#
# HARNESS-INVOKED. This tool carries no LLM-visible schema and the model never
# calls it: it is a deterministic precondition on the data, run before any fit,
# and its verdict is not a matter of judgement.
#
# WHY IT EXISTS.  Measured against the installed package on 2026-08-18, SIX of
# nine poisoned fixtures returned a silently WRONG number through the bridge
# rather than an error.  Reference fit on the clean data:
#
#     clean                       0.5045  -0.3130   0.2350   0.0671
#     competing risks {0,1,2}     0.3871  -0.2652   0.1923   0.1043   <- silent
#     event column is a factor    0.2923  -0.2278   0.1798   0.1085   <- silent
#     every subject an event      0.4751  -0.2905   0.2244   0.0604   <- silent
#     NA follow-up time           0.4949  -0.2730   0.2141   0.1388   <- silent
#     negative follow-up time     0.5039  -0.3133   0.2353   0.0657   <- silent
#     NA event indicator          ran, every coefficient NA
#
# A wrong fit of this kind passes every downstream numeric check perfectly,
# which is why the gate is P0 and number-grounding is not.
#
# REFUSAL IS CORRECT, NOT A LIMITATION.  Competing risks, time-varying
# covariates, left truncation and interval censoring are structurally
# unrepresentable in this estimator library: `schemas.json` has no start/stop/
# entry/id fields at all.  Producing a number for them would be worse than
# declining.
#
# NOT CHECKED, DELIBERATELY: proportional hazards.  R survival >= 3.0-10
# switched `cox.zph` to the "actual" calculation and with correlated covariates
# its false-positive rate reaches 100% at n=100 and n=1,000.  Correlated
# covariates are the EHR norm, so a p < 0.05 -> refuse rule would over-refuse
# catastrophically, and the behaviour depends on the installed R version.
#
# input.json:
#   data_path            required
#   z_expr               required   covariate matrix / data.frame
#   time_expr            required   follow-up time      (cohort designs)
#   delta_expr           required   event indicator     (cohort designs)
#   y_expr                          case indicator      (NCC designs; replaces
#                                                        time_expr/delta_expr)
#   stratum_expr                    optional
#   event_value                     which value of the event column means the
#                                   event occurred; default 1
#   covariates_time_zero            "yes" / "no" / "unsure" - the intake answer
#                                   for time-varying covariates and left
#                                   truncation, which are NOT detectable from a
#                                   flattened one-row-per-subject table.  Absent
#                                   or "unsure" refuses: the gate fails closed.
#   tie_threshold                   fraction of duplicated event times above
#                                   which the _ties estimators are required;
#                                   default 0.10
#   discrete                        {n_intervals, width, time_is_index} -- the
#                                   analyst's item-7 declaration; the
#                                   time column is cut into the intervals here
#                                   and the cut is reported in summary$discrete
#   baseline_inline                 {time:[..], cumhaz:[..]} -- the external
#                                   model's baseline hazard as M5 read it; only
#                                   checked against the horizon when `discrete`
#                                   is present, never a trigger for anything
#   test_data                       {path?, expr, time_col, event_col,
#                                   covariates[], stratum_col?} -- the analyst's
#                                   OWN test file; checked for the same
#                                   columns and the same contract; reported in
#                                   summary$test_data; cohort family only
#
# output.json:
#   {"status":"ok", "admissible":true|false,
#    "refusals":[{code,message,detail}], "advisories":[...],
#    "route":{"ties":bool}, "summary":{..., test_data?:{n_obs, n_events, event_rate},
#                                     discrete?:{n_intervals, width,
#     time_is_index, n_beyond_horizon, n_reach_horizon, events_min, events_max,
#     intervals_without_events, intervals_unobserved, baseline?:{status,detail}}}}
#   or {"status":"error", ...} if the gate itself could not run.

suppressPackageStartupMessages({
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript check_admissibility.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
}

# --- ingestion (requirement R1: the raw data never enters the model's context) -
# The profile and the fitted numbers cross the boundary; the rows never do.
# A tabular file becomes a single data.frame named after the file, so `data_expr`
# can address it the same way as an object inside an .rda.
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
  # a single-table file has one obvious object; say so, so data_expr is optional
  attr(e, "default_object") <- if (ext %in% c("rda", "rdata")) NULL else nm
  e
}

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)

  data_path <- input$data_path
  if (is.null(data_path) || !nzchar(data_path)) stop("data_path is required")
  if (!file.exists(data_path)) stop(sprintf("File not found: %s", data_path))

  e <- load_any(data_path)

  refusals   <- list()
  advisories <- list()
  refuse <- function(code, message, detail = NULL) {
    refusals[[length(refusals) + 1L]] <<-
      list(code = code, message = message, detail = detail)
  }
  advise <- function(code, message, detail = NULL) {
    advisories[[length(advisories) + 1L]] <<-
      list(code = code, message = message, detail = detail)
  }
  lvls <- function(x) {
    u <- unique(x[!is.na(x)])
    u <- if (is.factor(u)) as.character(u) else u
    sort(as.character(u))
  }

  event_value  <- if (!is.null(input$event_value)) input$event_value else 1
  tie_thresh   <- if (!is.null(input$tie_threshold))
                    as.numeric(input$tie_threshold) else 0.10

  ## ---- covariates -----------------------------------------------------
  z_raw <- eval_in(input$z_expr, e)
  if (is.null(z_raw)) stop("z_expr is required")
  n_cov <- if (is.matrix(z_raw) || is.data.frame(z_raw)) ncol(z_raw) else 1L
  cov_names <- if (is.data.frame(z_raw)) names(z_raw) else colnames(z_raw)
  if (is.null(cov_names)) cov_names <- paste0("column_", seq_len(n_cov))

  col_of <- function(i) if (is.data.frame(z_raw)) z_raw[[i]] else z_raw[, i]

  # A non-numeric covariate does NOT reach the estimator as itself. The bridge
  # does as.matrix then storage.mode(z) <- "double", which turns a factor or
  # character column into an ALL-NA column; the fit then dies deep inside with
  # "Hessian solve failed.", a message no analyst can act on. Name it here.
  bad_type <- character(0)
  has_na   <- character(0)
  constant <- character(0)
  for (i in seq_len(n_cov)) {
    v <- col_of(i)
    if (is.factor(v) || is.character(v) || is.logical(v)) {
      bad_type <- c(bad_type, sprintf("%s (%s)", cov_names[i], class(v)[1]))
    } else if (anyNA(v)) {
      has_na <- c(has_na, sprintf("%s (%d missing)", cov_names[i], sum(is.na(v))))
    } else if (length(unique(v)) <= 1L) {
      constant <- c(constant, cov_names[i])
    }
  }
  if (length(bad_type)) {
    refuse("covariate_not_numeric",
           paste("A covariate is not numeric. Encode it before fitting -- a",
                 "binary variable as 0/1, a categorical variable as indicator",
                 "columns. Left as it is, it silently becomes an all-missing",
                 "column and the fit fails with an unrelated message."),
           as.list(bad_type))
  }
  if (length(has_na)) {
    refuse("covariate_missing_values",
           paste("A covariate has missing values. This library does not impute.",
                 "Decide explicitly: drop the variable, drop those subjects, or",
                 "impute upstream and say so in the write-up."),
           as.list(has_na))
  }
  if (length(constant)) {
    advise("covariate_constant",
           "A covariate takes one value for every subject and carries no information.",
           as.list(constant))
  }

  # An infinite covariate is not a large number, it is a missing check upstream.
  # It reaches the solver and dies there with "Hessian solve failed.", which
  # names neither the column nor the reason.
  inf_cov <- character(0)
  for (i in seq_len(n_cov)) {
    v <- col_of(i)
    if (is.numeric(v) && any(is.infinite(v))) {
      inf_cov <- c(inf_cov, sprintf("%s (%d infinite)", cov_names[i],
                                    sum(is.infinite(v))))
    }
  }
  if (length(inf_cov)) {
    refuse("covariate_not_finite",
           paste("A covariate contains an infinite value. This is almost always",
                 "a division or a placeholder that escaped cleaning; it is not a",
                 "quantity the model can use."),
           as.list(inf_cov))
  }

  # Repeated rows are NOT refused. The estimator will treat them as independent
  # subjects, which is wrong if they are one subject entered twice and right if
  # they are two subjects who happen to match -- and only the analyst knows
  # which. Same reasoning as the time-zero question: the intent is invisible in
  # the data, so it is surfaced rather than decided.
  n_z_rows <- if (is.data.frame(z_raw) || is.matrix(z_raw)) nrow(z_raw) else length(z_raw)
  if (is.data.frame(z_raw) || is.matrix(z_raw)) {
    dup <- sum(duplicated(as.data.frame(z_raw)))
    if (dup > 0L) {
      advise("duplicate_rows",
             sprintf(paste("%d row(s) are identical to an earlier row across every",
                           "covariate. They will be counted as separate subjects,",
                           "which narrows the confidence in the fit. If they are one",
                           "subject entered more than once, remove them first."), dup),
             list(n_duplicated = dup, n_rows = n_z_rows))
    }
  }

  # Rank deficiency is an ADVISORY, deliberately. A linearly dependent group is
  # not identified by the unpenalised fits -- the split between the columns is
  # arbitrary, and measured on a synthetic cohort one coefficient moved from
  # 0.411 to 0.115 when a duplicate column was added -- but ridge and the
  # elastic net identify it perfectly well. Refusing would delete the candidates
  # that handle the situation, and letting cross-validation choose among them is
  # exactly what this agent is for.
  if ((is.data.frame(z_raw) || is.matrix(z_raw)) && n_cov > 1L && n_z_rows > n_cov) {
    zm <- suppressWarnings(as.matrix(z_raw))
    if (is.numeric(zm) && !anyNA(zm) && all(is.finite(zm))) {
      r <- tryCatch(qr(zm)$rank, error = function(e) NA_integer_)
      if (!is.na(r) && r < n_cov) {
        advise("rank_deficient",
               sprintf(paste("The covariates are linearly dependent: %d of %d are",
                             "redundant. The unpenalised fits cannot separate them",
                             "and their individual coefficients are arbitrary; the",
                             "ridge and lasso fits can, and the comparison below",
                             "will show whether that matters here."),
                       n_cov - r, n_cov),
               list(rank = r, n_covariates = n_cov))
      }
    }
  }

  ## ---- outcome --------------------------------------------------------
  is_ncc <- !is.null(input$y_expr) && nzchar(input$y_expr)
  ev_arg <- if (is_ncc) "y_expr" else "delta_expr"
  ev_raw <- eval_in(if (is_ncc) input$y_expr else input$delta_expr, e)
  if (is.null(ev_raw)) stop(sprintf("%s is required", ev_arg))

  n_obs <- length(ev_raw)

  # A FACTOR event column is the quietest failure of the lot. as.numeric on a
  # factor returns its integer CODES, so a 0/1 column stored as a factor becomes
  # {1,2}: every subject counts as an event, with weights 1 and 2. Nothing warns.
  if (is.factor(ev_raw)) {
    refuse("event_column_is_factor",
           paste("The event column is stored as a factor. Converting it to a",
                 "number yields its category codes, not its values, so a 0/1",
                 "column silently becomes 1/2 and every subject is treated as",
                 "having had the event. Convert it to a plain 0/1 numeric",
                 "column first."),
           list(levels = as.list(levels(ev_raw))))
  }
  if (anyNA(ev_raw)) {
    refuse("event_has_missing",
           paste("The event indicator is missing for some subjects. Whether an",
                 "event occurred cannot be left unknown: every coefficient comes",
                 "back missing."),
           list(n_missing = sum(is.na(ev_raw)), n_obs = n_obs))
  }

  ev_lv <- lvls(ev_raw)
  if (length(ev_lv) > 2L) {
    refuse("competing_risks",
           paste("The event column has more than two levels, which means more",
                 "than one kind of event. This library fits a single event type.",
                 "Decide which analysis you want and supply a 0/1 column for it:",
                 "a cause-specific analysis (the event of interest = 1, every",
                 "other outcome censored) or a composite (any event = 1). Passing",
                 "the column as it stands produces a fit that is neither."),
           list(levels_observed = as.list(ev_lv)))
  } else if (length(ev_lv) <= 1L) {
    refuse("degenerate_outcome",
           paste("The event column takes the same value for every subject. With",
                 "no contrast between those who had the event and those who did",
                 "not there is nothing to estimate; the fit returns numbers",
                 "regardless, and they mean nothing."),
           list(level_observed = as.list(ev_lv), n_obs = n_obs))
  } else if (!setequal(ev_lv, c("0", "1"))) {
    advise("event_recoded",
           sprintf("The event column holds %s; '%s' is being read as the event.",
                   paste(ev_lv, collapse = " and "), as.character(event_value)),
           list(levels_observed = as.list(ev_lv),
                event_value = as.character(event_value)))
  }

  # A CHARACTER event column must be refused, not coerced. as.numeric on
  # "Dead"/"Alive" returns all NA with only a warning, so `n_events` becomes 0,
  # the gate reports admissible with an event rate of 0%, and the run dies far
  # downstream inside the estimator -- after the analyst has approved a
  # configuration. The factor case one branch up is already refused for exactly
  # this reason; character was simply missed.
  if (is.character(ev_raw)) {
    ev_lv_c <- sort(unique(ev_raw[!is.na(ev_raw)]))
    if (anyNA(suppressWarnings(as.numeric(ev_lv_c)))) {
      refuse("event_column_is_text",
             sprintf(paste("The event column holds text (%s), not a 0/1",
                           "indicator. Reading it as a number gives NA for",
                           "every subject, which looks like an analysis with no",
                           "events rather than an error. Recode it first."),
                     paste(utils::head(ev_lv_c, 4), collapse = ", ")),
             list(levels_observed = as.list(utils::head(ev_lv_c, 8))))
    }
  }
  ev_num <- if (is.factor(ev_raw)) as.numeric(as.character(ev_raw)) else
            suppressWarnings(as.numeric(ev_raw))
  n_events <- sum(ev_num == suppressWarnings(as.numeric(event_value)), na.rm = TRUE)

  ## ---- matched sets ---------------------------------------------------
  # stratum_expr was DOCUMENTED in this header and never read. The cost was
  # not cosmetic: run_candidates.R hard-errors with "stratum_expr is required
  # for a nested case-control design", and it does so AFTER the analyst has
  # approved the configuration -- so the gate said "admissible" and the run died
  # later, which inverts the entire fail-before-you-fit design.
  st_raw <- eval_in(input$stratum_expr, e)
  matched <- NULL
  if (is_ncc && is.null(st_raw)) {
    refuse("matched_set_undeclared",
           paste("This is a matched design -- no follow-up duration was",
                 "declared -- but no matched-set column was named. Which rows",
                 "belong to the same matched set is not recoverable from the",
                 "data, and the conditional likelihood is undefined without it."),
           NULL)
  } else if (!is.null(st_raw)) {
    if (length(st_raw) != n_obs) {
      refuse("stratum_length_mismatch",
             sprintf(paste("The matched-set column has %d entries but the",
                           "outcome has %d."), length(st_raw), n_obs),
             list(n_stratum = length(st_raw), n_obs = n_obs))
    } else if (anyNA(st_raw)) {
      # table and tapply both drop NA silently, so a matched-set column
      # with missing entries yields a set count and a one-case count computed
      # over FEWER subjects than the file has -- and the card then reports a
      # structure the analysis will not actually use. Time, event and the
      # covariates all have a missingness refusal; the matched set had none.
      refuse("stratum_has_missing",
             sprintf(paste("The matched-set column is missing for %d of %d",
                           "subjects. Those rows belong to no set, and every",
                           "count below would be computed without them."),
                     sum(is.na(st_raw)), length(st_raw)),
             list(n_missing = sum(is.na(st_raw)), n_obs = length(st_raw)))
    } else {
      st_key   <- as.character(st_raw)
      sizes    <- as.numeric(table(st_key))
      ev_is    <- ev_num == suppressWarnings(as.numeric(event_value))
      per_set  <- tapply(ev_is, st_key, function(x) sum(x, na.rm = TRUE))
      matched  <- list(n_strata = length(sizes),
                       min_size = min(sizes), median_size = stats::median(sizes),
                       max_size = max(sizes),
                       n_one_case = sum(per_set == 1L),
                       n_no_case  = sum(per_set == 0L))
      if (is_ncc) {
        # A set with no case contributes nothing to the conditional likelihood;
        # a set of one has no within-set contrast. Both are silent -- the fit
        # returns numbers estimated from fewer sets than the analyst thinks.
        # EXACTLY ONE CASE PER SET is the 1:m contract the cv.* layer
        # enforces, and it is the falsification device for a matched design.
        # An earlier version of this check asked only whether any set had NO
        # case, which does not catch the mistake it exists to catch: declaring
        # the CONTROLS as cases leaves every set with m cases and none empty, so
        # it sailed through while the card read "sets with exactly one case:
        # 0 of 150". Under a cohort the analyst catches a complement mix-up from
        # an event rate of 75%; here the rate is the sampling ratio and looks
        # perfectly normal either way, so this count is what has to refuse.
        if (matched$n_one_case != matched$n_strata) {
          refuse("matched_sets_not_one_case",
                 sprintf(paste("Only %d of %d matched sets contain exactly one",
                               "case under the declared coding (%d contain none,",
                               "%d contain more than one). Two things look like",
                               "this: '%s' = %s names the CONTROLS rather than",
                               "the cases, or this is not a 1:m matched sample,",
                               "which the conditional-likelihood estimators",
                               "require. Check the count above."),
                         matched$n_one_case, matched$n_strata,
                         matched$n_no_case,
                         matched$n_strata - matched$n_one_case - matched$n_no_case,
                         as.character(ev_arg), as.character(event_value)),
                 list(n_one_case = matched$n_one_case,
                      n_strata = matched$n_strata,
                      n_no_case = matched$n_no_case))
        }
        if (matched$min_size < 2) {
          refuse("matched_set_of_one",
                 sprintf(paste("%d matched set(s) contain a single row. A set",
                               "with no control offers no within-set contrast."),
                         sum(sizes < 2)),
                 list(n_singleton = sum(sizes < 2)))
        }
      }
    }
  }

  ## ---- follow-up time (cohort designs only) ---------------------------
  tm <- NULL
  if (!is_ncc) {
    tm <- eval_in(input$time_expr, e)
    if (is.null(tm)) stop("time_expr is required")
    if (is.factor(tm) || is.character(tm)) {
      refuse("time_not_numeric",
             "The follow-up time column is not numeric.",
             list(class = class(tm)[1]))
      tm <- suppressWarnings(as.numeric(as.character(tm)))
    } else {
      tm <- as.numeric(tm)
    }
    # Neither of the next two errors. Both change the coefficients.
    if (anyNA(tm)) {
      refuse("time_has_missing",
             paste("Follow-up time is missing for some subjects. The fit runs",
                   "anyway and returns different coefficients, with no warning."),
             list(n_missing = sum(is.na(tm)), n_obs = length(tm)))
    }
    # Inf is not caught by anyNA. Measured: an infinite follow-up time runs and
    # returns different coefficients, silently.
    n_inf <- sum(is.infinite(tm))
    if (n_inf > 0L) {
      refuse("time_not_finite",
             paste("Follow-up time is infinite for some subjects. The fit runs",
                   "anyway and returns different coefficients, with no warning."),
             list(n_infinite = n_inf, n_obs = length(tm)))
    }
    # On a DECLARED discrete grid a time of exactly zero is a
    # subject observed in the first interval -- an event on the day of
    # transplant is recorded as day 0 and floor(0 / width) + 1 is interval 1
    # -- so only a negative time is refused there. The continuous-time
    # estimators need a positive duration, as before.
    zero_ok <- !is.null(input$discrete)
    np <- sum(!is.na(tm) & is.finite(tm) & (if (zero_ok) tm < 0 else tm <= 0))
    if (np > 0L) {
      refuse("time_not_positive",
             if (zero_ok)
               paste("Some subjects have a negative follow-up time, which no",
                     "interval of the declared grid can hold.")
             else
               paste("Some subjects have a follow-up time of zero or less. A",
                     "subject must be observed for a positive length of time to",
                     "contribute; these rows are silently absorbed by the fit."),
             list(n_non_positive = np,
                  min_time = min(tm, na.rm = TRUE)))
    }
    # Ties are a routing decision, never a refusal: the library represents them.
    # which, not a bare logical index. An NA in `ev_num` makes the index NA,
    # and `tm[NA]` RETURNS an NA element rather than dropping the row -- so
    # duplicated counts every NA after the first as a tie and the reported tie
    # fraction is invented. which drops NA positions outright.
    ev_times <- tm[which(!is.na(tm)
                         & ev_num == suppressWarnings(as.numeric(event_value)))]
    tie_frac <- if (length(ev_times)) sum(duplicated(ev_times)) / length(ev_times) else 0
    if (tie_frac > tie_thresh) {
      # DISCLOSURE, NOT AN INSTRUCTION. whether a
      # tie-corrected estimator is used is the ANALYST'S call, never something
      # inferred from the data, and the default is no correction. This message
      # used to read "the tie-handling estimators are required", which made the
      # data decide -- and the pipeline duly acted on it, silently swapping two
      # of the ten candidates onto a different likelihood. Reporting the fact
      # and leaving the decision alone is the whole change.
      advise("tied_event_times",
             sprintf(paste("%.0f%% of event times are shared with another",
                           "subject. This analysis applies no tie correction,",
                           "which is the default; say so if you want one."),
                     100 * tie_frac),
             list(tie_fraction = round(tie_frac, 4),
                  threshold = tie_thresh,
                  n_events = length(ev_times)))
    }
  } else {
    tie_frac <- 0
  }

  ## ---- the discrete-time grid ----------------------------------
  # The analyst declared that follow-up is in discrete intervals (item 7).
  # The grid is part of the model (ruling 1): the harness cuts the time
  # column into the declared intervals here, exactly as run_candidates.R
  # will, and reports what the cut does -- how many subjects fall beyond the
  # horizon, whether the last interval is reached, how the events spread --
  # so the declaration can be falsified from counts before anything is
  # fitted. The external baseline hazard, when one was read, is checked to
  # cover the horizon; its presence never raised the question (ruling 6).
  disc <- NULL
  if (!is.null(input$discrete)) {
    d <- input$discrete
    K <- suppressWarnings(as.integer(d$n_intervals))
    is_index <- isTRUE(d$time_is_index)
    width <- if (is_index) NA_real_ else suppressWarnings(as.numeric(d$width))
    if (is_ncc) {
      refuse("discrete_needs_followup_time",
             paste("A discrete-time analysis was declared for a matched design.",
                   "There is no follow-up duration to cut into intervals, and",
                   "the library has no grouped-time conditional-likelihood",
                   "estimator."), NULL)
    } else if (is.na(K) || K < 2L) {
      refuse("discrete_k_too_small",
             sprintf("K = %s: a discrete-time model needs at least two intervals.",
                     as.character(d$n_intervals)), NULL)
    } else if (!is_index && (is.na(width) || width <= 0)) {
      refuse("discrete_width_invalid",
             "The interval width must be a positive number in the units of the time column.",
             NULL)
    } else if (!is.null(tm) && !anyNA(tm) && all(is.finite(tm))) {
      ev_is <- ev_num == suppressWarnings(as.numeric(event_value))
      ev_is[is.na(ev_is)] <- FALSE
      beyond <- rep(FALSE, length(tm))
      bin <- NULL
      if (is_index) {
        if (any(abs(tm - round(tm)) > 1e-8) || any(tm < 1)) {
          refuse("discrete_index_not_integer",
                 paste("The time column was declared to be the interval index",
                       "1..K, but it holds values that are not whole numbers",
                       "of at least 1."),
                 list(n_bad = sum(abs(tm - round(tm)) > 1e-8 | tm < 1)))
        } else if (max(tm) > K) {
          refuse("discrete_index_beyond_k",
                 sprintf(paste("The time column reaches %s but K is %d; an",
                               "interval index must lie in 1..K. Raise K, or",
                               "give the width if the column is a time to bin."),
                         format(max(tm)), K),
                 list(max_index = max(tm), n_intervals = K))
        } else {
          bin <- as.integer(round(tm))
        }
      } else {
        # floor, not ceiling: interval k covers [(k-1) w, k w). This is the
        # MIUM grid (floor_bins in diskd.py), and the card states it.
        raw_bin <- floor(tm / width) + 1
        beyond <- raw_bin > K
        bin <- as.integer(pmin(raw_bin, K))
        ev_is[beyond] <- FALSE         # administrative censoring at the horizon
      }
      if (!is.null(bin)) {
        n_at   <- tabulate(bin, nbins = K)
        n_ev   <- tabulate(bin[ev_is], nbins = K)
        no_ev  <- which(n_ev == 0L)
        unobs  <- which(n_at == 0L)
        if (n_at[K] == 0L) {
          refuse("discrete_horizon_unreached",
                 sprintf(paste("No subject is observed in the last interval %d.",
                               "The discrete-time model fits one baseline",
                               "parameter per interval and needs the horizon to",
                               "be reached; lower K to the last interval anyone",
                               "reaches%s."),
                         K, if (is_index) "" else sprintf(" (%d at width %s)",
                                                          max(bin), format(width))),
                 list(n_intervals = K, last_reached = max(bin)))
        } else if (n_at[K] < 5L) {
          advise("discrete_few_reach_horizon",
                 sprintf(paste("Only %d subject(s) reach the last interval %d.",
                               "A cross-validation fold that holds them all out",
                               "leaves a training set without the horizon, and",
                               "the discrete members then fail on that fold and",
                               "are reported as such."), n_at[K], K),
                 list(n_reach_horizon = n_at[K]))
        }
        if (length(unobs)) {
          advise("discrete_intervals_unobserved",
                 sprintf(paste("%d interval(s) have no subject leaving in them",
                               "(%s). Their baseline parameter is estimated from",
                               "subjects at risk only; the borrowing members",
                               "anchor it to the external model, the",
                               "internal-only member may not converge."),
                         length(unobs), paste(utils::head(unobs, 10), collapse = ", ")),
                 list(intervals = as.list(unobs)))
        } else if (length(no_ev)) {
          advise("discrete_intervals_without_events",
                 sprintf(paste("%d interval(s) contain no event (%s). The",
                               "internal-only discrete fit has nothing to",
                               "estimate its baseline from there; the borrowing",
                               "members anchor it to the external model."),
                         length(no_ev), paste(utils::head(no_ev, 10), collapse = ", ")),
                 list(intervals = as.list(no_ev)))
        }
        bl <- NULL
        if (!is.null(input$baseline_inline)) {
          bt <- as.numeric(unlist(input$baseline_inline$time))
          bc <- as.numeric(unlist(input$baseline_inline$cumhaz))
          needed <- if (is_index) K else (K - 1) * width
          last_t <- if (length(bt)) max(bt) else -Inf
          if (!length(bt) || length(bt) != length(bc)) {
            bl <- list(status = "unusable", detail = "the baseline table is empty or malformed")
            refuse("discrete_baseline_malformed",
                   "The external baseline hazard could not be read as (time, cumulative hazard) pairs.",
                   NULL)
          } else if (last_t < needed) {
            bl <- list(status = "short of the horizon",
                       detail = sprintf("its last time point is %s, before interval %d begins at %s",
                                        format(last_t), K, format(needed)))
            refuse("discrete_baseline_short",
                   sprintf(paste("The external model's baseline hazard ends at time %s,",
                                 "before the last declared interval begins at %s.",
                                 "Nothing can be borrowed for intervals the external",
                                 "model says nothing about; lower K or the width, or",
                                 "check that the baseline is in the units of the",
                                 "time column."), format(last_t), format(needed)),
                   list(last_time = last_t, needed = needed))
          } else {
            # the increment over each interval, from the step function of the
            # cumulative hazard evaluated at the interval edges
            # (right-continuous, as run_candidates.R computes it)
            edges <- if (is_index) seq_len(K + 1) else (0:K) * width
            H_at <- function(t) { i <- sum(bt <= t); if (i == 0L) 0 else bc[i] }
            dH0 <- diff(vapply(edges, H_at, numeric(1)))
            bl <- list(status = "covers the horizon",
                       detail = sprintf("%d time points up to %s; %d of %d interval increments are zero",
                                        length(bt), format(last_t), sum(dH0 <= 0), K))
            if (any(dH0 <= 0)) {
              advise("discrete_baseline_zero_increment",
                     sprintf(paste("The external baseline hazard does not increase",
                                   "over %d of the %d intervals. The teacher's hazard",
                                   "there is zero and the borrowing members pull the",
                                   "internal baseline towards it."), sum(dH0 <= 0), K),
                     list(intervals = as.list(which(dH0 <= 0))))
            }
          }
        }
        disc <- list(n_intervals = K, width = if (is_index) NULL else width,
                     time_is_index = is_index,
                     n_beyond_horizon = sum(beyond),
                     n_reach_horizon = n_at[K],
                     events_min = min(n_ev), events_max = max(n_ev),
                     n_events_binned = sum(n_ev),
                     intervals_without_events = as.list(no_ev),
                     intervals_unobserved = as.list(unobs),
                     baseline = bl)
      }
    }
  }

  ## ---- the analyst's test data ----------------------------------
  # A second file the analyst supplied and named as their test set. It must
  # carry the declared columns (time, event, covariates, stratum) under the
  # same names, hold at least one event and one non-event, and pass the same
  # contract as the cohort -- otherwise the held-out numbers would be computed
  # on rows the estimator cannot use, or on none. Reported: how many rows and
  # events, so the card can say whether a C-index on it means anything.
  td <- NULL
  if (!is.null(input$test_data) && !is_ncc) {
    tspec <- input$test_data
    e_t <- e
    if (!is.null(tspec$path) && nzchar(tspec$path)) {
      if (!file.exists(tspec$path)) {
        refuse("test_data_missing_file",
               sprintf("The test data file was not found: %s", tspec$path), NULL)
      } else {
        e_t <- load_any(tspec$path)
      }
    }
    dt <- tryCatch(eval_in(tspec$expr, e_t), error = function(err) NULL)
    if (is.null(dt) && !any(vapply(refusals, function(r) r$code == "test_data_missing_file", logical(1)))) {
      refuse("test_data_unreadable",
             "The test data table could not be read from the file.", NULL)
    } else if (!is.null(dt)) {
      if (is.matrix(dt)) dt <- as.data.frame(dt, stringsAsFactors = FALSE)
      need <- c(tspec$time_col, tspec$event_col, unlist(tspec$covariates),
                if (!is.null(tspec$stratum_col)) tspec$stratum_col)
      miss <- setdiff(need, names(dt))
      if (length(miss)) {
        refuse("test_data_missing_columns",
               sprintf(paste("The test data lacks %d of the declared columns (%s).",
                             "A test set must carry the same variables under the",
                             "same names as your cohort."),
                       length(miss), paste(utils::head(miss, 8), collapse = ", ")),
               as.list(miss))
      } else {
        t_time  <- suppressWarnings(as.numeric(dt[[tspec$time_col]]))
        t_ev    <- dt[[tspec$event_col]]
        t_evn   <- if (is.factor(t_ev)) as.numeric(as.character(t_ev)) else suppressWarnings(as.numeric(t_ev))
        t_z     <- dt[, unlist(tspec$covariates), drop = FALSE]
        n_t     <- nrow(dt)
        bad_cov <- names(t_z)[vapply(t_z, function(v) is.factor(v) || is.character(v) || anyNA(v) ||
                                                  (is.numeric(v) && any(is.infinite(v))), logical(1))]
        if (length(bad_cov))
          refuse("test_data_covariate_unusable",
                 sprintf("In the test data %d covariate(s) are non-numeric, missing or infinite (%s).",
                         length(bad_cov), paste(utils::head(bad_cov, 8), collapse = ", ")),
                 as.list(bad_cov))
        if (anyNA(t_time) || any(!is.finite(t_time)) || any(t_time <= 0, na.rm = TRUE))
          refuse("test_data_time_invalid",
                 "The test data's follow-up time is missing, infinite or not positive for some rows.",
                 list(n_bad = sum(is.na(t_time) | !is.finite(t_time) | t_time <= 0)))
        t_is <- t_evn == suppressWarnings(as.numeric(event_value))
        n_ev_t <- sum(t_is, na.rm = TRUE)
        if (anyNA(t_evn))
          refuse("test_data_event_missing",
                 sprintf("The test data's event indicator is missing or non-numeric for %d rows.",
                         sum(is.na(t_evn))), NULL)
        else if (n_ev_t < 1L || n_ev_t >= n_t)
          refuse("test_data_degenerate",
                 sprintf(paste("The test data holds %d events among %d rows; a held-out",
                               "evaluation needs at least one event and one non-event."),
                         n_ev_t, n_t), list(n_obs = n_t, n_events = n_ev_t))
        else if (n_ev_t < 10L)
          advise("test_data_few_events",
                 sprintf(paste("The test data holds only %d events among %d rows; the",
                               "held-out C-index and AUC will be very noisy."), n_ev_t, n_t),
                 list(n_obs = n_t, n_events = n_ev_t))
        td <- list(n_obs = n_t, n_events = n_ev_t,
                   event_rate = if (n_t > 0) round(n_ev_t / n_t, 4) else NA)
      }
    }
  } else if (!is.null(input$test_data) && is_ncc) {
    refuse("test_data_needs_cohort",
           "Test data was supplied for a matched design; the held-out evaluation exists for the full-cohort family only.",
           NULL)
  }

  ## ---- what cannot be detected, only asked -----------------------------
  # A flattened one-row-per-subject table has already destroyed the evidence for
  # time-varying covariates and left truncation: the information was gone before
  # this tool saw the file. Duplicate ids and start/stop column names only catch
  # data the analyst correctly supplied in counting-process form. So this is an
  # INTAKE CONSTRAINT, not a detector, and it fails closed.
  #
  # Scale of what it prevents: Levesque et al. 2010, statins and diabetes
  # progression -- naive analysis HR 0.74 (apparent protection) against a proper
  # time-dependent analysis HR 1.97 (apparent harm). A sign flip, not an
  # imprecision.
  tz <- input$covariates_time_zero
  tz <- if (is.null(tz)) "" else tolower(as.character(tz))
  if (!(tz %in% c("yes", "no", "unsure", ""))) {
    stop("covariates_time_zero must be one of: yes, no, unsure")
  }
  if (tz == "no") {
    refuse("time_varying_covariates",
           paste("At least one covariate changes after the start of follow-up.",
                 "Treating a later value as if it had been known at time zero",
                 "can reverse the direction of an effect, not merely blur it.",
                 "This library fits one row per subject and cannot represent it."),
           NULL)
  } else if (tz %in% c("unsure", "")) {
    refuse("time_zero_undeclared",
           paste("It has not been established that every covariate value was",
                 "known at the start of follow-up. This cannot be checked from",
                 "the data -- a one-row-per-subject table looks identical either",
                 "way -- so it has to be stated before the analysis can run."),
           list(answer_given = if (nzchar(tz)) tz else NA))
  }

  ## ---- verdict ---------------------------------------------------------
  list(
    status     = "ok",
    admissible = length(refusals) == 0L,
    refusals   = refusals,
    advisories = advisories,
    # `route` no longer carries a tie instruction: nothing downstream may take
    # a routing decision from the data. The measured fraction is still reported
    # in `summary` below, as a fact the analyst can act on.
    route      = list(),
    summary    = list(
      design        = if (is_ncc) "nested case-control" else "cohort",
      n_obs         = n_obs,
      n_events      = n_events,
      event_rate    = if (n_obs > 0) round(n_events / n_obs, 4) else NA,
      n_covariates  = n_cov,
      matched_sets  = matched,
      event_levels  = as.list(ev_lv),
      tie_fraction  = round(tie_frac, 4),
      discrete      = disc,
      test_data     = td,
      followup      = if (!is.null(tm) && !all(is.na(tm)))
                        list(min = min(tm, na.rm = TRUE),
                             median = stats::median(tm, na.rm = TRUE),
                             max = max(tm, na.rm = TRUE)) else NULL
    )
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "check_admissibility.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
