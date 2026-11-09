#!/usr/bin/env Rscript
# fit_ncc_indi.R - dispatcher for the fit_ncc_indi MCP tool.
#
# Called by mcp/server.py as:
#   Rscript fit_ncc_indi.R <input.json> <output.json>
#
# Calls BregSurv::ncc_indi() with individual-level external matched
# case-control data. Internally maps the matched-set problem to a stratified
# Cox model (time = 1, delta = y) and dispatches to cox_indi().
#
# NCC API: y_int + stratum_int (required) and y_ext + stratum_ext (required),
# NOT time/delta. Strata are required because the matching design is what
# defines the conditional likelihood.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_ncc_indi.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
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

  y_int <- eval_in(input$y_int_expr, e)
  if (is.null(y_int)) stop("y_int_expr is required")
  y_int <- as.numeric(y_int)

  stratum_int <- eval_in(input$stratum_int_expr, e)
  if (is.null(stratum_int)) {
    stop("stratum_int_expr is required for ncc_indi (matched-set identifier)")
  }

  # External cohort
  z_ext <- eval_in(input$z_ext_expr, e)
  if (is.null(z_ext)) stop("z_ext_expr is required (ncc_indi requires individual-level external data)")
  z_ext <- as.matrix(z_ext); storage.mode(z_ext) <- "double"

  y_ext <- eval_in(input$y_ext_expr, e)
  if (is.null(y_ext)) stop("y_ext_expr is required")
  y_ext <- as.numeric(y_ext)

  stratum_ext <- eval_in(input$stratum_ext_expr, e)
  if (is.null(stratum_ext)) {
    stop("stratum_ext_expr is required for ncc_indi (matched-set identifier)")
  }

  if (ncol(z_int) != ncol(z_ext)) {
    stop(sprintf("Internal and external z must have the same number of columns (got %d vs %d)",
                 ncol(z_int), ncol(z_ext)))
  }

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  max_iter <- if (!is.null(input$max_iter)) as.integer(input$max_iter) else 100L
  tol      <- if (!is.null(input$tol))      as.numeric(input$tol)      else 1e-7

  fit <- ncc_indi(
    y_int       = y_int,
    z_int       = z_int,
    stratum_int = stratum_int,
    y_ext       = y_ext,
    z_ext       = z_ext,
    stratum_ext = stratum_ext,
    etas        = etas,
    max_iter    = max_iter,
    tol         = tol,
    message     = FALSE
  )

  list(
    status         = "ok",
    eta            = as.numeric(fit$eta),
    beta           = fit$beta,
    n_obs_int      = length(y_int),
    n_obs_ext      = length(y_ext),
    n_strata_int   = length(unique(stratum_int)),
    n_strata_ext   = length(unique(stratum_ext)),
    n_covariates   = ncol(z_int),
    n_etas         = length(fit$eta)
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_ncc_indi.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
