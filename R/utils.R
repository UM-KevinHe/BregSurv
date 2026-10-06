#' Generate a Sequence of Tuning Parameters (eta)
#'
#' Produces a numeric vector of `eta` values to be used in Cox–KL model.
#'
#' @param method Character string selecting how to generate \code{eta}:
#'   \dQuote{linear} for an evenly spaced sequence, or \dQuote{exponential} for an
#'   exponentially spaced sequence. Default is \dQuote{exponential}.
#' @param n Integer, the number of `eta` values to generate. Default is 10.
#' @param max_eta Numeric, the maximum value of `eta` in the sequence. Default is 5.
#' @param min_eta Numeric, the minimum value of `eta` in the sequence. Default is 0.
#'
#' @details
#' \itemize{
#'   \item \emph{Exponential}: values are formed by exponentiating a grid from
#'     \code{log(1)} to \code{log(100)}, then linearly rescaling to the interval
#'     \code{[min_eta, max_eta]}. Thus the smallest value equals \code{min_eta} and
#'     the largest equals \code{max_eta}.
#'   \item \emph{Linear}: values are \code{seq(min_eta, max_eta, length.out = n)}.
#' }
#' Both \code{min_eta} and \code{max_eta} must be single finite numbers with
#' \code{min_eta <= max_eta}; otherwise an error is signalled.
#'
#' Only the exact strings \dQuote{linear} and \dQuote{exponential} are supported;
#' other values for \code{method} will result in an error because \code{eta_values}
#' is never created.
#'
#' @return Numeric vector of length \code{n} containing the generated \code{eta}
#'   values, spanning \code{[min_eta, max_eta]}. These values are external-borrowing
#'   weights and are meaningful only when non-negative: the model-fitting and
#'   cross-validation functions of this package validate \code{eta}/\code{etas} and
#'   reject negative values, so \code{min_eta} should not be set below 0.
#'
#' @examples
#' # Generate 10 exponentially spaced eta values up to 5
#' generate_eta(method = "exponential", n = 10, max_eta = 5)
#'
#' # Generate 5 linearly spaced eta values up to 3
#' generate_eta(method = "linear", n = 5, min_eta= 0, max_eta = 3)
#'
#' # Exponential spacing that starts at 0.1 rather than 0
#' generate_eta(method = "exponential", n = 5, min_eta = 0.1, max_eta = 3)
#'
#' @export
generate_eta <- function(method = "exponential", n = 10, max_eta = 5, min_eta = 0) {
  if (!is.numeric(min_eta) || length(min_eta) != 1L || !is.finite(min_eta)) {
    stop("'min_eta' must be a single finite numeric value.", call. = FALSE)
  }
  if (!is.numeric(max_eta) || length(max_eta) != 1L || !is.finite(max_eta)) {
    stop("'max_eta' must be a single finite numeric value.", call. = FALSE)
  }
  if (min_eta > max_eta) {
    stop("'min_eta' must not be greater than 'max_eta'.", call. = FALSE)
  }
  if (method == "linear") {
    eta_values <- seq(min_eta, max_eta, length.out = n)
  } else if (method == "exponential") {
    eta_values <- exp(seq(log(1), log(100), length.out = n))
    eta_values <- (eta_values - min(eta_values)) / (max(eta_values) - min(eta_values)) *
      (max_eta - min_eta) + min_eta
  }
  return(eta_values)
}


#' Validate an integration-weight argument (internal)
#'
#' Checks that a tuning weight (\code{eta}/\code{etas}) is numeric, finite, and
#' non-negative. \code{eta}/\code{etas} is the external-borrowing weight and is
#' only meaningful for non-negative values. Callers handle the \code{NULL} case
#' according to their own convention (required vs. default) before calling this.
#'
#' @param etas Numeric vector (or scalar) of weights to validate.
#' @param scalar Logical; if \code{TRUE}, also require a single value.
#' @param arg Name used for \code{etas} in error messages.
#' @return \code{etas}, invisibly.
#' @keywords internal
#' @noRd
check_etas <- function(etas, scalar = FALSE, arg = "etas") {
  if (!is.numeric(etas)) {
    stop(sprintf("'%s' must be numeric.", arg), call. = FALSE)
  }
  if (scalar && length(etas) != 1L) {
    stop(sprintf("'%s' must be a single non-negative scalar.", arg), call. = FALSE)
  }
  if (length(etas) == 0L || any(!is.finite(etas)) || any(etas < 0)) {
    stop(sprintf("'%s' must be finite and non-negative.", arg), call. = FALSE)
  }
  invisible(etas)
}


# The value of the selected criterion at the chosen tuning parameters.
#
# `best` used to say WHICH eta and lambda won without saying by how much, so a
# caller comparing several candidates had to reach past it into the statistics
# table -- and the two families lay that table out differently (`internal_stat`
# for the unpenalized fits, `integrated_stat.best_per_eta` for ridge and elastic
# net), with a metric column whose NAME depends on `cv.criteria`. This picks the
# metric column out of whichever table it is handed, so `best` becomes uniform.
#
# Named `best_value`, not `best_loss`: for `CIndex_*` and `AUC` the quantity is
# maximized, and calling a concordance index a loss would put a wrong word into
# anything that reads this field. `best$criteria` says which quantity it is.
.best_value <- function(stat, idx) {
  if (is.null(stat) || !NROW(stat) || length(idx) != 1L || is.na(idx)) {
    return(NA_real_)
  }
  cols <- setdiff(names(stat), c("eta", "lambda", "alpha"))
  if (!length(cols)) return(NA_real_)
  as.numeric(stat[[cols[1L]]][idx])
}


# Coerce an event / case indicator to numeric, refusing the inputs that would
# otherwise be coerced into a plausible but wrong answer. A drop-in replacement
# for `as.numeric` at every point where an outcome indicator enters a fit.
#
# Measured against this package on 2026-08-18, `as.numeric(delta)` alone let
# three distinct wrong inputs through WITHOUT error or warning:
#   * a three-level status column {0 = censored, 1 = death, 2 = competing event}
#     entered the partial likelihood with the competing event weighted 2, giving
#     coefficients matching neither the composite nor the cause-specific fit;
#   * a 0/1 column stored as a FACTOR became {1, 2}, because as.numeric on a
#     factor returns its category codes, so every subject counted as an event;
#   * a character column coerced silently, which is harmless for "0"/"1" but not
#     for anything else.
#
# Degeneracy (every subject an event, or none) is deliberately NOT refused here.
# It is refused by the agent's admissibility gate, where the user can be told
# why. A library must still permit a degenerate stratum inside a larger loop.
.check_event <- function(delta, arg = "delta") {
  if (is.null(delta)) {
    stop(sprintf("'%s' is required.", arg), call. = FALSE)
  }
  if (is.factor(delta)) {
    stop(sprintf(paste0(
      "'%s' is a factor. Converting a factor to a number returns its category ",
      "codes, not its values, so a 0/1 indicator would silently become 1/2 and ",
      "every subject would count as an event. Convert it explicitly first, with ",
      "as.numeric(as.character(%s))."), arg, arg), call. = FALSE)
  }
  d <- suppressWarnings(as.numeric(delta))
  if (anyNA(d)) {
    stop(sprintf(paste0(
      "'%s' contains %d missing or non-numeric value(s). Whether an event ",
      "occurred cannot be left unknown: the fit runs and returns a coefficient ",
      "vector that is entirely NA."), arg, sum(is.na(d))), call. = FALSE)
  }
  u <- sort(unique(d))
  if (!all(u %in% c(0, 1))) {
    stop(sprintf(paste0(
      "'%s' must be a 0/1 indicator; the values observed are %s. More than two ",
      "levels usually means competing events, which this library does not fit. ",
      "Supply either a cause-specific indicator (the event of interest = 1, ",
      "every other outcome censored) or a composite one (any event = 1)."),
      arg, paste(u, collapse = ", ")), call. = FALSE)
  }
  d
}


# Internal worker shared by align_beta and align_beta_Q.
# Returns list(beta = <length-ncol(z), ordered to colnames(z)>, provided = <logical>).
.align_beta <- function(z, beta, arg = "beta") {
  p <- ncol(z)
  if (is.null(p)) {
    stop("z must be a matrix or data frame with columns.", call. = FALSE)
  }
  znames <- colnames(z)

  # Accept a one-column matrix carrying row names as a named vector.
  if (is.matrix(beta) && ncol(beta) == 1L) {
    bn <- rownames(beta)
    beta <- beta[, 1]
    if (is.null(names(beta))) names(beta) <- bn
  }
  bnames <- names(beta)
  beta <- as.numeric(beta)

  if (!is.null(bnames) && !is.null(znames)) {
    if (anyDuplicated(bnames)) {
      stop(sprintf("'%s' has duplicated names.", arg), call. = FALSE)
    }
    unknown <- setdiff(bnames, znames)
    if (length(unknown)) {
      stop(sprintf("Names in '%s' do not match any covariate in z: %s.",
                   arg, paste(unknown, collapse = ", ")), call. = FALSE)
    }
    beta_full <- rep(0, p)
    names(beta_full) <- znames
    beta_full[bnames] <- beta
    provided <- znames %in% bnames
    if (!all(provided)) {
      message(sprintf(
        "%d covariate(s) absent from external '%s' were set to 0: %s.",
        sum(!provided), arg, paste(znames[!provided], collapse = ", ")))
    }
  } else {
    if (length(beta) != p) {
      stop(sprintf(
        paste0("Length of '%s' (%d) does not match the number of covariates in z (%d). ",
               "Provide a named '%s' (names matching colnames(z)) to auto-align a partial ",
               "external vector, or pad it to length %d."),
        arg, length(beta), p, arg, p), call. = FALSE)
    }
    beta_full <- beta
    if (!is.null(znames)) names(beta_full) <- znames
    provided <- rep(TRUE, p)
  }
  list(beta = beta_full, provided = provided)
}


#' Align an external coefficient vector to the internal covariate space
#'
#' @description
#' Reconciles an external coefficient vector \code{beta} with the covariates of
#' the internal design matrix \code{z}, so that external information supplied on a
#' subset (or a differently ordered set) of covariates is placed correctly. When
#' \code{beta} carries names, they are matched against \code{colnames(z)} and any
#' covariate absent from \code{beta} is filled with 0 (the external source is
#' treated as providing no information for that covariate). When \code{beta} is
#' unnamed (or \code{z} has no column names), it is aligned positionally and must
#' already have length \code{ncol(z)}.
#'
#' Name-based alignment signals an error if \code{beta} has duplicated names, or if
#' any name in \code{beta} is not one of \code{colnames(z)} (covariates that exist
#' only in the external source must be dropped by the caller). Whenever at least one
#' covariate is zero-padded, a \code{message} listing the padded covariates is
#' emitted.
#'
#' @param z Internal covariate matrix or data frame. Its columns define the
#'   target coefficient space; column names, when present, are used for matching.
#' @param beta External coefficient vector (optionally named). A one-column matrix is
#'   also accepted -- the shape in which a \code{coef} result or a stored
#'   external-model artifact typically arrives -- and its row names are promoted to
#'   the names of the resulting vector.
#' @param arg Name used for \code{beta} in error messages.
#'
#' @return A numeric vector of length \code{ncol(z)}, ordered to \code{colnames(z)}
#'   and named with \code{colnames(z)} whenever \code{z} carries column names.
#' @seealso \code{\link{align_beta_Q}} for the Mahalanobis-distance setting.
#'
#' @examples
#' # Six internal covariates; the external source estimated only four of them.
#' z <- matrix(seq_len(30), nrow = 5, ncol = 6,
#'             dimnames = list(NULL, paste0("Z", 1:6)))
#' beta_ext <- c(Z1 = 0.30, Z3 = 0.25, Z5 = -0.10, Z6 = 0.05)
#'
#' # Z2 and Z4 are absent from the external vector and are zero-padded.
#' align_beta(z, beta_ext)
#'
#' # A one-column matrix is accepted; its row names are used as the names.
#' beta_mat <- matrix(c(0.30, 0.25, -0.10, 0.05), ncol = 1,
#'                    dimnames = list(c("Z1", "Z3", "Z5", "Z6"), "coef"))
#' align_beta(z, beta_mat)
#'
#' # An unnamed beta is aligned positionally and must have length ncol(z).
#' align_beta(z, c(0.30, 0, 0.25, 0, -0.10, 0.05))
#'
#' @export
align_beta <- function(z, beta, arg = "beta") {
  .align_beta(z, beta, arg = arg)$beta
}


#' Align an external coefficient vector and weighting matrix for MDTL
#'
#' @description
#' Extends \code{\link{align_beta}} to the Mahalanobis-distance transfer-learning
#' (MDTL) setting, where the external information is a coefficient vector
#' \code{beta} together with a symmetric positive-semidefinite weighting
#' (precision) matrix \code{Q}. \code{beta} is aligned to \code{colnames(z)}
#' exactly as in \code{\link{align_beta}}. \code{Q}, when supplied, is checked for
#' symmetry and positive-semidefiniteness and, if named, reordered and
#' zero-padded to the same covariate space; rows and columns for covariates the
#' external source did not estimate are set to 0 so those coordinates are left
#' unpenalized. When \code{Q} is \code{NULL}, a \emph{masked identity} is
#' returned: a diagonal matrix with 1 on covariates actually supplied by
#' \code{beta} and 0 on padded positions. This ensures that padded-zero
#' coefficients are not penalized as if they were genuine external information.
#'
#' Symmetry of \code{Q} is checked with \code{isSymmetric} at tolerance
#' \code{1e-8}, and positive semi-definiteness by requiring the smallest eigenvalue
#' to be at least \code{-1e-8}; violations of either are errors. Name-based
#' alignment of \code{Q} engages only when \code{rownames(Q)} is non-\code{NULL}
#' \emph{and} \code{z} has column names; otherwise \code{Q} is used positionally and
#' must be exactly \code{ncol(z)} by \code{ncol(z)}. Name-based alignment signals an
#' error if \code{rownames(Q)} contains duplicates, if any of them is not one of
#' \code{colnames(z)}, or if \code{colnames(Q)} is present but does not contain the
#' same names as \code{rownames(Q)}.
#'
#' @param z Internal covariate matrix or data frame.
#' @param beta External coefficient vector (optionally named). A one-column matrix
#'   with row names is accepted as a named vector; see \code{\link{align_beta}}.
#' @param Q Optional weighting/precision matrix (optionally with dimnames). If
#'   \code{NULL}, a masked identity is used.
#' @param arg_beta,arg_Q Names used for \code{beta} and \code{Q} in error messages.
#'
#' @return A list with components \code{beta} (numeric, length \code{ncol(z)}),
#'   \code{Q} (\code{ncol(z)} by \code{ncol(z)} matrix, carrying \code{colnames(z)}
#'   as both its row and column names whenever \code{z} has column names), and
#'   \code{provided} (logical mask of covariates supplied by the external source).
#' @seealso \code{\link{align_beta}}
#'
#' @examples
#' z <- matrix(seq_len(30), nrow = 5, ncol = 6,
#'             dimnames = list(NULL, paste0("Z", 1:6)))
#' beta_ext <- c(Z1 = 0.30, Z3 = 0.25, Z5 = -0.10, Z6 = 0.05)
#'
#' # Q = NULL gives the masked identity: 1 on the covariates the external source
#' # supplied, 0 on the zero-padded ones (Z2, Z4), which are left unpenalized.
#' aligned <- align_beta_Q(z, beta_ext)
#' aligned$beta
#' diag(aligned$Q)
#' aligned$provided
#'
#' # A named information matrix is reordered and zero-padded to colnames(z).
#' Q_ext <- diag(c(4, 2, 1, 3))
#' dimnames(Q_ext) <- list(names(beta_ext), names(beta_ext))
#' align_beta_Q(z, beta_ext, Q = Q_ext)$Q
#'
#' @export
align_beta_Q <- function(z, beta, Q = NULL, arg_beta = "beta", arg_Q = "Q") {
  al <- .align_beta(z, beta, arg = arg_beta)
  p <- length(al$beta)
  znames <- colnames(z)

  if (is.null(Q)) {
    ## No metric was released, so one is manufactured: the identity on the covered
    ## coordinates, zero on the rest.  MARK IT.  Every cv.* wrapper aligns before it
    ## calls the fit, so without this mark the fit cannot tell a metric the analyst
    ## supplied (which carries its own units) from one built here (which does not),
    ## and cannot choose the scale the identity should live on under standardize = TRUE.
    Q_full <- diag(as.numeric(al$provided), nrow = p)
    attr(Q_full, "manufactured") <- TRUE
  } else {
    ## A Q that THIS function manufactured on an earlier call keeps its mark, so a
    ## caller that aligns and then hands the result to a fit (every cv.* wrapper) does
    ## not turn a manufactured metric into one the analyst appears to have supplied.
    was_manufactured <- isTRUE(attr(Q, "manufactured"))
    Q <- as.matrix(Q)
    ## t does not carry an arbitrary attribute, so isSymmetric below would compare
    ## Q against a t(Q) that lacks the mark and declare an ordinary matrix asymmetric.
    attr(Q, "manufactured") <- NULL
    if (!isSymmetric(unname(Q), tol = 1e-8)) {
      stop(sprintf("'%s' must be symmetric.", arg_Q), call. = FALSE)
    }
    qnames <- rownames(Q)
    if (!is.null(qnames) && !is.null(znames)) {
      if (anyDuplicated(qnames)) {
        stop(sprintf("'%s' has duplicated names.", arg_Q), call. = FALSE)
      }
      unknown <- setdiff(qnames, znames)
      if (length(unknown)) {
        stop(sprintf("Names of '%s' do not match any covariate in z: %s.",
                     arg_Q, paste(unknown, collapse = ", ")), call. = FALSE)
      }
      if (!is.null(colnames(Q)) && !setequal(colnames(Q), qnames)) {
        stop(sprintf("Row and column names of '%s' must match.", arg_Q), call. = FALSE)
      }
      if (!is.null(colnames(Q))) {
        Q <- Q[qnames, qnames, drop = FALSE]
      }
      Q_full <- matrix(0, p, p)
      idx <- match(qnames, znames)
      Q_full[idx, idx] <- Q
    } else {
      if (nrow(Q) != p || ncol(Q) != p) {
        stop(sprintf("'%s' must be a %d by %d matrix (or carry names matching colnames(z)).",
                     arg_Q, p, p), call. = FALSE)
      }
      Q_full <- Q
    }
    ev <- eigen(Q_full, symmetric = TRUE, only.values = TRUE)$values
    if (min(ev) < -1e-8) {
      stop(sprintf("'%s' must be positive semi-definite.", arg_Q), call. = FALSE)
    }
  }
  if (!is.null(znames)) {
    dimnames(Q_full) <- list(znames, znames)
  }
  if (is.null(Q) || isTRUE(get0("was_manufactured", ifnotfound = FALSE))) {
    attr(Q_full, "manufactured") <- TRUE
  }
  list(beta = al$beta, Q = Q_full, provided = al$provided)
}


c_stat_stratcox <- function(time, xbeta, stratum, delta) {
  stratum <- factor(stratum)

  ord <- order(stratum, time, -delta)
  time <- time[ord]
  xbeta <- xbeta[ord]
  stratum <- stratum[ord]
  delta <- delta[ord]

  # Only evaluate strata with at least 2 individuals
  stratum_sizes <- table(stratum)
  valid_strata <- names(stratum_sizes[stratum_sizes > 1])

  # Compute per-stratum concordance
  count <- sapply(valid_strata, function(s) {
    idx <- stratum == s
    cox_c_index(time[idx], xbeta[idx], delta[idx])
  })

  numer <- Reduce(`+`, count["numer", ])
  denom <- Reduce(`+`, count["denom", ])
  c_stat <- numer / denom

  return(list(numer = numer,
              denom = denom,
              c_statistic = c_stat))
}


c_stat_stratcox_vec <- function(time, LP_mat, stratum, delta) {
  numer <- denom <- c_stat <- rep(NA_real_, ncol(LP_mat))
  for (j in seq_len(ncol(LP_mat))) {
    cs <- c_stat_stratcox(time, LP_mat[, j], stratum, delta)
    numer[j] <- cs$numer
    denom[j] <- cs$denom
    c_stat[j] <- cs$c_statistic
  }
  list(numer = numer, denom = denom, c_stat = c_stat)
}

auc_one_stratum <- function(y, score) {
  y <- as.integer(y)
  n1 <- sum(y == 1); n0 <- sum(y == 0)
  if (n1 == 0L || n0 == 0L) return(NA_real_)
  r <- rank(score, ties.method = "average")
  (sum(r[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
}

auc_stratified <- function(y, score, stratum) {
  f <- factor(stratum)
  levs <- levels(f)
  aucs <- numer <- denom <- numeric(length(levs))
  for (i in seq_along(levs)) {
    idx <- f == levs[i]
    yi  <- y[idx]; si <- score[idx]
    n1 <- sum(yi == 1); n0 <- sum(yi == 0)
    if (n1 == 0L || n0 == 0L) {
      aucs[i]  <- NA_real_
      numer[i] <- 0; denom[i] <- 0
    } else {
      aucs[i]  <- auc_one_stratum(yi, si)
      numer[i] <- aucs[i] * (n1 * n0)
      denom[i] <- (n1 * n0)
    }
  }
  list(
    auc_macro  = mean(aucs, na.rm = TRUE),
    auc_pooled = if (sum(denom) > 0) sum(numer) / sum(denom) else NA_real_
  )
}


get_fold <- function(nfolds = 5, delta, stratum) {
  n <- length(delta)
  fold <- integer(n)

  stratum <- as.factor(stratum)
  strata_levels <- levels(stratum)

  for (s in strata_levels) {
    idx <- which(stratum == s)
    delta_s <- delta[idx]

    ind1 <- which(delta_s == 1)
    ind0 <- which(delta_s == 0)

    n1 <- length(ind1)
    n0 <- length(ind0)

    fold1 <- 1:n1 %% nfolds
    fold0 <- (n1 + 1:n0) %% nfolds
    fold1[fold1 == 0] <- nfolds
    fold0[fold0 == 0] <- nfolds

    fold_s <- integer(length(idx))
    fold_s[ind1] <- sample(fold1)
    fold_s[ind0] <- sample(fold0)

    fold[idx] <- fold_s
  }

  return(fold)
}


get_fold_cc <- function(nfolds = 5, delta, stratum) { ## for case-control data

  stratum <- as.factor(stratum)
  strata_levels <- levels(stratum)
  n_strata <- length(strata_levels)

  events_per_stratum <- tapply(delta, stratum, function(x) sum(x == 1))
  size_per_stratum   <- tapply(delta, stratum, length)

  ord <- order(events_per_stratum, size_per_stratum, decreasing = TRUE)
  strata_ord <- strata_levels[ord]

  fold_events <- rep(0, nfolds)
  fold_sizes  <- rep(0, nfolds)

  ## Fold assignment at stratum level
  fold_by_stratum <- integer(n_strata)
  names(fold_by_stratum) <- strata_levels

  for (s in strata_ord) {
    scores <- fold_events + 1e-6 * fold_sizes
    best_fold <- which.min(scores)

    fold_by_stratum[s] <- best_fold
    fold_events[best_fold] <- fold_events[best_fold] + events_per_stratum[s]
    fold_sizes[best_fold]  <- fold_sizes[best_fold]  + size_per_stratum[s]
  }

  fold <- fold_by_stratum[as.character(stratum)]
  fold <- as.integer(fold)

  return(fold)
}

cc_loglik <- function(y, lp, stratum) {
  stratum <- as.factor(stratum)
  if (length(y) != length(lp) || length(y) != length(stratum)) {
    stop("Lengths of y, lp, and stratum must match in cc_loglik().", call. = FALSE)
  }

  events_per_stratum <- tapply(y, stratum, function(x) sum(x == 1))
  if (any(is.na(events_per_stratum)) || any(events_per_stratum != 1)) {
    stop("cc_loglik() assumes each stratum has exactly one case.", call. = FALSE)
  }

  ord <- order(stratum, -y)
  lp_ord    <- lp[ord]
  delta_ord <- y[ord]
  n_each_stratum <- as.numeric(table(stratum[ord]))

  pl_cal_theta(
    lp              = lp_ord,
    delta           = delta_ord,
    n_each_stratum  = n_each_stratum
  )
}


cc_auc <- function(y, lp, stratum) {
  stratum <- as.factor(stratum)
  if (length(y) != length(lp) || length(y) != length(stratum)) {
    stop("Lengths of y, lp, and stratum must match in cc_auc().", call. = FALSE)
  }

  split_y  <- split(y,  stratum)
  split_lp <- split(lp, stratum)

  numer <- 0
  denom <- 0

  for (s in seq_along(split_y)) {
    y_s  <- split_y[[s]]
    lp_s <- split_lp[[s]]

    if (sum(y_s == 1) != 1L) next
    if (sum(y_s == 0) < 1L)  next

    lp_case  <- lp_s[y_s == 1L]
    lp_ctrls <- lp_s[y_s == 0L]

    for (sc in lp_ctrls) {
      if (lp_case > sc) {
        numer <- numer + 1
      } else if (lp_case == sc) {
        numer <- numer + 0.5
      }
      denom <- denom + 1
    }
  }

  if (denom == 0) return(NA_real_)
  numer / denom
}



cc_brier <- function(y, lp, stratum) {
  stratum <- as.factor(stratum)
  if (length(y) != length(lp) || length(y) != length(stratum)) {
    stop("Lengths of y, lp, and stratum must match in cc_brier().", call. = FALSE)
  }

  split_y  <- split(y,  stratum)
  split_lp <- split(lp, stratum)

  se_sum <- 0
  n_tot  <- length(y)

  for (s in seq_along(split_y)) {
    y_s  <- split_y[[s]]
    lp_s <- split_lp[[s]]

    m_s   <- max(lp_s)
    exp_s <- exp(lp_s - m_s)
    p_s   <- exp_s / sum(exp_s)

    se_sum <- se_sum + sum((y_s - p_s)^2)
  }

  se_sum / n_tot
}

vcov_Estimate <- function(z, delta, time, stratum, beta_hat, lambda = 0) {

  if (missing(stratum)) {
    stratum <- matrix(1, nrow = nrow(z))
    colnames(stratum) <- "stratum"
  } else {
    stratum <- as.matrix(match(stratum, unique(stratum)))
  }

  ord <- order(stratum, time)
  stratum <- stratum[ord, , drop = FALSE]
  z <- as.matrix(z[ord, , drop = FALSE])
  delta <- delta[ord]

  n.each_stratum <- as.numeric(table(stratum))

  vcov_mat <- Cox_Vcov(
    Z = z,
    delta = delta,
    beta = beta_hat,
    n_each_stratum = n.each_stratum,
    lambda = lambda
  )

  se_beta <- sqrt(diag(vcov_mat))
  list(vcov = vcov_mat, se = se_beta)
}



#---------------------------- Functions for high-dim LASSO ----------------------------#
#' Setup Lambda Sequence for Cox–KL Model (Internal)
#'
#' Generates a sequence of penalty parameters (`lambda`) and initializes coefficients
#' for the Cox–KL model. The maximum lambda (`lambda.max`) is defined as the
#' smallest value that shrinks all coefficients (`beta`) to zero. Note that different
#' values of `eta` will produce different `lambda` sequences.
#' @keywords internal
#' @noRd
setupLambdaCoxKL <- function(Z, time, delta, delta_tilde, RS, beta.init, stratum,
                             group, group.multiplier, n.each_stratum, alpha,
                             eta, nlambda, lambda.min.ratio, tm = NULL) {
  n <- nrow(Z)
  K <- table(group)
  K1 <- as.integer(if (min(group)==0) cumsum(K) else c(0, cumsum(K)))
  storage.mode(K1) <- "integer"
  if (!is.null(tm)) { ## Breslow (1.3.0): the score at the null fit, with the tie-corrected risk sets
    LinPred <- rep(0, n)
    if (K1[1] != 0) {
      nullFit <- coxkl(Z[, group == 0, drop = FALSE], delta, time, stratum, RS, beta = NULL, eta,
                       ties = "breslow")
      LinPred <- as.numeric(nullFit$linear.predictors[, 1])
      beta.init <- c(nullFit$beta[, 1], rep(0, length(beta.init) - nrow(nullFit$beta)))
    }
    r <- (delta + eta * delta_tilde) / (1 + eta) -
      exp(LinPred) * .breslow_cumhaz(LinPred, delta, stratum, tm)
  } else if (K1[1]!=0) { ## some covariates are not penalized
    nullFit <- coxkl(Z[, group == 0, drop = FALSE], delta, time, stratum, RS, beta = NULL, eta)
    LinPred <- nullFit$linear.predictors[[1]]
    beta.init <- c(nullFit$beta[[1]], rep(0, length(beta.init) - length(nullFit$beta[[1]])))
    rsk <- c()
    for (i in seq_along(unique(stratum))){
      rsk <- c(rsk, rev(cumsum(rev(exp(LinPred[stratum == i])))))
    }
    # r <- (delta + eta * delta_tilde)/(1 + eta) - exp(LinPred) * cumsum(delta / rsk)

    r <- numeric(length(delta))
    for (i in seq_along(unique(stratum))) {
      idx <- which(stratum == i)
      r[idx] <- (delta[idx] + eta * delta_tilde[idx]) / (1 + eta) -
        exp(LinPred[idx]) * cumsum(delta[idx] / rsk[idx])
    }
  } else { ## all covariates are penalized
    w <- c()
    h <- c()
    for (i in seq_along(unique(stratum))){
      temp.w <- 1 / (n.each_stratum[i] - (1:n.each_stratum[i]) + 1)
      w <- c(w, temp.w)
      h <- c(h, cumsum(delta[stratum == i] * temp.w))
    }
    r <- (delta + eta * delta_tilde)/(1 + eta) - h
    beta.init <- beta.init
  }

  ## Determine lambda.max
  zmax <- maxgrad(Z, r, K1, as.double(group.multiplier)) / n
  lambda.max <- zmax/alpha

  if (lambda.min.ratio == 0){
    lambda <- c(exp(seq(log(lambda.max), log(1e-7 * lambda.max), len = nlambda-1)), 0)
  } else {
    lambda <- exp(seq(log(lambda.max), log(lambda.min.ratio * lambda.max), len = nlambda))
  }
  lambda[1] <- lambda[1] + 1e-9
  ls <- list(beta = beta.init, lambda.seq = lambda)
  return(ls)
}

setupG <- function(group, m){
  group.factor <- factor(group)
  if (any(levels(group.factor) == '0')) {
    g <- as.integer(group.factor) - 1
    lev <- levels(group.factor)[levels(group.factor) != '0']
  } else {
    g <- as.integer(group.factor)
    lev <- levels(group.factor)
  }
  if (is.numeric(group) | is.integer(group)) {
    lev <- paste0("G", lev)
  }
  if (is.null(m)) {
    m <- rep(NA, length(lev))
    names(m) <- lev
  } else {
    TRY <- try(as.integer(group) == g)
    if (inherits(TRY, 'try-error') || any(!TRY)) stop('Attempting to set group.multiplier is ambiguous if group is not a factor', call. = FALSE)
    if (length(m) != length(lev)) stop("Length of group.multiplier must equal number of penalized groups", call. = FALSE)
    if (storage.mode(m) != "double") storage.mode(m) <- "double"
    if (any(m < 0)) stop('group.multiplier cannot be negative', call.=FALSE)
  }
  # "g" contains the group index of each column, but convert "character" group name into integer
  structure(g, levels = lev, m = m)
}

# remove constant columns if necessary
subsetG <- function(g, nz) { # nz: index of non-constant features
  lev <- attr(g, 'levels')
  m <- attr(g, 'm')
  new <- g[nz] # only include non-constant columns
  dropped <- setdiff(g, new) # If the entire group has been dropped
  if (length(dropped) > 0) {
    lev <- lev[-dropped] # remaining group
    m <- m[-dropped]
    group.factor <- factor(new) #remaining group factor
    new <- as.integer(group.factor) - 1 * any(levels(group.factor) == '0') #new group index
  }
  structure(new, levels = lev, m = m)
}

# reorder group index of features
reorderG <- function(g, m) {
  og <- g
  lev <- attr(g, 'levels')
  m <- attr(g, 'm')
  if (any(g == 0)) {
    g <- as.integer(relevel(factor(g), "0")) - 1
  }
  if (any(order(g) != 1:length(g))) {
    reorder <- TRUE
    gf <- factor(g)
    if (any(levels(gf) == "0")) {
      gf <- relevel(gf, "0")
      g <- as.integer(gf) - 1
    } else {
      g <- as.integer(gf)
    }
    ord <- order(g)
    ord.inv <- match(1:length(g), ord)
    g <- g[ord]
  } else {
    reorder <- FALSE
    ord <- ord.inv <- NULL
  }
  structure(g, levels = lev, m = m, ord = ord, ord.inv = ord.inv, reorder = reorder)
}

#Feather-level standardization
standardize.Z <- function(Z){
  mysd <- function(z){
    sqrt(sum((z - mean(z))^2)/length(z))
  }
  new.Z <- scale(as.matrix(Z), scale = apply(as.matrix(Z), 2, mysd))
  center.Z <- attributes(new.Z)$`scaled:center`
  scale.Z <- attributes(new.Z)$`scaled:scale`
  new.Z <- new.Z[, , drop = F]
  res <- list(new.Z = new.Z, center.Z = center.Z, scale.Z = scale.Z)
  return(res)
}

## converting standardized betas back to original variables
unstandardize <- function(beta, gamma, std.Z){
  original.beta <- matrix(0, nrow = length(std.Z$scale), ncol = ncol(beta))
  original.beta[std.Z$nz, ] <- beta / std.Z$scale[std.Z$nz] # modified beta
  original.gamma <- t(apply(gamma, 1, function(x) x - crossprod(std.Z$center, original.beta))) # modified intercepts (gamma)
  return(list(gamma = original.gamma, beta = original.beta))
}


# Group-level orthogonalization (column in new order, from group_0 to group_max)
orthogonalize <- function(Z, group) {
  z.names <- colnames(Z)
  n <- nrow(Z)
  J <- max(group)
  QL <- vector("list", J)
  orthog.Z <- matrix(0, nrow = nrow(Z), ncol = ncol(Z))
  colnames(orthog.Z) <- z.names
  # unpenalized group will not be orthogonalized
  orthog.Z[, which(group == 0)] <- Z[, which(group == 0)]

  # SVD and generate orthogonalized X
  for (j in seq_along(integer(J))) {
    ind <- which(group == j)
    if (length(ind) == 0) { # skip 0-length group
      next
    }
    SVD <- svd(Z[, ind, drop = FALSE], nu = 0) # Q matrix (orthonormal matrix of eigenvectors)
    r <- which(SVD$d > 1e-10) #remove extremely small singular values
    QL[[j]] <- sweep(SVD$v[, r, drop = FALSE], 2, sqrt(n)/SVD$d[r], "*") # Q * Lambda^{-1/2}
    orthog.Z[, ind[r]] <- Z[, ind] %*% QL[[j]] # group orthogonalized X, where (X^T * X)/n = I
  }
  nz <- !apply(orthog.Z == 0, 2, all) #find all zero
  orthog.Z <- orthog.Z[, nz, drop = FALSE]
  attr(orthog.Z, "QL") <- QL
  attr(orthog.Z, "group") <- group[nz]
  return(orthog.Z)
}

# convert orthogonalized beta back to original scales
unorthogonalize <- function(beta, Z, group) {
  ind <- !sapply(attr(Z, "QL"), is.null)
  QL <- Matrix::bdiag(attr(Z, "QL")[ind]) #block diagonal matrix
  if (sum(group == 0) > 0){ #some groups are unpenalized
    ind0 <- which(group==0)
    original.beta <- as.matrix(rbind(beta[ind0, , drop = FALSE], QL %*% beta[-ind0, , drop = FALSE]))
  } else { # all groups are penalized
    original.beta <- as.matrix(QL %*% beta)
  }
  return(original.beta)
}



# standardize + orthogonalize covariate matrix
newZG.Std <- function(Z, g, m){
  if (any(is.na(Z))){
    stop("Missing data (NA's) detected in covariate matrix!", call. = FALSE)
  }
  if (length(g) != ncol(Z)) {
    stop ("Dimensions of group is not compatible with Z", call. = FALSE)
  }
  G <- setupG(g, m) # setup group
  std <- standardize.Z(Z)
  std.Z <- std[[1]]
  center <- std[[2]]
  scale <- std[[3]]

  small_scales <- which(scale <= 1e-6)
  if (length(small_scales) > 0) {
    stop(
      paste0(
        "The following variables have (near) constant columns: ",
        paste(names(scale)[small_scales], collapse = ", ")
      )
    )
  }

  nz <- which(scale > 1e-6) # non-constant columns
  if (length(nz) != ncol(Z)) {
    std.Z <- std.Z[, nz, drop = F]
    G <- subsetG(G, nz)
  }
  # Reorder groups
  G <- reorderG(G, attr(G, 'm'))
  if (attr(G, 'reorder')){
    std.Z <- std.Z[, attr(G, 'ord')]
  }
  # Group-level orthogonalization
  std.Z <- orthogonalize(std.Z, G)
  g <- attr(std.Z, "group")
  # Set group multiplier if missing
  m <- attr(G, 'm')
  if (all(is.na(m))) {
    m <- sqrt(table(g[g != 0]))
  }
  res <- list(std.Z = std.Z, g = g, m = m, reorder = attr(G, 'reorder'), nz = nz,
              ord.inv = attr(G, 'ord.inv'), center = center, scale = scale)
  return(res)
}

# Only orthogonalize covariate matrix
newZG.Unstd <- function(Z, g, m){
  if (any(is.na(Z))){
    stop("Missing data (NA's) detected in covariate matrix!", call. = FALSE)
  }
  if (length(g) != ncol(Z)) {
    stop ("Dimensions of group is not compatible with Z", call. = FALSE)
  }
  G <- setupG(g, m)
  mysd <- function(x){
    sqrt(sum((x - mean(x))^2)/length(x))
  }
  scale <- apply(as.matrix(Z), 2, mysd)


  small_scales <- which(scale <= 1e-6)
  if (length(small_scales) > 0) {
    stop(
      paste0(
        "The following variables have (near) constant columns: ",
        paste(names(scale)[small_scales], collapse = ", ")
      )
    )
  }

  nz <- which(scale > 1e-6) #remove constant columns
  if (length(nz) != ncol(Z)) {
    std.Z <- Z[, nz, drop = F]
    G <- subsetG(G, nz)
  } else {
    std.Z <- Z
  }
  G <- reorderG(G, attr(G, 'm'))
  if (attr(G, 'reorder')){
    std.Z <- std.Z[, attr(G, 'ord')]
  }
  std.Z <- orthogonalize(std.Z, G)
  g <- attr(std.Z, "group")
  # Set group multiplier if missing
  m <- attr(G, 'm')
  if (all(is.na(m))) {
    m <- sqrt(table(g[g != 0]))
  }
  res <- list(std.Z = std.Z, g = g, m = m, reorder = attr(G, 'reorder'),
              ord.inv = attr(G, 'ord.inv'), nz = nz)
  return(res)
}


loss.coxkl_highdim <- function(delta, y.hat, stratum, total = TRUE){
  y.hat <- as.matrix(y.hat)
  revCumsum.strat <- function(strat){
    temp.y.hat <- y.hat[which(stratum == strat), , drop=FALSE]
    temp.rsk <- apply(temp.y.hat, 2, function(x) rev(cumsum(rev(exp(x)))))
    return(temp.rsk)
  }
  rsk <- do.call(rbind, lapply(unique(stratum), function(i) revCumsum.strat(i)))

  if (total == TRUE) { #when delta = 0, loss contribution is 0
    return(-2 * (crossprod(delta, y.hat) - crossprod(delta, log(rsk)))) #return a vector (1 * nlambda)
  } else { #when delta = 0, loss contribution is 0
    return(-2 * (y.hat[delta == 1, , drop = FALSE] - log(rsk)[delta == 1, , drop = FALSE])) #return a matrix (n * nlambda)
  }
}



#---------------------------- Functions for  MDTL + elastic net ----------------------------#
#' Setup Lambda Sequence for Cox–MDTL Model
#' @keywords internal
#' @noRd
setupLambda_MDTL <- function(Z, time, delta, beta.init, stratum, beta_ext, Q, Qbeta_ext,
                             group, group.multiplier, n.each_stratum, alpha,
                             eta, nlambda, lambda.min.ratio, tm = NULL) {
  n <- nrow(Z)
  K <- table(group)
  K1 <- as.integer(if (min(group)==0) cumsum(K) else c(0, cumsum(K)))
  storage.mode(K1) <- "integer"


  if (!is.null(tm)) { ## Breslow (1.3.0): the score at the null fit, with the tie-corrected risk sets
    LinPred <- rep(0, n)
    Qbeta_Ustar <- rep(0, ncol(Z))
    if (K1[1] != 0) {
      nullFit <- cox_MDTL(Z[, group == 0, drop = FALSE], delta, time, stratum,
                          beta = beta_ext, Q = Q, etas = eta, ties = "breslow")
      beta_U_star <- as.numeric(nullFit$beta)
      Qbeta_Ustar <- as.vector(Q[, group == 0, drop = FALSE] %*% beta_U_star)
      LinPred <- as.numeric(nullFit$linear.predictors)
      beta.init <- c(beta_U_star, rep(0, length(beta.init) - length(beta_U_star)))
    }
    r <- delta - exp(LinPred) * .breslow_cumhaz(LinPred, delta, stratum, tm)
  } else if (K1[1]!=0) {
    nullFit <- cox_MDTL(Z[, group == 0, drop = FALSE], delta, time, stratum,
                        beta = beta_ext, Q = Q, etas = eta)
    beta_U_star <- as.numeric(nullFit$beta) #low-dim unpenalized beta estimate
    Qbeta_Ustar <- as.vector(Q[, group == 0, drop = FALSE] %*% beta_U_star) #for calculate lambda_max

    LinPred <- as.numeric(nullFit$linear.predictors)
    beta.init <- c(beta_U_star, rep(0, length(beta.init) - length(beta_U_star)))
    rsk <- c()
    for (i in seq_along(unique(stratum))){
      rsk <- c(rsk, rev(cumsum(rev(exp(LinPred[stratum == i])))))
    }

    r <- numeric(length(delta))
    for (i in seq_along(unique(stratum))) {
      idx <- which(stratum == i)
      r[idx] <- delta[idx] - exp(LinPred[idx]) * cumsum(delta[idx] / rsk[idx])
    }
  } else {
    w <- c()
    h <- c()
    for (i in seq_along(unique(stratum))){
      temp.w <- 1 / (n.each_stratum[i] - (1:n.each_stratum[i]) + 1)
      w <- c(w, temp.w)
      h <- c(h, cumsum(delta[stratum == i] * temp.w))
    }
    r <- delta - h
    beta.init <- beta.init

    Qbeta_Ustar <- rep(0, ncol(Z))
  }

  zmax <- maxgrad_MDTL(Z, r / n, Qbeta_ext, Qbeta_Ustar,
                       K1, as.double(group.multiplier), eta)

  lambda.max <- zmax / alpha

  if (lambda.min.ratio == 0){
    lambda <- c(exp(seq(log(lambda.max), log(1e-7 * lambda.max), len = nlambda-1)), 0)
  } else {
    lambda <- exp(seq(log(lambda.max), log(lambda.min.ratio * lambda.max), len = nlambda))
  }
  lambda[1] <- lambda[1] + 1e-9
  ls <- list(beta = beta.init, lambda.seq = lambda)
  return(ls)
}


get_T_from_stdZ <- function(std.Z) {
  QL_list <- attr(std.Z$std.Z, "QL")
  ind <- !sapply(QL_list, is.null)
  Matrix::bdiag(QL_list[ind])
}



set.lambda.cox.enet <- function(delta.obs, Z, time, ID, beta, weight,
                                group, group.multiplier, n.each_prov,
                                alpha = 1, nlambda = 100,
                                lambda.min.ratio = 1e-03, tm = NULL) {

  K  <- table(group)
  K1 <- if (min(group) == 0) cumsum(K) else c(0, cumsum(K))
  storage.mode(K1) <- "integer"

  # the same denominator as the solver (src/cox_indi_enet.cpp): the row count, or the total
  # weight when the external rows are weighted above 1
  n_eff <- max(sum(weight), nrow(Z))

  if (!is.null(tm)) { # Breslow (1.3.0): the score at the null fit, with the tie-corrected risk sets
    if (K1[1] != 0) {
      nullFit <- survival::coxph(
        survival::Surv(time, delta.obs) ~ Z[, group == 0, drop = FALSE] + survival::strata(ID),
        weights = weight, ties = "breslow")
      eta_lp <- as.numeric(nullFit$linear.predictors)
      beta.initial <- c(nullFit$coefficients, rep(0.0, length(beta) - length(nullFit$coefficients)))
    } else {
      eta_lp <- rep(0, length(delta.obs))
      beta.initial <- beta
    }
    r <- weight * delta.obs - exp(eta_lp) * .breslow_cumhaz(eta_lp, weight * delta.obs, ID, tm)
  } else if (K1[1] != 0) {
    # Unpenalized covariates exist: fit null model on those first
    nullFit  <- survival::coxph(
      survival::Surv(time, delta.obs) ~ Z[, group == 0, drop = FALSE] +
        survival::strata(ID),
      weights = weight
    )
    eta_lp       <- nullFit$linear.predictors
    beta.initial <- c(nullFit$coefficients,
                      rep(0.0, length(beta) - length(nullFit$coefficients)))

    # Risk set: pure sum of exp(lp), NO weight
    rsk <- numeric(length(delta.obs))
    for (s in seq_along(unique(ID))) {
      idx <- which(ID == s)
      rsk[idx] <- rev(cumsum(rev(exp(eta_lp[idx]))))
    }

    # Residual: r_i = w_i * delta_i  -  exp(eta_i) * cumsum(w_j * delta_j / rsk_j)
    r <- numeric(length(delta.obs))
    for (s in seq_along(unique(ID))) {
      idx  <- which(ID == s)
      ex   <- exp(eta_lp[idx])
      dLam <- (weight[idx] * delta.obs[idx]) / rsk[idx]
      dLam[!is.finite(dLam)] <- 0
      Lam  <- cumsum(dLam)
      r[idx] <- weight[idx] * delta.obs[idx] - ex * Lam
    }

  } else {
    # All covariates penalized: score at beta = 0, exp(eta) = 1
    r <- numeric(length(delta.obs))
    for (s in seq_along(unique(ID))) {
      idx   <- which(ID == s)
      n_s   <- length(idx)
      rsk_s <- rev(cumsum(rep(1.0, n_s)))
      dLam  <- (weight[idx] * delta.obs[idx]) / rsk_s
      dLam[!is.finite(dLam)] <- 0
      Lam   <- cumsum(dLam)
      r[idx] <- weight[idx] * delta.obs[idx] - Lam
    }
    beta.initial <- beta
  }

  lambda.max <- maxgrad_indi(Z, r, K1, as.double(group.multiplier), n_eff) / alpha

  lambda.seq <- exp(seq(log(lambda.max),
                        log(lambda.min.ratio * lambda.max),
                        length.out = nlambda))
  lambda.seq[1] <- lambda.seq[1] + 1e-5

  list(beta = beta.initial, lambda.seq = lambda.seq)
}





## ---------------------------------------------------------------------------------------------------
## Breslow tie correction (1.3.0)
##
## Every estimator of the family fits the Cox partial likelihood on data sorted by stratum and then by
## time. Without a tie correction ("none", the behaviour of every release before 1.3.0) the risk set of an
## event is everyone from its own row onward, so among subjects who share an event time the earlier rows
## are dropped from the later rows' risk sets, and the result depends on how the tied rows happen to be
## ordered. Under Breslow's approximation the risk set at time t is everyone whose time is t or later. The
## engines read two maps for this: for each sorted row, the 0-based index of the first and of the last row
## of its stratum with the same time. NULL maps (ties = "none") leave every engine on its pre-1.3.0 path.
.check_ties <- function(ties) {
  if (length(ties) != 1L || !ties %in% c("none", "breslow")) {
    stop("'ties' must be \"none\" or \"breslow\".", call. = FALSE)
  }
  ties
}

.tie_maps <- function(time, n_each, ties = "none") {
  if (identical(ties, "none")) return(NULL)
  n <- length(time)
  if (sum(n_each) != n) stop("tie maps: the stratum sizes do not add up to the number of rows.")
  first <- integer(n); last <- integer(n)
  ends <- cumsum(n_each); starts <- ends - n_each + 1
  for (s in seq_along(n_each)) {
    if (n_each[s] == 0) next
    idx <- starts[s]:ends[s]
    tt <- time[idx]
    if (is.unsorted(tt)) stop("tie maps: time must be sorted within each stratum.")
    g <- c(1L, 1L + cumsum(diff(tt) != 0))
    first[idx] <- idx[match(g, g)]
    last[idx] <- idx[length(g) + 1L - match(g, rev(g))]
  }
  list(first = first - 1L, last = last - 1L)
}

## the log partial likelihood the family scores with: Breslow's when ties = "breslow", else the
## pre-1.3.0 one. Data sorted by stratum then time, as for the maps.
.pl_ties <- function(lp, delta, time, n_each, ties = "none") {
  if (identical(ties, "breslow")) {
    ends <- cumsum(n_each); starts <- ends - n_each + 1
    for (s in seq_along(n_each)) if (n_each[s] > 1 && is.unsorted(time[starts[s]:ends[s]]))
      stop("the Breslow likelihood needs time sorted within each stratum.", call. = FALSE)
    pl_cal_breslow(as.numeric(lp), as.numeric(delta), as.numeric(time), n_each)
  } else pl_cal_theta(lp, delta, n_each)
}


## Breslow (1.3.0): each row's cumulative hazard at its own time, sum over the event times up to and
## including it of (event weight) / (risk-set sum), with the risk set of a tie group starting at its first
## row and every row of a tie group carrying the hazard up to its last row. `dw` is the event weight per
## row (delta, or weight * delta); data sorted by stratum then time, `tm` from .tie_maps.
.breslow_cumhaz <- function(lp, dw, stratum, tm) {
  ex <- exp(as.numeric(lp)); n <- length(ex)
  rsk <- numeric(n); H <- numeric(n)
  for (s in unique(stratum)) { idx <- which(stratum == s); rsk[idx] <- rev(cumsum(rev(ex[idx]))) }
  rsk <- rsk[tm$first + 1L]
  d <- dw / rsk; d[!is.finite(d)] <- 0
  for (s in unique(stratum)) { idx <- which(stratum == s); H[idx] <- cumsum(d[idx]) }
  H[tm$last + 1L]
}

## the tie handling a fitted object records (objects from releases before 1.3.0 carry none: "none")
.fit_ties <- function(object) {
  t <- object$ties
  if (is.null(t)) "none" else .check_ties(t)
}
