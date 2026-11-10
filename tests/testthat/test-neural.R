skip_if_not_installed("torch")
skip_if_not(torch::torch_is_installed(), "torch backend not installed")

test_that("the network's Cox loss is the package's partial likelihood", {
  ns <- asNamespace("BregSurv")
  set.seed(1); n <- 50
  time <- sort(sample(1:20, n, replace = TRUE)); delta <- rbinom(n, 1, 0.6); r <- rnorm(n)
  for (ties in c("none", "breslow")) {
    b <- list(time = time, delta = delta, stratum = rep(1, n), dtilde = numeric(n), ties = ties)
    loss <- ns$.nn_cox_loss(torch::torch_tensor(r, dtype = torch::torch_float64()), b, seq_len(n), 0)$item()
    expect_equal(loss * n, -ns$.pl_ties(r, delta, time, n, ties), tolerance = 1e-8)
  }
})

test_that("a small discrete network fits, predicts and is reproducible", {
  s <- sim_discrete(150, c(0.8, -0.6, 0.3), seq(-2.5, -1.5, length.out = 6), seed = 2)
  spec <- nn_score(hidden = 16, learning_rates = 1e-3, max_epochs = 30, patience = 3)
  tg <- target_discrete(s$interval, s$event, s$x, score = spec)
  rl <- release_model(beta = c(z1 = 0.8, z2 = -0.6, z3 = 0.3), baseline = exp(seq(-2.5, -1.5, length.out = 6)))
  a <- cv.bregsurv(tg, rl, etas = c(0, 5), nfolds = 3, seed = 1)
  b <- cv.bregsurv(tg, rl, etas = c(0, 5), nfolds = 3, seed = 1)
  expect_true(all(is.finite(a$path$value)))
  expect_identical(a$path, b$path)
  H <- predict(a, s$x[1:4, ], type = "hazard")
  expect_true(all(H > 0 & H < 1))
})
