#!/usr/bin/env Rscript
# profile_columns.R - column facts for the role-declaration protocol.
#
# Called by mcp/server.py as:
#   Rscript profile_columns.R <input.json> <output.json>
#
# HARNESS-INVOKED. No LLM-visible schema. This tool emits FACTS, never proposals.
# It does not say which column is the outcome; it says which columns COULD be one,
# and what each column contains, so that declaring is cheap for the analyst.
#
# WHY NOT PROPOSE.  A pre-filled suggestion changes what people write and what
# they believe (N=1,506), so "the analyst confirmed it" is weak evidence that the
# column was right. And the underlying question is not answerable from data: a
# one-row-per-subject table cannot distinguish an event column from its own
# complement, nor days from years.
#
# A data dictionary NARROWS the lists; it never decides. Measured against the
# dictionary this protocol was designed around
# (mimiciv31_20260816/.../metadata/data_dictionary.csv, 162 variables): `role =
# primary_outcome` covers EIGHT variables -- survival_time_days AND
# survival_time_years (same quantity, different units), survival_event AND
# survival_censored (exact complements), plus a human-readable status and three
# date columns -- and `role = outcome` carries a second complete time/event pair
# on a different horizon. Thirteen columns are marked outcome-ish, containing at
# least three valid (time, event) pairs. Reading roles and proceeding would mean
# choosing among them, which is the guessing this protocol exists to prevent. So
# the dictionary is used to shorten a 162-column list to 13, and the analyst
# still declares which pair, in which units, with which value meaning the event.
#
# input.json:
#   data_path             required
#   data_expr             optional R expression selecting the data.frame/matrix
#                         (e.g. "ExampleData_lowdim$train$z"). If omitted, the
#                         first data.frame in the file is profiled.
#   external_beta_expr    optional; its names become the name-match facts
#   external_beta_inline  optional; the same vector passed by value, for a
#                         caller whose coefficients live in their own file
#   dictionary_path       optional CSV with at least a variable-name column
#   dictionary_name_col   default "variable"
#   dictionary_role_col   default "role"
#   outcome_role_pattern  default "outcome" (regex, case-insensitive)
#   setaside_role_pattern default "identifier|index|quality|timing|proxy"
#   max_columns           cap on how many columns are described (default 400)
#
# output.json:
#   {"status":"ok", "n_rows":.., "n_columns":..,
#    "columns":[{name,type,n_missing,pct_missing,n_distinct,values?,summary?,
#                can_be_time,can_be_event,can_be_covariate,can_be_stratum,
#                quarantine,dictionary_role,matches_external,
#                time_grid?:{integer_valued,step,n_distinct,coarse}}],
#    "eligible":{"time":[..],"event":[..],"covariate":[..],"stratum":[..]},
#    "possible_ncc": true when a matched-set-shaped column exists, so the
#                    design question must be asked,
#    "possible_discrete": true when SOME eligible time column sits on a coarse
#                    grid -- informational; the time-scale question is
#                    asked from the settled time column's own time_grid,
#    "quarantined":[{name,reason}],
#    "external":{"present":..,"names":[..],"n_matched":..,"unmatched":[..]},
#    "dictionary":{"present":..,"n_matched":..,"outcome_ish":[..],"set_aside":[..]},
#    "complementary_pairs":[[a,b]]}

suppressPackageStartupMessages({
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript profile_columns.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) return(NULL)
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

  ## ---- locate the table ------------------------------------------------
  d <- eval_in(input$data_expr, e)
  if (is.null(d)) {
    # first data.frame anywhere one or two levels down, else first matrix
    pick <- NULL
    for (nm in ls(e)) {
      obj <- get(nm, envir = e)
      if (is.data.frame(obj) || is.matrix(obj)) { pick <- obj; break }
      if (is.list(obj)) {
        for (inner in obj) {
          if (is.data.frame(inner) || is.matrix(inner)) { pick <- inner; break }
        }
        if (!is.null(pick)) break
      }
    }
    if (is.null(pick)) {
      stop(paste("Could not find a table in the file. Supply data_expr, e.g.",
                 "\"ExampleData_lowdim$train$z\"."))
    }
    d <- pick
  }
  if (is.matrix(d)) d <- as.data.frame(d, stringsAsFactors = FALSE)
  if (!is.data.frame(d)) stop("data_expr must resolve to a data.frame or matrix")

  n_rows  <- nrow(d)
  cn      <- names(d)
  max_col <- if (!is.null(input$max_columns)) as.integer(input$max_columns) else 400L
  truncated <- length(cn) > max_col
  if (truncated) cn <- cn[seq_len(max_col)]

  ## ---- optional data dictionary ---------------------------------------
  dict_role <- setNames(rep(NA_character_, length(cn)), cn)
  dict_present <- FALSE
  if (!is.null(input$dictionary_path) && nzchar(input$dictionary_path) &&
      file.exists(input$dictionary_path)) {
    ncol_nm <- if (!is.null(input$dictionary_name_col)) input$dictionary_name_col else "variable"
    rcol_nm <- if (!is.null(input$dictionary_role_col)) input$dictionary_role_col else "role"
    dd <- utils::read.csv(input$dictionary_path, stringsAsFactors = FALSE,
                          check.names = FALSE, fileEncoding = "UTF-8-BOM")
    if (all(c(ncol_nm, rcol_nm) %in% names(dd))) {
      dict_present <- TRUE
      m <- match(cn, dd[[ncol_nm]])
      dict_role[!is.na(m)] <- as.character(dd[[rcol_nm]])[m[!is.na(m)]]
    }
  }
  out_pat <- if (!is.null(input$outcome_role_pattern)) input$outcome_role_pattern else "outcome"
  aside_pat <- if (!is.null(input$setaside_role_pattern)) input$setaside_role_pattern else
                 "identifier|index|quality|timing|proxy"

  ## ---- external model names -------------------------------------------
  ext_names <- NULL
  beta <- eval_in(input$external_beta_expr, e)
  # The published coefficients usually arrive as their OWN file -- that is
  # how both real cohorts were run -- so they cannot always be addressed as an
  # expression inside the data file. Passing them by value is the only way a web
  # form can offer them at all, and run_candidates.R has accepted `beta_inline`
  # since it existed; the profiler simply never learned to.
  if (is.null(beta) && !is.null(input$external_beta_inline)) {
    bi <- input$external_beta_inline
    beta <- setNames(as.numeric(unlist(bi, use.names = FALSE)), names(bi))
  }
  if (!is.null(beta)) {
    ext_names <- names(beta)
    if (is.null(ext_names) && is.matrix(beta) && ncol(beta) == 1L)
      ext_names <- rownames(beta)
  }

  ## ---- per-column facts ------------------------------------------------
  is_datelike <- function(v) inherits(v, c("Date", "POSIXct", "POSIXt"))
  cols <- vector("list", length(cn))
  binary_vals <- list()

  for (i in seq_along(cn)) {
    v  <- d[[cn[i]]]
    nm <- cn[i]
    nmiss <- sum(is.na(v))
    u <- unique(v[!is.na(v)])
    nd <- length(u)
    ty <- if (is.factor(v)) "factor" else if (is_datelike(v)) class(v)[1] else class(v)[1]

    numericish <- is.numeric(v) && !is.factor(v)
    # `can_be_time` is deliberately broad -- a follow-up time is a non-negative
    # number and nothing in the data separates it from age or eGFR. Two levels is
    # the one fact that does narrow it: a column taking exactly two values is an
    # event-indicator candidate, not a duration. Without that exclusion the list
    # ran to 7 of 11 columns here and would reach ~60 on a real EHR extract,
    # which defeats the point of shortening the question. The analyst can still
    # name any column explicitly; the numbered list is a convenience, not a
    # whitelist. What actually lets a clinician pick the right one at a glance is
    # the min/median/max shown beside each candidate.
    can_time <- (numericish || is_datelike(v)) && nd > 2L &&
                (if (numericish) all(v[!is.na(v)] >= 0) else TRUE)
    can_event <- nd == 2L
    can_cov <- numericish && nd > 1L

    # A MATCHED-SET IDENTIFIER: many SMALL groups of near-equal size. This is
    # what 1:m nested case-control sampling produces and almost nothing else
    # does. The two neighbours it has to be separated from are both common:
    #   * a site / centre / hospital column -- FEW LARGE groups, so it fails the
    #     "at least n/20 distinct values" test;
    #   * a subject identifier -- n groups of exactly one, so it fails the
    #     "median group size >= 2" test (and is quarantined already).
    # Detection exists to TRIGGER THE DESIGN QUESTION, never to answer it. A
    # cohort that happens to carry a matched-set-shaped column is asked and says
    # no, which costs one line; an NCC study that is never asked is analysed as
    # a cohort, which is silently wrong.
    can_stratum <- FALSE
    regular_sets <- FALSE
    if (nd >= 2L && nd < n_rows) {
      # as.character FIRST. table on a FACTOR returns one count per LEVEL,
      # including levels with zero observations, so a matched-set column stored
      # as a factor with unused levels gets group sizes of 0, fails the
      # median >= 2 test, and the design question is never asked -- a matched
      # study silently analysed as a cohort. check_admissibility.R already
      # coerces before tabulating; this is the same fix.
      grp <- as.numeric(table(as.character(v[!is.na(v)])))
      can_stratum <- length(grp) > 0L &&
                     nd >= max(2L, ceiling(n_rows / 20)) &&
                     stats::median(grp) >= 2 && max(grp) <= 20
      # THE SHAPE OF A 1:m MATCHED SAMPLE, as a separate fact: nearly every
      # group the same size. A follow-up time on a coarse grid (months, weeks)
      # passes can_stratum too -- 64 months over 300 rows is "many small
      # groups" -- but its group sizes vary; a matched-set column's do not.
      # `regular_sets` is what lets a time column NAMED as the follow-up stand
      # when it merely looks set-like (2026-09-15: the design question was
      # reopened on every request of four coarse-time cohorts).
      if (can_stratum) {
        modal <- max(table(grp))
        regular_sets <- modal / length(grp) >= 0.9
      }
    }

    q <- NA_character_
    if (nd <= 1L) {
      q <- "constant: one value for every subject"
    } else if (nmiss > 0.5 * n_rows) {
      q <- sprintf("%.0f%% missing", 100 * nmiss / n_rows)
    } else if (nd == n_rows && (is.character(v) || is.factor(v) || is.integer(v))) {
      q <- "one distinct value per subject: looks like an identifier"
    } else if (dict_present && !is.na(dict_role[i]) &&
               grepl(aside_pat, dict_role[i], ignore.case = TRUE)) {
      q <- sprintf("data dictionary role '%s'", dict_role[i])
    }

    if (can_event) binary_vals[[nm]] <- sort(as.character(u))

    entry <- list(
      name = nm, type = ty,
      n_missing = nmiss,
      pct_missing = round(100 * nmiss / max(1L, n_rows), 1),
      n_distinct = nd,
      can_be_time = can_time,
      can_be_event = can_event,
      can_be_covariate = can_cov,
      can_be_stratum = can_stratum,
      regular_sets = regular_sets,
      quarantine = if (is.na(q)) NULL else q,
      dictionary_role = if (is.na(dict_role[i])) NULL else unname(dict_role[i]),
      matches_external = if (is.null(ext_names)) NULL else nm %in% ext_names
    )
    # show the two levels of a candidate event column: the analyst has to say
    # which one means the event, so the levels themselves are the useful fact
    if (can_event) entry$values <- as.list(sort(as.character(u)))
    if (numericish && nd > 2L) {
      qs <- suppressWarnings(stats::quantile(v, c(0, 0.5, 1), na.rm = TRUE))
      entry$summary <- list(min = unname(qs[1]), median = unname(qs[2]),
                            max = unname(qs[3]))
    }
    # THE TIME-GRID FACTS. A follow-up time that sits on a coarse
    # grid -- every value a multiple of one step, and not many distinct
    # values -- is the data fact that makes the discrete-time question worth
    # asking: "is follow-up recorded in intervals, and of what width?" These
    # are facts about the column, never a decision about it: a column of
    # integer months may be a continuous follow-up time rounded to months,
    # and only the analyst knows. The question is asked when
    # `possible_discrete` is TRUE; the answer decides. The presence of a
    # baseline hazard in the external file never triggers it (ruling 6).
    if (can_time && numericish) {
      vv <- v[!is.na(v) & is.finite(v)]
      dv <- sort(unique(vv))
      step <- NA_real_
      if (length(dv) >= 2L) {
        # the common step: the smallest positive gap, if every value is
        # (up to rounding) a multiple of it
        gaps <- diff(dv)
        g0 <- min(gaps[gaps > 0])
        if (is.finite(g0) && g0 > 0 &&
            all(abs(dv / g0 - round(dv / g0)) < 1e-8)) step <- g0
      }
      entry$time_grid <- list(
        integer_valued = all(abs(vv - round(vv)) < 1e-8),
        step = if (is.na(step)) NULL else step,
        n_distinct = nd,
        # coarse: on a common step AND at most 100 distinct values. Absolute,
        # not relative to n: a small cohort followed for 53 weeks has 53
        # distinct values whether it has 200 rows or 2,000.
        coarse = !is.na(step) && nd <= 100L)
    }
    cols[[i]] <- entry
  }
  names(cols) <- NULL

  ## ---- complementary binary pairs -------------------------------------
  # The trap this catches, from the cohort this protocol was designed around:
  # `survival_event` (1 = death) and `survival_censored` (1 = censored) are exact
  # complements, both marked `primary_outcome`. Declaring the wrong one inverts
  # the analysis, and the data cannot tell them apart -- but it CAN say they are
  # complements, and the consequence card then reads 15% events against 85%.
  comp <- list()
  bn <- names(binary_vals)
  if (length(bn) >= 2L) {
    for (a in seq_len(length(bn) - 1L)) {
      va <- d[[bn[a]]]
      for (b in seq(a + 1L, length(bn))) {
        vb <- d[[bn[b]]]
        ok <- !is.na(va) & !is.na(vb)
        if (!any(ok)) next
        na_ <- suppressWarnings(as.numeric(as.character(va[ok])))
        nb_ <- suppressWarnings(as.numeric(as.character(vb[ok])))
        if (anyNA(na_) || anyNA(nb_)) next
        if (all(na_ + nb_ == 1)) comp[[length(comp) + 1L]] <- list(bn[a], bn[b])
      }
    }
  }

  ## ---- one case per set ---------------------------------------------------
  # THE DEFINING FACT OF A MATCHED SAMPLE, measured jointly: every group of a
  # set-shaped column holds exactly one row at one level of some two-valued
  # column (the case). `regular_sets` alone missed it (simulation prompt search,
  # 2026-09-30): controls drawn at random from the risk set leave the late sets
  # short, the group sizes vary, and a request that named the set id as the
  # follow-up time ran a cohort analysis on the set number with nothing
  # refusing it. A follow-up time on a coarse grid almost never holds exactly
  # one event at every value. Recorded as the two-valued columns that do it.
  for (i in seq_along(cols)) {
    if (!isTRUE(cols[[i]]$can_be_stratum)) next
    g <- as.character(d[[cols[[i]]$name]])
    hits <- character(0)
    for (b in setdiff(bn, cols[[i]]$name)) {
      vb <- as.character(d[[b]])
      ok <- !is.na(g) & !is.na(vb)
      if (!any(ok)) next
      for (lev in unique(vb[ok])) {
        per <- tapply(vb[ok] == lev, g[ok], sum)
        if (length(per) >= 2L && all(per == 1L)) { hits <- c(hits, b); break }
      }
    }
    if (length(hits)) cols[[i]]$one_case_per_set <- as.list(hits)
  }

  quarantined <- Filter(Negate(is.null), lapply(cols, function(c)
    if (!is.null(c$quarantine)) list(name = c$name, reason = c$quarantine) else NULL))
  qnames <- vapply(quarantined, function(x) x$name, character(1))

  elig <- function(flag) {
    nm <- vapply(cols, function(c) c$name, character(1))
    keep <- vapply(cols, function(c) isTRUE(c[[flag]]), logical(1)) & !(nm %in% qnames)
    as.list(nm[keep])
  }

  outcome_ish <- if (dict_present)
    as.list(cn[!is.na(dict_role) & grepl(out_pat, dict_role, ignore.case = TRUE)]) else list()

  list(
    status      = "ok",
    n_rows      = n_rows,
    n_columns   = ncol(d),
    truncated   = truncated,
    columns     = cols,
    eligible    = list(time = elig("can_be_time"),
                       event = elig("can_be_event"),
                       covariate = elig("can_be_covariate"),
                       stratum = elig("can_be_stratum")),
    # Whether the DESIGN QUESTION has to be asked. Never whether the answer is
    # yes -- that is the analyst's to state and the gate's to confirm.
    possible_ncc = length(elig("can_be_stratum")) > 0L,
    # Whether SOME eligible time column sits on a coarse grid.
    # Informational only: eligibility for "time" is deliberately broad, so on
    # an EHR extract this is nearly always TRUE (a site code, an age in
    # years). The harness asks the time-scale question from the SETTLED time
    # column's own `time_grid.coarse`, not from this flag.
    possible_discrete = any(vapply(cols, function(c)
      c$name %in% unlist(elig("can_be_time")) && !is.null(c$time_grid) &&
        isTRUE(c$time_grid$coarse), logical(1))),
    quarantined = quarantined,
    complementary_pairs = comp,
    external = list(
      present   = !is.null(ext_names),
      names     = if (is.null(ext_names)) list() else as.list(ext_names),
      n_matched = if (is.null(ext_names)) 0L else sum(ext_names %in% cn),
      unmatched = if (is.null(ext_names)) list() else as.list(setdiff(ext_names, cn))
    ),
    dictionary = list(
      present     = dict_present,
      n_matched   = sum(!is.na(dict_role)),
      outcome_ish = outcome_ish,
      set_aside   = as.list(qnames[qnames %in% cn[!is.na(dict_role)]])
    )
  )
}, error = function(err) {
  list(status = "error", message = conditionMessage(err),
       class = class(err)[1], where = "profile_columns.R")
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
