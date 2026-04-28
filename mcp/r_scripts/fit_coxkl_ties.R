#!/usr/bin/env Rscript
# fit_coxkl_ties.R - dispatcher for the fit_coxkl_ties MCP tool.
#
# Called by mcp/server.py as:
#   Rscript fit_coxkl_ties.R <input.json> <output.json>
#
# Like fit_coxkl, but uses SurvBregDiv::coxkl_ties() which handles tied event
# times via the Breslow or Exact partial likelihood. Note: coxkl_ties does NOT
# accept an external risk score (RS) — `beta` is required.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_coxkl_ties.R <input.json> <output.json>")
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

  time <- eval_in(input$time_expr, e)
  if (is.null(time)) stop("time_expr is required")
  time <- as.numeric(time)

  delta <- eval_in(input$delta_expr, e)
  if (is.null(delta)) stop("delta_expr is required")
  delta <- as.numeric(delta)

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # External beta (required — coxkl_ties has no RS alternative)
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
    stop("Provide only one of: beta_expr, beta_inline")
  }
  if (length(beta) != ncol(z)) {
    stop(sprintf("Length of beta (%d) does not match number of covariates in z (%d)",
                 length(beta), ncol(z)))
  }

  ties     <- if (!is.null(input$ties)) tolower(as.character(input$ties)) else "breslow"
  if (!(ties %in% c("breslow", "exact"))) {
    stop(sprintf("ties must be 'breslow' or 'exact' (got '%s')", ties))
  }

  stratum      <- eval_in(input$stratum_expr, e)
  beta_initial <- eval_in(input$beta_initial_expr, e)
  tol          <- if (!is.null(input$tol))      as.numeric(input$tol)      else 1e-4
  Mstop        <- if (!is.null(input$Mstop))    as.integer(input$Mstop)    else 100L
  comb_max     <- if (!is.null(input$comb_max)) as.numeric(input$comb_max) else 1e7

  fit <- coxkl_ties(
    z            = z,
    delta        = delta,
    time         = time,
    stratum      = stratum,
    beta         = beta,
    etas         = etas,
    ties         = ties,
    tol          = tol,
    Mstop        = Mstop,
    message      = FALSE,
    beta_initial = beta_initial,
    comb_max     = comb_max
  )

  list(
    status        = "ok",
    eta           = as.numeric(fit$eta),
    beta          = fit$beta,
    likelihood    = as.numeric(fit$likelihood),
    n_obs         = nrow(z),
    n_covariates  = ncol(z),
    n_etas        = length(fit$eta),
    ties          = ties,
    external_via  = beta_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_coxkl_ties.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
