#!/usr/bin/env Rscript
# cv_ncckl_enet.R - dispatcher for the cv_ncckl_enet MCP tool.
#
# K-fold CV of (eta, lambda) for BregSurv::ncckl_enet(). Same per-eta-best-
# lambda 1D return shape as cv_coxkl_enet, plus alpha + n_strata.
#
# CV CRITERIA WHITELIST (NCC FAMILY ONLY): "loss" / "AUC" / "CIndex" / "Brier".
# Cox-family criteria rejected at dispatcher level.
#
# IMPORTANT: cv.ncckl_enet() accepts BOTH `beta` AND `RS` (mutually exclusive),
# UNLIKE base cv.ncckl() which only accepts `beta`. Mirrors cv.coxkl_enet.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_ncckl_enet.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
}

metric_colname <- function(best_per_eta) {
  candidates <- setdiff(colnames(best_per_eta), c("eta", "lambda"))
  if (length(candidates) != 1L) {
    stop(sprintf("Unexpected best_per_eta columns: %s",
                 paste(colnames(best_per_eta), collapse = ", ")))
  }
  candidates
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

  y <- eval_in(input$y_expr, e)
  if (is.null(y)) stop("y_expr is required")
  y <- as.numeric(y)

  stratum <- eval_in(input$stratum_expr, e)
  if (is.null(stratum)) stop("stratum_expr is required for NCC functions")

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  beta <- NULL; RS <- NULL
  ext_sources <- character(0)
  if (!is.null(input$beta_expr) && nzchar(input$beta_expr)) {
    beta <- as.numeric(eval_in(input$beta_expr, e))
    ext_sources <- c(ext_sources, "beta_expr")
  }
  if (!is.null(input$beta_inline)) {
    beta <- as.numeric(unlist(input$beta_inline))
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

  cv_criteria <- if (!is.null(input$cv_criteria)) as.character(input$cv_criteria) else "loss"
  if (!(cv_criteria %in% c("loss", "AUC", "CIndex", "Brier"))) {
    stop(sprintf(
      paste0("cv_criteria must be one of NCC-family criteria: 'loss', 'AUC', 'CIndex', 'Brier' ",
             "(got '%s'). Cox-family criteria ('V&VH' / 'LinPred' / 'CIndex_pooled' / ",
             "'CIndex_foldaverage') are not valid for NCC cross-validation."),
      cv_criteria))
  }

  alpha   <- if (!is.null(input$alpha)) as.numeric(input$alpha) else 1.0
  lambda  <- NULL
  if (!is.null(input$lambda)) {
    lambda <- as.numeric(unlist(input$lambda))
    if (length(lambda) == 0L) lambda <- NULL
  }
  nlambda          <- if (!is.null(input$nlambda))          as.integer(input$nlambda)          else 100L
  lambda.min.ratio <- if (!is.null(input$lambda_min_ratio)) as.numeric(input$lambda_min_ratio) else NULL

  nfolds <- if (!is.null(input$nfolds)) as.integer(input$nfolds) else 5L
  seed   <- if (!is.null(input$seed))   as.integer(input$seed)   else NULL

  cv_args <- list(
    y = y, z = z, stratum = stratum,
    RS = RS, beta = beta, etas = etas,
    alpha = alpha, lambda = lambda, nlambda = nlambda,
    nfolds = nfolds, cv.criteria = cv_criteria,
    message = FALSE, seed = seed
  )
  if (!is.null(lambda.min.ratio)) cv_args$lambda.min.ratio <- lambda.min.ratio

  cv_fit <- do.call(cv.ncckl_enet, cv_args)

  best_per_eta <- cv_fit$integrated_stat.best_per_eta
  metric_name  <- metric_colname(best_per_eta)

  list(
    status              = "ok",
    criteria            = cv_fit$criteria,
    alpha               = as.numeric(cv_fit$alpha),
    nfolds              = cv_fit$nfolds,
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
    n_strata            = length(unique(stratum)),
    n_covariates        = ncol(z),
    n_etas              = length(etas),
    external_via        = ext_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_ncckl_enet.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
