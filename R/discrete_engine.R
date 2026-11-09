## The grouped-time (discrete-time) target, linear risk score.
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
## plus lambda * (alpha |beta|_1 + (1 - alpha) / 2 |beta|^2). Fisher scoring with the interval
## parameters profiled out by their (diagonal) Schur complement; lasso and elastic net by proximal Newton
## with coordinate descent. Every quantity is held as an n x K matrix of subjects by intervals.

.DT_FLOOR <- 1e-8   # lower bound on an interval hazard's baseline: an interval with no events in the
                    # training data would otherwise send its parameter to minus infinity

.dt_gamma_min <- function(link) if (link == "cloglog") log(-log1p(-.DT_FLOOR)) else stats::qlogis(.DT_FLOOR)

## log h and log(1 - h) for the linear predictor u, stably
.dt_logs <- function(u, link) {
  if (link == "cloglog") {
    e <- exp(u)
    lh <- ifelse(u > 3.6, log1p(-exp(-e)), log(-expm1(-e)))
    list(lh = lh, l1h = -e)
  } else {
    list(lh = -log1p(exp(-u)) , l1h = -log1p(exp(u)))
  }
}

## derivative of t log h + (1 - t) log(1 - h) in u, and its Fisher information
.dt_score_info <- function(u, t, link) {
  if (link == "cloglog") {
    e <- exp(u)
    mu <- -expm1(-e)
    r <- ifelse(mu > 0, e / mu, 1)
    list(d = t * r - e, w = e * r * (1 - mu))
  } else {
    mu <- stats::plogis(u)
    list(d = t - mu, w = mu * (1 - mu))
  }
}

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

## objective (to minimize) of the smooth part, all blocks, plus the quadratic terms
.dt_objective <- function(blocks, G, beta, link, n, pen) {
  val <- 0
  for (b in blocks) {
    U <- G[b$cell, , drop = FALSE] + drop(b$Z %*% beta)
    lg <- .dt_logs(U, link)
    val <- val - sum(b$Wt * (b$Tm * lg$lh + (1 - b$Tm) * lg$l1h), na.rm = TRUE)
  }
  val <- val / n
  if (!is.null(pen$Qm)) { dv <- beta - pen$bext; val <- val + 0.5 * pen$eta_m * sum(dv * (pen$Qm %*% dv)) }
  val + pen$lambda * (pen$alpha * sum(abs(beta)) + 0.5 * (1 - pen$alpha) * sum(beta^2))
}

## gradient and Fisher information of the smooth part (divided by n), in blocks
.dt_derivs <- function(blocks, G, beta, link, n, pen, n_cell, K) {
  p <- length(beta)
  gb <- numeric(p); Hbb <- matrix(0, p, p)
  gG <- matrix(0, n_cell, K); HGG <- matrix(0, n_cell, K)
  HGb <- array(0, c(n_cell, K, p))
  for (b in blocks) {
    U <- G[b$cell, , drop = FALSE] + drop(b$Z %*% beta)
    si <- .dt_score_info(U, b$Tm, link)
    D <- -b$Wt * si$d; D[!is.finite(D)] <- 0
    W <- b$Wt * si$w;  W[!is.finite(W)] <- 0
    gb <- gb + drop(crossprod(b$Z, rowSums(D)))
    Hbb <- Hbb + crossprod(b$Z * rowSums(W), b$Z)
    for (cc in unique(b$cell)) {
      idx <- which(b$cell == cc)
      gG[cc, ] <- gG[cc, ] + colSums(D[idx, , drop = FALSE])
      HGG[cc, ] <- HGG[cc, ] + colSums(W[idx, , drop = FALSE])
      HGb[cc, , ] <- HGb[cc, , ] + crossprod(W[idx, , drop = FALSE], b$Z[idx, , drop = FALSE])
    }
  }
  gb <- gb / n; Hbb <- Hbb / n; gG <- gG / n; HGG <- HGG / n; HGb <- HGb / n
  if (!is.null(pen$Qm)) { gb <- gb + pen$eta_m * drop(pen$Qm %*% (beta - pen$bext)); Hbb <- Hbb + pen$eta_m * pen$Qm }
  list(gb = gb, Hbb = Hbb, gG = gG, HGG = HGG, HGb = matrix(HGb, n_cell * K, p))
}

## Fit at one (eta, lambda). blocks already standardized; returns gamma (cells x K) and beta on the
## standardized scale. alpha = 0 is ridge; lambda = 0 is unpenalized.
.dt_solve <- function(blocks, link, n, K, n_cell, pen, beta0, G0, tol = 1e-9, max_iter = 200) {
  p <- ncol(blocks[[1]]$Z)
  beta <- beta0; G <- G0
  gmin <- .dt_gamma_min(link)
  live <- matrix(FALSE, n_cell, K)          # cells with anyone at risk
  for (b in blocks) for (cc in unique(b$cell)) live[cc, ] <- live[cc, ] | colSums(b$M[b$cell == cc, , drop = FALSE]) > 0
  F_old <- .dt_objective(blocks, G, beta, link, n, pen)
  l1 <- pen$lambda * pen$alpha; l2 <- pen$lambda * (1 - pen$alpha)
  converged <- FALSE
  for (it in seq_len(max_iter)) {
    dv <- .dt_derivs(blocks, G, beta, link, n, pen, n_cell, K)
    hg <- as.vector(dv$HGG); keep <- as.vector(live) & hg > 1e-14
    Dinv <- ifelse(keep, 1 / hg, 0)
    gGv <- as.vector(dv$gG)
    ## reduced (Schur) quadratic in the coefficient step
    Hs <- dv$Hbb - crossprod(dv$HGb * Dinv, dv$HGb)
    gs <- dv$gb - drop(crossprod(dv$HGb, Dinv * gGv))
    if (l1 == 0) {
      A <- Hs + diag(l2, p)
      step_b <- -tryCatch(solve(A, gs + l2 * beta), error = function(e) MASS::ginv(A) %*% (gs + l2 * beta))
      step_b <- drop(step_b)
    } else {
      ## proximal Newton: coordinate descent on the reduced quadratic plus the penalty
      x <- beta; v <- numeric(p); hd <- diag(Hs)
      for (sweep in seq_len(1000)) {
        maxd <- 0
        for (j in seq_len(p)) {
          a <- hd[j] + l2
          if (a <= 0) next
          zj <- hd[j] * x[j] - (gs[j] + v[j])
          xn <- sign(zj) * max(abs(zj) - l1, 0) / a
          d <- xn - x[j]
          if (d != 0) { v <- v + d * Hs[, j]; x[j] <- xn; maxd <- max(maxd, abs(d) * sqrt(a)) }
        }
        if (maxd < tol) break
      }
      step_b <- x - beta
    }
    step_G <- -Dinv * (gGv + drop(dv$HGb %*% step_b))
    ## backtracking on the full objective
    s <- 1; accepted <- FALSE
    for (h in 1:30) {
      bn <- beta + s * step_b
      Gn <- pmax(G + s * matrix(step_G, n_cell, K), gmin)
      Fn <- .dt_objective(blocks, Gn, bn, link, n, pen)
      if (is.finite(Fn) && Fn <= F_old + 1e-12 * abs(F_old)) { accepted <- TRUE; break }
      s <- s / 2
    }
    if (!accepted) break
    change <- max(abs(c(bn - beta, (Gn - G)[live])))
    beta <- bn; G <- Gn
    dF <- F_old - Fn; F_old <- Fn
    if (change < tol || dF < tol * 1e-3 * max(1, abs(Fn))) { converged <- TRUE; break }
  }
  ## a cell no training subject reaches carries the last reached interval of its row forward
  for (cc in seq_len(n_cell)) {
    if (!any(live[cc, ])) next
    last <- NA_real_
    for (k in seq_len(K)) { if (live[cc, k]) last <- G[cc, k] else if (!is.na(last)) G[cc, k] <- last }
  }
  list(beta = beta, G = G, objective = F_old, converged = converged, iterations = it)
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
              member = member, K = tg$K, link = tg$link)
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
  lg <- .dt_logs(U, pr$link)
  rowSums(b$M * (b$Y * lg$lh + (1 - b$Y) * lg$l1h))
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

.dt_lambda_max <- function(pr, rows, eta, alpha, link) {
  blocks <- .dt_blocks(pr, rows, eta)
  pen0 <- .dt_pen(pr, eta, 0, 0)
  G0 <- .dt_gamma_start(blocks, pr$n_cell, pr$K, link)
  ## fit the interval parameters with every coefficient held at zero
  fit0 <- .dt_solve_gamma_only(blocks, link, length(rows), pr$K, pr$n_cell, pen0, G0)
  dv <- .dt_derivs(blocks, fit0, numeric(ncol(pr$zs)), link, length(rows), pen0, pr$n_cell, pr$K)
  max(abs(dv$gb)) / max(alpha, 1e-3)
}

.dt_solve_gamma_only <- function(blocks, link, n, K, n_cell, pen, G) {
  beta <- numeric(ncol(blocks[[1]]$Z)); gmin <- .dt_gamma_min(link)
  for (it in 1:100) {
    dv <- .dt_derivs(blocks, G, beta, link, n, pen, n_cell, K)
    hg <- dv$HGG; step <- ifelse(hg > 1e-14, -dv$gG / hg, 0)
    Gn <- pmax(G + step, gmin)
    if (max(abs(Gn - G)) < 1e-10) { G <- Gn; break }
    G <- Gn
  }
  G
}

.dt_unscale <- function(pr, beta_s, G_s) {
  beta <- beta_s / pr$scale
  names(beta) <- colnames(pr$z)
  G <- G_s - sum(pr$center * beta)
  list(beta = beta, gamma = G[seq_len(pr$n_int_cell), , drop = FALSE])
}

## ---------------------------------------------------------------------------------------------------
## Cross-validation over (eta, lambda); the scorer is the pooled held-out negative log-likelihood per
## subject of the grouped-time model (the same functional for every member, linear or neural)
## ---------------------------------------------------------------------------------------------------
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

.dt_cv <- function(tg, member, ext, penalty, alpha, etas, lambda, nlambda, lambda.min.ratio, nfolds,
                   folds, seed, standardize, tol, max_iter) {
  pen_on <- penalty != "none"
  if (!pen_on) standardize <- TRUE         # an unpenalized fit does not depend on the scaling
  pr <- .dt_prepare(tg, member, ext, standardize)
  pr$interval <- tg$interval; pr$event <- tg$event
  n <- tg$n; p <- ncol(tg$z)
  if (is.null(folds)) folds <- .dt_folds(tg$event, tg$stratum, nfolds, seed)
  fold_ids <- sort(unique(folds))
  etas <- sort(unique(as.numeric(etas)))
  if (member != "none" && !any(etas == 0)) etas <- c(0, etas)
  if (member == "none") etas <- 0
  alpha_use <- switch(penalty, none = 0, ridge = 0, lasso = 1, enet = alpha)
  path <- list(); full_fits <- list()
  for (eta in etas) {
    all_rows <- seq_len(n)
    lams <- if (!pen_on) 0 else if (!is.null(lambda)) sort(lambda, decreasing = TRUE) else {
      lmax <- .dt_lambda_max(pr, all_rows, eta, if (penalty == "ridge") 1 else alpha_use, pr$link)
      if (penalty == "ridge") lmax <- lmax * 1e3
      ratio <- if (is.null(lambda.min.ratio)) (if (n < p) 0.05 else 1e-3) else lambda.min.ratio
      if (penalty == "ridge") ratio <- ratio * 1e-1
      exp(seq(log(lmax), log(lmax * ratio), length.out = nlambda))
    }
    ## full data along the path (warm starts)
    blocks <- .dt_blocks(pr, all_rows, eta)
    G <- .dt_gamma_start(blocks, pr$n_cell, pr$K, pr$link); b <- numeric(p)
    fits <- vector("list", length(lams))
    for (l in seq_along(lams)) {
      f <- .dt_solve(blocks, pr$link, n, pr$K, pr$n_cell, .dt_pen(pr, eta, lams[l], alpha_use), b, G, tol, max_iter)
      fits[[l]] <- f; b <- f$beta; G <- f$G
    }
    full_fits[[as.character(eta)]] <- list(lambda = lams, fits = fits)
    for (fo in fold_ids) {
      tr <- which(folds != fo); va <- which(folds == fo)
      blocks <- .dt_blocks(pr, tr, eta)
      G <- .dt_gamma_start(blocks, pr$n_cell, pr$K, pr$link); b <- numeric(p)
      for (l in seq_along(lams)) {
        f <- tryCatch(.dt_solve(blocks, pr$link, length(tr), pr$K, pr$n_cell, .dt_pen(pr, eta, lams[l], alpha_use),
                                b, G, tol, max_iter), error = function(e) e)
        ok <- !inherits(f, "error")
        ll <- if (ok) sum(.dt_loglik_rows(pr, va, f$G, f$beta)) else NA_real_
        if (ok) { b <- f$beta; G <- f$G }
        path[[length(path) + 1]] <- data.frame(eta = eta, lambda = lams[l], fold = fo, n_valid = length(va),
                                               loglik_valid = ll, ok = ok && is.finite(ll))
      }
    }
  }
  path <- do.call(rbind, path)
  key <- paste(path$eta, path$lambda)
  pooled <- do.call(rbind, lapply(split(path, factor(key, levels = unique(key))), function(r)
    data.frame(eta = r$eta[1], lambda = r$lambda[1], complete = all(r$ok),
               loss = if (all(r$ok)) -sum(r$loglik_valid) / sum(r$n_valid) else NA_real_)))
  rownames(pooled) <- NULL
  cand <- pooled[pooled$complete, ]
  if (!nrow(cand)) stop("No (eta, lambda) completed every fold.", call. = FALSE)
  best <- cand[order(cand$loss, cand$eta, -cand$lambda), ][1, ]
  ff <- full_fits[[as.character(best$eta)]]
  sel <- ff$fits[[which(ff$lambda == best$lambda)]]
  raw <- .dt_unscale(pr, sel$beta, sel$G)
  list(beta = raw$beta, gamma = raw$gamma, eta = best$eta, lambda = if (pen_on) best$lambda else NULL,
       value = best$loss, criterion = "discrete_nll", pooled = pooled, cv_path = path, folds = folds,
       seed = seed, converged = sel$converged, link = pr$link, K = pr$K, strata_levels = pr$strata_levels,
       standardize = standardize)
}

## single fit at given eta (and lambda)
.dt_fit <- function(tg, member, ext, eta, lambda, alpha, standardize, tol, max_iter) {
  pen_on <- !is.null(lambda) && lambda > 0
  if (!pen_on) standardize <- TRUE
  pr <- .dt_prepare(tg, member, ext, standardize)
  pr$interval <- tg$interval; pr$event <- tg$event
  rows <- seq_len(tg$n)
  blocks <- .dt_blocks(pr, rows, eta)
  G <- .dt_gamma_start(blocks, pr$n_cell, pr$K, pr$link)
  f <- .dt_solve(blocks, pr$link, tg$n, pr$K, pr$n_cell,
                 .dt_pen(pr, eta, if (pen_on) lambda else 0, if (pen_on) alpha else 0),
                 numeric(ncol(tg$z)), G, tol, max_iter)
  raw <- .dt_unscale(pr, f$beta, f$G)
  list(beta = raw$beta, gamma = raw$gamma, eta = eta, lambda = lambda, converged = f$converged,
       iterations = f$iterations, link = pr$link, K = pr$K, strata_levels = pr$strata_levels,
       loglik = sum(.dt_loglik_rows(pr, rows, f$G, f$beta)))
}

## interval hazards of new subjects under a linear discrete fit
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
