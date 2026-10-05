#!/usr/bin/env Rscript
# plot_splits.R - box plots of an evaluation by repeated splits (V4, 2026-10-04).
#
#   Rscript plot_splits.R <in.json> <out.json>
#
# HARNESS-INVOKED. Base R graphics only. One panel per measure the analyst asked for, one box
# per member over the splits on which it was fitted, and one more box, "CV-selected", holding on
# each split the numbers of whichever member cross-validation chose there -- the distribution of
# the procedure, not of a fixed member. Writes a PDF and a PNG; draws numbers, writes none.
#
# input.json: {values_csv, measures: [cindex, loss, ibs, tdauc], labels: {key: label},
#              order: [key, ...], selected_key: "cv_selected", out_base}
#   values_csv has columns split, key, measure, value (one row per split, member and measure).
# output.json: {status, pdf, png}

suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript plot_splits.R <in.json> <out.json>")
input_path <- args[1]; output_path <- args[2]

TITLES <- c(cindex = "C-index (higher is better)", loss = "Test loss (lower is better)",
            ibs = "Integrated Brier score (lower is better)", tdauc = "tdAUC (higher is better)")

draw <- function(v, input) {
  meas <- unlist(input$measures)
  keys <- unlist(input$order)
  labs <- unlist(input$labels[keys])
  sel  <- as.character(input$selected_key)
  nc <- if (length(meas) > 1L) 2L else 1L
  nr <- ceiling(length(meas) / nc)
  op <- par(mfrow = c(nr, nc), mar = c(4, 13, 3, 1), las = 1, cex.axis = 0.8)
  on.exit(par(op))
  for (m in meas) {
    sub <- v[v$measure == m & is.finite(v$value), , drop = FALSE]
    vals <- lapply(keys, function(k) sub$value[sub$key == k])
    names(vals) <- labs
    keep <- vapply(vals, length, 1L) > 0L
    if (!any(keep)) {
      plot.new(); title(main = TITLES[[m]]); text(0.5, 0.5, "no finite values"); next
    }
    cols <- ifelse(keys[keep] == sel, "#E69F00", "#9ECAE1")
    boxplot(vals[keep], horizontal = TRUE, col = cols, main = TITLES[[m]],
            xlab = "", border = "grey25", outcex = 0.5)
  }
}

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)
  v <- utils::read.csv(input$values_csv, stringsAsFactors = FALSE)
  pdf_f <- paste0(input$out_base, ".pdf"); png_f <- paste0(input$out_base, ".png")
  n_m <- length(input$measures)
  h <- if (n_m > 2L) 8 else 4.5
  grDevices::pdf(pdf_f, width = 11, height = h)
  draw(v, input)
  grDevices::dev.off()
  grDevices::png(png_f, width = 11, height = h, units = "in", res = 110,
                 type = if (isTRUE(capabilities("cairo"))) "cairo" else getOption("bitmapType"))
  draw(v, input)
  grDevices::dev.off()
  list(status = "ok", pdf = pdf_f, png = png_f)
}, error = function(err) {
  list(status = "error", message = conditionMessage(err), where = "plot_splits.R")
})

writeLines(toJSON(result, auto_unbox = TRUE, null = "null"), con = output_path)
