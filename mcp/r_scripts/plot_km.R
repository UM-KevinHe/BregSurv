#!/usr/bin/env Rscript
# plot_km.R - the Kaplan-Meier estimate of the target cohort (V4, 2026-10-06).
#
#   Rscript plot_km.R <in.json> <out.json>
#
# HARNESS-INVOKED, after every full-cohort analysis. Base R graphics and survival::survfit only:
# the curve of the declared follow-up time and event, with its pointwise 95% band, and the number
# at risk beneath; one curve per stratum when the analyst declared strata (at most MAX_STRATA of
# them, otherwise the pooled curve), or by the column the analyst asked for (`group_col`): its levels
# when it has at most MAX_STRATA of them, a numeric column with more split at its median. Draws numbers on the axes and the risk table, writes none into
# the report. Nothing is fitted and nothing here enters the analysis.
#
# input.json: {data_path, data_expr, time_col, event_col, event_value, stratum_col?, group_col?, out_base}
# output.json: {status, pdf, png, n, n_events, n_strata, grouped_by, grouping} or {status: "skipped" | "error", reason}

suppressPackageStartupMessages({ library(jsonlite); library(survival) })
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript plot_km.R <in.json> <out.json>")
input_path <- args[1]; output_path <- args[2]
MAX_STRATA <- 8L

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) return(NULL)
  eval(parse(text = expr_str), envir = env)
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

out <- function(x) writeLines(toJSON(x, auto_unbox = TRUE, null = "null", digits = NA), output_path)

res <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)
  e <- load_any(input$data_path)
  d <- eval_in(input$data_expr, e)
  if (is.null(d)) d <- get(ls(e)[1L], envir = e)
  d <- as.data.frame(d)
  tm <- suppressWarnings(as.numeric(d[[input$time_col]]))
  ev <- as.integer(as.character(d[[input$event_col]]) == as.character(input$event_value))
  keep <- is.finite(tm) & !is.na(ev)
  gc <- input$group_col
  grouping <- NULL
  if (!is.null(gc) && nzchar(gc)) {
    if (!gc %in% names(d)) stop(sprintf("no column called '%s'", gc))
    g <- d[[gc]]; nd <- length(unique(g[keep & !is.na(g)]))
    if (nd <= MAX_STRATA) {
      st <- as.factor(g); grouping <- "levels"
    } else if (is.numeric(g)) {
      md <- stats::median(g[keep], na.rm = TRUE)
      st <- factor(ifelse(g <= md, paste0("<= ", signif(md, 4)), paste0("> ", signif(md, 4))),
                   levels = paste0(c("<= ", "> "), signif(md, 4)))
      grouping <- "median"
    } else stop(sprintf("'%s' has %d values, too many to draw a curve for each", gc, nd))
    keep <- keep & !is.na(st); sc <- gc
  } else {
    sc <- input$stratum_col
    st <- if (!is.null(sc) && nzchar(sc) && sc %in% names(d)) as.factor(d[[sc]]) else NULL
    if (!is.null(st) && nlevels(droplevels(st[keep])) > MAX_STRATA) st <- NULL
    if (!is.null(st)) grouping <- "strata"
  }
  tm <- tm[keep]; ev <- ev[keep]; if (!is.null(st)) st <- droplevels(st[keep])
  fit <- if (is.null(st)) survfit(Surv(tm, ev) ~ 1) else survfit(Surv(tm, ev) ~ st)
  k <- if (is.null(st)) 1L else nlevels(st)
  pal <- c("#1f4e79", "#c0504d", "#4f8a3a", "#8064a2", "#d08a2c", "#2c8a8a", "#7f7f7f", "#a05a2c")[seq_len(k)]
  grid_t <- pretty(c(0, max(tm)), n = 5); grid_t <- grid_t[grid_t <= max(tm)]
  draw <- function() {
    layout(matrix(1:2, ncol = 1), heights = c(3.2, 0.6 + 0.35 * k))
    par(mar = c(4, 4.5, 2.5, 1), las = 1)
    plot(fit, col = pal, lwd = 2, conf.int = (k == 1), mark.time = TRUE, xlim = c(0, max(tm)),
         ylim = c(0, 1), xlab = paste0("Follow-up (", input$time_col, ")"),
         ylab = "Proportion without the event", xaxt = "n")
    axis(1, at = grid_t)
    title(main = "Kaplan-Meier estimate of the target cohort", cex.main = 1, font.main = 1)
    if (k > 1) legend("bottomleft", legend = paste0(sc, if (identical(grouping, "median")) " " else " = ", levels(st)), col = pal, lwd = 2, bty = "n", cex = 0.85)
    sm <- summary(fit, times = grid_t, extend = TRUE)
    strata_lab <- if (k > 1) levels(st) else "All"
    nr <- matrix(sm$n.risk, nrow = k, byrow = TRUE)
    par(mar = c(1, 4.5, 1.2, 1))
    plot(NA, xlim = c(0, max(tm)), ylim = c(0.5, k + 0.5), axes = FALSE, xlab = "", ylab = "")
    mtext("Number at risk", side = 3, adj = 0, cex = 0.8, line = 0.1)
    for (i in seq_len(k)) {
      text(grid_t, k + 1 - i, labels = nr[i, ], col = pal[i], cex = 0.8)
      axis(2, at = k + 1 - i, labels = strata_lab[i], tick = FALSE, cex.axis = 0.75, col.axis = pal[i])
    }
  }
  pdf(paste0(input$out_base, ".pdf"), width = 7, height = 5 + 0.3 * k); draw(); invisible(dev.off())
  png(paste0(input$out_base, ".png"), width = 7, height = 5 + 0.3 * k, units = "in", res = 150); draw(); invisible(dev.off())
  list(status = "ok", pdf = paste0(input$out_base, ".pdf"), png = paste0(input$out_base, ".png"),
       n = length(tm), n_events = sum(ev), n_strata = k,
       grouped_by = if (k > 1) sc else NULL, grouping = if (k > 1) grouping else NULL)
}, error = function(err) list(status = "error", reason = conditionMessage(err)))
out(res)
