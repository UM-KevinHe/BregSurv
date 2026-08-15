#' Multi-Source Integration for KL-Integrated Cox Elastic-Net Models
#'
#' Fits multiple KL-integrated Cox elastic-net models on the full data using multiple
#' external sources, and combines the fitted coefficient vectors across sources to
#' produce a single aggregated estimate.
#'
#' Unlike \code{coxkl_enet_bagging()}, this function does not bootstrap the data.
#' Instead, it runs \code{cv.coxkl_enet()} once per external source on the full dataset.
#' The resulting coefficient vectors are then aggregated (by default, averaged) to
#' obtain a combined estimate.
#'
#' @param z Matrix/data.frame of predictors of dimension \code{n x p}.
#' @param delta Event indicator vector.
#' @param time Survival time vector.
#' @param stratum Optional stratum indicator vector for stratified Cox models.
#' @param beta_list A list of external coefficient vectors, one per external source.
#'   Each element is aligned to the internal covariate space independently: if the
#'   element is named, names are matched against \code{colnames(z)}, covariates absent
#'   from that element are set to 0 (with a message) and the vector is reordered, so
#'   different sources may cover different subsets of the internal covariates. An
#'   unnamed element is aligned positionally and must have length \code{p}. A
#'   one-column matrix with row names is accepted as a named vector. See
#'   \code{\link{align_beta}}. If provided, \code{RS_list} should be \code{NULL}.
#' @param RS_list Optional list of external risk score vectors/matrices. Each element
#'   should be conformable with \code{n}. If provided, \code{beta_list} is ignored.
#' @param etas Numeric vector of non-negative integration weights. Must be finite
#'   and \eqn{\ge 0}.
#' @param combine How to combine coefficients across sources. Either \code{"mean"} (default)
#'   or \code{"median"}.
#' @param message Logical indicating whether to print progress.
#' @param seed Optional seed for reproducibility (passed to each CV run with an offset).
#' @param ... Additional arguments passed to \code{cv.coxkl_enet()} (e.g., \code{alpha},
#'   \code{lambda}, \code{nlambda}, \code{lambda.min.ratio}, \code{nfolds},
#'   \code{cv.criteria}, \code{c_index_stratum}, etc.).
#'
#' @return
#' An object of class \code{"coxkl_enet.multi"}, which is a list containing:
#' \itemize{
#'   \item \code{best_beta} — combined coefficient estimate across sources.
#'   \item \code{all_betas} — matrix of dimension \code{p x K_valid} of coefficient vectors
#'     from each successful fit.
#'   \item \code{etas} — the \code{etas} argument exactly as supplied by the caller (raw and
#'     unsorted); each \code{cv.coxkl_enet()} run sorts its own copy internally.
#'   \item \code{K} — total number of external sources provided.
#'   \item \code{valid_sources} — number of successful (non-error) fits used in aggregation.
#'   \item \code{combine} — combination rule used.
#'   \item \code{seed} — seed used (if any).
#'   \item \code{source_fits} — list of the \code{cv.coxkl_enet} fit objects for the valid
#'     sources, in the same order as the columns of \code{all_betas}.
#' }
#'
#' @export
coxkl_enet.multi <- function(
    z, delta, time, stratum = NULL,
    beta_list = NULL, RS_list = NULL,
    etas,
    combine = c("mean", "median"),
    message = FALSE,
    seed = NULL,
    ...
) {
  combine <- match.arg(combine)

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

  check_etas(etas)

  if (!is.null(RS_list)) {
    if (!is.list(RS_list) || length(RS_list) < 1) stop("RS_list must be a non-empty list.", call. = FALSE)
    K <- length(RS_list)
  } else {
    if (!is.list(beta_list) || length(beta_list) < 1) stop("beta_list must be a non-empty list.", call. = FALSE)
    K <- length(beta_list)
    for (k in seq_len(K)) {
      beta_list[[k]] <- align_beta(z, beta_list[[k]], arg = paste0("beta_list[[", k, "]]"))
    }
  }

  stratum_full <- if (is.null(stratum)) rep(1, n) else stratum

  if (message) {
    cat("Fitting integrated models over external sources:\n")
    pb <- txtProgressBar(min = 0, max = K, style = 3, width = 30)
  }

  res_list      <- vector("list", K)  # stores best_beta per source (or NA vector)
  fit_res_list  <- vector("list", K)  # stores full cv.coxkl_enet fit objects

  for (k in seq_len(K)) {
    RS_k   <- NULL
    beta_k <- NULL

    if (!is.null(RS_list)) {
      RS_k <- as.matrix(RS_list[[k]])
      if (nrow(RS_k) != n) stop("Each RS_list element must have nrow equal to nrow(z).", call. = FALSE)
    } else {
      beta_k <- beta_list[[k]]
    }

    fit_res <- tryCatch({
      cv.coxkl_enet(
        z        = z,
        delta    = delta,
        time     = time,
        stratum  = stratum_full,
        RS       = RS_k,
        beta     = beta_k,
        etas     = etas,
        message  = FALSE,
        seed     = if (is.null(seed)) NULL else (seed + k),
        ...
      )
    }, error = function(e) {
      return(NULL)
    })

    if (!is.null(fit_res)) {
      res_list[[k]]     <- as.vector(fit_res$best$best_beta)
      fit_res_list[[k]] <- fit_res   # save full fit object
    } else {
      res_list[[k]]     <- rep(NA_real_, p)
      fit_res_list[k]   <- list(NULL)   # store NULL WITHOUT deleting the element
    }

    if (message) setTxtProgressBar(pb, k)
  }

  if (message) close(pb)

  res_mat    <- do.call(cbind, res_list)
  valid_cols <- !apply(res_mat, 2, function(x) any(is.na(x)))

  if (sum(valid_cols) < K) {
    warning(sprintf(
      "Only %d out of %d external sources produced successful fits.",
      sum(valid_cols), K
    ))
    res_mat      <- res_mat[, valid_cols, drop = FALSE]
    fit_res_list <- fit_res_list[valid_cols]   # keep only valid fits
  }

  if (ncol(res_mat) == 0) stop("No successful fits were obtained.", call. = FALSE)

  if (combine == "mean") {
    combined_beta <- rowMeans(res_mat)
  } else {
    combined_beta <- apply(res_mat, 1, stats::median)
  }

  structure(
    list(
      best_beta    = combined_beta,
      all_betas    = res_mat,
      etas         = etas,
      K            = K,
      seed         = seed,
      valid_sources = sum(valid_cols),
      combine      = combine,
      source_fits  = fit_res_list   # full fit objects for each valid source
    ),
    class = "coxkl_enet.multi"
  )
}







#' Plot Method for Multi-Source KL-Integrated Cox Elastic-Net Models
#'
#' Produces a line plot of model performance (loss or C-index) as a function of
#' the transfer-learning shrinkage parameter \eqn{\eta} for each external source
#' in a \code{coxkl_enet.multi} object. Each source is displayed as a separate
#' line with a distinct color and linetype.
#'
#' @param x An object of class \code{"coxkl_enet.multi"}, as returned by
#'   \code{\link{coxkl_enet.multi}}.
#' @param test_z Numeric matrix of test predictors of dimension
#'   \code{n_test x p}. Required: evaluation is always carried out on test data.
#' @param test_time Numeric vector of test survival times of length
#'   \code{n_test}. Required, together with \code{test_z} and \code{test_delta}.
#' @param test_delta Numeric vector of test event indicators of length
#'   \code{n_test}. Required, together with \code{test_z} and \code{test_time}.
#' @param test_stratum Optional vector of stratum indicators of length
#'   \code{n_test} for stratified Cox models. When \code{NULL} (default), the test
#'   set is evaluated as a single stratum.
#' @param criteria Character string specifying the performance metric to plot.
#'   Either \code{"loss"} (default, negative log partial likelihood scaled by
#'   sample size) or \code{"CIndex"} (Harrell's concordance index).
#' @param ... Currently unused. Reserved for future extensions.
#'
#' @details
#' For each valid source fit stored in \code{x$source_fits}, the function
#' extracts the \code{p x n_eta} coefficient matrix
#' \code{integrated_stat.betahat_best}, where each column corresponds to one
#' value of \eqn{\eta}. It then calls \code{test_eval()} on every column to
#' compute the chosen performance metric, and overlays the resulting curves on
#' a single \pkg{ggplot2} figure.
#'
#' Colors are assigned automatically via \code{\link[scales]{hue_pal}} and
#' linetypes cycle through \code{"solid"}, \code{"dashed"}, \code{"dotdash"},
#' \code{"longdash"}, and \code{"twodash"} to remain distinguishable when
#' printed in grayscale.
#'
#' @return A \code{\link[ggplot2]{ggplot}} object. The plot can be further
#'   customized with standard \pkg{ggplot2} layers and themes.
#'
#' @seealso
#' \code{\link{coxkl_enet.multi}} for fitting the multi-source model,
#' \code{\link{plot.coxkl}} for the analogous plot method for single-source
#' \code{"coxkl"} objects.
#'
#' @examples
#' \dontrun{
#' fit <- coxkl_enet.multi(
#'   z         = z_train,
#'   delta     = delta_train,
#'   time      = time_train,
#'   beta_list = list(beta_ext1, beta_ext2, beta_ext3),
#'   etas      = seq(0, 1, by = 0.1)
#' )
#'
#' # Out-of-sample evaluation on a held-out test set
#' plot(fit,
#'      test_z     = z_test,
#'      test_time  = time_test,
#'      test_delta = delta_test,
#'      criteria   = "loss")
#' }
#'
#' @exportS3Method plot coxkl_enet.multi
plot.coxkl_enet.multi <- function(x, test_z = NULL, test_time = NULL, test_delta = NULL,
                                  test_stratum = NULL, criteria = c("loss", "CIndex"), ...) {
  object <- x
  criteria <- match.arg(criteria)
  if (!inherits(object, "coxkl_enet.multi")) stop("'object' must be of class 'coxkl_enet.multi'.", call. = FALSE)

  source_fits <- object$source_fits
  K <- length(source_fits)

  if (is.null(source_fits)) stop("No 'source_fits' found. Ensure coxkl_enet.multi stores source_fits.", call. = FALSE)

  if (is.null(test_z) || is.null(test_time) || is.null(test_delta)) {
    stop("test_z, test_time and test_delta must be supplied; in-sample evaluation is not available because source fits do not retain training data.",
         call. = FALSE)
  }

  results_list <- lapply(seq_len(K), function(k) {
    fit_k <- source_fits[[k]]
    if (is.null(fit_k)) return(NULL)

    beta_mat_k <- fit_k$integrated_stat.betahat_best  # p x n_eta
    etas_k     <- object$etas

    if (is.null(beta_mat_k) || is.null(etas_k)) return(NULL)

    eval_z       <- test_z
    eval_time    <- test_time
    eval_delta   <- test_delta
    eval_stratum <- test_stratum

    metrics <- sapply(seq_along(etas_k), function(i) {
      as.numeric(test_eval(
        test_z       = eval_z,
        test_delta   = eval_delta,
        test_time    = eval_time,
        test_stratum = eval_stratum,
        betahat      = beta_mat_k[, i],
        criteria     = criteria
      ))
    })

    data.frame(
      eta    = etas_k,
      metric = as.numeric(metrics),
      source = paste0("Source ", k)
    )
  })

  results_df <- do.call(rbind, Filter(Negate(is.null), results_list))

  if (nrow(results_df) == 0) stop("No valid source fits to plot.", call. = FALSE)

  ylab <- if (criteria == "CIndex") "C Index" else "Loss"

  source_levels <- unique(results_df$source)
  n_sources     <- length(source_levels)

  pal <- setNames(scales::hue_pal()(n_sources), source_levels)

  lty_cycle <- c("solid", "dashed", "dotdash", "longdash", "twodash")
  lty_vals  <- setNames(
    rep(lty_cycle, length.out = n_sources),
    source_levels
  )

  p <- ggplot(results_df, aes(
    x        = .data$eta,
    y        = .data$metric,
    color    = .data$source,
    linetype = .data$source,
    group    = .data$source
  )) +
    geom_line(linewidth = 0.6) +
    scale_color_manual(name = "Source", values = pal) +
    scale_linetype_manual(name = "Source", values = lty_vals) +
    labs(x = expression(eta), y = ylab) +
    theme_biometrics_legend() +
    theme(
      legend.position   = "right"
    )

  return(p)
}














