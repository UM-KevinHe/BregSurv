#!/usr/bin/env Rscript
# fit_cox_indi.R - dispatcher for the fit_cox_indi MCP tool.
#
# Called by mcp/server.py as:
#   Rscript fit_cox_indi.R <input.json> <output.json>
#
# Reads JSON parameters, loads the user's data file, resolves R expressions
# for both internal and external cohorts, calls SurvBregDiv::cox_indi(), writes
# results as JSON. On any error, writes a structured {status:"error",...} payload.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_cox_indi.R <input.json> <output.json>")
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

  # --- Required: data_path ---
  data_path <- input$data_path
  if (is.null(data_path) || !nzchar(data_path)) stop("data_path is required")
  if (!file.exists(data_path)) stop(sprintf("File not found: %s", data_path))

  # --- Load data into an isolated environment ---
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

  # --- Internal cohort (required) ---
  z_int <- eval_in(input$z_int_expr, e)
  if (is.null(z_int)) stop("z_int_expr is required and must resolve to a matrix or data.frame")
  z_int <- as.matrix(z_int)
  storage.mode(z_int) <- "double"

  time_int <- eval_in(input$time_int_expr, e)
  if (is.null(time_int)) stop("time_int_expr is required")
  time_int <- as.numeric(time_int)

  delta_int <- eval_in(input$delta_int_expr, e)
  if (is.null(delta_int)) stop("delta_int_expr is required")
  delta_int <- as.numeric(delta_int)

  # --- External cohort (required - the whole point of cox_indi) ---
  z_ext <- eval_in(input$z_ext_expr, e)
  if (is.null(z_ext)) stop("z_ext_expr is required (cox_indi requires individual-level external data)")
  z_ext <- as.matrix(z_ext)
  storage.mode(z_ext) <- "double"

  time_ext <- eval_in(input$time_ext_expr, e)
  if (is.null(time_ext)) stop("time_ext_expr is required")
  time_ext <- as.numeric(time_ext)

  delta_ext <- eval_in(input$delta_ext_expr, e)
  if (is.null(delta_ext)) stop("delta_ext_expr is required")
  delta_ext <- as.numeric(delta_ext)

  if (ncol(z_int) != ncol(z_ext)) {
    stop(sprintf(
      "Internal and external z must have the same number of columns (got %d vs %d)",
      ncol(z_int), ncol(z_ext)
    ))
  }

  # --- Required: etas ---
  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # --- Optional parameters ---
  stratum_int <- eval_in(input$stratum_int_expr, e)
  stratum_ext <- eval_in(input$stratum_ext_expr, e)
  max_iter    <- if (!is.null(input$max_iter)) as.integer(input$max_iter) else 100L
  tol         <- if (!is.null(input$tol))      as.numeric(input$tol)      else 1e-7

  # --- Call cox_indi() ---
  fit <- cox_indi(
    z_int       = z_int,
    delta_int   = delta_int,
    time_int    = time_int,
    stratum_int = stratum_int,
    z_ext       = z_ext,
    delta_ext   = delta_ext,
    time_ext    = time_ext,
    stratum_ext = stratum_ext,
    etas        = etas,
    max_iter    = max_iter,
    tol         = tol,
    message     = FALSE
  )

  # --- Shape the return payload ---
  # Drops linear.predictors_int / linear.predictors_ext (large; not needed in-context).
  # cox_indi does not compute a partial likelihood, so no `likelihood` field.
  list(
    status        = "ok",
    eta           = as.numeric(fit$eta),
    beta          = fit$beta,
    n_obs_int     = nrow(z_int),
    n_obs_ext     = nrow(z_ext),
    n_covariates  = ncol(z_int),
    n_etas        = length(fit$eta)
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_cox_indi.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
