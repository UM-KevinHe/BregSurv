#' Cross-validated Verweij and van Houwelingen loss at a fixed coefficient vector
#'
#' @description
#' Computes the cross-validated Verweij and van Houwelingen (V&VH) partial-likelihood
#' loss for a coefficient vector that is **held fixed across folds** rather than
#' refitted within each one.
#'
#' The V&VH quantity is the difference between the log partial likelihood on the
#' whole cohort and the log partial likelihood on the fold-complement, summed over
#' folds and scaled by \eqn{-2/n}. When a model is refitted inside each fold, that
#' is what \code{\link{cv.coxkl}} and its siblings report. When the coefficient
#' vector does not depend on the data at all -- a published external model used
#' unchanged -- the same quantity is still well defined: the leave-fold-out
#' coefficient simply equals the published vector on every fold.
#'
#' This makes an externally published model directly comparable, on one common
#' scale, with the fitted candidates. Supply the \code{folds} returned by the
#' \code{cv.*} function so that every candidate is scored on the identical
#' partition; scoring on a different split would make the comparison meaningless.
#'
#' @details
#' The arithmetic reproduces \code{\link{cv.coxkl}}'s \code{"V&VH"} branch exactly,
#' including the summation over folds (a sum, not an average) and the \eqn{-2/n}
#' scaling, so the number returned here is on the same scale as that function's
#' \code{VVH_Loss} column and the two may be placed in one table.
#'
#' No model is fitted. The routine evaluates one linear predictor and one partial
#' likelihood per fold, so it is far cheaper than any of the \code{cv.*} functions.
#'
#' @param z Numeric matrix or data frame of covariates, one row per subject.
#' @param delta Event indicator, 1 for an event and 0 for right censoring.
#' @param time Follow-up time.
#' @param stratum Optional stratum labels. If \code{NULL} the whole cohort is
#'   treated as one stratum, matching \code{\link{cv.coxkl}}.
#' @param beta The fixed coefficient vector. A **named** \code{beta} covering only
#'   a subset of \code{colnames(z)} is aligned by name and zero-padded, exactly as
#'   in \code{\link{align_beta}}; an unnamed one must have length \code{ncol(z)}.
#' @param folds Integer fold assignment, one entry per subject, as returned in the
#'   \code{folds} component of the \code{cv.*} functions.
#' @param folds_sorted Whether \code{folds} is already expressed in the internally
#'   sorted row order. The \code{cv.*} functions return it that way, so the default
#'   is \code{TRUE}. Pass \code{FALSE} if \code{folds} follows the row order of
#'   \code{z} as supplied.
#'
#' @param ties Tie handling in the partial likelihood. \code{"none"} (the default, and the behaviour of every release before 1.3.0) takes subjects who share an event time in the order the sorted data list them, so each is dropped from the risk sets of the tied rows after it; \code{"breslow"} uses Breslow's approximation, in which the risk set at an event time is everyone whose time is that time or later. The two coincide when no event time is tied. The V&VH loss is computed on the chosen likelihood.
#' @return A list with components
#'   \item{\code{VVH_Loss}}{the cross-validated loss, on the same scale as the
#'     \code{VVH_Loss} column of \code{\link{cv.coxkl}}.}
#'   \item{\code{criteria}}{always \code{"V&VH"}.}
#'   \item{\code{n}}{number of subjects.}
#'   \item{\code{nfolds}}{number of folds observed in \code{folds}.}
#'   \item{\code{per_fold}}{the per-fold contributions, before summation and
#'     scaling.}
#'
#' @seealso \code{\link{cv.coxkl}}, \code{\link{align_beta}}
#'
#' @examples
#' data(ExampleData_lowdim)
#' tr <- ExampleData_lowdim$train
#' z  <- as.matrix(tr$z)
#' storage.mode(z) <- "double"
#'
#' fit <- cv.coxkl(z = z, delta = tr$status, time = tr$time,
#'                 beta = ExampleData_lowdim$beta_external_good,
#'                 etas = c(0, 0.5, 2), nfolds = 5, seed = 1)
#'
#' # the published model used unchanged, scored on the very same folds
#' ext <- vvh_loss_fixed(z = z, delta = tr$status, time = tr$time,
#'                       beta = ExampleData_lowdim$beta_external_good,
#'                       folds = fit$folds)
#' ext$VVH_Loss
#' fit$internal_stat
#'
#' @export
vvh_loss_fixed <- function(z, delta, time, stratum = NULL, beta, folds,
                           folds_sorted = TRUE, ties = c("none", "breslow")) {
  ties <- .check_ties(match.arg(ties))

  z <- as.matrix(z)
  storage.mode(z) <- "double"
  n <- nrow(z)

  if (missing(beta) || is.null(beta)) {
    stop("'beta' is required.", call. = FALSE)
  }
  if (missing(folds) || is.null(folds)) {
    stop(paste0("'folds' is required. Pass the 'folds' component returned by the ",
                "cv.* function, so that every candidate is scored on the same ",
                "partition."), call. = FALSE)
  }
  folds <- as.integer(folds)
  if (length(folds) != n) {
    stop(sprintf("'folds' has length %d but z has %d rows.", length(folds), n),
         call. = FALSE)
  }
  if (length(delta) != n || length(time) != n) {
    stop("'delta' and 'time' must have one entry per row of 'z'.", call. = FALSE)
  }

  ## Align the external vector by name, zero-padding covariates it does not cover.
  beta <- align_beta(z, beta)

  ## Stratum handling, then the sort, exactly as cv.coxkl does them: pl_cal_theta
  ## consumes data ordered by (stratum, time) and per-stratum counts taken after
  ## that ordering.
  if (is.null(stratum)) {
    warning("Stratum not provided. Treating all data as one stratum.", call. = FALSE)
    stratum <- rep(1, n)
  } else {
    stratum <- match(stratum, unique(stratum))
  }
  time_order <- order(stratum, time)
  stratum <- as.numeric(stratum[time_order])
  z       <- z[time_order, , drop = FALSE]
  delta   <- .check_event(delta[time_order], "delta")
  time    <- as.numeric(time[time_order])
  if (!folds_sorted) folds <- folds[time_order]

  ufolds <- sort(unique(folds))
  nfolds <- length(ufolds)
  if (nfolds < 2L) {
    stop("'folds' must describe at least two folds.", call. = FALSE)
  }

  lp <- as.vector(z %*% beta)
  pl_full <- .pl_ties(lp, delta, time, as.numeric(table(stratum)), ties)

  per_fold <- vapply(ufolds, function(f) {
    keep <- which(folds != f)
    pl_full - .pl_ties(lp[keep], delta[keep], time[keep],
                       as.numeric(table(stratum[keep])), ties)
  }, numeric(1))

  list(
    VVH_Loss = -2 * sum(per_fold) / n,
    criteria = "V&VH",
    ties     = ties,
    n        = n,
    nfolds   = nfolds,
    per_fold = per_fold
  )
}
