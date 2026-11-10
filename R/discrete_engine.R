## The grouped-time (discrete-time) model with a linear risk score: the machinery shared by the
## discretekl, discrete_MDTL and discrete_indi families, and by cv.bregsurv() on a discrete target.
##
## Subject i is at risk in intervals 1..t_i, and y_ik = 1 when the event happens in interval k = t_i.
## The interval hazard is h_ik = g^{-1}(gamma_{s(i),k} + z_i' beta), with g the complementary log-log
## (grouped proportional hazards) or logit link. Every member of the framework is a weighted Bernoulli
## likelihood on the person-intervals, so one solver fits all of them:
##
##   none          -l(theta) / n
##   kl            sum_ik BCE(soft_ik, h_ik) / n,  soft = (y + eta * h_ext) / (1 + eta)        [the KL
##                 divergence between the external and target interval hazards, as for the Cox model]
##   mahalanobis   -l(theta) / n + (eta / 2) (beta - beta_ext)' Q (beta - beta_ext)            [same scale
##                 as cox_MDTL]
##   composite     -(l(theta) + eta * l_ext(theta)) / n, the external records with their own baseline
##
## plus lambda * (alpha |beta|_1 + (1 - alpha) / 2 |beta|^2). The solver is src/discrete.cpp: Fisher
## scoring with the interval parameters profiled out by their (diagonal) Schur complement; lasso and
## elastic net by proximal Newton with coordinate descent. Every quantity is an n x K matrix of
## subjects by intervals.

.DT_FLOOR <- 1e-8   # lower bound on an interval hazard's baseline: an interval with no events in the
                    # training data would otherwise send its parameter to minus infinity

.dt_gamma_min <- function(link) if (link == "cloglog") log(-log1p(-.DT_FLOOR)) else stats::qlogis(.DT_FLOOR)
.dt_link_code <- function(link) if (link == "cloglog") 0L else 1L

## one block of person-intervals: Z (n x p), interval (1..K), cell row (index into the gamma matrix),
## target matrix Tm (n x K), weight matrix Wt (n x K, zero where not at risk)
.dt_block <- function(Z, interval, event, cell, K, weight = 1, soft = NULL, eta = 0) {
  n <- nrow(Z)
  M <- outer(interval, seq_len(K), ">=") * 1
  Y <- matrix(0, n, K)
  ev <- which(event == 1)
  Y[cbind(ev, interval[ev])] <- 1
  Tm <- if (is.null(soft)) Y else (Y + eta * soft) / (1 + eta)
  list(Z = Z, interval = interval, event = event, cell = cell, M = M, Y = Y, Tm = Tm * M, Wt = weight * M)
}

## the blocks stacked into the arrays the C++ solver takes (cells 0-based)
.dt_stack <- function(blocks) {
  if (length(blocks) == 1L) {
    b <- blocks[[1]]
    return(list(Z = b$Z, cell = as.integer(b$cell) - 1L, Tm = b$Tm, Wt = b$Wt))
  }
  list(Z = do.call(rbind, lapply(blocks, `[[`, "Z")),
       cell = as.integer(unlist(lapply(blocks, `[[`, "cell"))) - 1L,
       Tm = do.call(rbind, lapply(blocks, `[[`, "Tm")),
       Wt = do.call(rbind, lapply(blocks, `[[`, "Wt")))
}

.dt_Qm <- function(pen) if (is.null(pen$Qm)) matrix(0, 0, 0) else pen$Qm
.dt_bext <- function(pen) if (is.null(pen$Qm) || is.null(pen$bext)) numeric(0) else as.numeric(pen$bext)

## Fit at one (eta, lambda). blocks already standardized; returns gamma (cells x K) and beta on the
## standardized scale. alpha = 0 is ridge; lambda = 0 is unpenalized.
.dt_solve <- function(blocks, link, n, K, n_cell, pen, beta0, G0, tol = 1e-9, max_iter = 200) {
  s <- .dt_stack(blocks)
  dt_solve_cpp(s$Z, s$cell, s$Tm, s$Wt, .dt_link_code(link), as.numeric(n), as.integer(n_cell),
               as.numeric(pen$lambda), as.numeric(pen$alpha), .dt_Qm(pen), .dt_bext(pen),
               as.numeric(pen$eta_m), as.numeric(beta0), G0, .dt_gamma_min(link), tol, as.integer(max_iter))
}

## ---------------------------------------------------------------------------------------------------
## Preparation: cells, standardization, member data
## ---------------------------------------------------------------------------------------------------
.dt_prepare <- function(tg, member, ext, standardize) {
  z <- tg$z; p <- ncol(z)
  center <- colMeans(z)
  scale <- if (standardize) apply(z, 2, stats::sd) else rep(1, p)
  scale[!is.finite(scale) | scale <= sqrt(.Machine$double.eps)] <- 1
  zs <- sweep(sweep(z, 2, center, "-"), 2, scale, "/")
  s_lab <- if (is.null(tg$stratum)) rep(1L, tg$n) else match(tg$stratum, unique(tg$stratum))
  n_int_cell <- max(s_lab)
  out <- list(z = z, zs = zs, center = center, scale = scale, cell = s_lab, n_int_cell = n_int_cell,
              strata_levels = if (is.null(tg$stratum)) NULL else unique(tg$stratum),
              member = member, K = tg$K, link = tg$link, interval = tg$interval, event = tg$event)
  if (member == "kl") out$teacher <- ext$teacher
  if (member == "mahalanobis") {
    out$bext <- ext$beta * scale
    Qm <- ext$Q
    if (!isTRUE(ext$manufactured)) Qm <- Qm / outer(scale, scale)
    out$Qm <- Qm
  }
  if (member == "composite") {
    ze <- sweep(sweep(ext$z, 2, center, "-"), 2, scale, "/")
    se <- if (is.null(ext$stratum)) rep(1L, nrow(ze)) else match(ext$stratum, unique(ext$stratum))
    out$ext <- list(zs = ze, interval = ext$interval, event = ext$event, cell = n_int_cell + se)
    out$n_cell <- n_int_cell + max(se)
  } else out$n_cell <- n_int_cell
  out
}

.dt_blocks <- function(pr, rows, eta) {
  K <- pr$K
  b1 <- .dt_block(pr$zs[rows, , drop = FALSE], pr$interval[rows], pr$event[rows], pr$cell[rows], K,
                  soft = if (pr$member == "kl" && eta > 0) pr$teacher[rows, , drop = FALSE] else NULL, eta = eta)
  blocks <- list(b1)
  if (pr$member == "composite" && eta > 0)
    blocks[[2]] <- .dt_block(pr$ext$zs, pr$ext$interval, pr$ext$event, pr$ext$cell, K, weight = eta)
  blocks
}

.dt_pen <- function(pr, eta, lambda, alpha) {
  list(lambda = lambda, alpha = alpha,
       Qm = if (pr$member == "mahalanobis" && eta > 0) pr$Qm else NULL,
       bext = pr$bext, eta_m = eta)
}

## the hard log-likelihood of subjects `rows` under (G, beta) on the standardized scale, per subject
.dt_loglik_rows <- function(pr, rows, G, beta) {
  b <- .dt_block(pr$zs[rows, , drop = FALSE], pr$interval[rows], pr$event[rows], pr$cell[rows], pr$K)
  U <- G[b$cell, , drop = FALSE] + drop(b$Z %*% beta)
  lh <- if (pr$link == "cloglog") { e <- exp(U); ifelse(U > 3.6, log1p(-exp(-e)), log(-expm1(-e))) } else
    -log1p(exp(-U))
  l1h <- if (pr$link == "cloglog") -exp(U) else -log1p(exp(U))
  rowSums(b$M * (b$Y * lh + (1 - b$Y) * l1h))
}

## start values for the interval parameters: the empirical hazard of each cell
.dt_gamma_start <- function(blocks, n_cell, K, link) {
  ev <- matrix(0, n_cell, K); at <- matrix(0, n_cell, K)
  for (b in blocks) for (cc in unique(b$cell)) {
    idx <- b$cell == cc
    ev[cc, ] <- ev[cc, ] + colSums(b$Y[idx, , drop = FALSE]); at[cc, ] <- at[cc, ] + colSums(b$M[idx, , drop = FALSE])
  }
  h <- pmin(pmax((ev + 0.5) / (at + 1), 1e-4), 0.5)
  if (link == "cloglog") log(-log1p(-h)) else stats::qlogis(h)
}

## the smallest lambda at which every coefficient is zero (divided by alpha for the elastic net)
.dt_lambda_max <- function(pr, rows, eta, alpha, link) {
  blocks <- .dt_blocks(pr, rows, eta)
  pen0 <- .dt_pen(pr, eta, 0, 0)
  G0 <- .dt_gamma_start(blocks, pr$n_cell, pr$K, link)
  s <- .dt_stack(blocks)
  r <- dt_null_fit_cpp(s$Z, s$cell, s$Tm, s$Wt, .dt_link_code(link), as.numeric(length(rows)),
                       as.integer(pr$n_cell), .dt_Qm(pen0), .dt_bext(pen0), as.numeric(eta), G0,
                       .dt_gamma_min(link))
  r$max_gradient / max(alpha, 1e-3)
}

.dt_unscale <- function(pr, beta_s, G_s) {
  beta <- beta_s / pr$scale
  names(beta) <- colnames(pr$z)
  G <- G_s - sum(pr$center * beta)
  gamma <- G[seq_len(pr$n_int_cell), , drop = FALSE]
  dimnames(gamma) <- list(.dt_cell_names(pr), paste0("interval_", seq_len(pr$K)))
  list(beta = beta, gamma = gamma)
}

.dt_cell_names <- function(pr) if (is.null(pr$strata_levels)) "baseline" else as.character(pr$strata_levels)

## ---------------------------------------------------------------------------------------------------
## Paths and cross-validation
## ---------------------------------------------------------------------------------------------------

## the penalty path at one eta: given, or log spaced down from lambda_max
.dt_lambda_seq <- function(pr, rows, eta, penalty, alpha, lambda, nlambda, lambda.min.ratio) {
  if (penalty == "none") return(0)
  if (!is.null(lambda)) return(sort(as.numeric(lambda), decreasing = TRUE))
  n <- length(rows); p <- ncol(pr$z)
  lmax <- .dt_lambda_max(pr, rows, eta, if (penalty == "ridge") 1 else alpha, pr$link)
  if (penalty == "ridge") lmax <- lmax * 1e3
  ratio <- if (is.null(lambda.min.ratio)) (if (n < p) 0.05 else 1e-3) else lambda.min.ratio
  if (penalty == "ridge") ratio <- ratio * 1e-1
  exp(seq(log(lmax), log(lmax * ratio), length.out = nlambda))
}

## fits along a penalty path at one eta on subjects `rows`, with warm starts
.dt_path <- function(pr, rows, eta, lams, alpha, tol, max_iter, keep_errors = FALSE) {
  blocks <- .dt_blocks(pr, rows, eta)
  G <- .dt_gamma_start(blocks, pr$n_cell, pr$K, pr$link); b <- numeric(ncol(pr$z))
  fits <- vector("list", length(lams))
  for (l in seq_along(lams)) {
    f <- if (keep_errors) tryCatch(.dt_solve(blocks, pr$link, length(rows), pr$K, pr$n_cell,
                                             .dt_pen(pr, eta, lams[l], alpha), b, G, tol, max_iter),
                                   error = function(e) e)
         else .dt_solve(blocks, pr$link, length(rows), pr$K, pr$n_cell, .dt_pen(pr, eta, lams[l], alpha),
                        b, G, tol, max_iter)
    fits[[l]] <- f
    if (!inherits(f, "error")) { b <- f$beta; G <- f$G }
  }
  fits
}

## cross-validation over (eta, lambda); the score is the pooled held-out negative log-likelihood per
## subject of the grouped-time model, the same functional for every member and every penalty
.dt_cv_core <- function(pr, etas, penalty, alpha, lambda, nlambda, lambda.min.ratio, folds, tol, max_iter,
                        message = FALSE) {
  n <- length(pr$interval)
  fold_ids <- sort(unique(folds))
  path <- list(); full <- list()
  if (message) pb <- utils::txtProgressBar(min = 0, max = length(etas), style = 3, width = 30)
  for (e in seq_along(etas)) {
    eta <- etas[e]
    all_rows <- seq_len(n)
    lams <- .dt_lambda_seq(pr, all_rows, eta, penalty, alpha, lambda, nlambda, lambda.min.ratio)
    full[[as.character(eta)]] <- list(lambda = lams, fits = .dt_path(pr, all_rows, eta, lams, alpha, tol, max_iter))
    for (fo in fold_ids) {
      tr <- which(folds != fo); va <- which(folds == fo)
      fits <- .dt_path(pr, tr, eta, lams, alpha, tol, max_iter, keep_errors = TRUE)
      for (l in seq_along(lams)) {
        f <- fits[[l]]
        ok <- !inherits(f, "error")
        ll <- if (ok) sum(.dt_loglik_rows(pr, va, f$G, f$beta)) else NA_real_
        path[[length(path) + 1]] <- data.frame(eta = eta, lambda = lams[l], fold = fo, n_valid = length(va),
                                               loglik_valid = ll, ok = ok && is.finite(ll))
      }
    }
    if (message) utils::setTxtProgressBar(pb, e)
  }
  if (message) close(pb)
  path <- do.call(rbind, path)
  key <- paste(path$eta, path$lambda)
  pooled <- do.call(rbind, lapply(split(path, factor(key, levels = unique(key))), function(r)
    data.frame(eta = r$eta[1], lambda = r$lambda[1], complete = all(r$ok),
               loss = if (all(r$ok)) -sum(r$loglik_valid) / sum(r$n_valid) else NA_real_)))
  rownames(pooled) <- NULL
  list(path = path, pooled = pooled, full = full)
}

## ---------------------------------------------------------------------------------------------------
## The exported families: validation through the target and release constructors, then formatting
## ---------------------------------------------------------------------------------------------------
.dt_setup <- function(member, z, delta, interval, stratum, link, n_intervals, standardize,
                      hazard = NULL, beta = NULL, baseline = NULL, Q = NULL,
                      z_ext = NULL, delta_ext = NULL, interval_ext = NULL, stratum_ext = NULL) {
  if (member == "composite" && is.null(n_intervals)) n_intervals <- max(c(interval, interval_ext))
  tg <- target_discrete(interval, delta, z, stratum = stratum, link = link, n_intervals = n_intervals)
  rel <- switch(member,
    kl = release_model(beta = beta, baseline = baseline, hazard = hazard),
    mahalanobis = release_coef(beta, Q),
    composite = release_records(z_ext, event = delta_ext, interval = interval_ext, stratum = stratum_ext))
  ext <- .ext_for_discrete(tg, rel, member)
  list(tg = tg, ext = ext, pr = .dt_prepare(tg, member, ext, standardize))
}

.dt_check_alpha <- function(alpha) {
  if (length(alpha) != 1 || !is.finite(alpha) || alpha <= 0 || alpha > 1)
    stop("'alpha' must be in (0, 1]; alpha = 1 is the lasso.", call. = FALSE)
  alpha
}

.dt_check_eta1 <- function(eta) {
  if (is.null(eta)) {
    warning("eta is not provided. Setting eta = 0 (no external information used).", call. = FALSE)
    eta <- 0
  }
  check_etas(eta, scalar = TRUE, arg = "eta")
  eta
}

## coefficients, baselines and log-likelihoods of a list of fits, on the original scale
.dt_collect <- function(pr, fits, labels) {
  L <- length(fits); p <- ncol(pr$z)
  beta <- matrix(NA_real_, p, L, dimnames = list(colnames(pr$z), labels))
  gamma <- array(NA_real_, c(pr$n_int_cell, pr$K, L),
                 dimnames = list(.dt_cell_names(pr), paste0("interval_", seq_len(pr$K)), labels))
  loglik <- stats::setNames(numeric(L), labels); conv <- stats::setNames(logical(L), labels)
  rows <- seq_len(nrow(pr$z))
  for (l in seq_len(L)) {
    raw <- .dt_unscale(pr, fits[[l]]$beta, fits[[l]]$G)
    beta[, l] <- raw$beta; gamma[, , l] <- raw$gamma
    loglik[l] <- sum(.dt_loglik_rows(pr, rows, fits[[l]]$G, fits[[l]]$beta))
    conv[l] <- fits[[l]]$converged
  }
  lp <- pr$z %*% beta
  list(beta = beta, gamma = gamma, likelihood = loglik, linear.predictors = lp, converged = conv,
       df = colSums(beta != 0))
}

## a family's fit: unpenalized over etas, or a penalty path at one eta (or one path per eta for the
## composite likelihood, as cox_indi_ridge / cox_indi_enet do)
.dt_fit_family <- function(s, penalty, etas, alpha, lambda, nlambda, lambda.min.ratio, tol, Mstop,
                           per_eta_paths, cls, message = FALSE) {
  pr <- s$pr; rows <- seq_len(s$tg$n)
  common <- list(link = pr$link, K = pr$K, strata_levels = pr$strata_levels)
  if (penalty == "none") {
    fits <- lapply(etas, function(eta) .dt_path(pr, rows, eta, 0, 0, tol, Mstop)[[1]])
    out <- c(list(eta = etas), .dt_collect(pr, fits, round(etas, 4)), common)
    out$df <- NULL
  } else if (!per_eta_paths) {
    lams <- .dt_lambda_seq(pr, rows, etas, penalty, alpha, lambda, nlambda, lambda.min.ratio)
    fits <- .dt_path(pr, rows, etas, lams, alpha, tol, Mstop)
    out <- c(list(eta = etas, lambda = lams), .dt_collect(pr, fits, signif(lams, 4)), common)
    if (penalty != "ridge") out$alpha <- alpha
  } else {
    per <- lapply(etas, function(eta) {
      lams <- .dt_lambda_seq(pr, rows, eta, penalty, alpha, lambda, nlambda, lambda.min.ratio)
      c(list(lambda = lams), .dt_collect(pr, .dt_path(pr, rows, eta, lams, alpha, tol, Mstop), signif(lams, 4)))
    })
    pick <- function(k) stats::setNames(lapply(per, `[[`, k), round(etas, 4))
    out <- c(list(eta = etas, lambda = pick("lambda"), beta = pick("beta"), gamma = pick("gamma"),
                  likelihood = pick("likelihood"), linear.predictors_int = pick("linear.predictors"),
                  converged = pick("converged")), common)
    if (penalty != "ridge") out$alpha <- alpha
  }
  if (!is.null(out$linear.predictors) && s$pr$member == "composite") {
    out$linear.predictors_int <- out$linear.predictors; out$linear.predictors <- NULL
  }
  structure(out, class = cls)
}

## a family's cross-validation, in the shape of the Cox estimators' results
.dt_cv_family <- function(s, penalty, etas, alpha, lambda, nlambda, lambda.min.ratio, nfolds, seed,
                          tol, Mstop, cls, message = FALSE) {
  tg <- s$tg; pr <- s$pr
  check_etas(etas); etas <- sort(unique(as.numeric(etas)))
  if (!is.numeric(nfolds) || length(nfolds) != 1 || nfolds < 2) stop("'nfolds' must be at least 2.", call. = FALSE)
  folds <- .dt_folds(tg$event, tg$stratum, nfolds, seed)
  rng_kind <- if (is.null(seed)) RNGkind()[1] else "Mersenne-Twister"
  core <- .dt_cv_core(pr, etas, penalty, alpha, lambda, nlambda, lambda.min.ratio, folds, tol, Mstop, message)
  pooled <- core$pooled
  cand <- pooled[pooled$complete, ]
  if (!nrow(cand)) stop("No (eta, lambda) completed every fold.", call. = FALSE)
  best <- cand[order(cand$loss, cand$eta, -cand$lambda), ][1, ]
  fit_at <- function(eta, lam) {
    ff <- core$full[[as.character(eta)]]
    .dt_unscale(pr, ff$fits[[which(ff$lambda == lam)]]$beta, ff$fits[[which(ff$lambda == lam)]]$G)
  }
  sel <- fit_at(best$eta, best$lambda)
  best_res <- list(best_eta = best$eta)
  if (penalty != "none") best_res$best_lambda <- best$lambda
  best_res <- c(best_res, list(best_beta = sel$beta, best_gamma = sel$gamma, best_value = best$loss,
                               criteria = "loss"))
  tail_fields <- list(criteria = "loss", nfolds = nfolds, folds = folds,
                      seed = if (is.null(seed)) NA_integer_ else as.integer(seed), rng_kind = rng_kind,
                      link = pr$link, K = pr$K, strata_levels = pr$strata_levels)
  if (penalty == "none") {
    beta_full <- vapply(etas, function(eta) fit_at(eta, 0)$beta, numeric(ncol(pr$z)))
    beta_full <- matrix(beta_full, ncol(pr$z), length(etas), dimnames = list(colnames(pr$z), round(etas, 4)))
    out <- c(list(internal_stat = data.frame(eta = pooled$eta, Loss = pooled$loss),
                  beta_full = beta_full, best = best_res), tail_fields)
  } else {
    full_results <- data.frame(eta = pooled$eta, lambda = pooled$lambda, Loss = pooled$loss)
    per <- lapply(etas, function(eta) {
      r <- cand[cand$eta == eta, , drop = FALSE]
      if (!nrow(r)) return(NULL)
      r[order(r$loss, -r$lambda), ][1, ]
    })
    per <- do.call(rbind, per)
    best_per_eta <- data.frame(eta = per$eta, lambda = per$lambda, Loss = per$loss)
    betahat_best <- vapply(seq_len(nrow(per)), function(i) fit_at(per$eta[i], per$lambda[i])$beta,
                           numeric(ncol(pr$z)))
    betahat_best <- matrix(betahat_best, ncol(pr$z), nrow(per), dimnames = list(colnames(pr$z), round(per$eta, 4)))
    out <- c(list(best = best_res, integrated_stat.full_results = full_results,
                  integrated_stat.best_per_eta = best_per_eta, integrated_stat.betahat_best = betahat_best),
             tail_fields)
    if (penalty != "ridge") out$alpha <- alpha
  }
  structure(out, class = cls)
}

## folds: event-stratified random assignment, or the package's stratified rule when strata are given
.dt_folds <- function(event, stratum, nfolds, seed) {
  if (!is.null(seed)) {
    old <- if (exists(".Random.seed", envir = globalenv())) get(".Random.seed", envir = globalenv()) else NULL
    on.exit(if (!is.null(old)) assign(".Random.seed", old, envir = globalenv()), add = TRUE)
    set.seed(seed, kind = "Mersenne-Twister")
  }
  folds <- integer(length(event))
  if (is.null(stratum)) {
    for (v in c(0L, 1L)) {
      i <- which(event == v)
      if (length(i) > 1) i <- sample(i)
      folds[i] <- 1L + (seq_along(i) - 1L) %% nfolds
    }
  } else folds <- get_fold(nfolds = nfolds, delta = event, stratum = stratum)
  folds
}

## interval hazards of new subjects under linear discrete coefficients and baselines
.dt_predict <- function(fit, z, stratum = NULL) {
  z <- .as_z(z)
  z <- z[, names(fit$beta), drop = FALSE]
  cell <- if (is.null(fit$strata_levels)) rep(1L, nrow(z)) else match(stratum, fit$strata_levels)
  if (anyNA(cell)) stop("'stratum' has levels the fit did not see.", call. = FALSE)
  U <- fit$gamma[cell, , drop = FALSE] + drop(z %*% fit$beta)
  H <- if (fit$link == "cloglog") -expm1(-exp(U)) else stats::plogis(U)
  H <- pmin(pmax(H, 1e-12), 1 - 1e-12)   # an interval held at the floor must not predict a hazard of exactly 0
  colnames(H) <- paste0("interval_", seq_len(ncol(H)))
  H
}
