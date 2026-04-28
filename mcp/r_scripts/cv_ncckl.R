#!/usr/bin/env Rscript
# cv_ncckl.R - dispatcher for the cv_ncckl MCP tool.
#
# Cross-validates SurvBregDiv::ncckl() over a candidate `etas` grid and
# selects the best eta under the chosen cv.criteria.
#
# CV folds are constructed at the stratum level (via get_fold_cc) so the
# 1:m matched structure is preserved within every fold.
#
# CV CRITERIA WHITELIST (NCC FAMILY ONLY): "loss" / "AUC" / "CIndex" / "Brier".
# The Cox-family criteria ("V&VH" / "LinPred" / "CIndex_pooled" /
# "CIndex_foldaverage") are explicitly rejected here. If they reach the
# underlying R function instead, match.arg silently picks choices[1] which
# would silently produce nonsense — never let them through.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_ncckl.R <input.json> <output.json>")
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

  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required")
  z <- as.matrix(z); storage.mode(z) <- "double"

  y <- eval_in(input$y_expr, e)
  if (is.null(y)) stop("y_expr is required")
  y <- as.numeric(y)

  stratum <- eval_in(input$stratum_expr, e)
  if (is.null(stratum)) stop("stratum_expr is required for NCC functions")

  if (is.null(input$etas)) stop("etas is required")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

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
  if (length(beta_sources) == 0L) {
    stop("Must provide exactly one of: beta_expr, beta_inline")
  }
  if (length(beta_sources) > 1L) {
    stop(sprintf("Provide only one of: beta_expr, beta_inline (got %d: %s)",
                 length(beta_sources), paste(beta_sources, collapse = ", ")))
  }

  cv_criteria <- if (!is.null(input$cv_criteria)) as.character(input$cv_criteria) else "loss"
  if (!(cv_criteria %in% c("loss", "AUC", "CIndex", "Brier"))) {
    stop(sprintf(
      paste0("cv_criteria must be one of NCC-family criteria: 'loss', 'AUC', 'CIndex', 'Brier' ",
             "(got '%s'). Cox-family criteria ('V&VH' / 'LinPred' / 'CIndex_pooled' / ",
             "'CIndex_foldaverage') are not valid for NCC cross-validation."),
      cv_criteria))
  }

  method   <- if (!is.null(input$method))   as.character(input$method)  else "breslow"
  if (!(method %in% c("breslow", "exact"))) {
    stop(sprintf("method must be 'breslow' or 'exact' (got '%s')", method))
  }
  tol      <- if (!is.null(input$tol))      as.numeric(input$tol)       else 1e-4
  Mstop    <- if (!is.null(input$Mstop))    as.integer(input$Mstop)     else 100L
  nfolds   <- if (!is.null(input$nfolds))   as.integer(input$nfolds)    else 5L
  seed     <- if (!is.null(input$seed))     as.integer(input$seed)      else NULL

  cv_fit <- cv.ncckl(
    y           = y,
    z           = z,
    stratum     = stratum,
    beta        = beta,
    etas        = etas,
    method      = method,
    tol         = tol,
    Mstop       = Mstop,
    nfolds      = nfolds,
    cv.criteria = cv_criteria,
    message     = FALSE,
    seed        = seed
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
    n_strata     = length(unique(stratum)),
    n_covariates = ncol(z),
    n_etas       = length(cv_fit$internal_stat$eta),
    method       = method,
    external_via = beta_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_ncckl.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
