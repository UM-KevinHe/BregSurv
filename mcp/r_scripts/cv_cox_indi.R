#!/usr/bin/env Rscript
# cv_cox_indi.R - dispatcher for the cv_cox_indi MCP tool.
#
# Cross-validates BregSurv::cox_indi() over a candidate `etas` grid.
# Internal data are split into folds; for each fold the model is trained on
# (internal-train + full external) and evaluated on the held-out internal
# fold. External data are always fully included in training.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_cox_indi.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
}

extract_metric <- function(internal_stat) {
  cn <- setdiff(colnames(internal_stat), "eta")
  if (length(cn) != 1L) {
    stop(sprintf("Unexpected internal_stat columns: %s",
                 paste(colnames(internal_stat), collapse = ", ")))
  }
  list(name = cn, values = as.numeric(internal_stat[[cn]]))
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

  z_int <- eval_in(input$z_int_expr, e)
  if (is.null(z_int)) stop("z_int_expr is required")
  z_int <- as.matrix(z_int); storage.mode(z_int) <- "double"

  time_int  <- as.numeric(eval_in(input$time_int_expr, e))
  delta_int <- as.numeric(eval_in(input$delta_int_expr, e))
  if (is.null(time_int))  stop("time_int_expr is required")
  if (is.null(delta_int)) stop("delta_int_expr is required")

  z_ext <- eval_in(input$z_ext_expr, e)
  if (is.null(z_ext)) stop("z_ext_expr is required (cv.cox_indi requires individual-level external data)")
  z_ext <- as.matrix(z_ext); storage.mode(z_ext) <- "double"

  time_ext  <- as.numeric(eval_in(input$time_ext_expr, e))
  delta_ext <- as.numeric(eval_in(input$delta_ext_expr, e))
  if (is.null(time_ext))  stop("time_ext_expr is required")
  if (is.null(delta_ext)) stop("delta_ext_expr is required")

  if (ncol(z_int) != ncol(z_ext)) {
    stop(sprintf("Internal and external z must have the same number of columns (got %d vs %d)",
                 ncol(z_int), ncol(z_ext)))
  }

  if (is.null(input$etas)) stop("etas is required")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  cv_criteria <- if (!is.null(input$cv_criteria)) as.character(input$cv_criteria) else "V&VH"
  if (!(cv_criteria %in% c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))) {
    stop(sprintf("cv_criteria must be one of 'V&VH', 'LinPred', 'CIndex_pooled', 'CIndex_foldaverage' (got '%s')",
                 cv_criteria))
  }

  stratum_int     <- eval_in(input$stratum_int_expr, e)
  stratum_ext     <- eval_in(input$stratum_ext_expr, e)
  c_index_stratum <- eval_in(input$c_index_stratum_expr, e)
  max_iter <- if (!is.null(input$max_iter)) as.integer(input$max_iter) else 100L
  tol      <- if (!is.null(input$tol))      as.numeric(input$tol)      else 1e-7
  nfolds   <- if (!is.null(input$nfolds))   as.integer(input$nfolds)   else 5L
  seed     <- if (!is.null(input$seed))     as.integer(input$seed)     else NULL

  cv_fit <- cv.cox_indi(
    z_int = z_int, delta_int = delta_int, time_int = time_int, stratum_int = stratum_int,
    z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext, stratum_ext = stratum_ext,
    etas = etas, nfolds = nfolds, cv.criteria = cv_criteria,
    c_index_stratum = c_index_stratum,
    max_iter = max_iter, tol = tol,
    message = FALSE, seed = seed
  )

  metric <- extract_metric(cv_fit$internal_stat)

  list(
    status       = "ok",
    criteria     = cv_fit$criteria,
    nfolds       = cv_fit$nfolds,
    etas         = as.numeric(cv_fit$internal_stat$eta),
    cv_metric    = metric,
    best         = list(
      best_eta  = as.numeric(cv_fit$best$best_eta),
      best_beta = as.numeric(cv_fit$best$best_beta),
      criteria  = cv_fit$best$criteria
    ),
    beta_full    = cv_fit$beta_full,
    n_obs_int    = nrow(z_int),
    n_obs_ext    = nrow(z_ext),
    n_covariates = ncol(z_int),
    n_etas       = length(cv_fit$internal_stat$eta)
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_cox_indi.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
