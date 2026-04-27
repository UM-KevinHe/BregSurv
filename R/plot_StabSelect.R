#' Plot Stability Selection Path
#'
#' Generates a visualization of the stability paths. Variables that exceed the 
#' specified probability threshold at any point in the path are highlighted.
#'
#' @param x An object of class \code{StabSelect}.
#' @param threshold Numeric. The selection probability threshold (0 to 1). Variables reaching this frequency are highlighted. Default is 0.75.
#' @param highlight_color Color for variables that are selected (stable). Default is "red".
#' @param background_color Color for variables that are not selected. Default is "gray".
#' @param ... Additional arguments passed to methods.
#'
#' @importFrom reshape2 melt
#' @importFrom ggplot2 ggplot aes geom_line geom_hline scale_x_reverse labs theme_minimal theme element_text element_line element_blank
#' @importFrom dplyr filter
#' @importFrom rlang .data
#' @method plot StabSelect
#' @export
plot.StabSelect <- function(x, threshold = 0.75, highlight_color = "red", background_color = "gray", ...) {
  
  if (!inherits(x, "StabSelect")) {
    stop("Object must be of class 'StabSelect'")
  }
  
  mat <- x$stability_path
  lambda_seq <- x$lambda
  n_var <- nrow(mat)
  var_names <- rownames(mat)
  
  # Identify variables that cross the threshold at least once along the path
  max_freqs <- apply(mat, 1, max)
  selected_indices <- which(max_freqs >= threshold)
  selected_vars <- var_names[selected_indices]
  
  if(is.null(colnames(mat))) colnames(mat) <- seq_len(ncol(mat))
  
  if (requireNamespace("reshape2", quietly = TRUE)) {
    df_long <- reshape2::melt(mat)
    colnames(df_long) <- c("Variable", "Index", "SelectionFreq")
  } else {
    df_long <- data.frame(
      Variable = rep(var_names, times = ncol(mat)),
      SelectionFreq = as.vector(mat),
      Index = rep(seq_len(ncol(mat)), each = n_var)
    )
  }
  
  if(is.factor(df_long$Index)) df_long$Index <- as.numeric(df_long$Index)
  
  df_long$Lambda <- lambda_seq[df_long$Index]
  df_long$Status <- ifelse(df_long$Variable %in% selected_vars, "Selected", "Other")
  
  p <- ggplot2::ggplot(df_long, ggplot2::aes(x = log10(.data$Lambda), y = .data$SelectionFreq, group = .data$Variable)) +
    ggplot2::geom_line(data = dplyr::filter(df_long, .data$Status == "Other"),
                       color = background_color, alpha = 0.5, size = 0.5) +
    ggplot2::geom_line(data = dplyr::filter(df_long, .data$Status == "Selected"),
                       color = highlight_color, size = 0.8) +
    ggplot2::geom_hline(yintercept = threshold, linetype = "dashed", linewidth = 0.6) +
    ggplot2::scale_x_reverse() +
    ggplot2::labs(
      x = expression(log[10](lambda)),
      y = "Selection Frequency",
      title = paste0("Stability Selection Path (Threshold = ", threshold, ")")
    ) +
    ggplot2::theme_minimal(base_size = 15, base_family = "serif") +
    ggplot2::theme(
      text = ggplot2::element_text(family = "serif"),
      panel.grid = ggplot2::element_blank(),
      panel.border = ggplot2::element_blank(),
      axis.line = ggplot2::element_line(color = "black", linewidth = 0.6),
      axis.ticks = ggplot2::element_line(color = "black", linewidth = 0.6),
      axis.text = ggplot2::element_text(size = 12, color = "black"),
      axis.title.x = ggplot2::element_text(size = 14),
      axis.title.y = ggplot2::element_text(size = 14),
      plot.title = ggplot2::element_text(hjust = 0, size = 13)
    )
  
  return(p)
}