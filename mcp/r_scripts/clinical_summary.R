#!/usr/bin/env Rscript
# clinical_summary.R - what the recommended model gives a clinician (V4).
#
#   Rscript clinical_summary.R <in.json> <out.json>
#
# HARNESS-INVOKED, after the analysis is fitted and selected, from RunResult.save(). It refits
# nothing and selects nothing: it takes the recommended model's coefficients (and, on the
# discrete-time row, its interval baseline) as they were fitted, and derives from them what a
# clinician uses. Every survival probability comes from the library (get_baseline_hazard,
# predict_surv_prob); the observed survival is survival::survfit.
#
#   hazard ratios          exp(beta) of the recommended model, beside the registry's, per unit of
#                          each variable as coded; an implausibly large coefficient is not
#                          exponentiated (it is a separation artefact, not an effect)
#   predicted survival     every subject's probability of being event-free at a few horizons,
#                          written to <out_base>_predicted.csv (row number in the data file)
#   risk groups            the cohort cut into groups of equal size by predicted risk at the
#                          middle horizon; per group: size, events, predicted and observed
#                          (Kaplan-Meier) survival at each horizon, median survival; a figure of
#                          the observed curves by group
#   reclassification       the same risk thresholds applied to the registry model's own
#                          prediction for the same subjects: who moves group (Cox rows, a
#                          coefficient release, a recommended model other than the registry's)
#   risk calculator        the covariate means and the survival at the means, per stratum, so a
#                          new patient's survival is S_mean(t)^exp((x - mean) . beta)
#
# Everything is computed on the data the model was fitted to (apparent), and says so.
#
# input.json: {data_path, data_expr, time_col, event_col, event_value, stratum_col?, beta:{name:value},
#              row: "cox" | "discrete", gamma?:[...], edges?:[...], external_beta?:{name:value},
#              n_groups?, horizons?:[...], out_base}
# output.json: {status:"ok", ...} or {status:"skipped" | "error", reason}

suppressPackageStartupMessages({ library(jsonlite); library(survival); library(BregSurv) })
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript clinical_summary.R <in.json> <out.json>")
input_path <- args[1]; output_path <- args[2]
BIG_BETA <- 5          # the report's separation flag (report_v3), kept the same here
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
                                 check.names = FALSE, na.strings = c("NA", "")), envir = e)
  } else if (ext %in% c("xlsx", "xls")) {
    if (!requireNamespace("readxl", quietly = TRUE)) stop("Reading .xlsx needs the 'readxl' package")
    assign(nm, as.data.frame(readxl::read_excel(data_path), check.names = FALSE), envir = e)
  } else if (ext == "parquet") {
    if (!requireNamespace("arrow", quietly = TRUE)) stop("Reading .parquet needs the 'arrow' package")
    assign(nm, as.data.frame(arrow::read_parquet(data_path)), envir = e)
  } else {
    stop(sprintf("Unsupported file type '.%s'.", ext))
  }
  e
}
out <- function(x) writeLines(toJSON(x, auto_unbox = TRUE, null = "null", na = "null", digits = 10),
                              output_path)
num <- function(x) as.numeric(unlist(x))

res <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)
  beta <- num(input$beta); names(beta) <- names(input$beta)
  if (!length(beta)) stop("the recommended model has no coefficients")
  e <- load_any(input$data_path)
  d <- eval_in(input$data_expr, e)
  if (is.null(d)) d <- get(ls(e)[1L], envir = e)
  d <- as.data.frame(d)
  miss <- setdiff(names(beta), names(d))
  if (length(miss)) stop(sprintf("columns not in the data: %s", paste(miss, collapse = ", ")))

  tm <- suppressWarnings(as.numeric(d[[input$time_col]]))
  ev <- as.integer(as.character(d[[input$event_col]]) == as.character(input$event_value))
  Z <- as.matrix(d[, names(beta), drop = FALSE]); storage.mode(Z) <- "double"
  sc <- input$stratum_col
  st <- if (!is.null(sc) && nzchar(sc) && sc %in% names(d)) as.character(d[[sc]]) else NULL
  keep <- is.finite(tm) & !is.na(ev) & stats::complete.cases(Z)
  if (!is.null(st)) keep <- keep & !is.na(st)
  rows <- which(keep)
  tm <- tm[keep]; ev <- ev[keep]; Z <- Z[keep, , drop = FALSE]
  if (!is.null(st)) st <- st[keep]
  if (sum(ev) < 2) stop("fewer than two events: nothing to summarise")
  lp <- as.vector(Z %*% beta)
  discrete <- identical(input$row, "discrete")

  ## ---- hazard ratios -------------------------------------------------------
  ext <- if (length(input$external_beta)) { b <- num(input$external_beta); names(b) <- names(input$external_beta); b } else NULL
  hr <- lapply(names(beta), function(v) {
    b <- unname(beta[v]); be <- if (!is.null(ext) && v %in% names(ext)) unname(ext[v]) else NA_real_
    list(variable = v,
         hr = if (is.finite(b) && abs(b) <= BIG_BETA) exp(b) else NA_real_,
         hr_registry = if (is.finite(be) && abs(be) <= BIG_BETA) exp(be) else NA_real_,
         flagged = is.finite(b) && abs(b) > BIG_BETA,
         sd = stats::sd(Z[, v]))
  })

  ## ---- the baseline: the library's Breslow estimator, or the interval baseline -
  if (discrete) {
    g <- num(input$gamma); edges <- num(input$edges)
    if (length(g) != length(edges) - 1L) stop("the interval baseline does not match the grid")
    to <- edges[-1]
    bl <- list(predict_baseline = function(times, strat_id = NULL)
      vapply(times, function(t) sum(exp(g[to <= t + 1e-9])), numeric(1)))
    st <- NULL   # the grouped-time row is not stratified
  } else {
    bl <- BregSurv::get_baseline_hazard(z = Z, delta = ev, time = tm, beta = beta, stratum = st)
  }

  ## ---- horizons ------------------------------------------------------------
  hz <- if (length(input$horizons)) num(input$horizons) else NULL
  if (is.null(hz)) {
    q <- stats::quantile(tm, c(0.25, 0.5, 0.75), names = FALSE)
    if (discrete) {
      hz <- vapply(q, function(x) to[which.min(abs(to - x))], numeric(1))
    } else {
      hz <- signif(q, 2)
    }
  }
  hz <- sort(unique(hz[is.finite(hz) & hz > 0 & hz < max(tm)]))
  if (!length(hz)) stop("no horizon inside the follow-up")
  mid <- hz[ceiling(length(hz) / 2)]

  S <- BregSurv::predict_surv_prob(lp, hz, bl, test_stratum = st)
  colnames(S) <- paste0("survival_at_", format(hz, trim = TRUE))
  risk_mid <- 1 - S[, which(hz == mid)]

  ## ---- risk groups by predicted risk at the middle horizon ------------------
  k <- as.integer(if (length(input$n_groups)) input$n_groups else 3L)
  k <- max(2L, min(k, 5L))
  cuts <- unique(stats::quantile(risk_mid, probs = seq(0, 1, length.out = k + 1), names = FALSE))
  if (length(cuts) < 3) stop("predicted risk does not vary enough to form groups")
  k <- length(cuts) - 1L
  labs <- if (k == 3) c("low", "intermediate", "high") else
          if (k == 2) c("lower", "higher") else paste0("group ", seq_len(k), c(" (lowest)", rep("", k - 2), " (highest)"))
  grp <- cut(risk_mid, breaks = cuts, include.lowest = TRUE, labels = labs)
  fit <- survfit(Surv(tm, ev) ~ grp)
  sm <- summary(fit, times = hz, extend = TRUE)
  sm_lab <- sub("^grp=", "", as.character(sm$strata))
  med <- summary(fit)$table[, "median"]; names(med) <- sub("^grp=", "", names(med))
  groups <- lapply(seq_len(k), function(i) {
    idx <- grp == labs[i]
    obs <- vapply(hz, function(t) {
      j <- which(sm_lab == labs[i] & abs(sm$time - t) < 1e-9)
      if (!length(j) || t > max(tm[idx])) NA_real_ else sm$surv[j[1]]
    }, numeric(1))
    list(group = labs[i], n = sum(idx), n_events = sum(ev[idx]),
         risk_from = cuts[i], risk_to = cuts[i + 1],
         predicted = as.list(unname(colMeans(S[idx, , drop = FALSE]))),
         observed = as.list(obs),
         median_survival = unname(med[labs[i]]))
  })

  ## ---- reclassification against the registry model (Cox rows) --------------
  reclass <- NULL
  if (!discrete && !is.null(ext) && !isTRUE(input$selected_is_registry)) {
    cv <- intersect(names(ext), names(beta))
    if (length(cv)) {
      Zr <- Z[, cv, drop = FALSE]; br <- ext[cv]
      lpr <- as.vector(Zr %*% br)
      blr <- BregSurv::get_baseline_hazard(z = Zr, delta = ev, time = tm, beta = br, stratum = st)
      Sr <- BregSurv::predict_surv_prob(lpr, mid, blr, test_stratum = st)
      gr <- cut(1 - Sr[, 1], breaks = c(-Inf, cuts[-c(1, length(cuts))], Inf), labels = labs)
      tab <- table(registry = gr, recommended = grp)
      up <- sum(as.integer(grp) > as.integer(gr)); down <- sum(as.integer(grp) < as.integer(gr))
      reclass <- list(groups = labs, counts = lapply(seq_len(k), function(i) as.integer(tab[i, ])),
                      n_moved_up = up, n_moved_down = down, n = length(grp),
                      registry_terms_used = cv)
    }
  }

  ## ---- risk calculator: survival at the covariate means ---------------------
  mu <- colMeans(Z)
  lp_mu <- sum(mu * beta)
  strata_u <- if (is.null(st)) NULL else sort(unique(st))
  if (!is.null(strata_u) && length(strata_u) > MAX_STRATA) strata_u <- strata_u[seq_len(MAX_STRATA)]
  base_at_mean <- if (is.null(st)) {
    list(list(stratum = NULL, survival = as.list(unname(BregSurv::predict_surv_prob(lp_mu, hz, bl)[1, ]))))
  } else lapply(strata_u, function(s)
    list(stratum = s, survival = as.list(unname(BregSurv::predict_surv_prob(lp_mu, hz, bl, test_stratum = s)[1, ]))))

  ## ---- the per-subject file ---------------------------------------------------
  csv <- paste0(input$out_base, "_predicted.csv")
  df <- data.frame(row = rows, check.names = FALSE)
  if (!is.null(st)) df[[sc]] <- st
  df$risk_score <- round(lp, 6)
  df$risk_group <- as.character(grp)
  df <- cbind(df, round(S, 6))
  utils::write.csv(df, csv, row.names = FALSE)

  ## ---- the figure: observed survival by risk group -----------------------------
  pal <- c("#4f8a3a", "#d08a2c", "#c0504d", "#8064a2", "#1f4e79")[seq_len(k)]
  if (k == 2) pal <- c("#4f8a3a", "#c0504d")
  grid_t <- pretty(c(0, max(tm)), n = 5); grid_t <- grid_t[grid_t <= max(tm)]
  draw <- function() {
    layout(matrix(1:2, ncol = 1), heights = c(3.2, 0.6 + 0.35 * k))
    par(mar = c(4, 4.5, 2.5, 1), las = 1)
    plot(fit, col = pal, lwd = 2, mark.time = TRUE, xlim = c(0, max(tm)), ylim = c(0, 1),
         xlab = paste0("Follow-up (", input$time_col, ")"), ylab = "Proportion without the event", xaxt = "n")
    axis(1, at = grid_t)
    abline(v = hz, lty = 3, col = "grey60")
    title(main = "Observed survival by predicted risk group", cex.main = 1, font.main = 1)
    legend("bottomleft", legend = paste0(labs, " risk"), col = pal, lwd = 2, bty = "n", cex = 0.85)
    smg <- summary(fit, times = grid_t, extend = TRUE)
    nr <- matrix(smg$n.risk, nrow = k, byrow = TRUE)
    par(mar = c(1, 4.5, 1.2, 1))
    plot(NA, xlim = c(0, max(tm)), ylim = c(0.5, k + 0.5), axes = FALSE, xlab = "", ylab = "")
    mtext("Number at risk", side = 3, adj = 0, cex = 0.8, line = 0.1)
    for (i in seq_len(k)) {
      text(grid_t, k + 1 - i, labels = nr[i, ], col = pal[i], cex = 0.8)
      axis(2, at = k + 1 - i, labels = labs[i], tick = FALSE, cex.axis = 0.75, col.axis = pal[i])
    }
  }
  pdf(paste0(input$out_base, "_groups.pdf"), width = 7, height = 5 + 0.3 * k); draw(); invisible(dev.off())
  png(paste0(input$out_base, "_groups.png"), width = 7, height = 5 + 0.3 * k, units = "in", res = 150); draw(); invisible(dev.off())

  list(status = "ok", basis = "apparent", time_col = input$time_col, row = input$row,
       n = length(tm), n_events = sum(ev), horizons = as.list(hz), middle_horizon = mid,
       hazard_ratios = hr, groups = groups, reclassification = reclass,
       calculator = list(means = as.list(mu), survival_at_means = base_at_mean),
       csv = csv, pdf = paste0(input$out_base, "_groups.pdf"), png = paste0(input$out_base, "_groups.png"))
}, error = function(err) list(status = "error", reason = conditionMessage(err)))
out(res)
