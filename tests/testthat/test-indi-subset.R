## External individual records that carry only some of the internal covariates (2.2.0)

sim_cox <- function(n, beta, seed) {
  set.seed(seed); p <- length(beta)
  x <- matrix(rnorm(n * p), n, p, dimnames = list(NULL, paste0("z", seq_len(p))))
  x[, 2] <- x[, 2] + 0.5 * x[, 1]                       # a covariate related to another
  tt <- rexp(n, 0.1 * exp(drop(x %*% beta))); cc <- rexp(n, 0.05)
  list(z = x, time = pmin(tt, cc), event = as.integer(tt <= cc))
}
mysd <- function(v) sqrt(mean((v - mean(v))^2))
## the log partial likelihood without ties, one stratum
pl <- function(beta, z, time, delta) {
  o <- order(time); th <- drop(z[o, , drop = FALSE] %*% beta)
  sum(delta[o] * (th - log(rev(cumsum(rev(exp(th)))))))
}
num_grad <- function(f, b, h = 1e-5)
  vapply(seq_along(b), function(j) { e <- replace(numeric(length(b)), j, h); (f(b + e) - f(b - e)) / (2 * h) }, 0)

I <- sim_cox(150, c(0.5, -0.4, 0.3, 0.6), 1)
E <- sim_cox(300, c(0.5, -0.4, 0.3, 0.6), 2)
ze <- E$z[, c("z1", "z3", "z4")]                        # the records lack z2
stacked <- function(fill, eta) {
  zf <- cbind(ze[, 1, drop = FALSE], z2 = fill, ze[, 2:3, drop = FALSE])
  data.frame(time = c(I$time, E$time), event = c(I$event, E$event), rbind(I$z, zf),
             cohort = rep(1:2, c(150, 300)), w = rep(c(1, eta), c(150, 300)))
}
coxph_stacked <- function(d)
  stats::coef(survival::coxph(survival::Surv(time, event) ~ z1 + z2 + z3 + z4 + survival::strata(cohort),
                              data = d, weights = w, ties = "breslow",
                              control = survival::coxph.control(eps = 1e-10, iter.max = 50)))

test_that("cox_indi on records that lack a covariate is the composite likelihood of the model without it", {
  eta <- 0.7
  fit <- cox_indi(I$z, I$event, I$time, z_ext = ze, delta_ext = E$event, time_ext = E$time,
                  etas = c(0, eta), tol = 1e-10)
  b0 <- coxph_stacked(stacked(0, eta)); b5 <- coxph_stacked(stacked(5, eta))
  expect_equal(unname(b0), unname(b5), tolerance = 1e-8)        # the constant cancels
  expect_equal(unname(fit$beta[, 2]), unname(b0), tolerance = 1e-6)
  expect_equal(unname(fit$beta[, 1]),
               unname(stats::coef(survival::coxph(survival::Surv(I$time, I$event) ~ I$z, ties = "breslow"))),
               tolerance = 1e-6)
  expect_identical(unname(fit$ext_covered), c(TRUE, FALSE, TRUE, TRUE))
  expect_identical(colnames(fit$data$z_ext), colnames(I$z))
})

test_that("named external columns are matched by name; unmatchable ones are refused", {
  f1 <- cox_indi(I$z, I$event, I$time, z_ext = E$z, delta_ext = E$event, time_ext = E$time, etas = 1)
  f2 <- cox_indi(I$z, I$event, I$time, z_ext = E$z[, c(3, 1, 4, 2)], delta_ext = E$event,
                 time_ext = E$time, etas = 1)
  expect_equal(f1$beta, f2$beta)
  zo <- E$z; colnames(zo) <- paste0("V", 1:4)                   # same width, other names: by position
  expect_equal(cox_indi(I$z, I$event, I$time, z_ext = zo, delta_ext = E$event, time_ext = E$time,
                        etas = 1)$beta, f1$beta)
  expect_error(cox_indi(I$z, I$event, I$time, z_ext = unname(ze), delta_ext = E$event,
                        time_ext = E$time, etas = 1), "column names")
  bad <- ze; colnames(bad) <- c("z1", "z3", "age")
  expect_error(cox_indi(I$z, I$event, I$time, z_ext = bad, delta_ext = E$event, time_ext = E$time,
                        etas = 1), "the internal data does not: age")
  expect_error(cv.cox_indi_enet(I$z, I$event, I$time, z_ext = bad, delta_ext = E$event,
                                time_ext = E$time, etas = 1), "the internal data does not: age")
})

test_that("cox_indi_ridge scales a covariate the records lack on the internal rows", {
  eta <- 1; lam <- 0.05
  fit <- cox_indi_ridge(I$z, I$event, I$time, z_ext = ze, delta_ext = E$event, time_ext = E$time,
                        etas = eta, lambda = lam, tol = 1e-12, max_iter = 200)
  b <- fit$beta[[1]][, 1]
  comp <- function(beta) pl(beta, I$z, I$time, I$event) + eta * pl(beta[c(1, 3, 4)], ze, E$time, E$event)
  ## the stationarity condition g / n_eff = lambda * scale^2 * beta gives back each column's scale
  s_kkt <- sqrt(num_grad(comp, b) / 450 / (lam * b))
  zall <- rbind(I$z, cbind(ze[, 1, drop = FALSE], z2 = 0, ze[, 2:3, drop = FALSE]))
  want <- c(mysd(zall[, 1]), mysd(I$z[, 2]), mysd(zall[, 3]), mysd(zall[, 4]))
  expect_equal(unname(s_kkt), want, tolerance = 1e-4)
  expect_identical(unname(fit$ext_covered), c(TRUE, FALSE, TRUE, TRUE))
})

test_that("cox_indi_enet standardizes a covariate the records lack on the internal rows", {
  fit <- cox_indi_enet(I$z, I$event, I$time, z_ext = ze, delta_ext = E$event, time_ext = E$time,
                       etas = 1, alpha = 1, nlambda = 30, tol = 1e-10, Mstop = 5000, returnX = TRUE)
  zall <- rbind(I$z, cbind(ze[, 1, drop = FALSE], z2 = 0, ze[, 2:3, drop = FALSE]))
  want <- c(mysd(zall[, 1]), mysd(I$z[, 2]), mysd(zall[, 3]), mysd(zall[, 4]))
  expect_equal(unname(fit$std.Z$scale), want, tolerance = 1e-12)
  expect_equal(unname(fit$std.Z$center[2]), mean(I$z[, 2]), tolerance = 1e-12)
  ## the lasso stationarity condition |g_j| = N lambda scale_j on every active coefficient
  B <- fit$beta[[1]]
  j <- which(colSums(B != 0) == 4)[1]
  expect_false(is.na(j))
  b <- B[, j]
  comp <- function(beta) pl(beta, I$z, I$time, I$event) + pl(beta[c(1, 3, 4)], ze, E$time, E$event)
  r <- abs(num_grad(comp, b)) / want
  expect_equal(r / mean(r), rep(1, 4), tolerance = 1e-3)
  ## the same records widened by hand and fitted as covered columns are standardized differently
  zf <- cbind(ze[, 1, drop = FALSE], z2 = mean(I$z[, 2]), ze[, 2:3, drop = FALSE])
  f_cov <- cox_indi_enet(I$z, I$event, I$time, z_ext = zf, delta_ext = E$event, time_ext = E$time,
                         etas = 1, alpha = 1, nlambda = 30, returnX = TRUE)
  expect_lt(f_cov$std.Z$scale[2], 0.9 * want[2])
})

test_that("the cross-validation functions take records that lack a covariate", {
  a <- list(z_int = I$z, delta_int = I$event, time_int = I$time, delta_ext = E$event, time_ext = E$time,
            nfolds = 3, seed = 1)
  ## at eta = 0 the records carry no weight, so the unpenalized loss is the internal one
  l_sub <- suppressWarnings(do.call(cv.cox_indi, c(a, list(z_ext = ze, etas = 0))))$best$best_value
  l_all <- suppressWarnings(do.call(cv.cox_indi, c(a, list(z_ext = E$z, etas = 0))))$best$best_value
  expect_equal(l_sub, l_all, tolerance = 1e-12)
  r <- suppressWarnings(do.call(cv.cox_indi_ridge, c(a, list(z_ext = ze, etas = c(0, 1), nlambda = 5))))
  e <- suppressWarnings(do.call(cv.cox_indi_enet, c(a, list(z_ext = ze, etas = c(0, 1), nlambda = 5))))
  expect_true(is.finite(r$best$best_value) && is.finite(e$best$best_value))
})

test_that("ncc_indi on matched records that lack a covariate is the stacked conditional likelihood", {
  sim_ncc <- function(nset, beta, seed) {
    set.seed(seed); m <- 4; n <- nset * m
    x <- matrix(rnorm(n * 3), n, 3, dimnames = list(NULL, c("z1", "z2", "z3")))
    set <- rep(seq_len(nset), each = m)
    y <- unlist(lapply(split(drop(x %*% beta), set), function(lp) {
      k <- sample.int(m, 1, prob = exp(lp)); replace(numeric(m), k, 1) }))
    list(z = x, y = y, set = set)
  }
  Ic <- sim_ncc(80, c(0.6, -0.5, 0.4), 3); Ec <- sim_ncc(150, c(0.6, -0.5, 0.4), 4)
  zc <- Ec$z[, c("z1", "z3")]; eta <- 0.6
  fit <- ncc_indi(Ic$y, Ic$z, Ic$set, Ec$y, zc, Ec$set, etas = eta, tol = 1e-10)
  d <- data.frame(y = c(Ic$y, Ec$y), rbind(Ic$z, cbind(zc[, 1, drop = FALSE], z2 = 0, zc[, 2, drop = FALSE])),
                  set = c(Ic$set, 1000 + Ec$set), w = rep(c(1, eta), c(length(Ic$y), length(Ec$y))), t1 = 1)
  ref <- stats::coef(survival::coxph(survival::Surv(t1, y) ~ z1 + z2 + z3 + survival::strata(set),
                                     data = d, weights = w, ties = "breslow",
                                     control = survival::coxph.control(eps = 1e-10)))
  expect_equal(unname(fit$beta[, 1]), unname(ref), tolerance = 1e-6)
  cv <- suppressWarnings(cv.ncc_indi_enet(Ic$y, Ic$z, Ic$set, Ec$y, zc, Ec$set, etas = c(0, 1), nlambda = 5,
                                          nfolds = 3))
  expect_true(is.finite(cv$best$best_value))
})

test_that("discrete_indi on records that lack a covariate equals the records with any constant in its place", {
  s <- sim_discrete(300, c(0.5, -0.4, 0.3), alpha = c(-2, -1.6, -1.3, -1.1), seed = 3)
  e <- sim_discrete(500, c(0.5, -0.4, 0.3), alpha = c(-1.8, -1.5, -1.2, -1), seed = 4)
  f_sub <- discrete_indi(s$x, s$event, s$interval, z_ext = e$x[, c("z1", "z3")], delta_ext = e$event,
                         interval_ext = e$interval, etas = c(0, 1))
  zm <- e$x; zm[, "z2"] <- mean(s$x[, "z2"])
  zc <- e$x; zc[, "z2"] <- 3.7
  f_m <- discrete_indi(s$x, s$event, s$interval, z_ext = zm, delta_ext = e$event, interval_ext = e$interval,
                       etas = c(0, 1))
  f_c <- discrete_indi(s$x, s$event, s$interval, z_ext = zc, delta_ext = e$event, interval_ext = e$interval,
                       etas = c(0, 1))
  expect_equal(f_sub$beta, f_m$beta, tolerance = 1e-10)
  expect_equal(f_sub$beta, f_c$beta, tolerance = 1e-6)
  ## without column names the records are matched by position, so they must carry every covariate
  expect_error(discrete_indi(unname(s$x), s$event, s$interval, z_ext = unname(e$x[, 1:2]), delta_ext = e$event,
                             interval_ext = e$interval, etas = 1), "name the columns")
})

test_that("cv.bregsurv and bregsurv take records that lack a covariate", {
  tg <- target_cox(I$time, I$event, I$z)
  rel <- release_records(ze, time = E$time, event = E$event)
  b <- bregsurv(tg, rel, divergence = "composite", eta = 0.7)
  direct <- cox_indi(I$z, I$event, I$time, z_ext = ze, delta_ext = E$event, time_ext = E$time, etas = 0.7)
  expect_equal(unname(b$coefficients), unname(direct$beta[, 1]), tolerance = 1e-8)
  for (dv in c("kl", "mahalanobis")) {
    r <- suppressMessages(cv.bregsurv(tg, rel, divergence = dv, etas = c(0, 1), nfolds = 3))
    expect_equal(unname(r$coefficients_external[2]), 0)
    expect_true(is.finite(r$value))
  }
  ## records without column names are matched by position, so they must carry every covariate
  tg0 <- target_cox(I$time, I$event, unname(I$z))
  rel0 <- release_records(unname(ze), time = E$time, event = E$event)
  expect_error(bregsurv(tg0, rel0, divergence = "composite", eta = 1), "name the columns")
  rel_none <- release_records(matrix(rnorm(300), 300, 1, dimnames = list(NULL, "age")),
                              time = E$time, event = E$event)
  expect_error(bregsurv(tg, rel_none, divergence = "composite", eta = 1), "none of the target covariates")
})
