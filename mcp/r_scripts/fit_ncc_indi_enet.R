#!/usr/bin/env Rscript
# fit_ncc_indi_enet.R - dispatcher for the fit_ncc_indi_enet MCP tool.
#
# Calls SurvBregDiv::ncc_indi_enet() — NCC + elastic-net + dual-cohort
# composite likelihood. Internal weight 1, external weight = eta.
#
# DESIGN: PLURAL `etas` (no scalar; no eta-default policy). Returns jagged
# structure: per-eta beta matrices and per-eta lambda sequences.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_ncc_indi_enet.R <input.json> <output.json>")
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
  if (is.null(stratum_int)) stop("stratum_int_expr is required for ncc_indi_enet")

  # External cohort
  z_ext <- eval_in(input$z_ext_expr, e)
  if (is.null(z_ext)) stop("z_ext_expr is required")
  z_ext <- as.matrix(z_ext); storage.mode(z_ext) <- "double"

  y_ext <- eval_in(input$y_ext_expr, e)
  if (is.null(y_ext)) stop("y_ext_expr is required")
  y_ext <- as.numeric(y_ext)

  stratum_ext <- eval_in(input$stratum_ext_expr, e)
  if (is.null(stratum_ext)) stop("stratum_ext_expr is required for ncc_indi_enet")

  if (ncol(z_int) != ncol(z_ext)) {
    stop(sprintf("Internal and external z must have the same number of columns (got %d vs %d)",
                 ncol(z_int), ncol(z_ext)))
  }

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  alpha   <- if (!is.null(input$alpha)) as.numeric(input$alpha) else 1.0
  lambda  <- NULL
  if (!is.null(input$lambda)) {
    lambda <- as.numeric(unlist(input$lambda))
    if (length(lambda) == 0L) lambda <- NULL
  }
  nlambda          <- if (!is.null(input$nlambda))          as.integer(input$nlambda)          else 100L
  lambda.min.ratio <- if (!is.null(input$lambda_min_ratio)) as.numeric(input$lambda_min_ratio) else NULL

  tol   <- if (!is.null(input$tol))   as.numeric(input$tol)   else 1e-4
  Mstop <- if (!is.null(input$Mstop)) as.integer(input$Mstop) else 1000L

  enet_args <- list(
    y_int       = y_int,
    z_int       = z_int,
    stratum_int = stratum_int,
    y_ext       = y_ext,
    z_ext       = z_ext,
    stratum_ext = stratum_ext,
    etas        = etas,
    alpha       = alpha,
    lambda      = lambda,
    nlambda     = nlambda,
    tol         = tol,
    Mstop       = Mstop,
    message     = FALSE
  )
  if (!is.null(lambda.min.ratio)) enet_args$lambda.min.ratio <- lambda.min.ratio

  fit <- do.call(ncc_indi_enet, enet_args)

  beta_per_eta   <- lapply(fit$beta,   function(m) as.matrix(m))
  lambda_per_eta <- lapply(fit$lambda, function(v) as.numeric(v))

  list(
    status            = "ok",
    etas              = as.numeric(fit$eta),
    alpha             = as.numeric(fit$alpha),
    beta_per_eta      = beta_per_eta,
    lambda_per_eta    = lambda_per_eta,
    n_obs_int         = nrow(z_int),
    n_obs_ext         = nrow(z_ext),
    n_strata_int      = length(unique(stratum_int)),
    n_strata_ext      = length(unique(stratum_ext)),
    n_covariates      = ncol(z_int),
    n_etas            = length(etas),
    n_lambda_per_eta  = vapply(lambda_per_eta, length, integer(1L))
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_ncc_indi_enet.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
