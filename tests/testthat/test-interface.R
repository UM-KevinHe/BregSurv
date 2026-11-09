test_that("cv.bregsurv returns exactly what the estimator it calls returns", {
  data(ExampleData_lowdim, package = "BregSurv")
  tr <- ExampleData_lowdim$train; z <- as.matrix(tr$z); b <- ExampleData_lowdim$beta_external_fair
  tg <- target_cox(tr$time, tr$status, z)
  etas <- c(0, 0.1, 1, 10)
  a <- suppressWarnings(cv.bregsurv(tg, release_coef(b), member = "kl", etas = etas, seed = 7))
  d <- suppressWarnings(cv.coxkl(z, tr$status, tr$time, beta = b, etas = etas, seed = 7, cv.criteria = "V&VH"))
  expect_identical(a$value, d$best$best_value)
  expect_equal(unname(coef(a)), as.numeric(d$best$best_beta), tolerance = 0)
  expect_identical(a$engine, "cv.coxkl")

  m <- suppressWarnings(cv.bregsurv(tg, release_coef(b), member = "mahalanobis", etas = etas, seed = 7))
  d <- suppressWarnings(cv.cox_MDTL(z, tr$status, tr$time, beta = b, etas = etas, seed = 7, cv.criteria = "V&VH"))
  expect_identical(m$value, d$best$best_value)
})

test_that("members fitted with one seed share one partition", {
  data(ExampleData_lowdim, package = "BregSurv")
  tr <- ExampleData_lowdim$train
  tg <- target_cox(tr$time, tr$status, tr$z)
  rl <- release_coef(ExampleData_lowdim$beta_external_fair)
  k <- suppressWarnings(cv.bregsurv(tg, rl, member = "kl", etas = c(0, 1), seed = 3))
  o <- suppressWarnings(cv.bregsurv(tg, seed = 3))
  expect_identical(k$folds, o$folds)
  expect_identical(o$eta, 0)
})

test_that("a release supports only the members its form admits", {
  set.seed(1)
  tg <- target_discrete(rep(1:5, 20), rep(0:1, 50), matrix(rnorm(200), 100))
  expect_error(cv.bregsurv(tg, release_score(rnorm(100))), "interval hazards")
  data(ExampleData_cc_lowdim, package = "BregSurv")
  C <- ExampleData_cc_lowdim$train
  tc <- target_ncc(C$y, C$stratum, C$z)
  expect_error(cv.bregsurv(tc, release_records(C$z, case = C$y, set = C$stratum), penalty = "ridge"), "ridge")
  expect_error(target_ncc(c(1, 1, 0), c(1, 1, 1), matrix(1:3)), "exactly one case")
})
