test_that("the target-only grouped-time model equals glm", {
  s <- sim_discrete(300, c(0.8, -0.6, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 11)
  fit <- bregsurv(target_discrete(s$interval, s$event, s$x))
  g <- glm(y ~ 0 + k + z1 + z2 + z3, family = binomial("cloglog"), data = person_period(s),
           control = glm.control(epsilon = 1e-14, maxit = 100))
  expect_equal(unname(coef(fit)), unname(coef(g)[c("z1", "z2", "z3")]), tolerance = 1e-6)
})

test_that("the composite likelihood equals a weighted glm on the stacked records", {
  s <- sim_discrete(300, c(0.8, -0.6, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 11)
  e <- sim_discrete(600, c(0.9, -0.5, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 12)
  fit <- bregsurv(target_discrete(s$interval, s$event, s$x),
                  release_records(e$x, interval = e$interval, event = e$event), eta = 0.5)
  li <- person_period(s); li$src <- "int"; li$w <- 1
  le <- person_period(e); le$src <- "ext"; le$w <- 0.5
  st <- rbind(li, le); st$cell <- interaction(st$src, st$k)
  g <- suppressWarnings(glm(y ~ 0 + cell + z1 + z2 + z3, family = binomial("cloglog"), weights = w, data = st,
                            control = glm.control(epsilon = 1e-14, maxit = 100)))
  expect_equal(unname(coef(fit)), unname(coef(g)[c("z1", "z2", "z3")]), tolerance = 1e-6)
})

test_that("the Kullback-Leibler divergence moves toward the external model and eta = 0 is the target alone", {
  s <- sim_discrete(200, c(0.8, -0.6, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 11)
  tg <- target_discrete(s$interval, s$event, s$x)
  bext <- c(z1 = 0.8, z2 = -0.6, z3 = 0.3)
  rl <- release_model(beta = bext, baseline = exp(seq(-2.5, -1.5, length.out = 6)))
  b0 <- coef(bregsurv(tg)); b_far <- coef(bregsurv(tg, rl, divergence = "kl", eta = 1e4))
  expect_equal(coef(bregsurv(tg, rl, divergence = "kl", eta = 0)), b0)
  expect_lt(max(abs(b_far - bext)), max(abs(b0 - bext)))
  cv <- cv.bregsurv(tg, rl, seed = 3)
  own <- cv.bregsurv(tg, seed = 3)
  expect_identical(cv$folds, own$folds)
  expect_equal(cv$path$value[cv$path$eta == 0], own$value)
})

test_that("the lasso solution satisfies its optimality conditions", {
  s <- sim_discrete(300, c(0.8, -0.6, 0.0, 0.0), seq(-2.5, -1.5, length.out = 6), seed = 4)
  lam <- 0.03
  fit <- bregsurv(target_discrete(s$interval, s$event, s$x), penalty = "lasso", lambda = lam, standardize = FALSE)
  pp <- person_period(s); n <- length(s$interval)
  f <- function(par) {
    u <- par[as.integer(pp$k)] + drop(as.matrix(pp[, paste0("z", 1:4)]) %*% par[-(1:6)])
    mu <- 1 - exp(-exp(u))
    -sum(pp$y * log(mu) + (1 - pp$y) * log1p(-mu)) / n
  }
  par <- c(fit$gamma[1, ], coef(fit))
  gr <- vapply(seq_along(par), function(j) { e <- numeric(length(par)); e[j] <- 1e-6
    (f(par + e) - f(par - e)) / 2e-6 }, numeric(1))
  b <- coef(fit); g <- gr[-(1:6)]
  expect_lt(max(abs(gr[1:6])), 1e-5)
  expect_lt(max(abs(g[b != 0] + lam * sign(b[b != 0]))), 1e-5)
  expect_true(all(abs(g[b == 0]) <= lam + 1e-5))
})
