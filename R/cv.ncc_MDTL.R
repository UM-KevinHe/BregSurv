#' Cross-Validated CLR with Mahalanobis Distance Transfer Learning
#'
#' @description
#' Performs K-fold cross-validation (CV) to select the integration parameter
#' \code{eta} for Conditional Logistic Regression with Mahalanobis distance
#' transfer learning, implemented via \code{\link{ncc_MDTL}}.
#'
#' This function is designed for 1:m matched case-control settings where each
#' stratum (matched set) contains exactly one case and \eqn{m} controls.
#'
#' @details
#' Cross-validation is performed at the stratum level: each matched set is
#' treated as an indivisible unit and assigned to a single fold using
#' \code{get_fold_cc}. This ensures that the conditional likelihood is
#' well-defined within each training and test split.
#'
#' The \code{cv.criteria} argument controls the CV performance metric:
#' \itemize{
#'   \item \code{"loss"}: Average negative conditional log-likelihood on held-out
#'     strata (lower is better).
#'   \item \code{"AUC"}: Matched-set AUC based on within-stratum comparisons
#'     (higher is better).
#'   \item \code{"CIndex"}: Alias for \code{"AUC"} in the 1:m matched setting.
#'   \item \code{"Brier"}: Conditional Brier score based on within-stratum softmax
#'     probabilities (lower is better).
#' }
#'
#' @param y Numeric vector of binary outcomes (0 = control, 1 = case).
#' @param z Numeric matrix of covariates.
#' @param stratum Numeric or factor vector defining the matched sets. \strong{Required}.
#' @param beta Numeric vector of external coefficients. \strong{Required}. If
#'   \code{beta} is named, names are matched against \code{colnames(z)}:
#'   covariates absent from \code{beta} are set to 0 (with a message) and the
#'   vector is reordered, so an external source covering only a subset of the
#'   internal covariates may be supplied directly. An unnamed \code{beta} is
#'   aligned positionally and must have length \code{ncol(z)}. A one-column
#'   matrix with row names is accepted as a named vector. See
#'   \code{\link{align_beta_Q}}. The bundled fixture
#'   \code{ExampleData_cc_lowdim$beta_external} is named \code{Z1}--\code{Z6} and
#'   therefore takes the name-matching path.
#' @param Q Optional weighting (precision) matrix for the Mahalanobis penalty,
#'   typically the precision matrix of the external estimator. Must be symmetric
#'   and positive semi-definite (both checked to a tolerance of 1e-8). If named,
#'   it is reordered and zero-padded to \code{colnames(z)}; only an unnamed
#'   \code{Q} must be exactly \code{ncol(z)} by \code{ncol(z)}. If \code{NULL}, a
#'   \emph{masked identity} is used: 1 on covariates actually supplied by
#'   \code{beta} and 0 on zero-padded positions, so padded coefficients are left
#'   unpenalized. See \code{\link{align_beta_Q}}.
#' @param etas Numeric vector of non-negative integration weights for
#'   \eqn{\eta}. \strong{Required}; the function stops if \code{etas} is
#'   \code{NULL}. Must be finite and \eqn{\ge 0}. The values are sorted in
#'   ascending order internally, and the rows of \code{internal_stat} / columns
#'   of \code{beta_full} follow that sorted order.
#' @param tol Convergence tolerance passed to \code{\link{ncc_MDTL}}. Default \code{1e-4}.
#' @param Mstop Maximum Newton-Raphson iterations passed to \code{\link{ncc_MDTL}}.
#'   Default \code{100}.
#' @param nfolds Number of cross-validation folds. Default \code{5}.
#' @param cv.criteria Character string specifying the CV performance criterion.
#'   One of \code{"loss"} (default), \code{"AUC"}, \code{"CIndex"}, or \code{"Brier"}.
#' @param message Logical. If \code{TRUE}, prints progress messages. Default \code{FALSE}.
#' @param seed Optional integer seed for reproducible fold assignment. Default \code{NULL}.
#' @param ... Additional arguments passed to \code{\link{ncc_MDTL}}.
#'
#' @return A list of class \code{"cv.ncc_MDTL"} containing:
#' \describe{
#'   \item{\code{internal_stat}}{A \code{data.frame} with one row per \code{eta} and
#'     the CV metric for the chosen \code{cv.criteria}.}
#'   \item{\code{beta_full}}{Matrix of coefficients from the full-data fit
#'     (columns correspond to \code{etas}).}
#'   \item{\code{best}}{A list with \code{best_eta}, \code{best_beta}, and \code{criteria}.}
#'   \item{\code{criteria}}{The criterion used for selection.}
#'   \item{\code{nfolds}}{The number of folds used.}
#' }
#'
#' @seealso \code{\link{ncc_MDTL}}, \code{\link{cv.ncckl}}
#'
#' @examples
#' \dontrun{
#' data(ExampleData_cc_lowdim)
#' train_cc <- ExampleData_cc_lowdim$train
#'
#' y        <- train_cc$y
#' z        <- train_cc$z
#' sets     <- train_cc$stratum
#' beta_ext <- ExampleData_cc_lowdim$beta_external
#'
#' eta_list <- generate_eta(method = "exponential", n = 50, max_eta = 10)
#'
#' cv_fit <- cv.ncc_MDTL(
#'   y        = y,
#'   z        = z,
#'   stratum  = sets,
#'   beta     = beta_ext,
#'   Q        = NULL,
#'   etas     = eta_list,
#'   nfolds   = 5,
#'   cv.criteria = "loss",
#'   seed     = 42
#' )
#' cv_fit$best$best_eta
#' }
#' @export
cv.ncc_MDTL <- function(y, z, stratum,
                            beta, Q = NULL,
                            etas = NULL,
                            tol = 1.0e-4, Mstop = 100,
                            nfolds = 5,
                            cv.criteria = c("loss", "AUC", "CIndex", "Brier"),
                            message = FALSE,
                            seed = NULL,
                            ...) {

  cv.criteria <- match.arg(cv.criteria, choices = c("loss", "AUC", "CIndex", "Brier"))

  y <- .check_event(y, "y")
  z <- as.matrix(z)

  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas   <- sort(as.numeric(etas))
  check_etas(etas)
  n_eta  <- length(etas)

  if (missing(stratum) || is.null(stratum)) {
    stop("stratum must be provided for cv.ncc_MDTL in 1:m matched settings.", call. = FALSE)
  }
  stratum <- as.factor(stratum)

  aligned <- align_beta_Q(z, beta, Q)
  beta <- aligned$beta
  Q <- aligned$Q

  events_per_stratum <- tapply(y, stratum, function(x) sum(x == 1))
  if (any(is.na(events_per_stratum)) || any(events_per_stratum != 1)) {
    stop(
      "cv.ncc_MDTL assumes a 1:m matched setting: each stratum must contain exactly ",
      "one case (sum(y==1) == 1 per stratum).",
      call. = FALSE
    )
  }

  n <- length(y)

  full_fit <- ncc_MDTL(
    y       = y,
    z       = z,
    stratum = stratum,
    beta    = beta,
    Q       = Q,
    etas    = etas,
    tol     = tol,
    Mstop   = Mstop,
    message = FALSE,
    ...
  )
  beta_full <- full_fit$beta

  ## Pin the fold assignment. `set.seed(seed)` on its own is NOT enough: it
  ## inherits the ambient RNG *kind*, and a session left in "L'Ecuyer-CMRG" by
  ## future/future.apply returns a DIFFERENT split from the same seed, hence a
  ## different cross-validated loss. The caller's RNG state
  ## is captured and restored on exit, so a parallel worker's stream is left
  ## exactly as it was found.
  if (!is.null(seed)) {
    .rs_old <- if (exists(".Random.seed", envir = globalenv()))
                 get(".Random.seed", envir = globalenv()) else NULL
    on.exit(if (!is.null(.rs_old))
              assign(".Random.seed", .rs_old, envir = globalenv()), add = TRUE)
    set.seed(seed, kind = "Mersenne-Twister")
  }
  .rng_kind <- RNGkind()[1]
  folds <- get_fold_cc(nfolds = nfolds, delta = y, stratum = stratum)
  if (length(folds) != n) {
    stop("get_fold_cc must return a fold assignment of length equal to length(y).", call. = FALSE)
  }

  result_mat <- matrix(NA_real_, nrow = nfolds, ncol = n_eta)
  ## Held-out size per fold, needed because the "loss" criterion is POOLED over
  ## subjects rather than averaged over folds -- get_fold_cc assigns whole
  ## matched sets, so the folds are not the same size. See the aggregation below.
  n_test_per_fold <- rep(NA_real_, nfolds)
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

    fold_fit <- ncc_MDTL(
      y       = y_train,
      z       = z_train,
      stratum = stratum_train,
      beta    = beta,
      Q       = Q,
      etas    = etas,
      tol     = tol,
      Mstop   = Mstop,
      message = FALSE,
      ...
    )
    beta_mat_fold <- fold_fit$beta

    for (i in seq_len(n_eta)) {
      beta_hat <- as.numeric(beta_mat_fold[, i])
      lp_test  <- as.numeric(z_test %*% beta_hat)

      if (cv.criteria == "loss") {
        loglik_test <- cc_loglik(y = y_test, lp = lp_test, stratum = stratum_test)
        ## Store the UNNORMALIZED fold total; the division happens once, at the
        ## pooled aggregation below.
        result_mat[f, i] <- -loglik_test
        n_test_per_fold[f] <- length(y_test)
      } else {
        cv_all_lp[test_idx, i] <- lp_test
      }
    }
  }

  if (cv.criteria == "loss") {
    ## POOLED, NOT THE MEAN OF PER-FOLD MEANS. 
    ##
    ## This used to be colMeans over per-fold mean losses, while the elastic
    ## net NCC drivers pooled (loss_sum / loss_n) and the whole COHORT side
    ## pools too (colSums over folds, then -2 * sum / n). The two are equal only
    ## when the folds are the same size, and get_fold_cc assigns whole matched
    ## sets, so they are not. The consequence was that unpenalized and penalized
    ## NCC members went into one argmin on two different scales; the agent's
    ## run_candidates.R now refuses such a set outright, which is what exposed
    ## this. Pooling here is what makes the NCC candidate set rankable, and it
    ## is the convention already used everywhere else in the package.
    ##
    ## The per-column denominator is load-bearing: a fold where this eta failed
    ## leaves NA, and a fixed denominator would shrink the numerator only,
    ## reporting a better loss for the eta that failed more often.
    result_vec <- vapply(seq_len(n_eta), function(i) {
      ok <- !is.na(result_mat[, i])
      if (!any(ok)) return(NA_real_)
      sum(result_mat[ok, i]) / sum(n_test_per_fold[ok])
    }, numeric(1))
  } else if (cv.criteria %in% c("AUC", "CIndex")) {
    result_vec <- apply(
      cv_all_lp, 2,
      function(lp) cc_auc(y = y, lp = lp, stratum = stratum)
    )
  } else if (cv.criteria == "Brier") {
    result_vec <- apply(
      cv_all_lp, 2,
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
    best_value = .best_value(results, best_eta_idx),
    criteria  = cv.criteria
  )

  structure(
    list(
      internal_stat = results,
      beta_full     = beta_full,
      best          = best_res,
      criteria      = cv.criteria,
      nfolds        = nfolds,
      ## the split actually used, so a replay can be checked rather than
      ## trusted. this is `get_fold_cc`, NOT `get_fold`,
      ## and it is assigned on the CALLER'S row order -- these drivers never
      ## reorder. The cohort claim this comment used to make was copied from
      ## cv.coxkl and was wrong here. `get_fold_cc` is also fully deterministic
      ## (it contains no RNG call at all), so it assigns whole matched sets by
      ## a fixed rule and `seed` below is provenance only.
      folds        = folds,
      seed        = if (is.null(seed)) NA_integer_ else as.integer(seed),
      rng_kind        = .rng_kind
    ),
    class = "cv.ncc_MDTL"
  )
}
