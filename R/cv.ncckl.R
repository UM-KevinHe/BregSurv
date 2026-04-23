#' Cross-Validated Conditional Logistic Regression with KL Integration
#'
#' @description
#' Performs K-fold cross-validation (CV) to select the integration parameter
#' \code{eta} for Conditional Logistic Regression with Kullback–Leibler (KL)
#' divergence data integration, implemented via \code{\link{ncckl}}.
#'
#' This function is designed for 1:m matched case–control settings where each
#' stratum (matched set) contains exactly one case and \eqn{m} controls.
#'
#' @details
#' The matched case–control problem is handled via \code{\link{ncckl}}, which
#' maps Conditional Logistic Regression to a Cox model with fixed event time and
#' uses \code{\link{coxkl_ties}} as the core engine.
#'
#' Cross-validation is performed at the stratum level: each matched set is
#' treated as an indivisible unit and assigned to a single fold using
#' \code{\link{get_fold_cc}}. This ensures that the conditional likelihood is
#' well-defined within each training and test split.
#'
#' The \code{cv.criteria} argument controls the CV performance metric:
#' \itemize{
#'   \item \code{"loss"}: Average negative conditional log-likelihood on held-out
#'     strata. For each fold, the conditional log-likelihood is computed over
#'     the test matched sets using the fitted \eqn{\hat\beta} from the
#'     corresponding training data; the fold-wise losses are then averaged.
#'   \item \code{"AUC"}: A matched-set AUC based on within-stratum comparisons.
#'     For each stratum, the case score is compared to the control scores,
#'     counting concordant/discordant/tied pairs and aggregating across all
#'     strata. Higher AUC indicates better discrimination.
#'   \item \code{"CIndex"}: Alias for \code{"AUC"}. In the 1:m matched
#'     case–control setting, the matched-set AUC is equivalent to the
#'     conditional concordance index, and is computed using the same path as
#'     \code{"AUC"}.
#'   \item \code{"Brier"}: A conditional Brier score based on within-stratum
#'     softmax probabilities. For each stratum, a probability is assigned to
#'     each member via
#'     \eqn{\hat p_{si} = \exp(\eta_{si}) / \sum_{j \in S_s} \exp(\eta_{sj})},
#'     and the Brier score is the mean squared error
#'     \eqn{(Y_{si} - \hat p_{si})^2} across all observations. Lower Brier
#'     indicates better conditional calibration and sharpness.
#' }
#'
#' The returned object has the same structure as \code{"cv.coxkl"} objects from
#' \code{\link{cv.coxkl_ties}}, facilitating downstream code reuse.
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#'   In the 1:m matched case–control setting, each stratum must contain exactly
#'   one case.
#' @param z Numeric matrix of covariates (rows = observations, columns = variables).
#' @param stratum Numeric or factor vector defining the matched sets (strata).
#'   Each unique value identifies one matched set.
#' @param beta Numeric vector of external coefficients. \strong{Required}.
#'   Length must equal the number of columns in \code{z}. These are used by
#'   \code{\link{ncckl}} / \code{\link{coxkl_ties}} to construct the KL
#'   divergence penalty.
#' @param etas Numeric vector of candidate tuning values for the integration
#'   parameter \eqn{\eta} to be cross-validated. The values will be sorted in
#'   ascending order.
#' @param method Character string specifying the tie-handling method used in the
#'   underlying Cox partial likelihood. Must be one of \code{"breslow"} or
#'   \code{"exact"}. For 1:m matched sets, these yield identical parameter
#'   estimates, but \code{"exact"} is theoretically preferable.
#' @param tol Convergence tolerance for the optimizer used inside
#'   \code{\link{ncckl}} / \code{\link{coxkl_ties}}. Default \code{1e-4}.
#' @param Mstop Maximum number of Newton iterations used inside
#'   \code{\link{ncckl}} / \code{\link{coxkl_ties}}. Default \code{100}.
#' @param nfolds Number of cross-validation folds. Default \code{5}.
#' @param cv.criteria Character string specifying the CV performance criterion.
#'   Choices are:
#'   \itemize{
#'     \item \code{"loss"}: Average negative conditional log-likelihood
#'       (lower is better).
#'     \item \code{"AUC"}: Matched-set AUC based on within-stratum comparisons
#'       (higher is better).
#'     \item \code{"CIndex"}: Concordance index in the matched-set setting,
#'       implemented via the same matched-set AUC calculation as \code{"AUC"}
#'       (higher is better).
#'     \item \code{"Brier"}: Conditional Brier score using within-stratum
#'       softmax probabilities (lower is better).
#'   }
#'   Default is \code{"loss"}.
#' @param message Logical; if \code{TRUE}, prints progress messages and fold-wise
#'   evaluation progress bars. Default \code{FALSE}.
#' @param seed Optional integer seed for reproducible fold assignment. Default
#'   \code{NULL}.
#' @param comb_max Integer. Maximum number of combinations for the
#'   \code{method = "exact"} calculation, passed down to
#'   \code{\link{ncckl}} / \code{\link{coxkl_ties}}. Default \code{1e7}.
#' @param ... Additional arguments (currently ignored).
#'
#' @return A \code{list} of class \code{"cv.ncckl"} containing:
#' \describe{
#'   \item{\code{internal_stat}}{A \code{data.frame} with one row per \code{eta}
#'     and the CV metric results for the chosen \code{cv.criteria}.}
#'   \item{\code{beta_full}}{The matrix of coefficients from the full-data fit
#'     (columns correspond to \code{etas}).}
#'   \item{\code{best}}{A list containing the \code{best_eta}, the corresponding
#'     \code{best_beta} from the full-data fit, and the \code{cv.criteria} used.}
#'   \item{\code{criteria}}{The criterion used for selection.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @examples
#' \dontrun{
#' data(ExampleData_cc)
#' train_cc <- ExampleData_cc$train
#'
#' y        <- train_cc$y
#' z        <- train_cc$z
#' sets     <- train_cc$stratum
#' beta_ext <- ExampleData_cc$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#'
#' cv_clr_kl <- cv.ncckl(
#'   y        = y,
#'   z        = z,
#'   stratum  = sets,
#'   beta     = beta_ext,
#'   etas     = eta_list,
#'   method   = "exact",
#'   nfolds   = 5,
#'   cv.criteria = "loss",
#'   seed     = 42
#' )
#'
#' cv_clr_kl$best$best_eta
#' }
#'
#' @export
cv.ncckl <- function(y, z, stratum,
                        beta = NULL,
                        etas = NULL,
                        method = c("breslow", "exact"),
                        tol = 1.0e-4,
                        Mstop = 100,
                        nfolds = 5,
                        cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
                        message = FALSE,
                        seed = NULL,
                        comb_max = 1e7,
                        ...) {

  cv.criteria <- match.arg(cv.criteria, choices = c("loss", "AUC", "CIndex", "Brier"))
  method   <- match.arg(tolower(method), c("exact", "breslow"))

  y <- as.numeric(y)
  z <- as.matrix(z)

  if (is.null(beta)) {
    stop("The 'beta' (external coefficients) must be provided for cv.ncckl.", call. = FALSE)
  }
  if (length(beta) != ncol(z)) {
    stop("The dimension of beta does not match the number of columns in z.")
  }
  if (is.null(etas)) {
    stop("etas must be provided.", call. = FALSE)
  }
  etas   <- sort(etas)
  n_eta  <- length(etas)

  if (missing(stratum) || is.null(stratum)) {
    stop("stratum must be provided for cv.ncckl in 1:m matched settings.", call. = FALSE)
  }
  stratum <- as.factor(stratum)

  events_per_stratum <- tapply(y, stratum, function(x) sum(x == 1))
  if (any(is.na(events_per_stratum)) || any(events_per_stratum != 1)) {
    stop(
      "cv.ncckl assumes a 1:m matched setting: each stratum must contain exactly ",
      "one case (sum(y==1) == 1 per stratum).",
      call. = FALSE
    )
  }

  n <- length(y)

  if (message) message("Fitting full conditional logistic KL model for all etas...")
  full_fit <- ncckl(
    y       = y,
    z       = z,
    stratum = stratum,
    etas    = etas,
    beta    = beta,
    method  = method,
    Mstop   = Mstop,
    tol     = tol,
    message = FALSE,
    comb_max = comb_max
  )
  beta_full <- full_fit$beta

  if (!is.null(seed)) set.seed(seed)
  folds <- get_fold_cc(nfolds = nfolds, delta = y, stratum = stratum)

  if (length(folds) != n) {
    stop("get_fold_cc must return a fold assignment of length equal to length(y).", call. = FALSE)
  }

  result_mat <- matrix(NA_real_, nrow = nfolds, ncol = n_eta)
  if (cv.criteria %in% c("AUC", "CIndex", "Brier")) {
    cv_all_lp <- matrix(NA_real_, nrow = n, ncol = n_eta)
  }

  for (f in seq_len(nfolds)) {
    if (message) message(sprintf("CV fold %d/%d starts...", f, nfolds))

    test_idx  <- which(folds == f)
    train_idx <- which(folds != f)

    y_train       <- y[train_idx]
    z_train       <- z[train_idx, , drop = FALSE]
    stratum_train <- droplevels(stratum[train_idx])

    y_test       <- y[test_idx]
    z_test       <- z[test_idx, , drop = FALSE]
    stratum_test <- droplevels(stratum[test_idx])

    ev_train <- tapply(y_train, stratum_train, function(x) sum(x == 1))
    ev_test  <- tapply(y_test,  stratum_test,  function(x) sum(x == 1))
    if (any(is.na(ev_train)) || any(ev_train != 1) ||
        any(is.na(ev_test))  || any(ev_test  != 1)) {
      stop(
        "Each training and test fold must preserve the 1:m matched structure ",
        "(exactly one case per stratum).",
        call. = FALSE
      )
    }

    fold_fit <- ncckl(
      y       = y_train,
      z       = z_train,
      stratum = stratum_train,
      etas    = etas,
      beta    = beta,
      method  = method,
      Mstop   = Mstop,
      tol     = tol,
      message = FALSE,
      comb_max = comb_max
    )
    beta_mat_fold <- fold_fit$beta

    if (message) {
      cat("Evaluating eta sequence on validation fold:\n")
      pb <- txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)
    }

    for (i in seq_len(n_eta)) {
      beta_hat <- as.numeric(beta_mat_fold[, i])
      lp_test  <- as.numeric(z_test %*% beta_hat)

      if (cv.criteria == "loss") {
        loglik_test <- cc_loglik(y = y_test, lp = lp_test, stratum = stratum_test)
        result_mat[f, i] <- -loglik_test / length(y_test)
      } else if (cv.criteria %in% c("AUC", "CIndex", "Brier")) {
        cv_all_lp[test_idx, i] <- lp_test
      }

      if (message) setTxtProgressBar(pb, i)
    }

    if (message) close(pb)
  }

  if (cv.criteria == "loss") {
    result_vec <- colMeans(result_mat, na.rm = TRUE)

  } else if (cv.criteria %in% c("AUC", "CIndex")) {
    result_vec <- apply(
      cv_all_lp,
      2,
      function(lp) cc_auc(y = y, lp = lp, stratum = stratum)
    )

  } else if (cv.criteria == "Brier") {
    result_vec <- apply(
      cv_all_lp,
      2,
      function(lp) cc_brier(y = y, lp = lp, stratum = stratum)
    )
  }

  results <- data.frame(eta = etas)

  if (cv.criteria == "loss") {
    results$loss <- result_vec
    best_eta_idx <- which.min(results$loss)

  } else if (cv.criteria == "AUC") {
    results$AUC <- result_vec
    best_eta_idx <- which.max(results$AUC)

  } else if (cv.criteria == "CIndex") {
    results$CIndex <- result_vec
    best_eta_idx <- which.max(results$CIndex)

  } else if (cv.criteria == "Brier") {
    results$Brier <- result_vec
    best_eta_idx <- which.min(results$Brier)
  }

  best_res <- list(
    best_eta  = etas[best_eta_idx],
    best_beta = beta_full[, best_eta_idx],
    criteria  = cv.criteria
  )

  structure(
    list(
      internal_stat = results,
      beta_full     = beta_full,
      best          = best_res,
      criteria      = cv.criteria,
      nfolds        = nfolds
    ),
    class = "cv.ncckl"
  )
}

