#!/usr/bin/env Rscript
# draw_splits.R - the random train/test splits of an evaluation the analyst asked for.
#
#   Rscript draw_splits.R <in.json> <out.json>
#
# HARNESS-INVOKED (V4, 2026-10-04: evaluation by repeated splits, on request). It draws the
# splits and writes one train file (and, when the cohort itself is split, one test file) per
# split; it fits nothing. Each split is then fitted by run_candidates.R exactly as an ordinary
# analysis is, with the split's train file as the data and its test file as the test data.
#
# The draw is EVENT-STRATIFIED and reproducible from the seed alone: one
# set.seed(seed, kind = "Mersenne-Twister") and the splits drawn in order, within the events and
# within the non-events separately, so every split keeps the cohort's event share. The replay
# script runs this same file and checks it returns the recorded rows.
#
# input.json:
#   data_path, data_expr   the cohort table, addressed as run_candidates.R addresses it
#   event_col, event_value which value of the event column means the event (the declaration's)
#   n_splits, fraction     how many splits; the share drawn into the TEST part ("split") or
#                          the share of rows KEPT ("subsample")
#   mode                   "split": the cohort is cut into train and test;
#                          "subsample": the analyst supplied a test file, so only the
#                          training rows are resampled (no test part is written)
#   seed                   the recorded seed
#   outdir                 where split_<k>/train.csv (and test.csv) are written
# output.json:
#   {status, n, n_events, mode, fraction, seed, rng_kind,
#    splits: [{split, rows: [1-based row numbers: the TEST rows for "split", the KEPT rows for
#              "subsample"], train, test?}]}

suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript draw_splits.R <in.json> <out.json>")
input_path <- args[1]; output_path <- args[2]

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
    assign(nm, as.data.frame(readxl::read_excel(data_path), check.names = FALSE), envir = e)
  } else if (ext == "parquet") {
    if (!requireNamespace("arrow", quietly = TRUE))
      stop("Reading .parquet needs the 'arrow' package: install.packages('arrow')")
    assign(nm, as.data.frame(arrow::read_parquet(data_path)), envir = e)
  } else {
    stop(sprintf("Unsupported file type '.%s'.", ext))
  }
  e
}

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)
  if (!file.exists(input$data_path)) stop(sprintf("File not found: %s", input$data_path))
  e <- load_any(input$data_path)
  df <- eval(parse(text = input$data_expr), envir = e)
  if (is.matrix(df)) df <- as.data.frame(df, stringsAsFactors = FALSE)
  if (!is.data.frame(df)) stop("the cohort is not a table, so it cannot be split")
  if (!(input$event_col %in% names(df))) stop(sprintf("no column called '%s'", input$event_col))

  raw <- df[[input$event_col]]
  if (is.factor(raw)) raw <- as.character(raw)
  ev <- if (!is.null(input$event_value) && nzchar(as.character(input$event_value))) {
    # the same recoding run_candidates.R applies: a numeric column is compared as a number
    if (is.numeric(raw) && !is.na(suppressWarnings(as.numeric(input$event_value))))
      raw == as.numeric(input$event_value) else as.character(raw) == as.character(input$event_value)
  } else as.numeric(raw) == 1
  ev[is.na(ev)] <- FALSE

  K    <- as.integer(input$n_splits)
  frac <- as.numeric(input$fraction)
  mode <- if (is.null(input$mode)) "split" else as.character(input$mode)
  seed <- as.integer(input$seed)
  if (is.na(K) || K < 1L) stop("n_splits must be a positive integer")
  if (is.na(frac) || frac <= 0 || frac >= 1) stop("fraction must lie strictly between 0 and 1")
  if (!(mode %in% c("split", "subsample"))) stop("mode must be 'split' or 'subsample'")

  groups <- list(which(ev), which(!ev))
  # one stream, the splits in order: split k is the k-th draw, whatever is replayed later
  set.seed(seed, kind = "Mersenne-Twister", normal.kind = "Inversion", sample.kind = "Rejection")
  dir.create(input$outdir, showWarnings = FALSE, recursive = TRUE)
  splits <- vector("list", K)
  for (k in seq_len(K)) {
    rows <- sort(unlist(lapply(groups, function(g) {
      m <- round(frac * length(g))
      if (m == 0L || length(g) == 0L) integer(0) else g[sample.int(length(g), m)]
    })))
    d <- file.path(input$outdir, sprintf("split_%04d", k))
    dir.create(d, showWarnings = FALSE)
    tr <- file.path(d, "train.csv")
    if (mode == "split") {
      utils::write.csv(df[-rows, , drop = FALSE], tr, row.names = FALSE)
      te <- file.path(d, "test.csv")
      utils::write.csv(df[rows, , drop = FALSE], te, row.names = FALSE)
      splits[[k]] <- list(split = k, rows = as.integer(rows), train = tr, test = te)
    } else {
      utils::write.csv(df[rows, , drop = FALSE], tr, row.names = FALSE)
      splits[[k]] <- list(split = k, rows = as.integer(rows), train = tr)
    }
  }
  list(status = "ok", n = nrow(df), n_events = sum(ev), mode = mode, fraction = frac,
       seed = seed, rng_kind = paste(RNGkind(), collapse = "/"), splits = splits)
}, error = function(err) {
  list(status = "error", message = conditionMessage(err), where = "draw_splits.R")
})

writeLines(toJSON(result, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE),
           con = output_path)
