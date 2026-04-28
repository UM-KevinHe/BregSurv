#!/usr/bin/env Rscript
# fit_coxkl_ridge.R - dispatcher for the fit_coxkl_ridge MCP tool.
#
# Calls SurvBregDiv::coxkl_ridge() — Cox PH with Ridge (L2) penalty + KL
# integration of external information. High-dimensional companion of
# coxkl(); useful when p >> n or under heavy collinearity.
#
# DESIGN: this fit takes a SINGLE `eta` (scalar) and returns the beta path
# along the lambda sequence at that one eta. Multi-eta scanning belongs in
# cv.coxkl_ridge. This is the user's intentional design — same as the
# fit_*_enet KL/MDTL functions.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_coxkl_ridge.R <input.json> <output.json>")
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
  if (is.null(z)) stop("z_expr is required")
  z <- as.matrix(z); storage.mode(z) <- "double"

  time  <- eval_in(input$time_expr, e)
  if (is.null(time)) stop("time_expr is required")
  time <- as.numeric(time)

  delta <- eval_in(input$delta_expr, e)
  if (is.null(delta)) stop("delta_expr is required")
  delta <- as.numeric(delta)

  # eta is REQUIRED at the dispatcher level. Defaulting to 0 (no borrowing)
  # happens in the Python layer, which also attaches a `_notice_eta_default`
  # so AI can surface the silent fallback to the user. By the time R sees
  # the payload, eta should already be a concrete numeric scalar.
  if (is.null(input$eta)) stop("eta is required (server-side defaulting handled in Python; R should never see NULL)")
  eta <- as.numeric(input$eta)
  if (length(eta) != 1L || !is.finite(eta) || eta < 0) {
    stop("eta must be a single non-negative finite scalar (got vector or invalid value)")
  }

  beta <- NULL; RS <- NULL
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

  # Optional ridge-specific parameters
  lambda <- NULL
  if (!is.null(input$lambda)) {
    lambda <- as.numeric(unlist(input$lambda))
    if (length(lambda) == 0L) lambda <- NULL
  }
  nlambda        <- if (!is.null(input$nlambda))        as.integer(input$nlambda)        else 100L
  penalty.factor <- if (!is.null(input$penalty_factor)) as.numeric(input$penalty_factor) else 0.999

  stratum      <- eval_in(input$stratum_expr, e)
  beta_initial <- eval_in(input$beta_initial_expr, e)
  tol       <- if (!is.null(input$tol))       as.numeric(input$tol)       else 1e-4
  Mstop     <- if (!is.null(input$Mstop))     as.integer(input$Mstop)     else 50L
  backtrack <- if (!is.null(input$backtrack)) as.logical(input$backtrack) else FALSE

  fit <- coxkl_ridge(
    z              = z,
    delta          = delta,
    time           = time,
    stratum        = stratum,
    RS             = RS,
    beta           = beta,
    eta            = eta,
    lambda         = lambda,
    nlambda        = nlambda,
    penalty.factor = penalty.factor,
    tol            = tol,
    Mstop          = Mstop,
    backtrack      = backtrack,
    beta_initial   = beta_initial,
    message        = FALSE
  )

  list(
    status       = "ok",
    eta          = eta,
    lambda       = as.numeric(fit$lambda),
    beta         = fit$beta,
    likelihood   = as.numeric(fit$likelihood),
    n_obs        = nrow(z),
    n_covariates = ncol(z),
    n_lambda     = length(fit$lambda),
    external_via = ext_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_coxkl_ridge.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
