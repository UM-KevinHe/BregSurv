# figure_lib.R - the figures the harness draws, as ggplot2 objects (V4).
#
# Sourced by plot_km.R, clinical_summary.R and plot_splits.R, which draw the default figures, and by
# restyle_figure.R, which changes how a figure looks at the analyst's request. Its text is also copied
# whole into every <figure>.style.R a restyle writes, so that script runs with R and its packages
# alone.
#
# A figure is a list saved as <base>.figure.rds beside <base>.png and <base>.pdf:
#   main   the ggplot the harness built: every curve, mark, box and line in it comes from the data
#   table  the numbers at risk under a survival curve (a ggplot), or NULL
#   meta   kind, title, size, the role of each layer of `main`, the groups and their colours
# A restyle adds terms to `main` ("p + theme_minimal() + ..."). It never touches `table` directly:
# the table takes the groups' colours and the font from the restyled `main` (fig_table_like), so the
# two parts always agree. What a restyle may and may not change is checked in restyle_figure.R.
#
# Base graphics are not used: a ggplot is an object a restyle can be added to and checked against.

suppressPackageStartupMessages(library(ggplot2))

# the palettes of the base-graphics figures these replace
FIG_PAL_KM <- c("#1f4e79", "#c0504d", "#4f8a3a", "#8064a2", "#d08a2c", "#2c8a8a", "#7f7f7f", "#a05a2c")
FIG_PAL_RISK <- c("#4f8a3a", "#d08a2c", "#c0504d", "#8064a2", "#1f4e79")

fig_theme <- function(base_size = 11) {
  theme_bw(base_size = base_size) +
    theme(panel.grid = element_blank(),
          plot.title = element_text(size = rel(1), face = "plain", hjust = 0.5),
          legend.background = element_blank(), legend.key = element_blank())
}

# The step function of a survfit object, one row per time (time zero added), by group.
fig_km_frame <- function(fit, groups) {
  k <- length(groups)
  g <- if (is.null(fit$strata)) rep(groups[1], length(fit$time)) else rep(groups, fit$strata)
  df <- data.frame(time = fit$time, surv = fit$surv,
                   lower = if (is.null(fit$lower)) NA_real_ else fit$lower,
                   upper = if (is.null(fit$upper)) NA_real_ else fit$upper,
                   n.censor = fit$n.censor, group = g, stringsAsFactors = FALSE)
  start <- data.frame(time = 0, surv = 1, lower = 1, upper = 1, n.censor = 0, group = groups,
                      stringsAsFactors = FALSE)
  df <- rbind(start, df)
  df$group <- factor(df$group, levels = groups)
  df[order(df$group, df$time), , drop = FALSE]
}

# A survival figure: the Kaplan-Meier curves by group, the censoring marks, the pointwise band of a
# single curve (dashed, as plot.survfit draws it), optional dotted vertical lines (the horizons of the
# risk groups), and the numbers at risk under it.
#   fit       survfit, strata in the order of `groups`
#   groups    the group labels, as the legend shows them ("All" for one curve)
#   legend_title  the legend's title (NULL when there is one group)
fig_survival <- function(kind, fit, groups, pal, title, xlab, ylab, xmax, grid_t, n_risk,
                         legend_title = NULL, band = FALSE, vlines = NULL) {
  k <- length(groups)
  pal <- stats::setNames(pal[seq_len(k)], groups)
  df <- fig_km_frame(fit, groups)
  roles <- character(0)
  p <- ggplot(df, aes(x = time, y = surv, colour = group, linetype = group))
  if (length(vlines)) {
    p <- p + geom_vline(data = data.frame(h = vlines), aes(xintercept = h), inherit.aes = FALSE,
                        linetype = "dotted", colour = "grey60", linewidth = 0.4)
    roles <- c(roles, "horizon")
  }
  if (isTRUE(band)) {
    p <- p + geom_step(aes(y = lower), linetype = "dashed", linewidth = 0.4, na.rm = TRUE) +
      geom_step(aes(y = upper), linetype = "dashed", linewidth = 0.4, na.rm = TRUE)
    roles <- c(roles, "band", "band")
  }
  p <- p + geom_step(linewidth = 0.8, direction = "hv")
  roles <- c(roles, "curve")
  cens <- df[df$n.censor > 0, , drop = FALSE]
  p <- p + geom_point(data = cens, shape = 3, size = 1.4, show.legend = FALSE)
  roles <- c(roles, "censor")
  # the legend's title is a label, not a scale name, so a scale a restyle adds keeps it; colour and
  # line type share it, and so share one legend (fig_sync_legends keeps them together after a restyle)
  p <- p +
    scale_colour_manual(values = pal) +
    scale_linetype_manual(values = stats::setNames(rep("solid", k), groups)) +
    scale_x_continuous(limits = c(0, xmax), breaks = grid_t) +
    scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.2)) +
    labs(title = title, x = xlab, y = ylab, colour = legend_title, linetype = legend_title) +
    fig_theme()
  # above the panel, where it covers no curve; one curve has no legend, set by guides rather than the
  # theme so that a whole theme a restyle adds (theme_minimal() and the like) does not bring it back
  p <- p + (if (k > 1) theme(legend.position = "top", legend.justification = "left")
             else guides(colour = "none", linetype = "none"))
  tab <- data.frame(time = rep(grid_t, k), group = factor(rep(groups, each = length(grid_t)), levels = groups),
                    n = as.vector(t(n_risk)))
  table <- ggplot(tab, aes(x = time, y = group, label = n, colour = group)) +
    geom_text(size = 3) +
    scale_x_continuous(limits = c(0, xmax), breaks = grid_t) +
    scale_y_discrete(limits = rev(groups)) +
    scale_colour_manual(values = pal, guide = "none") +
    labs(x = NULL, y = NULL, subtitle = "Number at risk") +
    theme_bw(base_size = 9) +
    theme(panel.grid = element_blank(), panel.border = element_blank(), axis.ticks = element_blank(),
          axis.text.x = element_blank(), plot.subtitle = element_text(size = 9))
  main_h <- 4.2; table_h <- 0.45 + 0.28 * k
  list(main = p, table = table,
       meta = list(kind = kind, title = title, layers = roles, groups = groups,
                   colours = as.list(pal), legend_title = legend_title,
                   width = 7, height = main_h + table_h, rel_heights = c(main_h, table_h)))
}

# Box plots of an evaluation by repeated splits: one panel per measure, one box per member, the
# member cross-validation selected on each split ("CV-selected") filled apart from the others.
fig_splits <- function(v, measures, titles, keys, labels, selected_key) {
  v <- v[v$measure %in% measures & is.finite(v$value) & v$key %in% keys, , drop = FALSE]
  if (!nrow(v)) stop("no finite values to draw")
  lab <- stats::setNames(labels, keys)
  v$label <- factor(lab[v$key], levels = rev(unname(lab[keys])))
  v$role <- factor(ifelse(v$key == selected_key, "CV-selected", "Other methods"),
                   levels = c("CV-selected", "Other methods"))
  v$measure <- factor(titles[v$measure], levels = unname(titles[measures]))
  nc <- if (length(measures) > 1L) 2L else 1L
  p <- ggplot(v, aes(x = value, y = label, fill = role)) +
    geom_boxplot(colour = "grey25", outlier.size = 0.5, linewidth = 0.4) +
    facet_wrap(~ measure, scales = "free_x", ncol = nc) +
    scale_fill_manual(values = c("CV-selected" = "#E69F00", "Other methods" = "#9ECAE1"), name = NULL) +
    labs(x = NULL, y = NULL) +
    fig_theme(10) + theme(strip.background = element_rect(fill = "grey92")) +
    guides(fill = "none")   # the boxes are named on the axis; guides, so a whole theme keeps it off
  nr <- ceiling(length(measures) / nc)
  list(main = p, table = NULL,
       meta = list(kind = "splits_boxplot", title = "Box plots of the evaluation by repeated splits",
                   layers = "box", groups = c("CV-selected", "Other methods"),
                   colours = list("CV-selected" = "#E69F00", "Other methods" = "#9ECAE1"),
                   legend_title = NULL, width = 11, height = if (nr > 1) 8 else 4.5, rel_heights = NULL))
}

# The colour each group has in `p` (after any restyle), as "#RRGGBB" strings named by group.
fig_colours <- function(p, groups, aesthetic = "colour") {
  b <- ggplot_build(p)
  sc <- b$plot$scales$get_scales(aesthetic)
  if (is.null(sc)) return(NULL)
  cols <- sc$map(factor(groups, levels = groups))
  stats::setNames(as.character(cols), groups)
}

# The titles of `p` as they will be drawn (title, x, y and the legend's), NULL where there is none.
fig_labels <- function(p) {
  l <- tryCatch(if (exists("get_labs", envir = asNamespace("ggplot2"))) ggplot2::get_labs(p) else p$labels,
                error = function(e) p$labels)
  one <- function(x) { v <- l[[x]]; if (is.null(v) || inherits(v, "waiver") || !length(v)) NULL else as.character(v)[1] }
  list(title = one("title"), x = one("x"), y = one("y"), colour = one("colour"),
       linetype = one("linetype"), fill = one("fill"))
}

# Colour and line type tell the same groups apart and share one legend only while their titles
# agree. A restyle that retitles one of them (labs(colour = "Sex"), a scale's name) would split the
# legend in two; the other follows it. `p0` is the harness's figure.
fig_sync_legends <- function(p0, p) {
  l0 <- fig_labels(p0); l1 <- fig_labels(p)
  if (identical(l1$colour, l1$linetype)) return(p)
  if (!identical(l1$colour, l0$colour)) p + labs(linetype = l1$colour) else p + labs(colour = l1$linetype)
}

# The numbers-at-risk table, given the colours and the font of `main` as it now is.
fig_table_like <- function(table, main, meta) {
  cols <- fig_colours(main, meta$groups)
  th <- complete_theme(main$theme)
  fam <- calc_element("text", th)$family
  t2 <- table + scale_colour_manual(values = cols, guide = "none")
  if (!is.null(fam) && nzchar(fam)) t2 <- t2 + theme(text = element_text(family = fam))
  t2
}

fig_grob <- function(fig) {
  if (is.null(fig$table)) return(fig$main)
  cowplot::plot_grid(fig$main, fig_table_like(fig$table, fig$main, fig$meta), ncol = 1,
                     align = "v", axis = "lr", rel_heights = fig$meta$rel_heights)
}

# Writes <out_base>.pdf and <out_base>.png; returns their paths.
fig_render <- function(fig, out_base) {
  g <- fig_grob(fig)
  w <- fig$meta$width; h <- fig$meta$height
  pdf_f <- paste0(out_base, ".pdf"); png_f <- paste0(out_base, ".png")
  suppressWarnings({
    grDevices::pdf(pdf_f, width = w, height = h); print(g); invisible(grDevices::dev.off())
    grDevices::png(png_f, width = w, height = h, units = "in", res = 150,
                   type = if (isTRUE(capabilities("cairo"))) "cairo" else getOption("bitmapType"))
    print(g); invisible(grDevices::dev.off())
  })
  list(pdf = pdf_f, png = png_f)
}

# Saves the figure object and a JSON description of it (what the harness shows the language model
# when the analyst asks for a change: the groups and their colours, the titles, the size).
fig_save <- function(fig, out_base) {
  saveRDS(fig, paste0(out_base, ".figure.rds"))
  desc <- list(kind = fig$meta$kind, title = fig$meta$title, groups = I(fig$meta$groups),
               colours = fig$meta$colours, legend_title = fig$meta$legend_title,
               layers = I(fig$meta$layers), labels = fig_labels(fig$main),
               rds = paste0(out_base, ".figure.rds"), png = paste0(out_base, ".png"),
               pdf = paste0(out_base, ".pdf"), base = out_base)
  writeLines(jsonlite::toJSON(desc, auto_unbox = TRUE, null = "null", pretty = TRUE),
             paste0(out_base, ".figure.json"))
  invisible(desc)
}

# Draws, saves and describes one figure; what the three figure scripts call. A figure drawn anew
# (a new analysis, or the curve split by another column) starts from the default look: the restyles
# of the figure it replaces are dropped with it.
fig_write <- function(fig, out_base) {
  unlink(paste0(out_base, c(".style.json", ".style.R")))
  files <- fig_render(fig, out_base)
  fig_save(fig, out_base)
  files
}

# line_width(x) and point_size(x), the two restyle terms that are not ggplot2 functions: the width of
# the curves (or the boxes' lines) and the size of the censoring marks, set on the layers that draw
# them. `roles` is meta$layers. Returns the changed plot.
fig_set_size <- function(p, roles, what, x) {
  x <- as.numeric(x)
  # a layer is an environment: this changes it in place, in every copy of `p` that shares it
  # (restyle_figure.R reads a fresh copy of the figure for each version it compares)
  set <- function(i, param, value) {
    l <- p$layers[[i]]
    ap <- l$aes_params
    ap[[param]] <- value
    l$aes_params <- ap
  }
  for (i in seq_along(roles)) {
    if (what == "line_width" && roles[i] %in% c("curve", "box")) set(i, "linewidth", x)
    if (what == "line_width" && roles[i] == "band") set(i, "linewidth", x / 2)
    if (what == "point_size" && roles[i] == "censor") set(i, "size", x)
  }
  p
}
