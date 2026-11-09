## a grouped-time cohort with complementary log-log hazards
sim_discrete <- function(n, beta, alpha, seed) {
  set.seed(seed); p <- length(beta); K <- length(alpha)
  x <- matrix(rnorm(n * p), n, p, dimnames = list(NULL, paste0("z", seq_len(p))))
  h <- 1 - exp(-exp(outer(drop(x %*% beta), alpha, "+")))
  hit <- matrix(runif(n * K), n, K) < h
  ev <- apply(hit, 1, function(r) if (any(r)) which(r)[1] else NA)
  interval <- ifelse(is.na(ev), K, ev); event <- as.integer(!is.na(ev))
  cens <- sample.int(K, n, replace = TRUE); cc <- cens < interval
  interval[cc] <- cens[cc]; event[cc] <- 0L
  interval[1] <- K
  list(x = x, interval = interval, event = event, K = K)
}

## the same cohort as one row per subject and interval at risk
person_period <- function(s) {
  rows <- rep(seq_along(s$interval), s$interval)
  k <- sequence(s$interval)
  data.frame(y = as.integer(k == s$interval[rows] & s$event[rows] == 1),
             k = factor(k, levels = seq_len(s$K)), s$x[rows, , drop = FALSE])
}
