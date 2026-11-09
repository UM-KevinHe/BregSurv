#!/usr/bin/env Rscript
# fit_cox_indi_enet.R - dispatcher for the fit_cox_indi_enet MCP tool.
#
# Calls BregSurv::cox_indi_enet() — Cox PH with elastic-net + dual-cohort
# composite likelihood. Internal observations get weight 1, external get
# weight `eta`. eta=0 recovers internal-only fit.
#
# DESIGN: this fit takes PLURAL `etas` — different from the singular-eta
# convention of fit_coxkl_enet / fit_cox_MDTL_enet. Returns a jagged
# structure: per-eta beta matrices and per-eta lambda sequences (each eta
# has its own auto-generated lambda path).

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_cox_indi_enet.R <input.json> <output.json>")
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

  # PLURAL etas (no defaulting policy; required, like base cox_indi)
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

  stratum_int <- eval_in(input$stratum_int_expr, e)
  stratum_ext <- eval_in(input$stratum_ext_expr, e)
  tol   <- if (!is.null(input$tol))   as.numeric(input$tol)   else 1e-4
  Mstop <- if (!is.null(input$Mstop)) as.integer(input$Mstop) else 1000L

  enet_args <- list(
    z_int       = z_int,
    delta_int   = delta_int,
    time_int    = time_int,
    stratum_int = stratum_int,
    z_ext       = z_ext,
    delta_ext   = delta_ext,
    time_ext    = time_ext,
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

  fit <- do.call(cox_indi_enet, enet_args)

  # fit$beta and fit$lambda are LISTS keyed by eta (jagged). Convert each
  # eta's per-lambda beta matrix to row-major numeric for JSON.
  beta_per_eta   <- lapply(fit$beta,   function(m) as.matrix(m))
  lambda_per_eta <- lapply(fit$lambda, function(v) as.numeric(v))

  list(
    status            = "ok",
    etas              = as.numeric(fit$eta),
    alpha             = as.numeric(fit$alpha),
    beta_per_eta      = beta_per_eta,           # list of p x L_i matrices
    lambda_per_eta    = lambda_per_eta,         # list of numeric vectors
    n_obs_int         = nrow(z_int),
    n_obs_ext         = nrow(z_ext),
    n_covariates      = ncol(z_int),
    n_etas            = length(etas),
    n_lambda_per_eta  = vapply(lambda_per_eta, length, integer(1L))
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_cox_indi_enet.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
