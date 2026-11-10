## the exported discrete-time families: same shape as the Cox families, and cv.bregsurv() returns
## exactly what they return

test_that("cv.bregsurv on a discrete target returns exactly the estimator it calls", {
  s <- sim_discrete(200, c(0.8, -0.6, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 11)
  bext <- c(z1 = 0.8, z2 = -0.6, z3 = 0.3); base <- exp(seq(-2.5, -1.5, length.out = 6))
  tg <- target_discrete(s$interval, s$event, s$x)
  etas <- c(0, 1, 10)
  a <- cv.bregsurv(tg, release_model(beta = bext, baseline = base), divergence = "kl", etas = etas, seed = 5)
  d <- cv.discretekl(s$x, s$event, s$interval, beta = bext, baseline = base, etas = etas, seed = 5)
  expect_identical(a$engine, "cv.discretekl")
  expect_identical(a$value, d$best$best_value)
  expect_identical(unname(coef(a)), unname(d$best$best_beta))
  expect_identical(a$folds, d$folds)

  m <- cv.bregsurv(tg, release_coef(bext), divergence = "mahalanobis", penalty = "lasso", etas = etas,
                   nlambda = 8, seed = 5)
  d <- cv.discrete_MDTL_enet(s$x, s$event, s$interval, beta = bext, etas = etas, alpha = 1, nlambda = 8, seed = 5)
  expect_identical(m$engine, "cv.discrete_MDTL_enet")
  expect_identical(m$value, d$best$best_value)
  expect_identical(m$lambda, d$best$best_lambda)
})

test_that("the families have the Cox families' result shapes", {
  s <- sim_discrete(150, c(0.8, -0.6, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 3)
  e <- sim_discrete(300, c(0.9, -0.5, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 4)
  bext <- c(z1 = 0.8, z2 = -0.6, z3 = 0.3)
  f <- discrete_MDTL(s$x, s$event, s$interval, beta = bext, etas = c(0, 1, 5))
  expect_s3_class(f, "discrete_MDTL")
  expect_identical(dim(f$beta), c(3L, 3L))
  expect_identical(dim(f$gamma), c(1L, 6L, 3L))
  r <- discretekl_ridge(s$x, s$event, s$interval, beta = bext, baseline = rep(0.1, 6), eta = 1, nlambda = 5)
  expect_identical(dim(r$beta), c(3L, 5L))
  expect_true(all(diff(r$lambda) < 0))
  i <- discrete_indi_enet(s$x, s$event, s$interval, z_ext = e$x, delta_ext = e$event, interval_ext = e$interval,
                          etas = c(0, 0.5), nlambda = 5)
  expect_length(i$beta, 2)
  expect_identical(dim(i$beta[[1]]), c(3L, 5L))
  cv <- cv.discrete_indi(s$x, s$event, s$interval, z_ext = e$x, delta_ext = e$event, interval_ext = e$interval,
                         etas = c(0, 0.5, 1), seed = 2)
  expect_s3_class(cv, "cv.discrete_indi")
  expect_named(cv$internal_stat, c("eta", "Loss"))
  expect_identical(cv$best$best_value, min(cv$internal_stat$Loss))
  expect_s3_class(cv.plot(cv), "ggplot")
})

test_that("the Kullback-Leibler family at eta = 0 is the target model, and composite at eta = 0 too", {
  s <- sim_discrete(250, c(0.8, -0.6, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 8)
  e <- sim_discrete(300, c(0.9, -0.5, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 9)
  g <- glm(y ~ 0 + k + z1 + z2 + z3, family = binomial("cloglog"), data = person_period(s),
           control = glm.control(epsilon = 1e-14, maxit = 100))
  k0 <- discretekl(s$x, s$event, s$interval, beta = c(z1 = 1), baseline = rep(0.1, 6), etas = 0)
  c0 <- discrete_indi(s$x, s$event, s$interval, z_ext = e$x, delta_ext = e$event, interval_ext = e$interval, etas = 0)
  expect_equal(unname(k0$beta[, 1]), unname(coef(g)[c("z1", "z2", "z3")]), tolerance = 1e-6)
  expect_equal(c0$beta[, 1], k0$beta[, 1], tolerance = 1e-10)
  expect_equal(unname(k0$gamma[1, , 1]), unname(coef(g)[paste0("k", 1:6)]), tolerance = 1e-6)
})

test_that("plot.cv.bregsurv draws the curve and the coefficients", {
  data(ExampleData_lowdim, package = "BregSurv")
  tr <- ExampleData_lowdim$train
  fit <- suppressWarnings(cv.bregsurv(target_cox(tr$time, tr$status, tr$z),
                                      release_coef(ExampleData_lowdim$beta_external_fair), divergence = "kl",
                                      etas = c(0, 0.1, 1, 10)))
  expect_s3_class(plot(fit), "ggplot")
  expect_s3_class(plot(fit, type = "coefficients"), "ggplot")
  expect_s3_class(plot(fit, reference = c("external model as is" = 2.6)), "ggplot")
  expect_length(fit$coefficients_target_only, 6)
  expect_length(fit$coefficients_external, 6)
})
