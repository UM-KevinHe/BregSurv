#' Plot Validation Results for coxkl Object
#'
#' @description
#' Plots the validation performance (Loss or C-Index) against the tuning parameter \code{eta}.
#' Compares the "Integrated" estimator (solid line) against the "Internal" baseline (dotted line, eta=0).
#'
#' The output of \code{\link{coxkl_ties}} also carries class \code{"coxkl"} and is
#' therefore served by this same method.
#'
#' @param x An object of class \code{"coxkl"}.
#' @param test_z Matrix of test covariates. Optional; see Details.
#' @param test_time Vector of test survival times. Optional; see Details.
#' @param test_delta Vector of test status indicators. Optional; see Details.
#' @param test_stratum Vector of test strata. Optional; see Details.
#' @param criteria Metric to plot: \code{"loss"} or \code{"CIndex"}.
#' @param ... Additional arguments.
#'
#' @details
#' The four \code{test_*} arguments act as a single unit. The training data stored
#' in the fitted object are used for evaluation only when \emph{all four} of
#' \code{test_z}, \code{test_time}, \code{test_delta} and \code{test_stratum} are
#' \code{NULL}. Supplying any one of them selects the external-test path, so
#' leaving \code{test_z} \code{NULL} while passing any of the others does not fall
#' back to the training data -- it produces an error. The one exception is
#' \code{test_time}: on the external-test path, if it alone is omitted all test
#' times are set to 1.
#'
#' @return A \code{ggplot} object.
#'
#' @importFrom ggplot2 ggplot aes geom_line geom_point geom_segment scale_color_manual scale_linetype_manual labs coord_cartesian
#' @importFrom rlang .data
#' @importFrom stats setNames
#' @method plot coxkl
#' @export
#' @examples
#' \dontrun{
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' test_dat_lowdim <- ExampleData_lowdim$test
#' beta_external_lowdim <- ExampleData_lowdim$beta_external_fair
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 50)
#' coxkl_est <- coxkl(z = train_dat_lowdim$z,
#'                    delta = train_dat_lowdim$status,
#'                    time = train_dat_lowdim$time,
#'                    stratum = train_dat_lowdim$stratum,
#'                    beta = beta_external_lowdim,
#'                    etas = eta_list)
#'
#' plot(coxkl_est,
#'      test_z = test_dat_lowdim$z,
#'      test_time = test_dat_lowdim$time,
#'      test_delta = test_dat_lowdim$status,
#'      test_stratum = test_dat_lowdim$stratum,
#'      criteria = "CIndex")
#' }
plot.coxkl <- function(x, test_z = NULL, test_time = NULL, test_delta = NULL,
                       test_stratum = NULL, criteria = c("loss", "CIndex"), ...) {
  object <- x

  criteria <- match.arg(criteria)
  if (!inherits(object, "coxkl")) stop("'object' must be of class 'coxkl'.", call. = FALSE)

  etas <- object$eta
  beta_mat <- object$beta
  z_train <- object$data$z
  time_train <- object$data$time
  delta_train <- object$data$delta
  stratum_train <- object$data$stratum

  using_train <- is.null(test_z) && is.null(test_time) && is.null(test_delta) && is.null(test_stratum)
  if (using_train) {
    test_z <- z_train
    test_time <- time_train
    test_delta <- delta_train
    test_stratum <- stratum_train
  }

  n_eval <- nrow(as.matrix(test_z))

  if (!using_train && is.null(test_time)) {
    test_time <- rep(1, n_eval)
  }

  if (criteria == "loss") {
    if (using_train) {
      metrics <- (-2 * object$likelihood) / n_eval
    } else {
      raw_metrics <- sapply(seq_along(etas), function(i)
        test_eval(
          test_z = test_z,
          test_delta = test_delta,
          test_time = test_time,
          test_stratum = test_stratum,
          betahat = beta_mat[, i],
          criteria = "loss"
        )
      )
      metrics <- as.numeric(raw_metrics)
    }
  } else {
    metrics <- sapply(seq_along(etas), function(i)
      test_eval(
        test_z = test_z,
        test_delta = test_delta,
        test_time = test_time,
        test_stratum = test_stratum,
        betahat = beta_mat[, i],
        criteria = "CIndex"
      )
    )
  }

  idx0 <- which.min(abs(etas - 0))
  x0 <- etas[idx0]
  y0 <- as.numeric(metrics[idx0])
  xmax <- max(etas, na.rm = TRUE)

  df <- data.frame(eta = etas, metric = as.numeric(metrics))
  ylab <- if (criteria == "CIndex") "C Index" else "Loss"

  lbl_integrated <- "Integrated"
  lbl_internal <- "Internal"
  cols <- setNames(c("#7570B3", "#1B9E77"), c(lbl_integrated, lbl_internal))
  ltypes <- setNames(c("solid", "dotted"), c(lbl_integrated, lbl_internal))

  p <- ggplot(df, aes(x = .data$eta, y = .data$metric)) +
    geom_line(aes(color = lbl_integrated, linetype = lbl_integrated), linewidth = 1) +
    geom_point(color = cols[lbl_integrated], size = 2) +
    geom_segment(
      data = data.frame(x0 = x0, y0 = y0, xmax = xmax),
      aes(x = .data$x0, xend = .data$xmax, y = .data$y0, yend = .data$y0,
          color = lbl_internal, linetype = lbl_internal),
      inherit.aes = FALSE, linewidth = 1
    ) +
    geom_point(
      data = data.frame(x0 = x0, y0 = y0),
      aes(x = .data$x0, y = .data$y0),
      inherit.aes = FALSE, color = cols[lbl_internal], shape = 16, size = 3
    ) +
    scale_color_manual(name = NULL, values = cols, breaks = c(lbl_integrated, lbl_internal)) +
    scale_linetype_manual(name = NULL, values = ltypes, breaks = c(lbl_integrated, lbl_internal)) +
    labs(x = expression(eta), y = ylab) +
    theme_biometrics_legend() +
    coord_cartesian(
      ylim = c(min(c(df$metric, y0), na.rm = TRUE) * 0.995,
               max(c(df$metric, y0), na.rm = TRUE) * 1.005)
    )

  return(p)
}

#' Plot Validation Results for coxkl_ridge Object
#'
#' @description
#' Plots the validation performance against the penalty parameter \code{lambda} (on log scale).
#' The optimal lambda is marked with a dashed orange line.
#'
#' @param x An object of class \code{"coxkl_ridge"}.
#' @param test_z Matrix of test covariates. Optional; see Details.
#' @param test_time Vector of test survival times. Optional; see Details.
#' @param test_delta Vector of test status indicators. Optional; see Details.
#' @param test_stratum Vector of test strata. Optional; see Details.
#' @param criteria Metric to plot: \code{"loss"} or \code{"CIndex"}.
#' @param ... Additional arguments.
#'
#' @details
#' The four \code{test_*} arguments act as a single unit. The training data stored
#' in the fitted object are used for evaluation only when \emph{all four} of
#' \code{test_z}, \code{test_time}, \code{test_delta} and \code{test_stratum} are
#' \code{NULL}. Supplying any one of them selects the external-test path, so
#' leaving \code{test_z} \code{NULL} while passing any of the others does not fall
#' back to the training data -- it produces an error. The one exception is
#' \code{test_time}: on the external-test path, if it alone is omitted all test
#' times are set to 1.
#'
#' @return A \code{ggplot} object.
#'
#' @importFrom ggplot2 ggplot aes geom_line geom_point geom_segment scale_x_reverse labs coord_cartesian
#' @importFrom rlang .data
#' @method plot coxkl_ridge
#' @export
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' test_dat_highdim <- ExampleData_highdim$test
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' coxkl_ridge_est <- coxkl_ridge(z = train_dat_highdim$z,
#'                                delta = train_dat_highdim$status,
#'                                time = train_dat_highdim$time,
#'                                stratum = train_dat_highdim$stratum,
#'                                beta = beta_external_highdim,
#'                                eta = 0)
#'
#' plot(coxkl_ridge_est,
#'      test_z = test_dat_highdim$z,
#'      test_time = test_dat_highdim$time,
#'      test_delta = test_dat_highdim$status,
#'      test_stratum = test_dat_highdim$stratum,
#'      criteria = "CIndex")
#' }
plot.coxkl_ridge <- function(x, test_z = NULL, test_time = NULL, test_delta = NULL,
                             test_stratum = NULL, criteria = c("loss", "CIndex"), ...) {
  object <- x

  criteria <- match.arg(criteria)
  if (!inherits(object, "coxkl_ridge")) stop("'object' must be of class 'coxkl_ridge'.", call. = FALSE)

 lambdas <- object$lambda
  beta_mat <- object$beta
  z_train <- object$data$z
  time_train <- object$data$time
  delta_train <- object$data$delta
  stratum_train <- object$data$stratum

  using_train <- is.null(test_z) && is.null(test_time) && is.null(test_delta) && is.null(test_stratum)
  if (using_train) {
    test_z <- z_train
    test_time <- time_train
    test_delta <- delta_train
    test_stratum <- stratum_train
  }

  n_eval <- nrow(as.matrix(test_z))

  if (!using_train && is.null(test_time)) {
    test_time <- rep(1, n_eval)
  }

  if (criteria == "loss") {
    if (using_train) {
      metrics <- (-2 * object$likelihood) / n_eval
    } else {
      raw_metrics <- sapply(seq_along(lambdas), function(i)
        test_eval(
          test_z = test_z,
          test_delta = test_delta,
          test_time = test_time,
          test_stratum = test_stratum,
          betahat = beta_mat[, i],
          criteria = "loss"
        )
      )
      metrics <- as.numeric(raw_metrics)
    }
    opt_idx <- which.min(metrics)
  } else {
    metrics <- sapply(seq_along(lambdas), function(i)
      test_eval(
        test_z = test_z,
        test_delta = test_delta,
        test_time = test_time,
        test_stratum = test_stratum,
        betahat = beta_mat[, i],
        criteria = "CIndex"
      )
    )
    opt_idx <- which.max(metrics)
  }

  df <- data.frame(lambda = lambdas, metric = as.numeric(metrics))
  df <- df[order(df$lambda, decreasing = TRUE), ]

  opt_lambda <- lambdas[opt_idx]
  ylow <- min(df$metric, na.rm = TRUE) * 0.995
  yhigh <- max(df$metric, na.rm = TRUE) * 1.005
  ylab <- if (criteria == "CIndex") "C Index" else "Loss"

  ggplot(df, aes(x = .data$lambda, y = .data$metric)) +
    geom_line(linewidth = 1, color = "#7570B3") +
    geom_point(size = 2, color = "#7570B3") +
    geom_segment(
      data = data.frame(x = opt_lambda),
      aes(x = .data$x, xend = .data$x, y = ylow, yend = yhigh),
      inherit.aes = FALSE, color = "#D95F02", linewidth = 1, linetype = "dashed"
    ) +
    scale_x_reverse(trans = "log10") +
    labs(x = expression(lambda), y = ylab) +
    coord_cartesian(ylim = c(ylow, yhigh)) +
    theme_biometrics()
}

#' Plot Validation Results for coxkl_enet Object
#'
#' @description
#' Plots the validation performance against the penalty parameter \code{lambda} (on log scale).
#' The optimal lambda is marked with a dashed orange line.
#'
#' @param x An object of class \code{"coxkl_enet"}.
#' @param test_z Matrix of test covariates. Optional; see Details.
#' @param test_time Vector of test survival times. Optional; see Details.
#' @param test_delta Vector of test status indicators. Optional; see Details.
#' @param test_stratum Vector of test strata. Optional; see Details.
#' @param criteria Metric to plot: \code{"loss"} or \code{"CIndex"}.
#' @param ... Additional arguments.
#'
#' @details
#' The four \code{test_*} arguments act as a single unit. The training data stored
#' in the fitted object are used for evaluation only when \emph{all four} of
#' \code{test_z}, \code{test_time}, \code{test_delta} and \code{test_stratum} are
#' \code{NULL}. Supplying any one of them selects the external-test path, so
#' leaving \code{test_z} \code{NULL} while passing any of the others does not fall
#' back to the training data -- it produces an error. The one exception is
#' \code{test_time}: on the external-test path, if it alone is omitted all test
#' times are set to 1.
#'
#' @return A \code{ggplot} object.
#'
#' @importFrom ggplot2 ggplot aes geom_line geom_point geom_segment scale_x_reverse labs coord_cartesian
#' @importFrom rlang .data
#' @method plot coxkl_enet
#' @export
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' test_dat_highdim <- ExampleData_highdim$test
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' coxkl_enet_est <- coxkl_enet(z = train_dat_highdim$z,
#'                              delta = train_dat_highdim$status,
#'                              time = train_dat_highdim$time,
#'                              stratum = train_dat_highdim$stratum,
#'                              beta = beta_external_highdim,
#'                              eta = 0)
#'
#' plot(coxkl_enet_est,
#'      test_z = test_dat_highdim$z,
#'      test_time = test_dat_highdim$time,
#'      test_delta = test_dat_highdim$status,
#'      test_stratum = test_dat_highdim$stratum,
#'      criteria = "CIndex")
#' }
plot.coxkl_enet <- function(x, test_z = NULL, test_time = NULL, test_delta = NULL,
                            test_stratum = NULL, criteria = c("loss", "CIndex"), ...) {
  object <- x

  criteria <- match.arg(criteria)
  if (!inherits(object, "coxkl_enet")) stop("'object' must be of class 'coxkl_enet'.", call. = FALSE)

  lambdas <- object$lambda
  beta_mat <- object$beta
  z_train <- object$data$z
  time_train <- object$data$time
  delta_train <- object$data$delta
  stratum_train <- object$data$stratum

  using_train <- is.null(test_z) && is.null(test_time) && is.null(test_delta) && is.null(test_stratum)
  if (using_train) {
    test_z <- z_train
    test_time <- time_train
    test_delta <- delta_train
    test_stratum <- stratum_train
  }

  n_eval <- nrow(as.matrix(test_z))


  if (!using_train && is.null(test_time)) {
    test_time <- rep(1, n_eval)
  }

  if (criteria == "loss") {
    if (using_train) {
      metrics <- (-2 * object$likelihood) / n_eval
    } else {
      raw_metrics <- sapply(seq_along(lambdas), function(i)
        test_eval(
          test_z = test_z,
          test_delta = test_delta,
          test_time = test_time,
          test_stratum = test_stratum,
          betahat = beta_mat[, i],
          criteria = "loss"
        )
      )
      metrics <- as.numeric(raw_metrics)
    }
    opt_idx <- which.min(metrics)
  } else {
    metrics <- sapply(seq_along(lambdas), function(i)
      test_eval(
        test_z = test_z,
        test_delta = test_delta,
        test_time = test_time,
        test_stratum = test_stratum,
        betahat = beta_mat[, i],
        criteria = "CIndex"
      )
    )
    opt_idx <- which.max(metrics)
  }

  df <- data.frame(lambda = lambdas, metric = as.numeric(metrics))
  df <- df[order(df$lambda, decreasing = TRUE), ]

  opt_lambda <- lambdas[opt_idx]
  ylow <- min(df$metric, na.rm = TRUE) * 0.995
  yhigh <- max(df$metric, na.rm = TRUE) * 1.005
  ylab <- if (criteria == "CIndex") "C Index" else "Loss"

  ggplot(df, aes(x = .data$lambda, y = .data$metric)) +
    geom_line(linewidth = 1, color = "#7570B3") +
    geom_point(size = 2, color = "#7570B3") +
    geom_segment(
      data = data.frame(x = opt_lambda),
      aes(x = .data$x, xend = .data$x, y = ylow, yend = yhigh),
      inherit.aes = FALSE, color = "#D95F02", linewidth = 1, linetype = "dashed"
    ) +
    scale_x_reverse(trans = "log10") +
    labs(x = expression(lambda), y = ylab) +
    coord_cartesian(ylim = c(ylow, yhigh)) +
    theme_biometrics()
}

#' Plot Validation Results for cox_MDTL Object
#'
#' @description
#' Plots the validation performance against \code{eta} for MDTL estimates.
#' Compares the "Integrated" estimator (solid line) against the "Internal" baseline (dotted line, eta=0).
#'
#' @param x An object of class \code{"cox_MDTL"}.
#' @param test_z Matrix of test covariates. Optional; see Details.
#' @param test_time Vector of test survival times. Optional; see Details.
#' @param test_delta Vector of test status indicators. Optional; see Details.
#' @param test_stratum Vector of test strata. Optional; see Details.
#' @param criteria Metric to plot: \code{"loss"} or \code{"CIndex"}.
#' @param ... Additional arguments.
#'
#' @details
#' The four \code{test_*} arguments act as a single unit. The training data stored
#' in the fitted object are used for evaluation only when \emph{all four} of
#' \code{test_z}, \code{test_time}, \code{test_delta} and \code{test_stratum} are
#' \code{NULL}. Supplying any one of them selects the external-test path, so
#' leaving \code{test_z} \code{NULL} while passing any of the others does not fall
#' back to the training data -- it produces an error. The one exception is
#' \code{test_time}: on the external-test path, if it alone is omitted all test
#' times are set to 1.
#'
#' @return A \code{ggplot} object.
#'
#' @importFrom ggplot2 ggplot aes geom_line geom_point geom_segment scale_color_manual scale_linetype_manual labs coord_cartesian
#' @importFrom rlang .data
#' @importFrom stats setNames
#' @method plot cox_MDTL
#' @export
#' @examples
#' \dontrun{
#' data(ExampleData_lowdim)
#' train_dat_lowdim <- ExampleData_lowdim$train
#' test_dat_lowdim <- ExampleData_lowdim$test
#' beta_external_lowdim <- ExampleData_lowdim$beta_external_fair
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 5)
#' cox_MDTL_est <- cox_MDTL(z = train_dat_lowdim$z,
#'                          delta = train_dat_lowdim$status,
#'                          time = train_dat_lowdim$time,
#'                          beta = beta_external_lowdim,
#'                          Q = NULL,
#'                          etas = eta_list)
#'
#' plot(cox_MDTL_est,
#'      test_z = test_dat_lowdim$z,
#'      test_time = test_dat_lowdim$time,
#'      test_delta = test_dat_lowdim$status,
#'      test_stratum = test_dat_lowdim$stratum,
#'      criteria = "CIndex")
#' }
plot.cox_MDTL <- function(x, test_z = NULL, test_time = NULL, test_delta = NULL,
                          test_stratum = NULL, criteria = c("loss", "CIndex"), ...) {
  object <- x

  criteria <- match.arg(criteria)
  if (!inherits(object, "cox_MDTL")) stop("'object' must be of class 'cox_MDTL'.", call. = FALSE)

  etas <- object$eta
  beta_mat <- object$beta
  z_train <- object$data$z
  time_train <- object$data$time
  delta_train <- object$data$delta
  stratum_train <- object$data$stratum

  using_train <- is.null(test_z) && is.null(test_time) && is.null(test_delta) && is.null(test_stratum)
  if (using_train) {
    test_z <- z_train
    test_time <- time_train
    test_delta <- delta_train
    test_stratum <- stratum_train
  }

  n_eval <- nrow(as.matrix(test_z))


  if (!using_train && is.null(test_time)) {
    test_time <- rep(1, n_eval)
  }

  if (criteria == "loss") {
    if (using_train) {
      metrics <- (-2 * object$likelihood) / n_eval
    } else {
      raw_metrics <- sapply(seq_along(etas), function(i)
        test_eval(
          test_z = test_z,
          test_delta = test_delta,
          test_time = test_time,
          test_stratum = test_stratum,
          betahat = beta_mat[, i],
          criteria = "loss"
        )
      )
      metrics <- as.numeric(raw_metrics)
    }
  } else {
    metrics <- sapply(seq_along(etas), function(i)
      test_eval(
        test_z = test_z,
        test_delta = test_delta,
        test_time = test_time,
        test_stratum = test_stratum,
        betahat = beta_mat[, i],
        criteria = "CIndex"
      )
    )
  }

  idx0 <- which.min(abs(etas - 0))
  x0 <- etas[idx0]
  y0 <- as.numeric(metrics[idx0])
  xmax <- max(etas, na.rm = TRUE)

  df <- data.frame(eta = etas, metric = as.numeric(metrics))
  ylab <- if (criteria == "CIndex") "C Index" else "Loss"

  lbl_integrated <- "Integrated"
  lbl_internal <- "Internal"
  cols <- setNames(c("#7570B3", "#1B9E77"), c(lbl_integrated, lbl_internal))
  ltypes <- setNames(c("solid", "dotted"), c(lbl_integrated, lbl_internal))

  p <- ggplot(df, aes(x = .data$eta, y = .data$metric)) +
    geom_line(aes(color = lbl_integrated, linetype = lbl_integrated), linewidth = 1) +
    geom_point(color = cols[lbl_integrated], size = 2) +
    geom_segment(
      data = data.frame(x0 = x0, y0 = y0, xmax = xmax),
      aes(x = .data$x0, xend = .data$xmax, y = .data$y0, yend = .data$y0,
          color = lbl_internal, linetype = lbl_internal),
      inherit.aes = FALSE, linewidth = 1
    ) +
    geom_point(
      data = data.frame(x0 = x0, y0 = y0),
      aes(x = .data$x0, y = .data$y0),
      inherit.aes = FALSE, color = cols[lbl_internal], shape = 16, size = 3
    ) +
    scale_color_manual(name = NULL, values = cols, breaks = c(lbl_integrated, lbl_internal)) +
    scale_linetype_manual(name = NULL, values = ltypes, breaks = c(lbl_integrated, lbl_internal)) +
    labs(x = expression(eta), y = ylab) +
    theme_biometrics_legend() +
    coord_cartesian(
      ylim = c(min(c(df$metric, y0), na.rm = TRUE) * 0.995,
               max(c(df$metric, y0), na.rm = TRUE) * 1.005)
    )

  return(p)
}

#' Plot Validation Results for cox_MDTL_ridge Object
#'
#' @description
#' Plots the validation performance against \code{lambda} for MDTL ridge estimates.
#'
#' @param x An object of class \code{"cox_MDTL_ridge"}.
#' @param test_z Matrix of test covariates. Optional; see Details.
#' @param test_time Vector of test survival times. Optional; see Details.
#' @param test_delta Vector of test status indicators. Optional; see Details.
#' @param test_stratum Vector of test strata. Optional; see Details.
#' @param criteria Metric to plot: \code{"loss"} or \code{"CIndex"}.
#' @param ... Additional arguments.
#'
#' @details
#' The four \code{test_*} arguments act as a single unit. The training data stored
#' in the fitted object are used for evaluation only when \emph{all four} of
#' \code{test_z}, \code{test_time}, \code{test_delta} and \code{test_stratum} are
#' \code{NULL}. Supplying any one of them selects the external-test path, so
#' leaving \code{test_z} \code{NULL} while passing any of the others does not fall
#' back to the training data -- it produces an error. The one exception is
#' \code{test_time}: on the external-test path, if it alone is omitted all test
#' times are set to 1.
#'
#' @return A \code{ggplot} object.
#'
#' @importFrom ggplot2 ggplot aes geom_line geom_point geom_segment scale_x_reverse labs coord_cartesian
#' @importFrom rlang .data
#' @method plot cox_MDTL_ridge
#' @export
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' test_dat_highdim <- ExampleData_highdim$test
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' mdtl_ridge_est <- cox_MDTL_ridge(z = train_dat_highdim$z,
#'                                  delta = train_dat_highdim$status,
#'                                  time = train_dat_highdim$time,
#'                                  beta = beta_external_highdim,
#'                                  Q = NULL,
#'                                  eta = 0)
#'
#' plot(mdtl_ridge_est,
#'      test_z = test_dat_highdim$z,
#'      test_time = test_dat_highdim$time,
#'      test_delta = test_dat_highdim$status,
#'      criteria = "CIndex")
#' }
plot.cox_MDTL_ridge <- function(x, test_z = NULL, test_time = NULL, test_delta = NULL,
                                test_stratum = NULL, criteria = c("loss", "CIndex"), ...) {
  object <- x

  criteria <- match.arg(criteria)
  if (!inherits(object, "cox_MDTL_ridge")) stop("'object' must be of class 'cox_MDTL_ridge'.", call. = FALSE)

  lambdas <- object$lambda
  beta_mat <- object$beta
  z_train <- object$data$z
  time_train <- object$data$time
  delta_train <- object$data$delta
  stratum_train <- object$data$stratum

  using_train <- is.null(test_z) && is.null(test_time) && is.null(test_delta) && is.null(test_stratum)
  if (using_train) {
    test_z <- z_train
    test_time <- time_train
    test_delta <- delta_train
    test_stratum <- stratum_train
  }

  n_eval <- nrow(as.matrix(test_z))


  if (!using_train && is.null(test_time)) {
    test_time <- rep(1, n_eval)
  }

  if (criteria == "loss") {
    if (using_train) {
      metrics <- (-2 * object$likelihood) / n_eval
    } else {
      raw_metrics <- sapply(seq_along(lambdas), function(i)
        test_eval(
          test_z = test_z,
          test_delta = test_delta,
          test_time = test_time,
          test_stratum = test_stratum,
          betahat = beta_mat[, i],
          criteria = "loss"
        )
      )
      metrics <- as.numeric(raw_metrics)
    }
    opt_idx <- which.min(metrics)
  } else {
    metrics <- sapply(seq_along(lambdas), function(i)
      test_eval(
        test_z = test_z,
        test_delta = test_delta,
        test_time = test_time,
        test_stratum = test_stratum,
        betahat = beta_mat[, i],
        criteria = "CIndex"
      )
    )
    opt_idx <- which.max(metrics)
  }

  df <- data.frame(lambda = lambdas, metric = as.numeric(metrics))
  df <- df[order(df$lambda, decreasing = TRUE), ]

  opt_lambda <- lambdas[opt_idx]
  ylow <- min(df$metric, na.rm = TRUE) * 0.995
  yhigh <- max(df$metric, na.rm = TRUE) * 1.005
  ylab <- if (criteria == "CIndex") "C Index" else "Loss"

  ggplot(df, aes(x = .data$lambda, y = .data$metric)) +
    geom_line(linewidth = 1, color = "#7570B3") +
    geom_point(size = 2, color = "#7570B3") +
    geom_segment(
      data = data.frame(x = opt_lambda),
      aes(x = .data$x, xend = .data$x, y = ylow, yend = yhigh),
      inherit.aes = FALSE, color = "#D95F02", linewidth = 1, linetype = "dashed"
    ) +
    scale_x_reverse(trans = "log10") +
    labs(x = expression(lambda), y = ylab) +
    coord_cartesian(ylim = c(ylow, yhigh)) +
    theme_biometrics()
}

#' Plot Validation Results for cox_MDTL_enet Object
#'
#' @description
#' Plots the validation performance against \code{lambda} for MDTL elastic net estimates.
#'
#' @param x An object of class \code{"cox_MDTL_enet"}.
#' @param test_z Matrix of test covariates. Optional; see Details.
#' @param test_time Vector of test survival times. Optional; see Details.
#' @param test_delta Vector of test status indicators. Optional; see Details.
#' @param test_stratum Vector of test strata. Optional; see Details.
#' @param criteria Metric to plot: \code{"loss"} or \code{"CIndex"}.
#' @param ... Additional arguments.
#'
#' @details
#' The four \code{test_*} arguments act as a single unit. The training data stored
#' in the fitted object are used for evaluation only when \emph{all four} of
#' \code{test_z}, \code{test_time}, \code{test_delta} and \code{test_stratum} are
#' \code{NULL}. Supplying any one of them selects the external-test path, so
#' leaving \code{test_z} \code{NULL} while passing any of the others does not fall
#' back to the training data -- it produces an error. The one exception is
#' \code{test_time}: on the external-test path, if it alone is omitted all test
#' times are set to 1.
#'
#' @return A \code{ggplot} object.
#'
#' @importFrom ggplot2 ggplot aes geom_line geom_point geom_segment scale_x_reverse labs coord_cartesian
#' @importFrom rlang .data
#' @method plot cox_MDTL_enet
#' @export
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim <- ExampleData_highdim$train
#' test_dat_highdim <- ExampleData_highdim$test
#' beta_external_highdim <- ExampleData_highdim$beta_external
#'
#' cox_MDTL_enet_est <- cox_MDTL_enet(z = train_dat_highdim$z,
#'                                    delta = train_dat_highdim$status,
#'                                    time = train_dat_highdim$time,
#'                                    beta = beta_external_highdim,
#'                                    Q = NULL,
#'                                    eta = 0)
#'
#' plot(cox_MDTL_enet_est,
#'      test_z = test_dat_highdim$z,
#'      test_time = test_dat_highdim$time,
#'      test_delta = test_dat_highdim$status,
#'      test_stratum = test_dat_highdim$stratum,
#'      criteria = "CIndex")
#' }
plot.cox_MDTL_enet <- function(x, test_z = NULL, test_time = NULL, test_delta = NULL,
                               test_stratum = NULL, criteria = c("loss", "CIndex"), ...) {
  object <- x

  criteria <- match.arg(criteria)
  if (!inherits(object, "cox_MDTL_enet")) stop("'object' must be of class 'cox_MDTL_enet'.", call. = FALSE)

  lambdas <- object$lambda
  beta_mat <- object$beta
  z_train <- object$data$z
  time_train <- object$data$time
  delta_train <- object$data$delta
  stratum_train <- object$data$stratum

  using_train <- is.null(test_z) && is.null(test_time) && is.null(test_delta) && is.null(test_stratum)
  if (using_train) {
    test_z <- z_train
    test_time <- time_train
    test_delta <- delta_train
    test_stratum <- stratum_train
  }

  n_eval <- nrow(as.matrix(test_z))


  if (!using_train && is.null(test_time)) {
    test_time <- rep(1, n_eval)
  }

  if (criteria == "loss") {
    if (using_train) {
      metrics <- (-2 * object$likelihood) / n_eval
    } else {
      raw_metrics <- sapply(seq_along(lambdas), function(i)
        test_eval(
          test_z = test_z,
          test_delta = test_delta,
          test_time = test_time,
          test_stratum = test_stratum,
          betahat = beta_mat[, i],
          criteria = "loss"
        )
      )
      metrics <- as.numeric(raw_metrics)
    }
    opt_idx <- which.min(metrics)
  } else {
    metrics <- sapply(seq_along(lambdas), function(i)
      test_eval(
        test_z = test_z,
        test_delta = test_delta,
        test_time = test_time,
        test_stratum = test_stratum,
        betahat = beta_mat[, i],
        criteria = "CIndex"
      )
    )
    opt_idx <- which.max(metrics)
  }

  df <- data.frame(lambda = lambdas, metric = as.numeric(metrics))
  df <- df[order(df$lambda, decreasing = TRUE), ]

  opt_lambda <- lambdas[opt_idx]
  ylow <- min(df$metric, na.rm = TRUE) * 0.995
  yhigh <- max(df$metric, na.rm = TRUE) * 1.005
  ylab <- if (criteria == "CIndex") "C Index" else "Loss"

  ggplot(df, aes(x = .data$lambda, y = .data$metric)) +
    geom_line(linewidth = 1, color = "#7570B3") +
    geom_point(size = 2, color = "#7570B3") +
    geom_segment(
      data = data.frame(x = opt_lambda),
      aes(x = .data$x, xend = .data$x, y = ylow, yend = yhigh),
      inherit.aes = FALSE, color = "#D95F02", linewidth = 1, linetype = "dashed"
    ) +
    scale_x_reverse(trans = "log10") +
    labs(x = expression(lambda), y = ylab) +
    coord_cartesian(ylim = c(ylow, yhigh)) +
    theme_biometrics()
}




theme_biometrics <- function() {
  theme_minimal(base_size = 13) +
    theme(
      panel.grid = element_blank(),
      panel.border = element_blank(),
      axis.line = element_line(color = "black"),
      axis.ticks.length = unit(0.1, "cm"),
      axis.ticks = element_line(color = "black"),
      axis.text = element_text(size = 14),
      plot.title = element_text(size = 14, hjust = 0.0),
      legend.position = "none"
    )
}

theme_biometrics_legend <- function() {
  theme_minimal(base_size = 13) +
    theme(
      panel.grid = element_blank(),
      panel.border = element_blank(),
      axis.line = element_line(color = "black"),
      axis.ticks.length = unit(0.1, "cm"),
      axis.ticks = element_line(color = "black"),
      axis.text = element_text(size = 14),
      plot.title = element_text(size = 14, hjust = 0.0),
      legend.position = "top",
      legend.title = element_blank(),
      legend.text = element_text(size = 14),
      legend.key.width = unit(2, "lines"),
      legend.key.height = unit(1, "lines")
    )
}






