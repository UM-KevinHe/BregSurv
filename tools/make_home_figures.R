## Builds man/figures/home-cv-curve.png, the cross-validation curve on the website's home page
## (pkgdown/index.md), from the first fit shown there. Needs BregSurv installed.
##
##   Rscript tools/make_home_figures.R            # from the package root
suppressPackageStartupMessages(library(BregSurv))
data(ExampleData_lowdim)
tr <- ExampleData_lowdim$train
target <- target_cox(time = tr$time, event = tr$status, z = tr$z)
fit <- cv.bregsurv(target, release_coef(ExampleData_lowdim$beta_external_poor), divergence = "kl")
out <- file.path("man", "figures", "home-cv-curve.png")
ggplot2::ggsave(out, plot(fit), width = 7, height = 4.2, dpi = 150, bg = "white")
cat("wrote", out, "\n")
