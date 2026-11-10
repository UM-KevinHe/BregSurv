#' Plot a fitted model: the cross-validation curve, the coefficients, or predicted survival
#'
#' @description
#' Three views of a [cv.bregsurv()] fit:
#' * `type = "cv"`: the cross-validated criterion against the integration weight \eqn{\eta} (each
#'   \eqn{\eta} at its best penalty level under a penalty). The dotted line is your data alone
#'   (\eqn{\eta = 0}) and the red point the selected \eqn{\eta}; a curve that dips below the dotted
#'   line means borrowing helped. The \eqn{\eta} axis is on a pseudo-log scale.
#' * `type = "coefficients"`: for each covariate, the coefficient from your data alone, the external
#'   coefficient and the selected fit; the arrows show where borrowing moved each coefficient.
#' * `type = "survival"`: the predicted survival curves of the subjects in `newz` under the selected
#'   fit: at the end of each interval for a discrete-time target, over `times` for a Cox target (with
#'   the Breslow baseline hazard of the training data).
#'
#' @param x A `cv.bregsurv` fit.
#' @param type `"cv"`, `"coefficients"` or `"survival"`.
#' @param reference For `type = "cv"`: optional named values to draw as horizontal reference lines,
#'   such as the cross-validated loss of the external model used unchanged (see [vvh_loss_fixed()]).
#'   The names label the lines.
#' @param covariates For `type = "coefficients"`: the covariates to show. `NULL` shows all of them, or,
#'   with more than 25, the 25 with the largest coefficients.
#' @param newz,stratum For `type = "survival"`: the covariates of the subjects to draw (a few rows,
#'   with the target's column names) and, for a stratified target, their strata.
#' @param times For `type = "survival"` on a Cox target: the time grid; `NULL` spans the training
#'   follow-up.
#' @param labels For `type = "survival"`: names of the subjects; `NULL` uses the row names of `newz`
#'   or "subject 1", "subject 2", ...
#' @param ... Unused.
#' @return A `ggplot` object.
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' fit <- cv.bregsurv(target_cox(tr$time, tr$status, tr$z),
#'                    release_coef(ExampleData_lowdim$beta_external_fair), divergence = "kl")
#' plot(fit)
#' plot(fit, type = "coefficients")
#' plot(fit, type = "survival", newz = ExampleData_lowdim$test$z[1:3, ])
#' @importFrom rlang .data
#' @export
plot.cv.bregsurv <- function(x, type = c("cv", "coefficients", "survival"), reference = NULL, covariates = NULL,
                             newz = NULL, stratum = NULL, times = NULL, labels = NULL, ...) {
  type <- match.arg(type)
  switch(type, cv = .plot_cv_bregsurv(x, reference), coefficients = .plot_coef_bregsurv(x, covariates),
         survival = .plot_surv_bregsurv(x, newz, stratum, times, labels))
}

.bs_col <- c(curve = "#2F6690", selected = "#C8553D", base = "#55636D", reference = "#A87A2A")

.theme_bregsurv <- function() {
  ggplot2::theme_minimal(base_size = 12) +
    ggplot2::theme(panel.grid.minor = ggplot2::element_blank(),
                   panel.grid.major = ggplot2::element_line(colour = "#E4E7EA", linewidth = 0.35),
                   axis.line = ggplot2::element_line(colour = "#9AA3AA", linewidth = 0.35),
                   axis.ticks = ggplot2::element_line(colour = "#9AA3AA", linewidth = 0.35),
                   plot.title = ggplot2::element_text(face = "bold", size = 12.5),
                   plot.subtitle = ggplot2::element_text(colour = "#55636D"),
                   legend.position = "top", legend.justification = "left")
}

.criterion_label <- function(criterion) {
  switch(criterion,
         "V&VH" = "Cross-validated loss (partial likelihood)",
         "LinPred" = "Cross-validated loss (linear predictor)",
         "CIndex_pooled" = "Cross-validated C-index",
         "CIndex_foldaverage" = "Cross-validated C-index (fold average)",
         "loss" = "Cross-validated loss (negative log-likelihood)",
         "AUC" = "Cross-validated AUC",
         "CIndex" = "Cross-validated C-index",
         "Brier" = "Cross-validated Brier score",
         "Cross-validated criterion")
}

.eta_breaks <- function(etas) {
  pos <- etas[etas > 0]
  if (!length(pos)) return(0)
  b <- c(0, 10^seq(floor(log10(min(pos))), ceiling(log10(max(pos)))))
  b[b <= max(etas) * 1.0001]
}

.eta_labels <- function(b) vapply(b, function(v) {
  if (v == 0) "0" else if (v >= 1e4 || v < 1e-3) format(v, scientific = TRUE)
  else format(v, scientific = FALSE, drop0trailing = TRUE, trim = TRUE)
}, character(1))

.plot_cv_bregsurv <- function(x, reference) {
  df <- x$path
  if (is.null(df) || !nrow(df)) stop("This fit has no cross-validation path to plot.", call. = FALSE)
  df <- df[is.finite(df$value), , drop = FALSE]
  df <- df[order(df$eta), , drop = FALSE]
  if (nrow(df) < 2) stop("The cross-validation path has a single integration weight; there is no curve to plot.",
                         call. = FALSE)
  pos <- df$eta[df$eta > 0]
  trans <- scales::pseudo_log_trans(sigma = if (length(pos)) min(pos) / 2 else 1, base = 10)
  hl <- data.frame(value = numeric(0), label = character(0), kind = character(0))
  if (any(df$eta == 0)) hl <- rbind(hl, data.frame(value = df$value[df$eta == 0][1], label = "your data alone",
                                                   kind = "base"))
  if (!is.null(reference)) {
    if (is.null(names(reference))) names(reference) <- paste("reference", seq_along(reference))
    hl <- rbind(hl, data.frame(value = as.numeric(reference), label = names(reference), kind = "reference"))
  }
  sel <- data.frame(eta = x$eta, value = x$value)
  title <- paste0(.divergence_title(x$divergence), if (x$penalty != "none") paste0(", ", x$penalty, " penalty"))
  subtitle <- bquote("selected " * eta == .(signif(x$eta, 3)) * ",  cross-validated value " * .(signif(x$value, 4)))
  g <- ggplot2::ggplot(df, ggplot2::aes(x = .data$eta, y = .data$value))
  if (nrow(hl)) {
    g <- g + ggplot2::geom_hline(data = hl, ggplot2::aes(yintercept = .data$value, colour = .data$kind),
                                 linetype = "dotted", linewidth = 0.7, show.legend = FALSE) +
      ggplot2::annotate("text", x = max(df$eta), y = hl$value, label = hl$label, hjust = 1, vjust = -0.45,
                        size = 3.3, colour = unname(.bs_col[hl$kind]))
  }
  g + ggplot2::geom_line(colour = .bs_col[["curve"]], linewidth = 0.9) +
    ggplot2::geom_point(colour = .bs_col[["curve"]], size = 1.3) +
    ggplot2::geom_vline(xintercept = x$eta, colour = .bs_col[["selected"]], linetype = "dashed", linewidth = 0.45) +
    ggplot2::geom_point(data = sel, colour = .bs_col[["selected"]], size = 3.2) +
    ggplot2::scale_colour_manual(values = .bs_col, guide = "none") +
    .eta_scale(trans, .eta_breaks(df$eta)) +
    ggplot2::labs(x = expression("integration weight " * eta), y = .criterion_label(x$criterion),
                  title = title, subtitle = subtitle) +
    .theme_bregsurv()
}

## ggplot2 renamed `trans` to `transform` in 3.5.0
.eta_scale <- function(trans, breaks) {
  if (utils::packageVersion("ggplot2") >= "3.5.0")
    ggplot2::scale_x_continuous(transform = trans, breaks = breaks, labels = .eta_labels)
  else ggplot2::scale_x_continuous(trans = trans, breaks = breaks, labels = .eta_labels)
}

.divergence_title <- function(d) switch(d, composite = "Composite likelihood", mahalanobis = "Mahalanobis distance",
                                        kl = "Kullback-Leibler divergence", none = "Your data alone")

.plot_coef_bregsurv <- function(x, covariates) {
  if (is.null(x$coefficients)) stop("A neural target has no coefficients to plot.", call. = FALSE)
  sel <- x$coefficients
  own <- x$coefficients_target_only
  ext <- x$coefficients_external
  vars <- names(sel)
  if (!is.null(covariates)) {
    vars <- intersect(as.character(covariates), vars)
    if (!length(vars)) stop("None of 'covariates' is a covariate of the fit.", call. = FALSE)
  } else if (length(vars) > 25) {
    size <- pmax(abs(sel), if (is.null(ext)) 0 else abs(ext), if (is.null(own)) 0 else abs(own))
    vars <- vars[vars %in% names(sort(size, decreasing = TRUE))[1:25]]
  }
  lab_own <- "your data alone"
  lab_ext <- "external"
  lab_sel <- paste0("selected (eta = ", signif(x$eta, 3), ")")
  rows <- list(data.frame(covariate = vars, source = lab_sel, value = unname(sel[vars])))
  if (!is.null(own)) rows <- c(rows, list(data.frame(covariate = vars, source = lab_own, value = unname(own[vars]))))
  if (!is.null(ext)) rows <- c(rows, list(data.frame(covariate = vars, source = lab_ext, value = unname(ext[vars]))))
  df <- do.call(rbind, rows)
  lev <- c(lab_own, lab_ext, lab_sel)
  df$source <- factor(df$source, levels = lev[lev %in% df$source])
  df$covariate <- factor(df$covariate, levels = rev(vars))
  cols <- stats::setNames(c(.bs_col[["base"]], .bs_col[["reference"]], .bs_col[["curve"]]), lev)
  shapes <- stats::setNames(c(1, 17, 16), lev)
  g <- ggplot2::ggplot(df, ggplot2::aes(x = .data$value, y = .data$covariate)) +
    ggplot2::geom_vline(xintercept = 0, colour = "#B9C0C6", linewidth = 0.4)
  if (!is.null(own)) {
    seg <- data.frame(covariate = factor(vars, levels = rev(vars)), from = unname(own[vars]), to = unname(sel[vars]))
    seg <- seg[abs(seg$to - seg$from) > 1e-8, , drop = FALSE]
    if (nrow(seg)) g <- g + ggplot2::geom_segment(data = seg, ggplot2::aes(x = .data$from, xend = .data$to,
                                                                           y = .data$covariate, yend = .data$covariate),
                                                  inherit.aes = FALSE, colour = "#8FA3B3", linewidth = 0.5,
                                                  arrow = grid::arrow(length = grid::unit(0.14, "cm"), type = "closed"))
  }
  g + ggplot2::geom_point(ggplot2::aes(colour = .data$source, shape = .data$source), size = 2.6, stroke = 0.9) +
    ggplot2::scale_colour_manual(values = cols) +
    ggplot2::scale_shape_manual(values = shapes) +
    ggplot2::labs(x = "coefficient", y = NULL, colour = NULL, shape = NULL,
                  title = paste0("What borrowing did (", .divergence_title(x$divergence), ")")) +
    .theme_bregsurv()
}

.plot_surv_bregsurv <- function(x, newz, stratum, times, labels) {
  if (is.null(newz)) stop("type = \"survival\" needs 'newz', the covariates of the subjects to draw.", call. = FALSE)
  newz <- .as_z(newz, "newz")
  if (nrow(newz) > 12) stop("Draw at most 12 subjects at a time.", call. = FALSE)
  if (is.null(labels)) {
    rn <- rownames(newz)
    labels <- if (is.null(rn)) paste("subject", seq_len(nrow(newz))) else
      if (all(grepl("^[0-9]+$", rn))) paste("subject", rn) else rn
  }
  if (length(labels) != nrow(newz)) stop("'labels' must name every row of 'newz'.", call. = FALSE)
  tt <- x$target
  if (tt$type == "ncc") stop("A nested case-control target has no survival curve.", call. = FALSE)
  if (tt$type == "discrete") {
    S <- stats::predict(x, newz, stratum = stratum, type = "survival")
    grid_t <- 0:ncol(S)
    S <- cbind(1, S)
    xlab <- "interval"
  } else {
    if (is.null(times)) times <- seq(0, max(x$training$time), length.out = 200)
    grid_t <- sort(unique(c(0, times)))
    S <- stats::predict(x, newz, stratum = stratum, type = "survival", times = grid_t)
    xlab <- "time"
  }
  df <- data.frame(subject = factor(rep(labels, times = length(grid_t)), levels = labels),
                   time = rep(grid_t, each = nrow(S)), survival = c(S))
  pal <- c("#2F6690", "#C8553D", "#A87A2A", "#3A7D44", "#7B5EA7", "#55636D")
  g <- ggplot2::ggplot(df, ggplot2::aes(x = .data$time, y = .data$survival, colour = .data$subject)) +
    ggplot2::geom_step(linewidth = 0.85) +
    ggplot2::scale_y_continuous(limits = c(0, 1)) +
    ggplot2::labs(x = xlab, y = "predicted survival", colour = NULL,
                  title = paste0("Predicted survival (", .divergence_title(x$divergence), ")"),
                  subtitle = bquote("selected " * eta == .(signif(x$eta, 3)))) +
    .theme_bregsurv()
  if (tt$type == "discrete") g <- g + ggplot2::geom_point(size = 1.8) + ggplot2::scale_x_continuous(breaks = grid_t)
  if (length(labels) <= length(pal)) g <- g + ggplot2::scale_colour_manual(values = pal[seq_along(labels)])
  g
}
