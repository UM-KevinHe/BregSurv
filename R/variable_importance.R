#' Bootstrap Variable Importance via Selection Frequency
#'
#' Performs bootstrap resampling and refits the CoxKL elastic-net/LASSO CV procedure
#' B times, then summarizes each variable's selection frequency (proportion of times
#' the variable is selected with nonzero coefficient in the best model).
#'
#' @param z Numeric covariate matrix/data.frame (n x p). If a data.frame is provided,
#'   it will be converted to a numeric matrix via \code{as.matrix(z)}.
#' @param delta Numeric vector of event indicators.
#' @param time Numeric vector of observed times.
#' @param stratum Optional stratum vector. Default NULL.
#' @param RS Optional external risk scores. Default NULL.
#' @param beta Optional numeric vector of external coefficients. Default NULL. It is
#'   forwarded to \code{\link{cv.coxkl_enet}}, which aligns it: if \code{beta} is
#'   named, names are matched against \code{colnames(z)}, covariates absent from
#'   \code{beta} are set to 0 (with a message) and the vector is reordered. An
#'   unnamed \code{beta} is aligned positionally and must have length
#'   \code{ncol(z)}. See \code{\link{align_beta}}.
#' @param etas Numeric vector of non-negative candidate eta values. Must be finite
#'   and \eqn{\ge 0}; this is validated by \code{\link{cv.coxkl_enet}}.
#' @param B Integer. Number of bootstrap replications. Default is 10.
#' @param nonzero_tol Numeric tolerance for defining "selected". Default 1e-10.
#' @param seed Optional integer seed for reproducibility.
#' @param message Logical. Whether to print progress messages. Default FALSE.
#' @param ncores Integer. Number of parallel cores. Default 1 (sequential execution).
#' @param ... Additional arguments passed to \code{cv.coxkl_enet()} (e.g., \code{alpha},
#'   \code{lambda}, \code{nlambda}, \code{lambda.min.ratio}, \code{nfolds},
#'   \code{cv.criteria}, \code{c_index_stratum}, etc.).
#'
#' @return An object of class "variable_importance" with fields:
#' \describe{
#'   \item{freq}{Named numeric vector of selection frequencies (length p).}
#'   \item{count}{Named integer vector of selection counts (length p).}
#'   \item{B}{Number of bootstrap replications.}
#'   \item{nonzero_tol}{The tolerance used to define "selected".}
#'   \item{call}{Matched call.}
#' }
#'
#' @export
variable_importance <- function(
    z, delta, time, stratum = NULL, RS = NULL, beta = NULL,
    etas,
    B = 10,
    nonzero_tol = 1e-10,
    seed = NULL,
    message = FALSE,
    ncores = 1,
    ...
) {
  if (is.data.frame(z)) z <- as.matrix(z)
  if (!is.matrix(z)) stop("z must be a matrix or a data.frame convertible to a matrix.", call. = FALSE)
  storage.mode(z) <- "double"
  if (!is.numeric(z)) stop("z must be numeric after conversion.", call. = FALSE)
  if (anyNA(z)) stop("z contains NA values. Please impute or remove missing values before fitting.", call. = FALSE)
  n <- nrow(z)
  p <- ncol(z)
  if (length(delta) != n) stop("delta length must match nrow(z).", call. = FALSE)
  if (length(time) != n) stop("time length must match nrow(z).", call. = FALSE)
  if (!is.null(stratum) && length(stratum) != n) stop("stratum length must match nrow(z).", call. = FALSE)
  if (B < 1) stop("B must be >= 1.", call. = FALSE)
  var_names <- colnames(z)
  if (is.null(var_names)) var_names <- paste0("V", seq_len(p))

  ncores <- max(1L, as.integer(ncores))

  # Capture ... for passing to workers
  dots <- list(...)

  # Define worker function
  boot_one <- function(b, z, delta, time, stratum, RS, beta, etas, var_names, p, nonzero_tol, seed, dots) {
    if (!is.null(seed)) set.seed(seed + b)
    idx <- sample.int(nrow(z), size = nrow(z), replace = TRUE)
    cv_fit <- do.call(cv.coxkl_enet, c(
      list(
        z = z[idx, , drop = FALSE],
        delta = delta[idx],
        time = time[idx],
        stratum = if (is.null(stratum)) NULL else stratum[idx],
        RS = RS,
        beta = beta,
        etas = etas,
        message = FALSE,
        seed = if (is.null(seed)) NULL else (seed + b)
      ),
      dots
    ))
    bhat <- cv_fit$best$best_beta
    if (is.null(names(bhat))) names(bhat) <- var_names
    if (!all(var_names %in% names(bhat))) {
      tmp <- setNames(rep(0, p), var_names)
      tmp[names(bhat)] <- bhat
      bhat <- tmp
    } else {
      bhat <- bhat[var_names]
    }
    as.integer(abs(bhat) > nonzero_tol)
  }

  if (message) cat("Running", B, "bootstrap replications on", ncores, "core(s)...\n")

  if (ncores == 1L) {
    # Sequential execution with progress bar
    if (message) pb <- txtProgressBar(min = 0, max = B, style = 3, width = 30)
    results <- vector("list", B)
    for (b in seq_len(B)) {
      results[[b]] <- boot_one(b, z, delta, time, stratum, RS, beta, etas, var_names, p, nonzero_tol, seed, dots)
      if (message) setTxtProgressBar(pb, b)
    }
    if (message) close(pb)
  } else {
    # Parallel execution
    cl <- parallel::makeCluster(ncores)
    on.exit(parallel::stopCluster(cl), add = TRUE)

    # Set up parallel RNG
    if (!is.null(seed)) {
      RNGkind("L'Ecuyer-CMRG")
      set.seed(seed)
      parallel::clusterSetRNGStream(cl, seed)
    }

    results <- parallel::parLapply(
      cl, seq_len(B), boot_one,
      z = z, delta = delta, time = time, stratum = stratum,
      RS = RS, beta = beta, etas = etas, var_names = var_names,
      p = p, nonzero_tol = nonzero_tol, seed = seed, dots = dots
    )
  }

  # Aggregate counts
  counts <- setNames(integer(p), var_names)
  for (sel in results) {
    counts <- counts + sel
  }

  if (message) cat("Done.\n")

  freq <- counts / B
  out <- list(
    freq = freq,
    count = counts,
    B = B,
    nonzero_tol = nonzero_tol,
    call = match.call()
  )
  class(out) <- "variable_importance"
  out
}



#' Plot Variable Importance (Selection Frequency)
#'
#' Plots selection frequencies as a horizontal bar chart, ordered from highest to lowest.
#' By default (threshold = 1), all variables are shown. If threshold != 1, only variables
#' with selection frequency > threshold are shown. If the number of displayed variables
#' exceeds \code{top}, only the top \code{top} variables are plotted.
#'
#' @param x An object of class \code{variable_importance}.
#' @param threshold Numeric between 0 and 1. Default is 1, meaning no threshold filtering.
#'   If not equal to 1, variables with \code{SelectionFreq > threshold} are plotted.
#' @param top Integer. Maximum number of variables to plot. Default is all variables.
#' @param title Character. Plot title. Default "Top variables by selection frequency".
#' @param ... Unused.
#'
#' @return A \code{ggplot} object.
#'
#' @importFrom rlang .data
#' @method plot variable_importance
#' @export
plot.variable_importance <- function(
    x,
    threshold = 1,
    top = length(x$freq),
    title = "Top variables by selection frequency",
    ...
) {
  if (!inherits(x, "variable_importance")) stop("x must be of class 'variable_importance'.")
  if (!requireNamespace("ggplot2", quietly = TRUE)) stop("Package 'ggplot2' is required for plotting.")
  if (!is.numeric(threshold) || length(threshold) != 1L || is.na(threshold) || threshold < 0 || threshold > 1) {
    stop("threshold must be a single number in [0,1].")
  }
  if (!is.numeric(top) || length(top) != 1L || is.na(top) || top < 1) stop("top must be a positive integer.")
  top <- as.integer(top)

  df <- data.frame(
    Variable = names(x$freq),
    SelectionFreq = as.numeric(x$freq),
    stringsAsFactors = FALSE
  )

  if (threshold != 1) {
    df <- df[df$SelectionFreq > threshold, , drop = FALSE]
  }

  if (nrow(df) == 0) {
    stop("No variables to plot under the current threshold.")
  }

  df <- df[order(df$SelectionFreq, decreasing = TRUE), , drop = FALSE]
  if (nrow(df) > top) df <- df[seq_len(top), , drop = FALSE]

  df$Variable <- factor(df$Variable, levels = rev(df$Variable))

  p <- ggplot2::ggplot(df, ggplot2::aes(x = .data$SelectionFreq, y = .data$Variable)) +
    ggplot2::geom_col(width = 0.8) +
    ggplot2::scale_x_continuous(limits = c(0, 1)) +
    ggplot2::labs(
      x = "Selection Frequency",
      y = "Variable",
      title = title
    ) +
    ggplot2::theme_minimal(base_size = 15, base_family = "serif") +
    ggplot2::theme(
      text = ggplot2::element_text(family = "serif"),
      panel.grid = ggplot2::element_blank(),
      axis.line = ggplot2::element_line(color = "black", linewidth = 0.6),
      axis.ticks = ggplot2::element_line(color = "black", linewidth = 0.6),
      axis.text = ggplot2::element_text(size = 12, color = "black"),
      axis.title.x = ggplot2::element_text(size = 14),
      axis.title.y = ggplot2::element_text(size = 14),
      plot.title = ggplot2::element_text(hjust = 0, size = 13)
    )

  p
}

