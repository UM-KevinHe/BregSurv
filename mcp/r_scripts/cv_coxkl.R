#!/usr/bin/env Rscript
# cv_coxkl.R - dispatcher for the cv_coxkl MCP tool.
#
# Called by mcp/server.py as:
#   Rscript cv_coxkl.R <input.json> <output.json>
#
# Cross-validates SurvBregDiv::coxkl() over a candidate `etas` grid and
# selects the best eta under the chosen cv.criteria.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_coxkl.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
}

# Map cv.coxkl's data.frame `internal_stat` (eta + one metric column) into a
# {name, values} pair so the JSON return shape is uniform across all cv.*
# tools.
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

  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required")
  z <- as.matrix(z)
  storage.mode(z) <- "double"

  time  <- as.numeric(eval_in(input$time_expr, e))
  delta <- as.numeric(eval_in(input$delta_expr, e))
  if (is.null(time))  stop("time_expr is required")
  if (is.null(delta)) stop("delta_expr is required")

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # External info: exactly one of beta_expr / beta_inline / RS_expr / RS_inline
  beta <- NULL
  RS <- NULL
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

  cv_criteria <- if (!is.null(input$cv_criteria)) as.character(input$cv_criteria) else "V&VH"
  if (!(cv_criteria %in% c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))) {
    stop(sprintf("cv_criteria must be one of 'V&VH', 'LinPred', 'CIndex_pooled', 'CIndex_foldaverage' (got '%s')",
                 cv_criteria))
  }

  stratum         <- eval_in(input$stratum_expr, e)
  c_index_stratum <- eval_in(input$c_index_stratum_expr, e)
  tol       <- if (!is.null(input$tol))       as.numeric(input$tol)       else 1e-4
  Mstop     <- if (!is.null(input$Mstop))     as.integer(input$Mstop)     else 100L
  backtrack <- if (!is.null(input$backtrack)) as.logical(input$backtrack) else FALSE
  nfolds    <- if (!is.null(input$nfolds))    as.integer(input$nfolds)    else 5L
  seed      <- if (!is.null(input$seed))      as.integer(input$seed)      else NULL

  cv_fit <- cv.coxkl(
    z = z, delta = delta, time = time, stratum = stratum,
    RS = RS, beta = beta, etas = etas,
    tol = tol, Mstop = Mstop, backtrack = backtrack,
    nfolds = nfolds, cv.criteria = cv_criteria,
    c_index_stratum = c_index_stratum,
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
    n_obs        = nrow(z),
    n_covariates = ncol(z),
    n_etas       = length(cv_fit$internal_stat$eta),
    external_via = ext_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_coxkl.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
