#!/usr/bin/env Rscript
# fit_cox_MDTL_ridge.R - dispatcher for the fit_cox_MDTL_ridge MCP tool.
#
# Calls BregSurv::cox_MDTL_ridge() — Cox PH with Ridge (L2) penalty +
# Mahalanobis-distance penalty toward external β. High-dimensional companion
# of cox_MDTL().
#
# DESIGN: same singular-eta convention as fit_coxkl_ridge — fit at one
# scalar eta, return the beta path along the lambda sequence at that eta.
# Multi-eta scanning belongs in cv.cox_MDTL_ridge.
#
# DESIGN INVARIANT: MDTL family never accepts RS — only `beta` (+ optional
# `vcov`). If you ever see `RS` referenced by an MDTL function, that is a bug.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_cox_MDTL_ridge.R <input.json> <output.json>")
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

  if (is.null(input$eta)) stop("eta is required (server-side defaulting handled in Python; R should never see NULL)")
  eta <- as.numeric(input$eta)
  if (length(eta) != 1L || !is.finite(eta) || eta < 0) {
    stop("eta must be a single non-negative finite scalar (got vector or invalid value)")
  }

  # External beta (required, exactly one of expr/inline)
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
  if (length(beta_sources) == 0L) stop("Must provide exactly one of: beta_expr, beta_inline")
  if (length(beta_sources) > 1L) {
    stop(sprintf("Provide only one of: beta_expr, beta_inline (got %d: %s)",
                 length(beta_sources), paste(beta_sources, collapse = ", ")))
  }
  if (length(beta) != ncol(z)) {
    stop(sprintf("Length of external beta (%d) does not match number of covariates in z (%d)",
                 length(beta), ncol(z)))
  }

  # Optional vcov (precision matrix Q)
  vcov <- NULL
  vcov_sources <- character(0)
  if (!is.null(input$vcov_expr) && nzchar(input$vcov_expr)) {
    vcov <- as.matrix(eval_in(input$vcov_expr, e))
    storage.mode(vcov) <- "double"
    vcov_sources <- c(vcov_sources, "vcov_expr")
  }
  if (!is.null(input$vcov_inline)) {
    raw <- input$vcov_inline
    mat <- do.call(rbind, lapply(raw, function(row) as.numeric(unlist(row))))
    vcov <- as.matrix(mat); storage.mode(vcov) <- "double"
    vcov_sources <- c(vcov_sources, "vcov_inline")
  }
  if (length(vcov_sources) > 1L) stop("Provide only one of: vcov_expr, vcov_inline")
  if (!is.null(vcov)) {
    if (nrow(vcov) != ncol(z) || ncol(vcov) != ncol(z)) {
      stop(sprintf("vcov must be %d x %d to match z (got %d x %d)",
                   ncol(z), ncol(z), nrow(vcov), ncol(vcov)))
    }
  }

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

  fit <- cox_MDTL_ridge(
    z              = z,
    delta          = delta,
    time           = time,
    stratum        = stratum,
    beta           = beta,
    vcov           = vcov,
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
    vcov_used    = if (length(vcov_sources) == 0L) "identity" else vcov_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_cox_MDTL_ridge.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
