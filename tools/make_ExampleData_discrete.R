## Builds data/ExampleData_discrete.rda: a simulated discrete-time cohort, an external registry
## cohort from a related population, and the registry's published model.
##
##   Rscript tools/make_ExampleData_discrete.R            # from the package root
##
## Six intervals (say, years after transplant); the interval hazard follows a grouped
## proportional-hazards (complementary log-log) model. The registry's population has somewhat
## different effects and a higher baseline; its published model is a grouped proportional-hazards
## fit on Z1-Z5 (the registry did not record Z6).

make_ExampleData_discrete <- function(seed = 25L, n_train = 150, n_test = 2000, n_external = 1000) {
  set.seed(seed, kind = "Mersenne-Twister")
  K <- 6
  alpha <- seq(-2.6, -1.8, length.out = K)
  beta <- c(Z1 = 0.7, Z2 = -0.6, Z3 = 0.5, Z4 = -0.4, Z5 = 0.3, Z6 = 0)
  beta_registry <- c(Z1 = 0.8, Z2 = -0.5, Z3 = 0.6, Z4 = -0.3, Z5 = 0.35, Z6 = 0)
  covariates <- function(n) data.frame(Z1 = rnorm(n), Z2 = rnorm(n), Z3 = rnorm(n),
                                       Z4 = rbinom(n, 1, 0.5), Z5 = rnorm(n), Z6 = rnorm(n))
  draw <- function(n, b, a) {
    z <- covariates(n)
    h <- 1 - exp(-exp(outer(drop(as.matrix(z) %*% b), a, "+")))
    hit <- matrix(runif(n * K), n, K) < h
    first <- apply(hit, 1, function(r) if (any(r)) which(r)[1] else NA)
    interval <- ifelse(is.na(first), K, first)
    status <- as.integer(!is.na(first))
    censor <- sample.int(K, n, replace = TRUE)          # censored at the end of a random interval
    cens <- censor < interval
    interval[cens] <- censor[cens]; status[cens] <- 0L
    list(z = z, interval = as.integer(interval), status = status)
  }
  train <- draw(n_train, beta, alpha)
  test <- draw(n_test, beta, alpha)
  external <- draw(n_external, beta_registry, alpha + 0.15)

  ## the registry's published model, fitted to its own records on Z1-Z5
  rows <- rep(seq_along(external$interval), external$interval)
  k <- sequence(external$interval)
  pp <- data.frame(y = as.integer(k == external$interval[rows] & external$status[rows] == 1),
                   k = factor(k, levels = seq_len(K)), external$z[rows, paste0("Z", 1:5)])
  fit <- stats::glm(y ~ 0 + k + Z1 + Z2 + Z3 + Z4 + Z5, family = stats::binomial("cloglog"), data = pp)
  covered <- paste0("Z", 1:5)
  beta_external <- stats::coef(fit)[covered]
  Q_external <- solve(stats::vcov(fit)[covered, covered])
  baseline_external <- unname(exp(stats::coef(fit)[paste0("k", seq_len(K))]))

  list(train = train, test = test, external = external,
       beta_external = beta_external, Q_external = Q_external, baseline_external = baseline_external)
}

if (sys.nframe() == 0L) {
  ExampleData_discrete <- make_ExampleData_discrete()
  save(ExampleData_discrete, file = file.path("data", "ExampleData_discrete.rda"), compress = "xz")
  cat("wrote data/ExampleData_discrete.rda\n")
}
