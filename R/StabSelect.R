#' Stability Selection for KL-Integrated Cox Elastic-Net Models
#'
#' Performs stability selection for the KL-integrated Cox elastic-net model
#' by repeatedly refitting the model on bootstrap or subsampled datasets and
#' aggregating variable selection frequencies across replicates. This procedure
#' provides a robust measure of variable importance that is less sensitive to
#' a single split of the data.
#'
#' @inheritParams cv.coxkl_enet
#' @param B Integer. Number of bootstrap/subsampling replicates used for
#'   stability selection. Default is \code{50}.
#' @param fraction_sample Numeric in \code{(0, 1]}. Fraction of the original
#'   sample size used in each replicate (without replacement if subsampling is
#'   used). Default is \code{0.5}.
#' @param ncores Integer. Number of parallel cores. Default 1 (sequential execution).
#'
#' @return
#' An object of class \code{"StabSelect"}, which is a list containing:
#' \item{stability_path}{A numeric matrix of dimension
#'   \code{n_vars x n_lambda} giving, for each variable (rows) and each value of
#'   \code{lambda} (columns), the empirical selection probability across the
#'   \code{B} replicates.}
#' \item{lambda}{Numeric vector giving the global \code{lambda} sequence used
#'   for the underlying elastic-net fits.}
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim      <- ExampleData_highdim$train
#' beta_external_highdim  <- ExampleData_highdim$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 50)
#'
#' coxkl.StabSelect <- coxkl_enet.StabSelect(
#'   z            = train_dat_highdim$z,
#'   delta        = train_dat_highdim$status,
#'   time         = train_dat_highdim$time,
#'   stratum      = train_dat_highdim$stratum,
#'   beta         = beta_external_highdim,
#'   etas         = eta_list,
#'   cv.criteria  = "CIndex_pooled",
#'   B            = 20,
#'   message      = TRUE
#' )
#'
#' # Plot with different thresholds without re-running stability selection
#' plot(coxkl.StabSelect, threshold = 0.6)
#' plot(coxkl.StabSelect, threshold = 0.8)
#' }
#'
#' @export

coxkl_enet.StabSelect <- function(z, delta, time, stratum = NULL, RS = NULL, beta = NULL,
                                  etas, alpha = 1.0,
                                  lambda = NULL, nlambda = 100, lambda.min.ratio = 0.1,
                                  nfolds = 5,
                                  cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                                  c_index_stratum = NULL,
                                  message = FALSE, seed = NULL,
                                  B = 50,
                                  fraction_sample = 0.5,
                                  ncores = 1,
                                  ...) {

  if (!is.null(seed)) set.seed(seed)
  cv.criteria <- match.arg(cv.criteria)
  check_etas(etas)

  z <- as.matrix(z)
  n_full <- nrow(z)
  p_vars <- ncol(z)
  var_names <- colnames(z)
  if(is.null(var_names)) var_names <- paste0("V", 1:p_vars)

  if (is.null(lambda.min.ratio)) {
    lambda.min.ratio <- ifelse(n_full < p_vars, 0.05, 1e-03)
  }

  if (is.null(lambda)) {
    if(message) message("Generating global lambda sequence using full data...")
    lambda_max_candidates <- numeric(length(etas))
    for(i in seq_along(etas)) {
      fit_tmp <- coxkl_enet(z = z, delta = delta, time = time, stratum = stratum,
                            RS = RS, beta = beta, eta = etas[i], alpha = alpha,
                            nlambda = 5, lambda.min.ratio = lambda.min.ratio, ...)
      if(!is.null(fit_tmp$lambda)) lambda_max_candidates[i] <- max(fit_tmp$lambda)
    }
    global_lambda_max <- 1.1 * max(lambda_max_candidates)
    lambda <- exp(seq(log(global_lambda_max), log(global_lambda_max * lambda.min.ratio), length.out = nlambda))
  }

  n_lambda_seq <- length(lambda)

  ncores <- max(1L, as.integer(ncores))

  # Capture ... for passing to workers
  dots <- list(...)

  # Define worker function
  stab_one <- function(b, z, delta, time, stratum, RS, beta, etas, alpha, lambda,
                       nfolds, cv.criteria, n_full, p_vars, n_lambda_seq,
                       fraction_sample, seed, dots) {
    if (!is.null(seed)) set.seed(seed + b)

    sub_idx <- sort(sample(seq_len(n_full), size = floor(fraction_sample * n_full)))
    z_sub <- z[sub_idx, , drop = FALSE]
    delta_sub <- delta[sub_idx]
    time_sub <- time[sub_idx]
    stratum_sub <- if(!is.null(stratum)) stratum[sub_idx] else NULL
    RS_sub <- if(!is.null(RS)) RS[sub_idx] else NULL

    result <- tryCatch({
      cv_fit <- do.call(cv.coxkl_enet, c(
        list(
          z = z_sub, delta = delta_sub, time = time_sub, stratum = stratum_sub,
          RS = RS_sub, beta = beta,
          etas = etas, alpha = alpha,
          lambda = lambda,
          nfolds = nfolds,
          cv.criteria = cv.criteria,
          message = FALSE
        ),
        dots
      ))

      best_eta <- cv_fit$best$best_eta

      fit_best <- do.call(coxkl_enet, c(
        list(
          z = z_sub, delta = delta_sub, time = time_sub, stratum = stratum_sub,
          RS = RS_sub, beta = beta,
          eta = best_eta,
          lambda = lambda,
          alpha = alpha
        ),
        dots
      ))

      coef_matrix <- fit_best$beta
      selection_mat <- (coef_matrix != 0) * 1.0

      if(ncol(selection_mat) < n_lambda_seq) {
        selection_mat_padded <- matrix(0, nrow = p_vars, ncol = n_lambda_seq)
        selection_mat_padded[, 1:ncol(selection_mat)] <- selection_mat
        selection_mat <- selection_mat_padded
      }

      selection_mat

    }, error = function(e) {
      matrix(0, nrow = p_vars, ncol = n_lambda_seq)
    })

    return(result)
  }

  if(message) {
    message(sprintf("Starting Stability Selection with B=%d replicates on %d core(s)...", B, ncores))
  }

  if (ncores == 1L) {
    # Sequential execution with progress bar
    if(message) pb <- txtProgressBar(min = 0, max = B, style = 3)
    res_list <- vector("list", B)
    for (b in 1:B) {
      res_list[[b]] <- stab_one(b, z, delta, time, stratum, RS, beta, etas, alpha, lambda,
                                nfolds, cv.criteria, n_full, p_vars, n_lambda_seq,
                                fraction_sample, seed, dots)
      if(message) setTxtProgressBar(pb, b)
    }
    if(message) close(pb)
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

    res_list <- parallel::parLapply(
      cl, seq_len(B), stab_one,
      z = z, delta = delta, time = time, stratum = stratum,
      RS = RS, beta = beta, etas = etas, alpha = alpha, lambda = lambda,
      nfolds = nfolds, cv.criteria = cv.criteria,
      n_full = n_full, p_vars = p_vars, n_lambda_seq = n_lambda_seq,
      fraction_sample = fraction_sample, seed = seed, dots = dots
    )
  }

  if(message) message("Done.")

  # Aggregate results
  stability_counts <- matrix(0, nrow = p_vars, ncol = n_lambda_seq)
  rownames(stability_counts) <- var_names
  for (sel_mat in res_list) {
    stability_counts <- stability_counts + sel_mat
  }

  stability_probs <- stability_counts / B

  res <- list(
    stability_path = stability_probs,
    lambda = lambda
  )
  class(res) <- "StabSelect"
  return(res)
}



#' Stability Selection for MDTL-Integrated Cox Elastic-Net Models
#'
#' Performs stability selection for the Mahalanobis-distance–based transfer-learning
#' Cox elastic-net model (\code{cox_MDTL_enet}) by repeatedly refitting the model on
#' bootstrap or subsampled datasets and aggregating variable selection frequencies
#' across replicates. This procedure yields a more robust measure of variable
#' importance that is less sensitive to a single data split.
#'
#' @inheritParams cv.cox_MDTL_enet
#' @param B Integer. Number of bootstrap/subsampling replicates used for stability
#'   selection. Default is \code{50}.
#' @param fraction_sample Numeric in \code{(0, 1]}. Fraction of the original sample
#'   size used in each replicate. Default is \code{0.5}.
#' @param ncores Integer. Number of parallel cores. Default 1 (sequential execution).
#'
#' @return
#' An object of class \code{"StabSelect"} containing:
#' \itemize{
#'   \item \code{stability_path} — a numeric matrix storing selection probabilities
#'   for each variable–\code{lambda} pair across the \code{B} replicates.
#'   \item \code{lambda} — the global \code{lambda} sequence used for the underlying
#'   elastic-net fits.
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_highdim)
#' train_dat_highdim      <- ExampleData_highdim$train
#' beta_external_highdim  <- ExampleData_highdim$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 10, max_eta = 10)
#'
#' mdtl.StabSelect <- cox_MDTL_enet.StabSelect(
#'   z            = train_dat_highdim$z,
#'   delta        = train_dat_highdim$status,
#'   time         = train_dat_highdim$time,
#'   stratum      = train_dat_highdim$stratum,
#'   beta         = beta_external_highdim,
#'   Q            = NULL,
#'   etas         = eta_list,
#'   cv.criteria  = "CIndex_pooled",
#'   B            = 20,
#'   message      = TRUE
#' )
#'
#' # Visualize selection with a chosen threshold
#' plot(mdtl.StabSelect, threshold = 0.75)
#' }
#'
#' @export
cox_MDTL_enet.StabSelect <- function(z, delta, time, stratum = NULL,
                                     beta, Q = NULL,
                                     etas = NULL, alpha = 1.0,
                                     lambda = NULL, nlambda = 100, lambda.min.ratio = 0.1,
                                     nfolds = 5,
                                     cv.criteria = c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"),
                                     c_index_stratum = NULL,
                                     message = FALSE, seed = NULL,
                                     B = 50,
                                     fraction_sample = 0.5,
                                     ncores = 1,
                                     ...) {

  if (!is.null(seed)) set.seed(seed)
  cv.criteria <- match.arg(cv.criteria)
  if (!is.null(etas)) check_etas(etas)

  z <- as.matrix(z)
  n_full <- nrow(z)
  p_vars <- ncol(z)
  var_names <- colnames(z)
  if(is.null(var_names)) var_names <- paste0("V", 1:p_vars)

  if (is.null(lambda.min.ratio)) {
    lambda.min.ratio <- ifelse(n_full < p_vars, 0.05, 1e-03)
  }

  if (is.null(lambda)) {
    if(message) message("Generating global lambda sequence using full data...")
    lambda_max_candidates <- numeric(length(etas))
    for(i in seq_along(etas)) {
      fit_tmp <- cox_MDTL_enet(z = z, delta = delta, time = time, stratum = stratum,
                               beta = beta, Q = Q,
                               eta = etas[i], alpha = alpha,
                               nlambda = 5, lambda.min.ratio = lambda.min.ratio, ...)
      if(!is.null(fit_tmp$lambda)) lambda_max_candidates[i] <- max(fit_tmp$lambda)
    }
    global_lambda_max <- 1.1 * max(lambda_max_candidates)
    lambda <- exp(seq(log(global_lambda_max), log(global_lambda_max * lambda.min.ratio), length.out = nlambda))
  }

  n_lambda_seq <- length(lambda)

  ncores <- max(1L, as.integer(ncores))

  # Capture ... for passing to workers
  dots <- list(...)

  # Define worker function
  stab_one <- function(b, z, delta, time, stratum, beta, Q, etas, alpha, lambda,
                       nfolds, cv.criteria, n_full, p_vars, n_lambda_seq,
                       fraction_sample, seed, dots) {
    if (!is.null(seed)) set.seed(seed + b)

    sub_idx <- sort(sample(seq_len(n_full), size = floor(fraction_sample * n_full)))
    z_sub <- z[sub_idx, , drop = FALSE]
    delta_sub <- delta[sub_idx]
    time_sub <- time[sub_idx]
    stratum_sub <- if(!is.null(stratum)) stratum[sub_idx] else NULL

    result <- tryCatch({
      cv_fit <- do.call(cv.cox_MDTL_enet, c(
        list(
          z = z_sub, delta = delta_sub, time = time_sub, stratum = stratum_sub,
          beta = beta, Q = Q,
          etas = etas, alpha = alpha,
          lambda = lambda,
          nfolds = nfolds,
          cv.criteria = cv.criteria,
          message = FALSE
        ),
        dots
      ))

      best_eta <- cv_fit$best$best_eta

      fit_best <- do.call(cox_MDTL_enet, c(
        list(
          z = z_sub, delta = delta_sub, time = time_sub, stratum = stratum_sub,
          beta = beta, Q = Q,
          eta = best_eta,
          alpha = alpha,
          lambda = lambda
        ),
        dots
      ))

      coef_matrix <- fit_best$beta
      selection_mat <- (coef_matrix != 0) * 1.0

      if(ncol(selection_mat) < n_lambda_seq) {
        selection_mat_padded <- matrix(0, nrow = p_vars, ncol = n_lambda_seq)
        selection_mat_padded[, 1:ncol(selection_mat)] <- selection_mat
        selection_mat <- selection_mat_padded
      }

      selection_mat

    }, error = function(e) {
      matrix(0, nrow = p_vars, ncol = n_lambda_seq)
    })

    return(result)
  }

  if(message) {
    message(sprintf("Starting Stability Selection (MDTL) with B=%d on %d core(s)...", B, ncores))
  }

  if (ncores == 1L) {
    # Sequential execution with progress bar
    if(message) pb <- txtProgressBar(min = 0, max = B, style = 3)
    res_list <- vector("list", B)
    for (b in 1:B) {
      res_list[[b]] <- stab_one(b, z, delta, time, stratum, beta, Q, etas, alpha, lambda,
                                nfolds, cv.criteria, n_full, p_vars, n_lambda_seq,
                                fraction_sample, seed, dots)
      if(message) setTxtProgressBar(pb, b)
    }
    if(message) close(pb)
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

    res_list <- parallel::parLapply(
      cl, seq_len(B), stab_one,
      z = z, delta = delta, time = time, stratum = stratum,
      beta = beta, Q = Q, etas = etas, alpha = alpha, lambda = lambda,
      nfolds = nfolds, cv.criteria = cv.criteria,
      n_full = n_full, p_vars = p_vars, n_lambda_seq = n_lambda_seq,
      fraction_sample = fraction_sample, seed = seed, dots = dots
    )
  }

  if(message) message("Done.")

  # Aggregate results
  stability_counts <- matrix(0, nrow = p_vars, ncol = n_lambda_seq)
  rownames(stability_counts) <- var_names
  for (sel_mat in res_list) {
    stability_counts <- stability_counts + sel_mat
  }

  stability_probs <- stability_counts / B

  res <- list(
    stability_path = stability_probs,
    lambda = lambda
  )
  class(res) <- "StabSelect"
  return(res)
}
