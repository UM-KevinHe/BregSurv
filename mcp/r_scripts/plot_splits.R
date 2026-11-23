#!/usr/bin/env Rscript
# plot_splits.R - box plots of an evaluation by repeated splits (V4).
#
#   Rscript plot_splits.R <in.json> <out.json>
#
# HARNESS-INVOKED. ggplot2 (figure_lib.R). One panel per measure the analyst asked for, one box
# per member over the splits on which it was fitted, and one more box, "CV-selected", holding on
# each split the numbers of whichever member cross-validation chose there -- the distribution of
# the procedure, not of a fixed member. Writes a PDF and a PNG; draws numbers, writes none.
#
# input.json: {values_csv, measures: [cindex, loss, ibs, tdauc], labels: {key: label},
#              order: [key, ...], selected_key: "cv_selected", out_base}
#   values_csv has columns split, key, measure, value (one row per split, member and measure).
# output.json: {status, pdf, png}; also <out_base>.figure.rds / .figure.json (restyle_figure.R)

suppressPackageStartupMessages(library(jsonlite))
script_dir <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", a[grepl("^--file=", a)])
  if (length(f)) dirname(normalizePath(f[1])) else getwd()
})
source(file.path(script_dir, "figure_lib.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript plot_splits.R <in.json> <out.json>")
input_path <- args[1]; output_path <- args[2]

TITLES <- c(cindex = "C-index (higher is better)", loss = "Test loss (lower is better)",
            ibs = "Integrated Brier score (lower is better)", tdauc = "tdAUC (higher is better)")

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)
  v <- utils::read.csv(input$values_csv, stringsAsFactors = FALSE)
  meas <- unlist(input$measures)
  keys <- unlist(input$order)
  labs <- unlist(input$labels[keys])
  meas <- meas[vapply(meas, function(m) any(v$measure == m & is.finite(v$value)), logical(1))]
  if (!length(meas)) stop("no finite values to draw")
  fig <- fig_splits(v, meas, TITLES, keys, labs, as.character(input$selected_key))
  files <- fig_write(fig, input$out_base)
  list(status = "ok", pdf = files$pdf, png = files$png)
}, error = function(err) {
  list(status = "error", message = conditionMessage(err), where = "plot_splits.R")
})

writeLines(toJSON(result, auto_unbox = TRUE, null = "null"), con = output_path)
