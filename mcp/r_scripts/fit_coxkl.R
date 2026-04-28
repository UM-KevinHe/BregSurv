#!/usr/bin/env Rscript
# fit_coxkl.R — dispatcher for the fit_coxkl MCP tool.
#
# Called by mcp/server.py as:
#   Rscript fit_coxkl.R <input.json> <output.json>
#
# Reads JSON parameters, loads the user's data file, resolves R expressions
# against the loaded environment, calls SurvBregDiv::coxkl(), writes results
# as JSON. On any error, writes a structured {status:"error",...} payload.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_coxkl.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

# Evaluate an R-expression string inside a given environment.
# Returns NULL if the string is NULL or empty.
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

  # --- Required fields: z / time / delta ---
  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required and must resolve to a matrix or data.frame")
  z <- as.matrix(z)
  storage.mode(z) <- "double"

  time <- eval_in(input$time_expr, e)
  if (is.null(time)) stop("time_expr is required")
  time <- as.numeric(time)

  delta <- eval_in(input$delta_expr, e)
  if (is.null(delta)) stop("delta_expr is required")
  delta <- as.numeric(delta)

  # --- Required: etas (inline JSON array) ---
  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # --- External info: exactly one of beta_expr / beta_inline / RS_expr / RS_inline ---
  beta <- NULL
  RS   <- NULL
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
    stop(sprintf(
      "Provide only one of: beta_expr, beta_inline, RS_expr, RS_inline (got %d: %s)",
      length(ext_sources), paste(ext_sources, collapse = ", ")
    ))
  }

  # --- Optional parameters ---
  stratum      <- eval_in(input$stratum_expr, e)
  beta_initial <- eval_in(input$beta_initial_expr, e)
  tol          <- if (!is.null(input$tol))       as.numeric(input$tol)       else 1e-4
  Mstop        <- if (!is.null(input$Mstop))     as.integer(input$Mstop)     else 100L
  backtrack    <- if (!is.null(input$backtrack)) as.logical(input$backtrack) else FALSE

  # --- Call coxkl() ---
  fit <- coxkl(
    z            = z,
    delta        = delta,
    time         = time,
    stratum      = stratum,
    RS           = RS,
    beta         = beta,
    etas         = etas,
    tol          = tol,
    Mstop        = Mstop,
    backtrack    = backtrack,
    beta_initial = beta_initial,
    message      = FALSE
  )

  # --- Shape the return payload ---
  # coxkl$beta is a p x n_etas matrix; jsonlite serialises row-major.
  list(
    status        = "ok",
    eta           = as.numeric(fit$eta),
    beta          = fit$beta,
    likelihood    = as.numeric(fit$likelihood),
    n_obs         = nrow(z),
    n_covariates  = ncol(z),
    n_etas        = length(fit$eta),
    external_via  = ext_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_coxkl.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
