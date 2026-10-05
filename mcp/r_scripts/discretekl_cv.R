## discretekl_cv.R -- DiscreteKL (Wang et al., AoAS) with an external Cox model as teacher.
##
## Requires the DiscreteKL package in this folder:
##   R CMD build DiscreteKL && R CMD INSTALL DiscreteKL_1.0.tar.gz
## The estimator is DiscreteKL::discSurvKL_cloglog (Newton-Raphson in C++); this
## file adds what a fit needs around it: the Cox-to-discrete teacher, feature
## scaling, the exact complementary log-log log-likelihood, K-fold selection of
## eta by held-out NLL, and prediction.  The same steps produced the
## DiscreteKL / Internal-DiscreteKL rows of the MIUM comparison
## (60_refit_discretekl_deviance.R); the code below is that logic without the
## manifest bookkeeping.
##
## Data convention
##   time_bin  integer 1..K (K discrete intervals), event 0/1, x numeric n x p matrix
##   with column names.  Every interval 1..K must occur in the training data (true
##   under administrative censoring at the horizon): the package fits one baseline
##   parameter per observed interval.
## Model:  h_k(x) = 1 - exp(-exp(gamma_k + x'beta)),   S_k(x) = prod_{j<=k} (1 - h_j(x)).
## Teacher from an external Cox model with coefficients beta_ext and baseline
## cumulative-hazard increments dH0_k over the K intervals:  gamma_k = log(dH0_k),
## beta = beta_ext on the external columns and 0 elsewhere.  The KL penalty
## eta * KL(teacher || student) is added to the internal log-likelihood; eta = 0
## is the internal-only model.
##
## Usage
##   source("discretekl_cv.R")
##   teacher <- dkl_teacher(beta_ext, dH0, colnames(x))
##   cv      <- dkl_cv(time_bin, x, event, teacher, etas = c(0, 1, 5, 10, 20, 50, 100))
##   cv$eta; cv$pooled                         # selected eta and the CV path
##   pred    <- dkl_predict(cv$fit, x_new)     # $lp, $hazard (n x K), $survival (n x K)
##   pred0   <- dkl_predict(cv$internal, x_new)
##   Rscript discretekl_cv.R --self-test

dkl_teacher <- function(beta_ext, dH0, colnames_x) {
  if (is.null(names(beta_ext)) || !all(names(beta_ext) %in% colnames_x)) {
    stop("beta_ext must be named and every name must be a column of x")
  }
  dH0 <- as.numeric(dH0)
  if (any(!is.finite(dH0)) || any(dH0 < 0) || !any(dH0 > 0)) stop("dH0 must be finite, >= 0, not all zero")
  beta <- setNames(numeric(length(colnames_x)), colnames_x)
  beta[names(beta_ext)] <- as.numeric(beta_ext)
  list(beta = beta, gamma = log(pmax(dH0, 1e-12)))
}

dkl_scaler <- function(x) {
  center <- colMeans(x)
  spread <- apply(x, 2L, stats::sd)
  spread[!is.finite(spread) | spread <= sqrt(.Machine$double.eps)] <- 1
  list(center = center, scale = spread)
}
dkl_scale <- function(x, s) sweep(sweep(as.matrix(x), 2L, s$center, "-"), 2L, s$scale, "/")
dkl_scale_teacher <- function(teacher, s) {
  list(beta = unname(s$scale * teacher$beta), gamma = unname(teacher$gamma + sum(s$center * teacher$beta)))
}
dkl_unscale <- function(beta_scaled, gamma_scaled, s) {
  beta <- setNames(as.numeric(beta_scaled) / s$scale, names(s$scale))
  list(beta = beta, gamma = as.numeric(gamma_scaled) - sum(s$center * beta))
}

## log h for h = 1 - exp(-exp(u)), stable for large and small u
dkl_log_hazard <- function(u) {
  out <- numeric(length(u))
  high <- u > 3.6
  out[high] <- log1p(-exp(-exp(u[high])))
  out[!high] <- log(-expm1(-exp(u[!high])))
  out
}

## exact log-likelihood of the cloglog model (raw or scaled scale, as long as x, gamma, beta agree)
dkl_loglik <- function(time_bin, x, event, gamma, beta, per_subject = FALSE) {
  time_bin <- as.integer(time_bin); event <- as.integer(event)
  if (any(time_bin < 1L) || any(time_bin > length(gamma))) stop("time_bin outside 1..length(gamma)")
  lp <- drop(as.matrix(x) %*% as.numeric(beta))
  cum <- cumsum(exp(as.numeric(gamma)))
  survived_before <- ifelse(time_bin > 1L, -exp(lp) * cum[pmax(time_bin - 1L, 1L)], 0)
  ll <- ifelse(event == 1L,
               survived_before + dkl_log_hazard(gamma[time_bin] + lp),
               -exp(lp) * cum[time_bin])
  if (per_subject) ll else sum(ll)
}

## one fit at a given eta; returns parameters on the raw scale plus the scaler
dkl_fit <- function(time_bin, x, event, teacher, eta, tol = 1e-20, max_iter = 25L) {
  if (!requireNamespace("DiscreteKL", quietly = TRUE)) stop("install the DiscreteKL package first")
  x <- as.matrix(x); time_bin <- as.integer(time_bin); event <- as.integer(event)
  K <- length(teacher$gamma)
  if (max(time_bin) != K) stop("the training data must contain interval K = ", K, " (max time_bin is ", max(time_bin), ")")
  if (!identical(names(teacher$beta), colnames(x))) stop("teacher$beta must be named like the columns of x")
  s <- dkl_scaler(x)
  xs <- dkl_scale(x, s)
  ts <- dkl_scale_teacher(teacher, s)
  obj <- DiscreteKL::discSurvKL_cloglog(t = time_bin, X = xs, ind = event, tol = tol, max_iter = max_iter,
                                        beta_t_tilde = ts$gamma, beta_v_tilde = ts$beta, eta = eta)
  gamma_s <- as.numeric(obj$beta_t); beta_s <- as.numeric(obj$beta_v)
  if (length(gamma_s) != K || length(beta_s) != ncol(x) || any(!is.finite(c(gamma_s, beta_s)))) {
    stop("DiscreteKL returned a non-finite or mis-sized fit at eta = ", eta)
  }
  ## first-order condition of the penalised likelihood at the solution: a convergence diagnostic
  upd <- DiscreteKL::UpdateKL_cloglog(t = as.matrix(time_bin), X = xs, delta = as.matrix(event),
                                      beta_t = as.matrix(gamma_s), beta_v = as.matrix(beta_s),
                                      max_t = K, c = ncol(x), r = nrow(x),
                                      beta_t_tilde = as.matrix(ts$gamma), beta_v_tilde = as.matrix(ts$beta),
                                      eta = eta, epsilon = .Machine$double.eps)
  raw <- dkl_unscale(beta_s, gamma_s, s)
  list(eta = eta, beta = raw$beta, gamma = raw$gamma, scaler = s, K = K,
       loglik_train = dkl_loglik(time_bin, x, event, raw$gamma, raw$beta),
       score_max_abs = max(abs(c(as.numeric(upd$score_t), as.numeric(upd$score_v)))))
}

dkl_predict <- function(fit, x_new) {
  x_new <- as.matrix(x_new)
  if (!identical(colnames(x_new), names(fit$beta))) stop("x_new must have the training columns")
  lp <- drop(x_new %*% fit$beta)
  hazard <- 1 - exp(-exp(outer(lp, fit$gamma, "+")))
  colnames(hazard) <- paste0("interval_", seq_len(fit$K))
  list(lp = lp, hazard = hazard, survival = t(apply(1 - hazard, 1L, cumprod)))
}

## K-fold selection of eta by pooled held-out NLL per subject (ties -> smaller eta),
## then final fits at the selected eta and at eta = 0 (Internal-DiscreteKL) on all data.
dkl_cv <- function(time_bin, x, event, teacher, etas = c(0, 1, 5, 10, 20, 50, 100),
                   folds = NULL, nfold = 5L, seed = 1L, tol = 1e-20, max_iter = 25L) {
  x <- as.matrix(x); time_bin <- as.integer(time_bin); event <- as.integer(event)
  etas <- sort(unique(as.numeric(etas)))
  if (!any(etas == 0)) stop("etas must contain 0 (the internal-only model)")
  if (is.null(folds)) { # event-stratified folds
    set.seed(seed, kind = "Mersenne-Twister")
    folds <- integer(length(event))
    for (v in c(0L, 1L)) { i <- sample(which(event == v)); folds[i] <- 1L + (seq_along(i) - 1L) %% nfold }
  }
  path <- list()
  for (f in sort(unique(folds))) {
    tr <- folds != f; va <- !tr
    for (eta in etas) {
      fit <- tryCatch(dkl_fit(time_bin[tr], x[tr, , drop = FALSE], event[tr], teacher, eta, tol, max_iter),
                      error = function(e) e)
      ok <- !inherits(fit, "error")
      ll <- if (ok) dkl_loglik(time_bin[va], x[va, , drop = FALSE], event[va], fit$gamma, fit$beta) else NA_real_
      path[[length(path) + 1L]] <- data.frame(
        eta = eta, fold = f, n_valid = sum(va), loglik_valid = ll,
        status = if (!ok) conditionMessage(fit) else if (is.finite(ll)) "ok" else "nonfinite", stringsAsFactors = FALSE)
    }
  }
  path <- do.call(rbind, path)
  pooled <- do.call(rbind, lapply(etas, function(eta) {
    rows <- path[path$eta == eta, ]
    complete <- all(rows$status == "ok")
    data.frame(eta = eta, complete = complete,
               nll_per_subject = if (complete) -sum(rows$loglik_valid) / sum(rows$n_valid) else NA_real_)
  }))
  if (!any(pooled$complete)) stop("no eta completed every fold")
  if (!pooled$complete[pooled$eta == 0]) stop("the eta = 0 fit (Internal-DiscreteKL) failed in some fold")
  cand <- pooled[pooled$complete, ]
  eta_sel <- cand$eta[order(cand$nll_per_subject, cand$eta)][1L]
  fit <- dkl_fit(time_bin, x, event, teacher, eta_sel, tol, max_iter)
  internal <- if (eta_sel == 0) fit else dkl_fit(time_bin, x, event, teacher, 0, tol, max_iter)
  list(eta = eta_sel, fit = fit, internal = internal, cv_path = path, pooled = pooled, folds = folds)
}

## ---- self-test: simulated cloglog data, the true model as the external teacher -----
if (!interactive() && any(commandArgs(trailingOnly = TRUE) == "--self-test")) {
  set.seed(11)
  n <- 400; p <- 5; K <- 12
  beta <- c(0.8, -0.8, 0.5, 0, 0.3); alpha <- seq(-3, -1.5, length.out = K)
  x <- matrix(rnorm(n * p), n, p, dimnames = list(NULL, paste0("z", 1:p)))
  lp <- drop(x %*% beta)
  h <- 1 - exp(-exp(outer(lp, alpha, "+")))
  u <- matrix(runif(n * K), n, K)
  ev <- apply(u < h, 1L, function(r) if (any(r)) which(r)[1L] else NA)
  tb <- ifelse(is.na(ev), K, ev); event <- as.integer(!is.na(ev))
  cens <- sample.int(K, n, replace = TRUE); cc <- cens < tb; tb[cc] <- cens[cc]; event[cc] <- 0L
  tb[1L] <- K # make sure interval K is observed
  teacher <- dkl_teacher(setNames(beta, colnames(x)), exp(alpha), colnames(x))
  tr <- 1:120; te <- 121:n
  cv <- dkl_cv(tb[tr], x[tr, ], event[tr], teacher, etas = c(0, 1, 5, 20, 100), seed = 3)
  ## eta = 0 equals the package's unpenalised fit on the same scaled data
  s <- dkl_scaler(x[tr, ]); ref <- DiscreteKL::discSurv_cloglog(tb[tr], dkl_scale(x[tr, ], s), event[tr])
  stopifnot(isTRUE(all.equal(unname(as.numeric(ref$beta_v) / s$scale), unname(cv$internal$beta), tolerance = 1e-8)))
  pred <- dkl_predict(cv$fit, x[te, ]); pred0 <- dkl_predict(cv$internal, x[te, ])
  stopifnot(all(is.finite(pred$hazard)), all(diff(t(pred$survival)) <= 1e-12), ncol(pred$hazard) == K)
  nll <- function(f) -mean(dkl_loglik(tb[te], x[te, ], event[te], f$gamma, f$beta, per_subject = TRUE))
  cat(sprintf("self-test: n_train=%d events=%d | selected eta=%g | score max|.|=%.1e\n",
              length(tr), sum(event[tr]), cv$eta, cv$fit$score_max_abs))
  print(cv$pooled, row.names = FALSE)
  cat(sprintf("test NLL per subject: DiscreteKL=%.4f  Internal=%.4f\n", nll(cv$fit), nll(cv$internal)))
  cat("discretekl_cv.R self-test: PASS\n")
}
