#!/usr/bin/env Rscript
# fit_ncckl.R - dispatcher for the fit_ncckl MCP tool.
#
# Called by mcp/server.py as:
#   Rscript fit_ncckl.R <input.json> <output.json>
#
# Reads JSON parameters, loads the user's data file, resolves R expressions
# against the loaded environment, calls BregSurv::ncckl(), writes results
# as JSON. On any error, writes a structured {status:"error",...} payload.
#
# NCC API differs from Cox in three ways enforced here:
#   - takes `y` (binary outcome) + `stratum` (matched-set ID), NOT time/delta
#   - `stratum` is REQUIRED, not optional
#   - external info is `beta` only (RS is not accepted by ncckl)

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_ncckl.R <input.json> <output.json>")
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

  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required and must resolve to a matrix or data.frame")
  z <- as.matrix(z)
  storage.mode(z) <- "double"

  y <- eval_in(input$y_expr, e)
  if (is.null(y)) stop("y_expr is required (binary outcome: 1=case, 0=control)")
  y <- as.numeric(y)

  stratum <- eval_in(input$stratum_expr, e)
  if (is.null(stratum)) {
    stop("stratum_expr is required for NCC functions (matched-set identifier)")
  }

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # External info: ncckl accepts only `beta` (no RS).
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
  if (length(beta) != ncol(z)) {
    stop(sprintf("Length of external beta (%d) does not match number of covariates in z (%d)",
                 length(beta), ncol(z)))
  }

  method   <- if (!is.null(input$method))   as.character(input$method)  else "breslow"
  if (!(method %in% c("breslow", "exact"))) {
    stop(sprintf("method must be 'breslow' or 'exact' (got '%s'). NOTE: this controls the matched-set likelihood form (1:M vs n:m), NOT tie-handling — every NCC matched set has exactly one event by construction.", method))
  }
  tol      <- if (!is.null(input$tol))      as.numeric(input$tol)       else 1e-4
  Mstop    <- if (!is.null(input$Mstop))    as.integer(input$Mstop)     else 100L
  comb_max <- if (!is.null(input$comb_max)) as.numeric(input$comb_max)  else 1e7

  fit <- ncckl(
    y        = y,
    z        = z,
    stratum  = stratum,
    etas     = etas,
    beta     = beta,
    method   = method,
    Mstop    = Mstop,
    tol      = tol,
    message  = FALSE,
    comb_max = comb_max
  )

  list(
    status        = "ok",
    eta           = as.numeric(fit$eta),
    beta          = fit$beta,
    likelihood    = as.numeric(fit$likelihood),
    n_obs         = nrow(z),
    n_strata      = length(unique(stratum)),
    n_covariates  = ncol(z),
    n_etas        = length(fit$eta),
    method        = method,
    external_via  = beta_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_ncckl.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
