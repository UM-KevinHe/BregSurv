#!/usr/bin/env Rscript
# fit_ncc_MDTL.R - dispatcher for the fit_ncc_MDTL MCP tool.
#
# Called by mcp/server.py as:
#   Rscript fit_ncc_MDTL.R <input.json> <output.json>
#
# Calls SurvBregDiv::ncc_MDTL() with external beta and optional precision
# matrix vcov. Penalty is (eta/2) * (beta - beta_ext)^T Q (beta - beta_ext).
#
# DESIGN INVARIANT: MDTL family never accepts RS. Only `beta` (+ optional
# `vcov`). If you ever see RS as a parameter or returned field for an MDTL
# function, that's a bug — see CLAUDE.md "MDTL never accepts RS" rule.

suppressPackageStartupMessages({
  library(jsonlite)
  library(SurvBregDiv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_ncc_MDTL.R <input.json> <output.json>")
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
  if (is.null(stratum)) {
    stop("stratum_expr is required for NCC functions (matched-set identifier)")
  }

  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

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

  # Optional vcov (precision / covariance matrix)
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
  if (length(vcov_sources) > 1L) {
    stop("Provide only one of: vcov_expr, vcov_inline")
  }
  if (!is.null(vcov)) {
    if (nrow(vcov) != ncol(z) || ncol(vcov) != ncol(z)) {
      stop(sprintf("vcov must be %d x %d to match z (got %d x %d)",
                   ncol(z), ncol(z), nrow(vcov), ncol(vcov)))
    }
  }

  beta_initial <- eval_in(input$beta_initial_expr, e)
  tol       <- if (!is.null(input$tol))       as.numeric(input$tol)       else 1e-4
  Mstop     <- if (!is.null(input$Mstop))     as.integer(input$Mstop)     else 50L
  backtrack <- if (!is.null(input$backtrack)) as.logical(input$backtrack) else FALSE

  fit <- ncc_MDTL(
    y            = y,
    z            = z,
    stratum      = stratum,
    beta         = beta,
    vcov         = vcov,
    etas         = etas,
    tol          = tol,
    Mstop        = Mstop,
    backtrack    = backtrack,
    message      = FALSE,
    beta_initial = beta_initial
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
    vcov_used     = if (length(vcov_sources) == 0L) "identity" else vcov_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_ncc_MDTL.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
