#!/usr/bin/env Rscript
# poison_fixtures.R - build the admissibility test fixtures.
#
#   Rscript poison_fixtures.R <out.rda>
#
# Takes the package's own example cohorts and injects ONE violation per
# fixture, leaving everything else untouched, so a refusal can only be
# attributed to the thing that was injected. The clean originals are carried
# through as controls: the suite has to prove it does not over-refuse, which is
# the failure mode that would make the gate unusable in practice.
#
# These are deliberately built from data already in the repository rather than
# from the two real EHR cohorts, so the suite runs anywhere, in CI, and on a
# machine that holds no patient data.
#
# Every poison here was MEASURED against the installed package on 2026-08-18
# before being written down. Six of them return a silently wrong number through
# the bridge rather than an error; two die deep in the solver with a message no
# analyst can act on ("Hessian solve failed."); one returns all-NA coefficients.

args <- commandArgs(trailingOnly = TRUE)
if (!length(args)) stop("Usage: Rscript poison_fixtures.R <out.rda>")
out <- args[1]

here <- dirname(normalizePath(sub("^--file=", "", grep("^--file=",
        commandArgs(trailingOnly = FALSE), value = TRUE)[1]), mustWork = FALSE))
data_dir <- file.path(dirname(here), "data")

load(file.path(data_dir, "ExampleData_lowdim.rda"))
load(file.path(data_dir, "ExampleData_cc_lowdim.rda"))

set.seed(20260818)

tr  <- ExampleData_lowdim$train
cc  <- ExampleData_cc_lowdim$train
bex <- ExampleData_lowdim$beta_external_good

z0 <- tr$z          # data.frame, 6 numeric columns
d0 <- as.numeric(tr$status)
t0 <- as.numeric(tr$time)
ev <- which(d0 == 1)

POISON <- list(

  ## ---- controls: these must NOT be refused --------------------------------
  clean          = list(z = z0, time = t0, delta = d0),
  clean_recoded  = list(z = z0, time = t0, delta = ifelse(d0 == 1, 2, 1)),

  ## ---- outcome ------------------------------------------------------------
  # a third of the events are a different cause; the fit runs and lands on
  # neither the composite nor the cause-specific answer
  competing      = list(z = z0, time = t0,
                        delta = { s <- d0
                                  s[sample(ev, max(1, floor(length(ev) / 3)))] <- 2
                                  s }),
  # as.numeric on a factor returns CATEGORY CODES: 0/1 becomes 1/2, so every
  # subject counts as an event. This is what a CSV read with factors produces.
  event_factor   = list(z = z0, time = t0, delta = factor(d0)),
  all_events     = list(z = z0, time = t0, delta = rep(1, length(d0))),
  no_events      = list(z = z0, time = t0, delta = rep(0, length(d0))),
  event_na       = list(z = z0, time = t0,
                        delta = { s <- d0; s[c(2, 7)] <- NA; s }),

  ## ---- follow-up time -----------------------------------------------------
  time_na        = list(z = z0, delta = d0,
                        time = { t <- t0; t[c(3, 9)] <- NA; t }),
  time_zero      = list(z = z0, delta = d0,
                        time = { t <- t0; t[c(3, 9)] <- 0; t }),
  time_negative  = list(z = z0, delta = d0,
                        time = { t <- t0; t[c(3, 9)] <- -1; t }),
  time_character = list(z = z0, delta = d0, time = as.character(t0)),

  ## ---- covariates ---------------------------------------------------------
  cov_factor     = list(z = { d <- z0
                              d[[3]] <- factor(sample(c("lo", "hi"),
                                                      nrow(d), TRUE))
                              d },
                        time = t0, delta = d0),
  cov_na         = list(z = { d <- z0
                              d[sample(nrow(d), 8), 2] <- NA
                              d },
                        time = t0, delta = d0),
  cov_constant   = list(z = { d <- z0; d[[4]] <- 1; d },
                        time = t0, delta = d0),

  ## ---- the contract, not a catalogue of mistakes --------------------------
  # These three were missed by the first pass because it recorded the failures
  # that had been MEASURED rather than deriving the requirements the estimator
  # actually has. All three were then measured too, and all three run silently:
  #   Inf follow-up time      0.4120 -0.2736  0.2113   against 0.4111 -0.2673 ...
  #   20 duplicated subjects  0.4101 -0.2680  0.2187
  #   a collinear covariate   0.1149 -0.2656  0.2145   <- the first coefficient
  #                                                       loses two thirds of it
  time_infinite  = list(z = z0, delta = d0,
                        time = { t <- t0; t[4] <- Inf; t }),
  cov_infinite   = list(z = { d <- z0; d[6, 2] <- Inf; d },
                        time = t0, delta = d0),
  # duplicated rows and collinearity are ADVISORIES, not refusals: whether two
  # identical rows are one subject twice is not in the data, and a linearly
  # dependent group is handled perfectly well by the penalised members -- which
  # is precisely the choice cross-validation is here to make.
  duplicated_rows = list(z = rbind(z0, z0[1:10, , drop = FALSE]),
                         time = c(t0, t0[1:10]), delta = c(d0, d0[1:10])),
  collinear_cov   = list(z = { d <- z0; d[[5]] <- d[[1]] * 2; d },
                         time = t0, delta = d0),

  ## ---- ties: a ROUTING decision, never a refusal --------------------------
  # ceiling, not round: rounding these times to one decimal sends the smallest
  # of them to exactly 0, which trips the non-positive-time refusal and would
  # test the wrong thing.
  heavy_ties     = list(z = z0, delta = d0, time = ceiling(t0 * 10) / 10)
)

NCC <- list(
  clean       = list(z = cc$z, y = as.numeric(cc$y), stratum = cc$stratum),
  y_factor    = list(z = cc$z, y = factor(cc$y),     stratum = cc$stratum),
  y_degenerate = list(z = cc$z, y = rep(1, length(cc$y)), stratum = cc$stratum)
)

save(POISON, NCC, bex, file = out)
cat(sprintf("wrote %d cohort fixtures and %d NCC fixtures to %s\n",
            length(POISON), length(NCC), out))
