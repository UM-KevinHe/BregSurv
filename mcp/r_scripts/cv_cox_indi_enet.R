#!/usr/bin/env Rscript
# cv_cox_indi_enet.R - dispatcher for the cv_cox_indi_enet MCP tool.
#
# K-fold CV of (eta, lambda) for SurvBregDiv::cox_indi_enet(). Internal
# data are split into folds; the external cohort is fully included in
# every training fold (assumed large and fixed).
#
# Same per-eta-best-lambda return shape as cv_coxkl_enet.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_cox_indi_enet.R <input.json> <output.json>")
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

  # Internal cohort
  z_int <- eval_in(input$z_int_expr, e)
  if (is.null(z_int)) stop("z_int_expr is required")
  z_int <- as.matrix(z_int); storage.mode(z_int) <- "double"

  time_int  <- as.numeric(eval_in(input$time_int_expr, e))
  delta_int <- as.numeric(eval_in(input$delta_int_expr, e))
  if (is.null(time_int))  stop("time_int_expr is required")
  if (is.null(delta_int)) stop("delta_int_expr is required")

  # External cohort
  z_ext <- eval_in(input$z_ext_expr, e)
  if (is.null(z_ext)) stop("z_ext_expr is required")
  z_ext <- as.matrix(z_ext); storage.mode(z_ext) <- "double"

  time_ext  <- as.numeric(eval_in(input$time_ext_expr, e))
  delta_ext <- as.numeric(eval_in(input$delta_ext_expr, e))
  if (is.null(time_ext))  stop("time_ext_expr is required")
  if (is.null(delta_ext)) stop("delta_ext_expr is required")

  if (ncol(z_int) != ncol(z_ext)) {
    stop(sprintf("Internal and external z must have the same number of columns (got %d vs %d)",
                 ncol(z_int), ncol(z_ext)))
  }

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  cv_criteria <- if (!is.null(input$cv_criteria)) as.character(input$cv_criteria) else "V&VH"
  if (!(cv_criteria %in% c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))) {
    stop(sprintf(
      paste0("cv_criteria must be one of Cox-family criteria: 'V&VH', 'LinPred', ",
             "'CIndex_pooled', 'CIndex_foldaverage' (got '%s'). NCC-family criteria ",
             "('loss' / 'AUC' / 'CIndex' / 'Brier') are not valid for Cox cross-validation."),
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

  stratum_int     <- eval_in(input$stratum_int_expr, e)
  stratum_ext     <- eval_in(input$stratum_ext_expr, e)
  c_index_stratum <- eval_in(input$c_index_stratum_expr, e)
  nfolds <- if (!is.null(input$nfolds)) as.integer(input$nfolds) else 5L
  seed   <- if (!is.null(input$seed))   as.integer(input$seed)   else NULL

  cv_args <- list(
    z_int = z_int, delta_int = delta_int, time_int = time_int, stratum_int = stratum_int,
    z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext, stratum_ext = stratum_ext,
    etas = etas, alpha = alpha, lambda = lambda, nlambda = nlambda,
    nfolds = nfolds, cv.criteria = cv_criteria,
    c_index_stratum = c_index_stratum,
    message = FALSE, seed = seed
  )
  if (!is.null(lambda.min.ratio)) cv_args$lambda.min.ratio <- lambda.min.ratio

  cv_fit <- do.call(cv.cox_indi_enet, cv_args)

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
    n_obs_int           = nrow(z_int),
    n_obs_ext           = nrow(z_ext),
    n_covariates        = ncol(z_int),
    n_etas              = length(etas)
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_cox_indi_enet.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
