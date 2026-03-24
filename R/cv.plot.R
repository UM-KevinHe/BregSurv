#' Plot Cross-Validation Results vs Eta
#'
#' @description
#' Plots cross-validation performance across eta values for
#' \code{cv.coxkl}, \code{cv.coxkl_ridge}, \code{cv.coxkl_enet},
#' \code{cv.cox_MDTL}, \code{cv.cox_MDTL_ridge}, \code{cv.cox_MDTL_enet},
#' \code{cv.ncckl}, \code{cv.ncckl_enet}, or \code{cv.cox_indi_enet}
#' objects in a Biometrics-style figure. It displays the cross-validated
#' performance curve (each eta at its best lambda), a baseline reference at
#' \code{eta = 0}, and marks the optimal \code{eta}.
#'
#' @param object A fitted cross-validation result object.
#' @param line_color Color for the CV performance curve. Default is \code{"#7570B3"}.
#' @param baseline_color Color for the baseline line. Default is \code{"#1B9E77"}.
#' @param ... Additional arguments (currently ignored).
#'
#' @return A ggplot object (cowplot combined).
#'
#' @import ggplot2
#' @importFrom cowplot plot_grid get_legend
#' @importFrom grid unit
#' @importFrom rlang .data
#' @export
cv.plot <- function(object,
                    line_color = "#7570B3",
                    baseline_color = "#1B9E77",
                    ...) {

  if (inherits(object, "cv.coxkl") ||
      inherits(object, "cv.cox_MDTL") ||
      inherits(object, "cv.ncckl") ||
      inherits(object, "cv.cox_indi")) {

    df <- object$internal_stat
    criteria <- object$criteria

  } else if (inherits(object, "cv.coxkl_ridge")   ||
             inherits(object, "cv.cox_MDTL_ridge") ||
             inherits(object, "cv.coxkl_enet")     ||
             inherits(object, "cv.cox_MDTL_enet")  ||
             inherits(object, "cv.ncckl_enet")  ||
             inherits(object, "cv.cox_indi_enet")) {

    df <- object$integrated_stat.best_per_eta
    criteria <- object$criteria

  } else {
    stop("Object class not recognized for cv.plot.", call. = FALSE)
  }

  loss_type <- criteria %in% c("V&VH", "LinPred", "loss", "Brier")

  ylab <- switch(
    criteria,
    "V&VH"  = "Loss",
    "LinPred" = "Loss",
    "loss" = "Loss",
    "Brier" = "Brier Score",
    "AUC" = "AUC",
    "CIndex" = "C Index",
    "CIndex_pooled" = "C Index",
    "CIndex_foldaverage" = "C Index",
    "cindex" = "C Index",
    if (loss_type) "Loss" else "C Index"
  )

  loss_candidates   <- c("VVH_Loss", "LinPred_Loss", "Loss", "loss", "Brier")
  cindex_candidates <- c("CIndex_pooled", "CIndex_foldaverage", "CIndex", "cindex", "AUC")
  candidates <- if (loss_type) loss_candidates else cindex_candidates

  metric_col <- NULL
  for (nm in candidates) {
    if (nm %in% names(df)) {
      metric_col <- nm
      break
    }
  }
  if (is.null(metric_col)) {
    num_cols <- names(df)[vapply(df, is.numeric, logical(1))]
    num_cols <- setdiff(num_cols, c("eta", "lambda"))
    if (length(num_cols) == 0L) {
      stop("Could not detect metric column in CV results.", call. = FALSE)
    }
    metric_col <- num_cols[length(num_cols)]
  }

  df$eta <- as.numeric(df$eta)
  df <- df[order(df$eta), , drop = FALSE]
  df$metric <- as.numeric(df[[metric_col]])

  if (!any(df$eta == 0)) {
    idx0 <- which.min(abs(df$eta - 0))
  } else {
    idx0 <- which(df$eta == 0)[1]
  }
  baseline_val <- df$metric[idx0]
  baseline_eta <- df$eta[idx0]

  if (loss_type) {
    opt_idx <- which.min(df$metric)
  } else {
    opt_idx <- which.max(df$metric)
  }
  opt_eta <- df$eta[opt_idx]

  xmin <- min(df$eta, na.rm = TRUE)
  xmax <- max(df$eta, na.rm = TRUE)

  y_all <- c(df$metric, baseline_val)
  ylow  <- min(y_all, na.rm = TRUE) * 0.995
  yhigh <- max(y_all, na.rm = TRUE) * 1.005

  g_main <- ggplot(df, aes(x = .data$eta, y = .data$metric, group = 1)) +
    geom_line(linewidth = 1, color = line_color) +
    geom_point(size = 1.3, color = line_color) +
    geom_segment(
      data = data.frame(xmin = xmin, xmax = xmax, y = baseline_val),
      aes(x = .data$xmin, xend = .data$xmax, y = .data$y, yend = .data$y),
      inherit.aes = FALSE, color = baseline_color,
      linetype = "dotted", linewidth = 1
    ) +
    geom_point(
      data = data.frame(eta = baseline_eta, metric = baseline_val),
      aes(x = .data$eta, y = .data$metric),
      inherit.aes = FALSE, color = baseline_color,
      shape = 16, size = 2.4
    ) +
    geom_segment(
      data = data.frame(x = opt_eta),
      aes(x = .data$x, xend = .data$x, y = ylow, yend = yhigh),
      inherit.aes = FALSE, color = "#D95F02",
      linewidth = 1, linetype = "dashed"
    ) +
    labs(x = expression(eta), y = ylab) +
    coord_cartesian(ylim = c(ylow, yhigh)) +
    theme_minimal(base_size = 13) +
    theme(
      panel.grid = element_blank(),
      panel.border = element_blank(),
      axis.line = element_line(color = "black"),
      axis.ticks.length = unit(0.1, "cm"),
      axis.ticks = element_line(color = "black"),
      axis.text = element_text(size = 14),
      legend.position = "none"
    )

  legend_df <- data.frame(
    Method = factor(c("Integrated", "Internal"),
                    levels = c("Integrated", "Internal")),
    x = 0, y = 0
  )

  g_legend <- ggplot(legend_df, aes(x = .data$x, y = .data$y, color = .data$Method)) +
    geom_line(aes(linetype = .data$Method), linewidth = 1) +
    scale_color_manual(values = c("Integrated" = line_color, "Internal" = baseline_color)) +
    scale_linetype_manual(values = c("Integrated" = "solid", "Internal" = "dotted")) +
    theme_void(base_size = 13) +
    theme(
      legend.position = "top",
      legend.title = element_blank(),
      legend.text = element_text(size = 14),
      legend.key.width = unit(1.2, "lines"),
      legend.key.height = unit(0.6, "lines")
    ) +
    guides(
      color = guide_legend(
        keywidth = 1.2, keyheight = 0.4,
        override.aes = list(
          linetype = c("solid", "dotted"),
          shape = c(NA, 16),
          linewidth = 1
        )
      ),
      linetype = "none"
    )

  leg <- cowplot::get_legend(g_legend)

  cowplot::plot_grid(
    leg,
    g_main,
    ncol = 1,
    rel_heights = c(0.08, 1)
  )
}
