#!/usr/bin/env Rscript
# fit_ncckl_enet.R - dispatcher for the fit_ncckl_enet MCP tool.
#
# Calls SurvBregDiv::ncckl_enet() — NCC conditional logistic regression with
# elastic-net penalty + KL divergence integration of external β. Single-eta
# convention.
#
# IMPORTANT: ncckl_enet() accepts BOTH `beta` AND `RS` (mutually exclusive),
# UNLIKE base ncckl() which only accepts `beta`. Mirrors coxkl_enet's design.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_ncckl_enet.R <input.json> <output.json>")
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

  y <- eval_in(input$y_expr, e)
  if (is.null(y)) stop("y_expr is required (binary outcome: 1=case, 0=control)")
  y <- as.numeric(y)

  stratum <- eval_in(input$stratum_expr, e)
  if (is.null(stratum)) stop("stratum_expr is required for NCC functions (matched-set identifier)")

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

  alpha   <- if (!is.null(input$alpha)) as.numeric(input$alpha) else 1.0
  lambda  <- NULL
  if (!is.null(input$lambda)) {
    lambda <- as.numeric(unlist(input$lambda))
    if (length(lambda) == 0L) lambda <- NULL
  }
  nlambda          <- if (!is.null(input$nlambda))          as.integer(input$nlambda)          else 100L
  lambda.min.ratio <- if (!is.null(input$lambda_min_ratio)) as.numeric(input$lambda_min_ratio) else 1e-3

  tol   <- if (!is.null(input$tol))   as.numeric(input$tol)   else 1e-4
  Mstop <- if (!is.null(input$Mstop)) as.integer(input$Mstop) else 1000L

  fit <- ncckl_enet(
    y                = y,
    z                = z,
    stratum          = stratum,
    RS               = RS,
    beta             = beta,
    eta              = eta,
    alpha            = alpha,
    lambda           = lambda,
    nlambda          = nlambda,
    lambda.min.ratio = lambda.min.ratio,
    tol              = tol,
    Mstop            = Mstop,
    message          = FALSE
  )

  list(
    status       = "ok",
    eta          = eta,
    alpha        = as.numeric(fit$alpha),
    lambda       = as.numeric(fit$lambda),
    beta         = fit$beta,
    likelihood   = as.numeric(fit$likelihood),
    n_obs        = nrow(z),
    n_strata     = length(unique(stratum)),
    n_covariates = ncol(z),
    n_lambda     = length(fit$lambda),
    external_via = ext_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_ncckl_enet.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
