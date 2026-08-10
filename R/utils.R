#' Generate a Sequence of Tuning Parameters (eta)
#'
#' Produces a numeric vector of `eta` values to be used in Cox–KL model.
#'
#' @param method Character string selecting how to generate \code{eta}:
#'   \dQuote{linear} or \dQuote{exponential}. Default is \dQuote{exponential}.
#'   for an exponentially spaced sequence scaled to `max_eta`. Default is `"exponential"`.
#' @param n Integer, the number of `eta` values to generate. Default is 10.
#' @param max_eta Numeric, the maximum value of `eta` in the sequence. Default is 5.
#' @param min_eta Numeric, the minimum value of `eta` in the sequence. Default is 0.
#'
#' @details
#' \itemize{
#'   \item \emph{Exponential}: values are formed by exponentiating a grid from
#'     \code{log(1)} to \code{log(100)}, then linearly rescaling to the interval
#'     \code{[0, max_eta]}. Thus the smallest value equals \code{0} and the largest
#'     equals \code{max_eta}.
#'   \item \emph{Linear}: the current implementation calls
#'     \code{seq(min_eta, max_eta, length.out = n)} and therefore assumes a
#'     numeric object \code{min_eta} exists in the calling environment.
#' }
#' Only the exact strings \dQuote{linear} and \dQuote{exponential} are supported;
#' other values for \code{method} will result in an error because \code{eta_values}
#' is never created.
#'
#' @return Numeric vector of length \code{n} containing the generated \code{eta} values.
#'
#' @examples
#' # Generate 10 exponentially spaced eta values up to 5
#' generate_eta(method = "exponential", n = 10, max_eta = 5)
#'
#' # Generate 5 linearly spaced eta values up to 3
#' generate_eta(method = "linear", n = 5, min_eta= 0, max_eta = 3)
#'
#' @export
generate_eta <- function(method = "exponential", n = 10, max_eta = 5, min_eta = 0) {
  if (method == "linear") {
    eta_values <- seq(min_eta, max_eta, length.out = n)
  } else if (method == "exponential") {
    eta_values <- exp(seq(log(1), log(100), length.out = n))
    eta_values <- (eta_values - min(eta_values)) / (max(eta_values) - min(eta_values)) * max_eta
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


# Internal worker shared by align_beta() and align_beta_Q().
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
#' @param z Internal covariate matrix or data frame. Its columns define the
#'   target coefficient space; column names, when present, are used for matching.
#' @param beta External coefficient vector (optionally named).
#' @param arg Name used for \code{beta} in error messages.
#'
#' @return A numeric vector of length \code{ncol(z)}, ordered to \code{colnames(z)}.
#' @seealso \code{\link{align_beta_Q}} for the Mahalanobis-distance setting.
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
#' @param z Internal covariate matrix or data frame.
#' @param beta External coefficient vector (optionally named).
#' @param Q Optional weighting/precision matrix (optionally with dimnames). If
#'   \code{NULL}, a masked identity is used.
#' @param arg_beta,arg_Q Names used for \code{beta} and \code{Q} in error messages.
#'
#' @return A list with components \code{beta} (numeric, length \code{ncol(z)}),
#'   \code{Q} (\code{ncol(z)} by \code{ncol(z)} matrix), and \code{provided}
#'   (logical mask of covariates supplied by the external source).
#' @seealso \code{\link{align_beta}}
#' @export
align_beta_Q <- function(z, beta, Q = NULL, arg_beta = "beta", arg_Q = "Q") {
  al <- .align_beta(z, beta, arg = arg_beta)
  p <- length(al$beta)
  znames <- colnames(z)

  if (is.null(Q)) {
    Q_full <- diag(as.numeric(al$provided), nrow = p)
  } else {
    Q <- as.matrix(Q)
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
                             eta, nlambda, lambda.min.ratio) {
  n <- nrow(Z)
  K <- table(group)
  K1 <- as.integer(if (min(group)==0) cumsum(K) else c(0, cumsum(K)))
  storage.mode(K1) <- "integer"
  if (K1[1]!=0) { ## some covariates are not penalized
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
  dropped <- setdiff(g, new)  # If the entire group has been dropped
  if (length(dropped) > 0) {
    lev <- lev[-dropped] # remaining group
    m <- m[-dropped]
    group.factor <- factor(new) #remaining group factor
    new <- as.integer(group.factor) - 1 * any(levels(group.factor) == '0')  #new group index
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
  original.beta[std.Z$nz, ] <- beta / std.Z$scale[std.Z$nz]  # modified beta
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
    SVD <- svd(Z[, ind, drop = FALSE], nu = 0)  # Q matrix (orthonormal matrix of eigenvectors)
    r <- which(SVD$d > 1e-10)  #remove extremely small singular values
    QL[[j]] <- sweep(SVD$v[, r, drop = FALSE], 2, sqrt(n)/SVD$d[r], "*") # Q * Lambda^{-1/2}
    orthog.Z[, ind[r]] <- Z[, ind] %*% QL[[j]]  # group orthogonalized X, where (X^T * X)/n = I
  }
  nz <- !apply(orthog.Z == 0, 2, all)  #find all zero
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
  } else {  # all groups are penalized
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

  nz <- which(scale > 1e-6)   # non-constant columns
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
                             eta, nlambda, lambda.min.ratio) {
  n <- nrow(Z)
  K <- table(group)
  K1 <- as.integer(if (min(group)==0) cumsum(K) else c(0, cumsum(K)))
  storage.mode(K1) <- "integer"


  if (K1[1]!=0) {
    nullFit <- cox_MDTL(Z[, group == 0, drop = FALSE], delta, time, stratum,
                        beta = beta_ext, Q = Q, etas = eta)
    beta_U_star <- as.numeric(nullFit$beta)  #low-dim unpenalized beta estimate
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
                                lambda.min.ratio = 1e-03) {

  K  <- table(group)
  K1 <- if (min(group) == 0) cumsum(K) else c(0, cumsum(K))
  storage.mode(K1) <- "integer"

  # n_eff <- sum(weight)
  n_eff <- nrow(Z)

  if (K1[1] != 0) {
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



