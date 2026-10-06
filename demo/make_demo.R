#!/usr/bin/env Rscript
# Build the synthetic example the web app ships with (no patient data):
#   Rscript demo/make_demo.R
# A small kidney transplant cohort (90 patients, 8 clinical variables in their usual units) and a
# registry model fitted on 20,000 patients from a population that differs in two effects (BMI and donor
# age). The registry model covers 5 of the 8 variables and has one predictor the cohort lacks
# (hla_mismatch). Combining the two clearly beats either alone: the cohort is too small to estimate
# eight effects well, and the registry model misses three of them and is biased on two.
# `patient_id` and `site` are columns no sensible analysis adjusts for.
suppressMessages(library(survival))
RNGkind("Mersenne-Twister"); set.seed(5)
n <- 90L; shift <- 0.6
vars <- c("age", "bmi", "egfr", "hgb", "albumin", "dialysis_yrs", "donor_age", "cold_ischemia")
mu  <- c(age = 52, bmi = 27, egfr = 55, hgb = 11.5, albumin = 3.9, dialysis_yrs = 4, donor_age = 42, cold_ischemia = 16)
sdv <- c(age = 13, bmi = 5, egfr = 18, hgb = 1.6, albumin = 0.5, dialysis_yrs = 2.5, donor_age = 15, cold_ischemia = 6)
# effects per standard deviation in the cohort's population
b_int <- c(age = 0.60, bmi = -0.25, egfr = -0.50, hgb = -0.35, albumin = -0.35, dialysis_yrs = 0.40,
           donor_age = 0.35, cold_ischemia = 0.20)
b_reg <- b_int; b_reg["bmi"] <- b_int["bmi"] + 0.30 * shift; b_reg["donor_age"] <- b_int["donor_age"] - 0.25 * shift
make <- function(m, b, hla = FALSE, base = 0.0009, cens = 0.0006, maxt = 3650) {
  z <- matrix(rnorm(m * length(vars)), m, dimnames = list(NULL, vars))
  lp <- drop(z %*% b[vars]); h <- if (hla) rnorm(m) else NULL
  if (hla) lp <- lp + 0.20 * h
  tt <- rexp(m, base * exp(lp)); cc <- pmin(rexp(m, cens), maxt)
  D <- data.frame(round(sweep(sweep(z, 2, sdv[vars], "*"), 2, mu[vars], "+"), 1))
  D$followup_days <- pmax(1, round(pmin(tt, cc))); D$died <- as.integer(tt <= cc)
  if (hla) D$hla_mismatch <- round(3 + 1.5 * h)
  D
}
coh <- make(n, b_int); coh$patient_id <- seq_len(n); coh$site <- rep(1:3, length.out = n)
coh <- coh[, c("patient_id", "site", vars, "followup_days", "died")]
invisible(make(5000, b_int))                     # the test set used when this example was chosen
reg <- make(20000, b_reg, hla = TRUE)
covered <- c("age", "bmi", "egfr", "donor_age", "cold_ischemia")
f <- coxph(as.formula(paste("Surv(followup_days, died) ~", paste(c(covered, "hla_mismatch"), collapse = "+"))), data = reg)
dir.create("demo", showWarnings = FALSE)
write.csv(coh, "demo/kidney_cohort.csv", row.names = FALSE)
write.csv(data.frame(variable = names(coef(f)), coefficient = signif(unname(coef(f)), 4)),
          "demo/registry_coefficients.csv", row.names = FALSE)
cat(n, "patients,", sum(coh$died), "events; registry model with", length(coef(f)), "coefficients\n")
