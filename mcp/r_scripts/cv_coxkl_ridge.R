#!/usr/bin/env Rscript
# cv_coxkl_ridge.R - dispatcher for the cv_coxkl_ridge MCP tool.
#
# K-fold cross-validation of (eta, lambda) for BregSurv::coxkl_ridge.
# Internally evaluates a 2D grid of (eta x lambda); for each eta, the best
# lambda is selected; among those per-eta winners, the global best (eta,
# lambda) pair is reported.
#
# RETURN SHAPE (consistent across all cv_*_ridge / cv_*_enet tools):
#   - etas:                array length n_etas
#   - cv_metric.values:    array length n_etas, the metric AT each eta's
#                          best lambda (this is the "1D plot data")
#   - best_lambda_per_eta: array length n_etas, the lambda selected per eta
#   - best:                {best_eta, best_lambda, best_beta, criteria}
#   - beta_best_per_eta:   p x n_etas matrix (beta at each eta's best lambda)
#   - full_grid:           {etas, lambdas (jagged list), metric (jagged list)}
#                          for users who want the full 2D surface
#
# CV CRITERIA WHITELIST (Cox FAMILY): "V&VH" / "LinPred" / "CIndex_pooled" /
# "CIndex_foldaverage". NCC criteria rejected at dispatcher level.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_coxkl_ridge.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
}

# Identify the metric column name in best_per_eta (one of "Loss",
# "CIndex_pooled", "CIndex_foldaverage"). Returns the name string.
metric_colname <- function(best_per_eta) {
  candidates <- setdiff(colnames(best_per_eta), c("eta", "lambda"))
  if (length(candidates) != 1L) {
    stop(sprintf("Unexpected best_per_eta columns: %s",
                 paste(colnames(best_per_eta), collapse = ", ")))
  }
  candidates
}

# --- External-coefficient linkage (requirement R2) ---------------------------
# The external coefficient vector is matched to the internal covariates BY NAME.
# `as.numeric` used to strip those names here, which disabled the package's
# aligner and silently reintroduced POSITIONAL borrowing whenever the two
# lengths happened to agree. Keep the names.
as_named_numeric <- function(x) {
  if (is.null(x)) return(NULL)
  nm <- names(x)
  if (is.null(nm) && is.matrix(x) && ncol(x) == 1L) nm <- rownames(x)
  v <- as.numeric(unlist(x, use.names = FALSE))
  if (!is.null(nm) && length(nm) == length(v)) names(v) <- nm
  v
}

# BregSurv zero-pads internal covariates the external model does not cover, but
# HARD-ERRORS on external names with no internal counterpart. R2 calls for those
# to be dropped, so drop them here and report exactly what was dropped.
link_external <- function(z, beta, Q = NULL) {
  zn <- colnames(z)
  bn <- names(beta)
  if (is.null(beta) || is.null(bn) || is.null(zn)) {
    return(list(beta = beta, Q = Q, linkage = list(
      matched_by = "position", n_internal = ncol(z),
      n_external = length(beta),
      covered = list(), zero_padded = list(), dropped = list())))
  }
  keep    <- bn %in% zn
  dropped <- bn[!keep]
  beta    <- beta[keep]
  if (!is.null(Q) && !is.null(rownames(Q))) {
    qk <- rownames(Q) %in% zn
    Q  <- Q[qk, qk, drop = FALSE]
  }
  list(beta = beta, Q = Q, linkage = list(
    matched_by  = "name",
    n_internal  = ncol(z),
    n_external  = length(bn),
    covered     = as.list(intersect(zn, bn)),
    zero_padded = as.list(setdiff(zn, bn)),
    dropped     = as.list(dropped)))
}

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)

  data_path <- input$data_path
  if (is.null(data_path) || !nzchar(data_path)) stop("data_path is required")
  if (!file.exists(data_path)) stop(sprintf("File not found: %s", data_path))

  ext <- tolower(tools::file_ext(data_path))
  e <- new.env()
  if (ext %in% c("rda", "rdata")) {
    load(data_path, envir = e)
  } else if (ext == "rds") {
    obj_name <- tools::file_path_sans_ext(basename(data_path))
    assign(obj_name, readRDS(data_path), envir = e)
  } else {
    stop(sprintf("Unsupported file extension: .%s", ext))
  }

  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required")
  z <- as.matrix(z); storage.mode(z) <- "double"

  time  <- as.numeric(eval_in(input$time_expr, e))
  delta <- as.numeric(eval_in(input$delta_expr, e))
  if (is.null(time))  stop("time_expr is required")
  if (is.null(delta)) stop("delta_expr is required")

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  beta <- NULL; RS <- NULL
  ext_sources <- character(0)
  if (!is.null(input$beta_expr) && nzchar(input$beta_expr)) {
    beta <- as_named_numeric(eval_in(input$beta_expr, e))
    ext_sources <- c(ext_sources, "beta_expr")
  }
  if (!is.null(input$beta_inline)) {
    beta <- as_named_numeric(input$beta_inline)
    ext_sources <- c(ext_sources, "beta_inline")
  }
  if (!is.null(input$RS_expr) && nzchar(input$RS_expr)) {
    RS <- as.matrix(as.numeric(eval_in(input$RS_expr, e)))
    ext_sources <- c(ext_sources, "RS_expr")
  }
  if (!is.null(input$RS_inline)) {
    RS <- as.matrix(as.numeric(unlist(input$RS_inline)))
    ext_sources <- c(ext_sources, "RS_inline")
  }
  if (length(ext_sources) == 0L) {
    stop("Must provide exactly one of: beta_expr, beta_inline, RS_expr, RS_inline")
  }
  if (length(ext_sources) > 1L) {
    stop(sprintf("Provide only one of: beta_expr, beta_inline, RS_expr, RS_inline (got: %s)",
                 paste(ext_sources, collapse = ", ")))
  }

  cv_criteria <- if (!is.null(input$cv_criteria)) as.character(input$cv_criteria) else "V&VH"
  if (!(cv_criteria %in% c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))) {
    stop(sprintf(
      paste0("cv_criteria must be one of Cox-family criteria: 'V&VH', 'LinPred', ",
             "'CIndex_pooled', 'CIndex_foldaverage' (got '%s'). NCC-family criteria ",
             "('loss' / 'AUC' / 'CIndex' / 'Brier') are not valid for Cox cross-validation."),
      cv_criteria))
  }

  lambda <- NULL
  if (!is.null(input$lambda)) {
    lambda <- as.numeric(unlist(input$lambda))
    if (length(lambda) == 0L) lambda <- NULL
  }
  nlambda          <- if (!is.null(input$nlambda))          as.integer(input$nlambda)          else 100L

  stratum         <- eval_in(input$stratum_expr, e)
  c_index_stratum <- eval_in(input$c_index_stratum_expr, e)
  nfolds <- if (!is.null(input$nfolds)) as.integer(input$nfolds) else 5L
  # A4: the seed is never NULL. Fold assignment is drawn with sample, so an
  # absent seed hands the cross-validated loss -- and therefore the choice
  # between candidates -- to the ambient RNG. over 30
  # unseeded rounds the recommended estimator flipped 8 times out of 30,
  # because the run-to-run wobble in the loss was four times the gap between
  # the candidates. A fixed documented default costs nothing statistically
  # (the partition is arbitrary) and makes the run repeatable by default.
  DEFAULT_CV_SEED <- 20260818L
  seed   <- if (!is.null(input$seed)) as.integer(input$seed) else DEFAULT_CV_SEED
  seed_source <- if (!is.null(input$seed)) "caller" else "bridge_default"

  .lk  <- link_external(z, beta)
  beta <- .lk$beta

  cv_fit <- cv.coxkl_ridge(
    z = z, delta = delta, time = time, stratum = stratum,
    RS = RS, beta = beta, etas = etas,
    lambda = lambda, nlambda = nlambda,
    nfolds = nfolds, cv.criteria = cv_criteria,
    c_index_stratum = c_index_stratum,
    message = FALSE, seed = seed
  )

  best_per_eta <- cv_fit$integrated_stat.best_per_eta
  metric_name  <- metric_colname(best_per_eta)

  list(
    status              = "ok",
    linkage             = .lk$linkage,
    criteria            = cv_fit$criteria,
    nfolds              = cv_fit$nfolds,
    seed                = seed,
    seed_source         = seed_source,
    rng_kind            = if (!is.null(cv_fit$rng_kind)) cv_fit$rng_kind else NA,
    folds               = if (!is.null(cv_fit$folds)) as.integer(cv_fit$folds) else NA,
    etas                = as.numeric(best_per_eta$eta),
    cv_metric           = list(name = metric_name,
                               values = as.numeric(best_per_eta[[metric_name]])),
    best_lambda_per_eta = as.numeric(best_per_eta$lambda),
    best                = list(
      best_eta    = as.numeric(cv_fit$best$best_eta),
      best_lambda = as.numeric(cv_fit$best$best_lambda),
      best_beta   = as.numeric(cv_fit$best$best_beta),
      criteria    = cv_fit$best$criteria
    ),
    beta_best_per_eta   = cv_fit$integrated_stat.betahat_best,
    n_obs               = nrow(z),
    n_covariates        = ncol(z),
    n_etas              = length(etas),
    external_via        = ext_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_coxkl_ridge.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
