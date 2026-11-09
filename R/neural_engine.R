## Neural targets (torch). Only the Kullback-Leibler member is defined for a neural risk score, and it
## reduces to a soft target exactly as for the linear model:
##
##   discrete time   masked binary cross-entropy of the interval logits against
##                   (y_ik + eta * h_ext_ik) / (1 + eta)          (a logistic-hazard network)
##   Cox             minus the partial likelihood with each event indicator replaced by
##                   (delta_i + eta * delta_tilde_i) / (1 + eta),  delta_tilde from the external score
##
## The protocol follows the discrete-time distillation runner the agent uses: K score folds, inside each
## an event-stratified fit / early-stop split, standardization on the fit part, the learning rate chosen
## at eta = 0, then eta, then a refit on all the data for the median best epoch from one shared
## initialization. A discrete network is scored by the pooled held-out negative log-likelihood per
## subject, the same functional as the linear discrete member; a Cox network by the cross-validated
## partial-likelihood loss of Verweij and Van Houwelingen on the same folds cv.coxkl draws.

.need_torch <- function() {
  if (!requireNamespace("torch", quietly = TRUE))
    stop("A neural target needs the 'torch' package: install.packages(\"torch\"), then ",
         "torch::install_torch().", call. = FALSE)
  if (!torch::torch_is_installed())
    stop("The torch backend is not installed: run torch::install_torch() once.", call. = FALSE)
}

.nn_module <- function() {
  block <- torch::nn_module(
    "bregsurv_block",
    initialize = function(n_in, n_out, dropout) {
      self$linear <- torch::nn_linear(n_in, n_out)
      torch::nn_init_kaiming_normal_(self$linear$weight, nonlinearity = "relu")
      self$norm <- torch::nn_layer_norm(n_out)
      self$drop <- if (dropout > 0) torch::nn_dropout(dropout) else NULL
      self$residual <- n_in == n_out
    },
    forward = function(x) {
      out <- torch::nnf_relu(self$norm(self$linear(x)))
      if (!is.null(self$drop)) out <- self$drop(out)
      if (self$residual) out + x else out
    })
  torch::nn_module(
    "bregsurv_net",
    initialize = function(n_in, n_out, hidden, dropout) {
      widths <- c(n_in, hidden)
      self$blocks <- torch::nn_module_list(lapply(seq_along(hidden), function(i)
        block(widths[i], widths[i + 1], dropout)))
      self$head <- torch::nn_linear(widths[length(widths)], n_out)
      torch::nn_init_kaiming_normal_(self$head$weight, nonlinearity = "relu")
    },
    forward = function(x) {
      for (i in seq_along(self$blocks)) x <- self$blocks[[i]](x)
      self$head(x)
    })
}

.nn_state_copy <- function(model) lapply(model$state_dict(), function(t) t$clone())

.nn_scaler <- function(x) {
  center <- colMeans(x)
  scale <- sqrt(colMeans(sweep(x, 2, center)^2))
  scale[!is.finite(scale) | scale <= sqrt(.Machine$double.eps)] <- 1
  list(center = center, scale = scale)
}
.nn_apply <- function(x, s) sweep(sweep(x, 2, s$center, "-"), 2, s$scale, "/")

.nn_stop_split <- function(pool, event, fraction, seed) {
  set.seed(seed, kind = "Mersenne-Twister")
  fit <- integer(0); stop_ <- integer(0)
  for (v in c(0L, 1L)) {
    m <- pool[event[pool] == v]
    if (!length(m)) next
    if (length(m) > 1) m <- sample(m)
    ns <- if (length(m) == 1) 0L else min(max(1L, round(length(m) * fraction)), length(m) - 1L)
    stop_ <- c(stop_, m[seq_len(ns)]); fit <- c(fit, m[setdiff(seq_along(m), seq_len(ns))])
  }
  if (!length(fit) || !length(stop_)) stop("the early-stop split produced an empty part.", call. = FALSE)
  list(fit = sort(fit), stop = sort(stop_))
}

## ---------------------------------------------------------------------------------------------------
## Losses
## ---------------------------------------------------------------------------------------------------
.nn_dt_loss <- function(logits, bundle, idx, eta) {
  hard <- bundle$hard[idx, , drop = FALSE]; mask <- bundle$mask[idx, , drop = FALSE]
  soft <- if (eta > 0) (hard + eta * bundle$teacher[idx, , drop = FALSE]) / (1 + eta) else hard
  el <- torch::nnf_binary_cross_entropy_with_logits(logits, soft, reduction = "none")
  (el * mask)$sum(dim = 2)$mean()
}
.nn_dt_hard <- function(logits, bundle) {
  el <- torch::nnf_binary_cross_entropy_with_logits(logits, bundle$hard, reduction = "none")
  (el * bundle$mask)$sum(dim = 2)
}

## Cox: rows of a batch sorted by (stratum, time) in R; risk sets formed within the batch
.nn_cox_loss <- function(r, bundle, idx, eta) {
  pos <- order(bundle$stratum[idx], bundle$time[idx])    # positions within the batch
  o <- idx[pos]
  st <- bundle$stratum[o]; tm <- bundle$time[o]
  n_each <- as.numeric(table(factor(st, levels = unique(st))))
  ties_map <- .tie_maps(tm, n_each, bundle$ties)
  rr <- r[pos]
  ends <- cumsum(n_each); starts <- ends - n_each + 1
  lse <- vector("list", length(n_each))
  for (s in seq_along(n_each)) {
    seg <- rr[starts[s]:ends[s]]
    lse[[s]] <- torch::torch_flip(torch::torch_logcumsumexp(torch::torch_flip(seg, 1), dim = 1), 1)
  }
  lr <- torch::torch_cat(lse)
  if (!is.null(ties_map)) lr <- lr[ties_map$first + 1L]
  w <- if (eta > 0) (bundle$delta[o] + eta * bundle$dtilde[o]) / (1 + eta) else bundle$delta[o]
  wt <- torch::torch_tensor(w, dtype = rr$dtype)
  dt <- torch::torch_tensor(bundle$delta[o], dtype = rr$dtype)
  -(wt * rr - dt * lr)$sum() / length(o)
}

## ---------------------------------------------------------------------------------------------------
## Training one network
## ---------------------------------------------------------------------------------------------------
.nn_train <- function(kind, spec, init, n_out, fit_b, eta, lr, seed, stop_b = NULL, epochs = NULL) {
  torch::torch_manual_seed(seed)
  set.seed(seed, kind = "Mersenne-Twister")
  model <- .nn_module()(fit_b$p, n_out, spec$hidden, spec$dropout)
  model$load_state_dict(init)
  opt <- torch::optim_adam(model$parameters, lr = lr, betas = c(0.9, 0.99), eps = 1e-8)
  n <- fit_b$n
  bs <- if (!is.null(spec$batch_size)) spec$batch_size else if (kind == "discrete") 32L else 64L
  n_ep <- if (is.null(stop_b)) max(1L, as.integer(epochs)) else spec$max_epochs
  best_val <- Inf; best_ep <- 0L; best_state <- .nn_state_copy(model); stale <- 0L; ep <- 0L
  loss_fn <- function(b, out, idx) if (kind == "discrete") .nn_dt_loss(out, b, idx, eta) else
    .nn_cox_loss(out$squeeze(2), b, idx, eta)
  for (ep in seq_len(n_ep)) {
    model$train()
    ord <- sample.int(n)
    for (start in seq(1L, n, by = bs)) {
      idx <- ord[start:min(n, start + bs - 1L)]
      if (kind == "cox" && sum(fit_b$delta[idx]) == 0) next
      opt$zero_grad()
      loss <- loss_fn(fit_b, model(fit_b$x[idx, , drop = FALSE]), idx)
      if (!is.finite(loss$item())) stop("non-finite training loss at epoch ", ep, call. = FALSE)
      loss$backward(); opt$step()
    }
    if (is.null(stop_b)) next
    model$eval()
    val <- torch::with_no_grad(loss_fn(stop_b, model(stop_b$x), seq_len(stop_b$n))$item())
    if (!is.finite(val)) stop("non-finite early-stop loss at epoch ", ep, call. = FALSE)
    if (val < best_val - spec$min_delta) { best_val <- val; best_ep <- ep; best_state <- .nn_state_copy(model); stale <- 0L }
    else { stale <- stale + 1L; if (stale >= spec$patience) break }
  }
  if (!is.null(stop_b)) model$load_state_dict(best_state) else best_ep <- ep
  model$eval()
  list(model = model, best_epoch = best_ep)
}

## ---------------------------------------------------------------------------------------------------
## Bundles
## ---------------------------------------------------------------------------------------------------
.nn_bundle_dt <- function(xs, interval, event, teacher, K) {
  n <- nrow(xs)
  hard <- matrix(0, n, K); ev <- which(event == 1); hard[cbind(ev, interval[ev])] <- 1
  mask <- outer(interval, seq_len(K), ">=") * 1
  f <- function(m) torch::torch_tensor(m, dtype = torch::torch_float())
  list(n = n, p = ncol(xs), x = f(xs), hard = f(hard), mask = f(mask),
       teacher = if (is.null(teacher)) f(matrix(0, n, K)) else f(teacher))
}

.nn_bundle_cox <- function(xs, time, delta, stratum, RS, ties) {
  ## data arrive sorted by (stratum, time); delta_tilde over this subset's own risk sets
  n_each <- as.numeric(table(factor(stratum, levels = unique(stratum))))
  tm <- .tie_maps(time, n_each, ties)
  dtl <- if (is.null(RS)) numeric(length(time)) else
    as.numeric(calculateDeltaTilde(delta, time, RS, n_each, tie_first = tm$first))
  list(n = nrow(xs), p = ncol(xs), x = torch::torch_tensor(xs, dtype = torch::torch_float()),
       time = time, delta = delta, stratum = stratum, dtilde = dtl, ties = ties)
}

.nn_predict_raw <- function(model, xs) {
  model$eval()
  torch::with_no_grad(as.matrix(torch::as_array(model(torch::torch_tensor(xs, dtype = torch::torch_float())))))
}

## ---------------------------------------------------------------------------------------------------
## Cross-validation
## ---------------------------------------------------------------------------------------------------
.nn_cv <- function(tg, ext, etas, nfolds, folds, seed) {
  .need_torch()
  spec <- tg$score
  torch::torch_set_num_threads(max(1L, spec$threads))
  if (is.null(seed)) seed <- 20260907L
  old_seed <- if (exists(".Random.seed", envir = globalenv())) get(".Random.seed", envir = globalenv()) else NULL
  on.exit(if (!is.null(old_seed)) assign(".Random.seed", old_seed, envir = globalenv()), add = TRUE)
  kind <- tg$type
  etas <- sort(unique(c(0, as.numeric(etas))))
  if (is.null(ext)) etas <- 0

  if (kind == "discrete") {
    x <- tg$z; n <- tg$n; K <- tg$K
    teacher <- ext$teacher
    if (is.null(folds)) folds <- .dt_folds(tg$event, tg$stratum, nfolds, seed)
    order_sorted <- seq_len(n)
    n_out <- K
  } else {
    st <- if (is.null(tg$stratum)) rep(1, tg$n) else match(tg$stratum, unique(tg$stratum))
    order_sorted <- order(st, tg$time)
    x <- tg$z[order_sorted, , drop = FALSE]
    time <- tg$time[order_sorted]; delta <- tg$event[order_sorted]; st <- st[order_sorted]
    RS <- if (is.null(ext)) NULL else ext$score[order_sorted]
    n <- tg$n; n_out <- 1L
    if (is.null(folds)) {
      set.seed(seed, kind = "Mersenne-Twister")
      folds <- get_fold(nfolds = nfolds, delta = delta, stratum = st)
    }
    n_each_full <- as.numeric(table(st))
  }
  fold_ids <- sort(unique(folds))
  ev_vec <- if (kind == "discrete") tg$event else delta

  ## per-fold contexts: split, scaler, bundles, a shared initialization
  ctx <- lapply(fold_ids, function(fo) {
    pool <- which(folds != fo); score <- which(folds == fo)
    sp <- .nn_stop_split(pool, ev_vec, spec$stop_fraction, seed + fo * 11)
    sc <- .nn_scaler(x[sp$fit, , drop = FALSE])
    mk <- function(rows) if (kind == "discrete")
      .nn_bundle_dt(.nn_apply(x[rows, , drop = FALSE], sc), tg$interval[rows], tg$event[rows],
                    if (is.null(teacher)) NULL else teacher[rows, , drop = FALSE], K)
      else .nn_bundle_cox(.nn_apply(x[rows, , drop = FALSE], sc), time[rows], delta[rows], st[rows],
                          if (is.null(RS)) NULL else RS[rows], tg$ties)
    torch::torch_manual_seed(seed + fo * 100 + 1)
    init <- .nn_state_copy(.nn_module()(ncol(x), n_out, spec$hidden, spec$dropout))
    list(fold = fo, pool = pool, score = score, scaler = sc, fit = mk(sp$fit), stop = mk(sp$stop),
         init = init, fit_seed = seed + fo * 100 + 2)
  })

  ## the cross-validated score of one (learning rate, eta)
  score_of <- function(lr, eta) {
    total <- 0; epochs <- integer(0)
    for (cx in ctx) {
      tr <- tryCatch(.nn_train(kind, spec, cx$init, n_out, cx$fit, eta, lr, cx$fit_seed, stop_b = cx$stop),
                     error = function(e) e)
      if (inherits(tr, "error")) return(list(value = Inf, epochs = epochs))
      epochs <- c(epochs, tr$best_epoch)
      if (kind == "discrete") {
        sb <- .nn_bundle_dt(.nn_apply(x[cx$score, , drop = FALSE], cx$scaler), tg$interval[cx$score],
                            tg$event[cx$score], NULL, K)
        h <- torch::with_no_grad(.nn_dt_hard(tr$model(sb$x), sb)$sum()$item())
        total <- total + h
      } else {
        lp_all <- drop(.nn_predict_raw(tr$model, .nn_apply(x, cx$scaler)))
        trn <- cx$pool
        total <- total + (.pl_ties(lp_all, delta, time, n_each_full, tg$ties) -
                          .pl_ties(lp_all[trn], delta[trn], time[trn], as.numeric(table(st[trn])), tg$ties))
      }
    }
    if (!is.finite(total)) return(list(value = Inf, epochs = epochs))
    list(value = if (kind == "discrete") total / n else -2 * total / n, epochs = epochs)
  }

  lr_scores <- vapply(spec$learning_rates, function(lr) score_of(lr, 0)$value, numeric(1))
  if (!any(is.finite(lr_scores))) stop("No learning rate completed every fold at eta = 0.", call. = FALSE)
  lr <- spec$learning_rates[order(lr_scores, spec$learning_rates)][1]
  res <- lapply(etas, function(e) score_of(lr, e))
  vals <- vapply(res, `[[`, numeric(1), "value")
  if (!is.finite(vals[etas == 0])) stop("The eta = 0 network did not complete every fold.", call. = FALSE)
  ok <- is.finite(vals)
  best <- which(ok)[order(vals[ok], etas[ok])][1]
  eta_sel <- etas[best]
  ep_sel <- max(1L, as.integer(round(stats::median(res[[best]]$epochs))))

  ## refit on all the data from one shared initialization
  sc <- .nn_scaler(x)
  allb <- if (kind == "discrete") .nn_bundle_dt(.nn_apply(x, sc), tg$interval, tg$event, teacher, K) else
    .nn_bundle_cox(.nn_apply(x, sc), time, delta, st, RS, tg$ties)
  torch::torch_manual_seed(seed + 90001)
  init <- .nn_state_copy(.nn_module()(ncol(x), n_out, spec$hidden, spec$dropout))
  final <- .nn_train(kind, spec, init, n_out, allb, eta_sel, lr, seed + 90002, epochs = ep_sel)

  out <- list(model = final$model, scaler = sc, eta = eta_sel, value = vals[best],
              criterion = if (kind == "discrete") "discrete_nll" else "V&VH",
              pooled = data.frame(eta = etas, loss = vals), learning_rate = lr,
              epochs = ep_sel, folds = folds, seed = seed,
              columns = colnames(tg$z), kind = kind, K = if (kind == "discrete") K else NULL)
  out$lr_scores <- data.frame(learning_rate = spec$learning_rates, loss = lr_scores)
  if (kind == "cox") {
    ## Breslow baseline of the fitted network, for survival prediction
    lp <- drop(.nn_predict_raw(final$model, .nn_apply(x, sc)))
    out$baseline <- .breslow_table(lp, time, delta, st)
    out$strata_levels <- if (is.null(tg$stratum)) NULL else unique(tg$stratum)
    out$folds_order <- "sorted by (stratum, time), as cv.coxkl returns them"
  }
  out
}

## Breslow cumulative baseline hazard per stratum, as a step function table
.breslow_table <- function(lp, time, delta, stratum) {
  lapply(split(seq_along(time), stratum), function(idx) {
    t <- time[idx]; d <- delta[idx]; e <- exp(lp[idx])
    ut <- sort(unique(t[d == 1]))
    inc <- vapply(ut, function(u) sum(d[t == u]) / sum(e[t >= u]), numeric(1))
    data.frame(time = ut, cumhaz = cumsum(inc))
  })
}

.nn_predict <- function(fit, z, stratum = NULL) {
  .need_torch()
  z <- .as_z(z)[, fit$columns, drop = FALSE]
  out <- .nn_predict_raw(fit$model, .nn_apply(z, fit$scaler))
  if (fit$kind == "discrete") {
    H <- pmin(pmax(stats::plogis(out), 1e-7), 1 - 1e-7)
    colnames(H) <- paste0("interval_", seq_len(ncol(H)))
    H
  } else drop(out)
}
