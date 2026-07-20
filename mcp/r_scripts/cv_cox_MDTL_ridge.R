#!/usr/bin/env Rscript
# cv_cox_MDTL_ridge.R - dispatcher for the cv_cox_MDTL_ridge MCP tool.
#
# K-fold CV of (eta, lambda) for BregSurv::cox_MDTL_ridge(). Same
# 2D-grid -> per-eta-best-lambda -> global-best return shape as
# cv_coxkl_ridge.
#
# DESIGN INVARIANT: MDTL family never accepts RS — only `beta` (+ optional
# `vcov`). If you ever see `RS` referenced by an MDTL function, that is a bug.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_cox_MDTL_ridge.R <input.json> <output.json>")
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

  time  <- as.numeric(eval_in(input$time_expr, e))
  delta <- as.numeric(eval_in(input$delta_expr, e))
  if (is.null(time))  stop("time_expr is required")
  if (is.null(delta)) stop("delta_expr is required")

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # Required external beta (one of expr/inline)
  beta <- NULL
  beta_sources <- character(0)
  if (!is.null(input$beta_expr) && nzchar(input$beta_expr)) {
    beta <- as.numeric(eval_in(input$beta_expr, e))
    beta_sources <- c(beta_sources, "beta_expr")
  }
  if (!is.null(input$beta_inline)) {
    beta <- as.numeric(unlist(input$beta_inline))
    beta_sources <- c(beta_sources, "beta_inline")
  }
  if (length(beta_sources) == 0L) stop("Must provide exactly one of: beta_expr, beta_inline")
  if (length(beta_sources) > 1L) {
    stop(sprintf("Provide only one of: beta_expr, beta_inline (got %d: %s)",
                 length(beta_sources), paste(beta_sources, collapse = ", ")))
  }
  if (length(beta) != ncol(z)) {
    stop(sprintf("Length of external beta (%d) does not match number of covariates in z (%d)",
                 length(beta), ncol(z)))
  }

  # Optional vcov
  vcov <- NULL
  vcov_sources <- character(0)
  if (!is.null(input$vcov_expr) && nzchar(input$vcov_expr)) {
    vcov <- as.matrix(eval_in(input$vcov_expr, e))
    storage.mode(vcov) <- "double"
    vcov_sources <- c(vcov_sources, "vcov_expr")
  }
  if (!is.null(input$vcov_inline)) {
    raw <- input$vcov_inline
    mat <- do.call(rbind, lapply(raw, function(row) as.numeric(unlist(row))))
    vcov <- as.matrix(mat); storage.mode(vcov) <- "double"
    vcov_sources <- c(vcov_sources, "vcov_inline")
  }
  if (length(vcov_sources) > 1L) stop("Provide only one of: vcov_expr, vcov_inline")
  if (!is.null(vcov)) {
    if (nrow(vcov) != ncol(z) || ncol(vcov) != ncol(z)) {
      stop(sprintf("vcov must be %d x %d to match z (got %d x %d)",
                   ncol(z), ncol(z), nrow(vcov), ncol(vcov)))
    }
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
  lambda.min.ratio <- if (!is.null(input$lambda_min_ratio)) as.numeric(input$lambda_min_ratio) else NULL

  stratum         <- eval_in(input$stratum_expr, e)
  c_index_stratum <- eval_in(input$c_index_stratum_expr, e)
  nfolds <- if (!is.null(input$nfolds)) as.integer(input$nfolds) else 5L
  seed   <- if (!is.null(input$seed))   as.integer(input$seed)   else NULL

  cv_args <- list(
    z = z, delta = delta, time = time, stratum = stratum,
    beta = beta, vcov = vcov, etas = etas,
    lambda = lambda, nlambda = nlambda,
    nfolds = nfolds, cv.criteria = cv_criteria,
    c_index_stratum = c_index_stratum,
    message = FALSE, seed = seed
  )
  # Only set lambda.min.ratio when user supplied one; otherwise let R use
  # its expression-based default ifelse(n_obs<n_vars, 0.01, 1e-4).
  if (!is.null(lambda.min.ratio)) cv_args$lambda.min.ratio <- lambda.min.ratio

  cv_fit <- do.call(cv.cox_MDTL_ridge, cv_args)

  best_per_eta <- cv_fit$integrated_stat.best_per_eta
  metric_name  <- metric_colname(best_per_eta)

  list(
    status              = "ok",
    criteria            = cv_fit$criteria,
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
    n_covariates        = ncol(z),
    n_etas              = length(etas),
    vcov_used           = if (length(vcov_sources) == 0L) "identity" else vcov_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_cox_MDTL_ridge.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
