## Additions to the example data used by Get started:
##   * ExampleData_lowdim$score_external: the scores a published risk calculator gives the train and
##     test subjects of ExampleData_lowdim (the calculator is the linear predictor of
##     beta_external_poor, i.e. it was built on two of the six covariates);
##   * ExampleData_ties: the ExampleData_lowdim cohorts with follow-up recorded on a grid (times rounded
##     up to the next multiple of 0.05), so that many event times are tied.
##
##   Rscript tools/make_ExampleData_extras.R            # from the package root

load(file.path("data", "ExampleData_lowdim.rda"))
calculator <- ExampleData_lowdim$beta_external_poor
ExampleData_lowdim$score_external <- list(
  train = drop(as.matrix(ExampleData_lowdim$train$z) %*% calculator),
  test = drop(as.matrix(ExampleData_lowdim$test$z) %*% calculator))
save(ExampleData_lowdim, file = file.path("data", "ExampleData_lowdim.rda"), compress = "xz")

grid <- 0.05
on_grid <- function(d) list(z = d$z, time = ceiling(d$time / grid) * grid, status = d$status)
ExampleData_ties <- list(train = on_grid(ExampleData_lowdim$train), test = on_grid(ExampleData_lowdim$test),
                         beta_external = ExampleData_lowdim$beta_external_fair)
save(ExampleData_ties, file = file.path("data", "ExampleData_ties.rda"), compress = "xz")

ev <- ExampleData_ties$train$time[ExampleData_ties$train$status == 1]
cat("ExampleData_ties: ", length(ev), " events at ", length(unique(ev)), " distinct times\n", sep = "")
